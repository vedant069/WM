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
    """Check for new emails and update the vector database with only recent emails"""
    try:
        # Clear existing vector database
        clear_vector_db()
        logger.info("Cleared existing vector database")
        
        # Fetch 20 most recent emails
        new_emails = fetch_recent_emails(max_emails=20)
        
        if not new_emails:
            return "No emails found."
        
        # Add all recent emails to the database
        for i, email in enumerate(new_emails):
            doc_id = f"email_{i}"
            add_document_to_vector_db(doc_id, email)
        
        return f"Updated database with {len(new_emails)} most recent emails"
    
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
    """Send WhatsApp message using Twilio client with support for long messages"""
    try:
        # Ensure message is not empty
        if not message or message.isspace():
            message = "No response generated."
        
        # Add logging to track message content
        logger.debug(f"Attempting to send message to {to_number}: {message[:100]}...")
        
        # Split long messages into chunks
        message_chunks = split_long_message(message)
        
        responses = []
        for chunk in message_chunks:
            # Ensure the number format is correct
            formatted_number = to_number if to_number.startswith('whatsapp:') else f"whatsapp:{to_number}"
            
            # Add error handling for message sending
            try:
                message = client.messages.create(
                    from_=TWILIO_PHONE_NUMBER,
                    body=chunk,
                    to=formatted_number
                )
                logger.info(f"Message sent successfully. SID: {message.sid}, Status: {message.status}")
                responses.append(message)
            except Exception as e:
                logger.error(f"Failed to send message chunk: {str(e)}")
                raise
        
        return True
    except Exception as e:
        logger.error(f"Error in send_whatsapp_message: {str(e)}")
        return False

@app.route("/webhook", methods=['POST'])
def webhook():
    try:
        # Add more detailed logging
        logger.info(f"Received webhook request: {request.values}")
        
        incoming_msg = request.values.get('Body', '').lower()
        sender = request.values.get('From', '')
        
        if not sender or not incoming_msg:
            logger.error("Missing sender or message content")
            return str(MessagingResponse())
            
        sender_number = sender.replace('whatsapp:', '')
        
        logger.info(f"Processing message: '{incoming_msg}' from {sender}")
        
        # Generate response
        response_text = None
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
                try:
                    response_text = generate_response(user_conversations[sender], incoming_msg)
                except Exception as e:
                    logger.error(f"Error generating response: {str(e)}")
                    response_text = "I apologize, but I encountered an error. Please try again."

        # Ensure we have a response
        if not response_text:
            response_text = "I apologize, but I couldn't generate a response."

        # Send response
        logger.info(f"Sending response to {sender_number}")
        success = send_whatsapp_message(sender_number, response_text)
        
        if not success:
            logger.error("Failed to send WhatsApp message")
            # Create a basic TwiML response as fallback
            resp = MessagingResponse()
            resp.message("Sorry, there was an error sending the message.")
            return str(resp)
        
        # Return empty TwiML response since we've already sent the message
        return str(MessagingResponse())
        
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        resp = MessagingResponse()
        resp.message("An error occurred. Please try again.")
        return str(resp)

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
        
    # Initial email load (20 most recent)
    print("Loading initial emails...")
    initial_emails = fetch_recent_emails(max_emails=20)
    if initial_emails:
        for i, email in enumerate(initial_emails):
            doc_id = f"email_{i}"
            add_document_to_vector_db(doc_id, email)
        print(f"Loaded {len(initial_emails)} recent emails into the database.")
    else:
        print("No emails found.")
    
    app.run(debug=True, port=5000) 