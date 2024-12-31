from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import logging
from rag import generate_response, add_document_to_vector_db, clear_vector_db, model, debug_database_state
from get_emails import fetch_recent_emails
from compose import EmailComposer, handle_compose_request
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Initialize Twilio client
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Store user conversations and initialize composer
user_conversations = {}
email_composer = EmailComposer(model)
draft_states = {}

def send_whatsapp_message(to_number, message):
    """Send WhatsApp message with error handling"""
    try:
        formatted_number = to_number if to_number.startswith('whatsapp:') else f"whatsapp:{to_number}"
        message = client.messages.create(
            from_=TWILIO_PHONE_NUMBER,
            body=message,
            to=formatted_number
        )
        logger.info(f"Message sent successfully. SID: {message.sid}")
        return True
    except Exception as e:
        error_msg = str(e)
        if "exceeded the null daily messages limit" in error_msg:
            logger.error("Daily message limit exceeded for Twilio account")
            print("\nMessage that would have been sent:")
            print("-----------------------------------")
            print(message)
            print("-----------------------------------")
            print("\n=== TWILIO ERROR ===")
            print("Daily message limit exceeded for this Twilio account.")
            print("Please wait for the limit to reset or upgrade your Twilio plan.")
            print("==================\n")
        else:
            logger.error(f"Error sending message: {error_msg}")
        return False

@app.route("/webhook", methods=['POST'])
def webhook():
    try:
        incoming_msg = request.values.get('Body', '').strip().lower()
        sender = request.values.get('From', '')
        
        logger.info(f"Received message: '{incoming_msg}' from {sender}")
        
        if not sender or not incoming_msg:
            logger.error("Missing sender or message content")
            return str(MessagingResponse())
        
        # Handle special commands
        if incoming_msg == "refresh":
            logger.info("Refreshing email database...")
            clear_vector_db()
            emails = fetch_recent_emails()
            if emails:
                stored_count = add_document_to_vector_db("recent_emails", emails)
                response = f"✨ Database refreshed! Loaded {stored_count} recent emails."
            else:
                response = "❌ No recent emails found to refresh."
            send_whatsapp_message(sender, response)
            return str(MessagingResponse())
            
        if incoming_msg == "clear":
            logger.info("Clearing email database...")
            clear_vector_db()
            user_conversations[sender] = ""  # Clear conversation history
            response = "🧹 Database and conversation history cleared!"
            send_whatsapp_message(sender, response)
            return str(MessagingResponse())
        
        # Check if user is in composition mode
        if sender in draft_states:
            logger.info(f"User {sender} is in composition mode")
            response, draft_id = handle_compose_request(incoming_msg, email_composer, draft_states[sender])
            if draft_id:
                draft_states[sender] = draft_id
            else:
                del draft_states[sender]
            send_whatsapp_message(sender, response)
            return str(MessagingResponse())
        
        # Handle compose command
        if incoming_msg == "compose":
            logger.info(f"Starting composition for {sender}")
            response, draft_id = handle_compose_request(incoming_msg, email_composer)
            if draft_id:
                draft_states[sender] = draft_id
            send_whatsapp_message(sender, response)
            return str(MessagingResponse())
        
        # Regular email query handling
        logger.info(f"Processing regular query for {sender}")
        response_text = generate_response(user_conversations.get(sender, ""), incoming_msg)
        send_whatsapp_message(sender, response_text)
        
        # Update conversation history
        user_conversations[sender] = f"{user_conversations.get(sender, '')}\nUser: {incoming_msg}\nAssistant: {response_text}"
        
        return str(MessagingResponse())
        
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        logger.exception("Full traceback:")
        return str(MessagingResponse())

if __name__ == "__main__":
    # Verify Twilio credentials
    try:
        client.api.accounts(TWILIO_ACCOUNT_SID).fetch()
        logger.info("Twilio credentials verified successfully!")
        
        # Initialize the database
        clear_vector_db()
        logger.info("Loading recent emails...")
        emails = fetch_recent_emails()
        if emails:
            add_document_to_vector_db("recent_emails", emails)
            logger.info(f"Loaded {len(emails)} emails into the database")
        
        # Show database state
        debug_database_state()
        
    except Exception as e:
        logger.error(f"Error during startup: {str(e)}")
        exit(1)
        
    app.run(debug=True, port=5000) 