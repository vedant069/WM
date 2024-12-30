from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import os
from dotenv import load_dotenv
from get_emails import fetch_recent_emails
from rag import (
    add_document_to_vector_db, 
    generate_response, 
    clear_vector_db, 
    get_email_count,
    get_email_status,
    should_store_email,
    EmailMetadata,
    debug_database_state
)
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
    """Check for new emails and update the vector database with only today and yesterday's emails"""
    try:
        # Clear existing vector database
        clear_vector_db()
        logger.info("Cleared existing vector database")
        
        # Fetch recent emails
        new_emails = fetch_recent_emails()
        
        if not new_emails:
            return "No emails found."
        
        # Add only today and yesterday's emails to the database
        stored_count = 0
        for i, email in enumerate(new_emails):
            if should_store_email(float(email['timestamp'])):
                doc_id = f"email_{i}"
                add_document_to_vector_db(doc_id, email)
                stored_count += 1
        
        return f"Updated database with {stored_count} emails from today and yesterday"
    
    except Exception as e:
        logger.error(f"Error refreshing emails: {str(e)}")
        return "Error refreshing emails. Please try again."

def split_long_message(message, limit=1500):
    """
    Split long messages into smaller chunks while preserving word boundaries
    and adding continuation markers.
    """
    if len(message) <= limit:
        return [message]
    
    chunks = []
    current_chunk = ""
    words = message.split()
    
    for word in words:
        if len(current_chunk) + len(word) + 1 <= limit:
            current_chunk += " " + word if current_chunk else word
        else:
            # Add continuation marker to indicate there's more
            chunks.append(current_chunk + " (continued...)")
            current_chunk = word
    
    if current_chunk:
        chunks.append(current_chunk)
    
    # Add part numbers for clarity
    return [f"[Part {i+1}/{len(chunks)}]\n{chunk}" 
            for i, chunk in enumerate(chunks)]

def send_whatsapp_message(to_number, message):
    """Send WhatsApp message with terminal fallback"""
    try:
        # Ensure message is not empty
        if not message or message.isspace():
            message = "No response generated."
        
        # Try sending via Twilio
        formatted_number = to_number if to_number.startswith('whatsapp:') else f"whatsapp:{to_number}"
        
        try:
            message = client.messages.create(
                from_=TWILIO_PHONE_NUMBER,
                body=message,
                to=formatted_number
            )
            logger.info(f"Message sent successfully. SID: {message.sid}")
            return True
        except Exception as twilio_error:
            # Check if it's a daily limit error
            if "daily messages limit" in str(twilio_error):
                logger.warning("Twilio daily limit reached. Falling back to terminal output.")
                print("\n" + "="*50)
                print("📱 WhatsApp Message (Terminal Fallback)")
                print("="*50)
                print(f"To: {to_number}")
                print("-"*50)
                print(message)
                print("="*50 + "\n")
                return True
            else:
                raise  # Re-raise other Twilio errors
                
    except Exception as e:
        logger.error(f"Error in send_whatsapp_message: {str(e)}")
        # Fallback to terminal for any error
        print("\n" + "="*50)
        print("⚠️ Error sending WhatsApp message. Displaying in terminal:")
        print("="*50)
        print(message)
        print("="*50 + "\n")
        return False

@app.route("/webhook", methods=['POST'])
def webhook():
    try:
        incoming_msg = request.values.get('Body', '').lower()
        sender = request.values.get('From', '')
        
        if not sender or not incoming_msg:
            logger.error("Missing sender or message content")
            return str(MessagingResponse())
        
        # Process message and generate response
        response_text = generate_response(user_conversations.get(sender, ""), incoming_msg)
        
        # Try to send via WhatsApp, falls back to terminal if there's an error
        send_whatsapp_message(sender, response_text)
        
        return str(MessagingResponse())
        
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return str(MessagingResponse())

# Add a test route
@app.route("/test", methods=['GET'])
def test():
    return "WhatsApp bot server is running!"

if __name__ == "__main__":
    # Verify Twilio credentials on startup
    try:
        client.api.accounts(TWILIO_ACCOUNT_SID).fetch()
        logger.info("Twilio credentials verified successfully!")
    except Exception as e:
        logger.error(f"Error verifying Twilio credentials: {str(e)}")
        logger.error("Please check your TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN")
        exit(1)
        
    # Initial email load
    print("Loading recent emails...")
    initial_emails = fetch_recent_emails()
    if initial_emails:
        stored_count = add_document_to_vector_db("initial", initial_emails)
        print(f"Loaded {stored_count} emails from today and yesterday into the database.")
        metadata = EmailMetadata()
        for email in initial_emails:
            if should_store_email(float(email['timestamp'])):
                metadata.add_email(email)
        print(metadata.get_status_string())
    else:
        print("No recent emails found.")
    
    # After loading initial emails
    debug_database_state()
    
    app.run(debug=True, port=5000) 