from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import os
from dotenv import load_dotenv
from get_emails import fetch_recent_emails
from rag import add_document_to_vector_db, generate_response, clear_vector_db, get_email_count
import logging

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Twilio credentials
TWILIO_ACCOUNT_SID = "AC8c0ec056b250511baf3cf5264bf78b5a"
TWILIO_AUTH_TOKEN = "89f60aba41e08097ad2bb6c6aea13ad2"
TWILIO_PHONE_NUMBER = "whatsapp:+14155238886"

# Initialize Twilio client
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Store conversation history for each user
user_conversations = {}

# Add logging configuration
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def refresh_emails():
    """Check for new emails and add them to the vector database"""
    current_count = get_email_count()
    new_emails = fetch_recent_emails()
    
    if len(new_emails) <= current_count:
        return "No new emails to add."
    
    new_emails_to_add = new_emails[current_count:]
    num_new_emails = len(new_emails_to_add)
    
    if num_new_emails > 0:
        for i, email in enumerate(new_emails_to_add):
            email_text = f"""
Subject: {email['subject']}
From: {email['sender']}
Date: {email['date']}
Body:
{email['body']}
"""
            doc_id = f"email_{get_email_count() + i}"
            add_document_to_vector_db(doc_id, email_text)
        return f"Added {num_new_emails} new {'email' if num_new_emails == 1 else 'emails'}"
    return "Database is up to date"

def send_whatsapp_message(to_number, message):
    """Send WhatsApp message using Twilio client"""
    try:
        message = client.messages.create(
            from_=TWILIO_PHONE_NUMBER,
            body=message,
            to=f"whatsapp:{to_number}"
        )
        logger.debug(f"Message sent successfully: {message.sid}")
        return True
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        return False

@app.route("/webhook", methods=['POST'])
def webhook():
    try:
        incoming_msg = request.values.get('Body', '').lower()
        sender = request.values.get('From', '')
        sender_number = sender.replace('whatsapp:', '')
        
        logger.debug(f"Received message: '{incoming_msg}' from {sender}")
        
        # Handle the message and generate response
        if incoming_msg == 'refresh':
            response_text = refresh_emails()
        elif incoming_msg == 'clear':
            user_conversations[sender] = ""
            response_text = "Conversation history cleared. How can I help you with your emails?"
        else:
            if sender not in user_conversations:
                user_conversations[sender] = ""
                response_text = ("Welcome to Email Assistant! 👋\n\n"
                             "You can ask questions about your emails.\n\n"
                             "Special commands:\n"
                             "- Type 'refresh' to check for new emails\n"
                             "- Type 'clear' to reset conversation\n\n"
                             "What would you like to know about your emails?")
            else:
                response_text = generate_response(user_conversations[sender], incoming_msg)
                user_conversations[sender] += f"\nUser: {incoming_msg}\nAssistant: {response_text}"

        # Send the response using Twilio client
        success = send_whatsapp_message(sender_number, response_text)
        
        if not success:
            logger.error("Failed to send message via Twilio client")
            
        # Still return a TwiML response
        resp = MessagingResponse()
        return str(resp)
        
    except Exception as e:
        logger.error(f"Error in webhook: {str(e)}")
        return str(MessagingResponse())

# Add a test route
@app.route("/test", methods=['GET'])
def test():
    return "WhatsApp bot server is running!"

if __name__ == "__main__":
    # Verify Twilio credentials on startup
    try:
        # Test the Twilio client
        client.api.accounts(TWILIO_ACCOUNT_SID).fetch()
        logger.info("Twilio credentials verified successfully!")
    except Exception as e:
        logger.error(f"Error verifying Twilio credentials: {str(e)}")
        logger.error("Please check your TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN")
        exit(1)
        
    # Ensure initial email load
    if get_email_count() == 0:
        print("Loading initial emails...")
        initial_emails = fetch_recent_emails()
        for i, email in enumerate(initial_emails):
            email_text = f"""
Subject: {email['subject']}
From: {email['sender']}
Date: {email['date']}
Body:
{email['body']}
"""
            doc_id = f"email_{i}"
            add_document_to_vector_db(doc_id, email_text)
        print(f"Loaded {len(initial_emails)} emails into the database.")
    
    app.run(debug=True, port=5000) 