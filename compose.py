import google.generativeai as genai
from datetime import datetime
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EmailComposer:
    def __init__(self, model):
        self.model = model
        self.drafts = {}
        # Get email credentials from environment variables
        self.email_address = os.getenv('EMAIL_ADDRESS')
        self.email_password = os.getenv('EMAIL_APP_PASSWORD')  # App-specific password for Gmail
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        
    def send_email(self, draft_id):
        """Actually send the email using SMTP"""
        try:
            if draft_id not in self.drafts:
                return "Draft not found."
            
            draft = self.drafts[draft_id]
            
            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.email_address
            msg['To'] = draft['to']
            msg['Subject'] = draft['subject']
            
            # Add body
            msg.attach(MIMEText(draft['body'], 'plain'))
            
            # Connect to SMTP server
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_address, self.email_password)
                server.send_message(msg)
            
            # Clean up draft after sending
            del self.drafts[draft_id]
            
            return "✅ Email sent successfully!"
            
        except Exception as e:
            logger.error(f"Error sending email: {str(e)}")
            return f"❌ Failed to send email: {str(e)}"
    
    def start_composition(self, recipient=None):
        """Start composing a new email"""
        draft_id = datetime.now().strftime("%Y%m%d%H%M%S")
        self.drafts[draft_id] = {
            'to': recipient,
            'subject': '',
            'body': '',
            'status': 'getting_recipient' if not recipient else 'getting_subject'
        }
        return draft_id
    
    def generate_email(self, subject, context=""):
        """Generate email content using Gemini"""
        try:
            prompt = f"""Write a professional email with the following details:
            Subject: {subject}
            Additional Context: {context}
            
            Guidelines:
            - Keep it professional and concise
            - Use appropriate greeting and closing
            - Maintain a friendly yet formal tone
            - Focus on clarity and directness
            - Your name is Vedant Nadhe
            - Your email address is {self.email_address}
            - Your phone number is +91-1234567890
            
            Please provide only the email body without subject or recipient information."""
            
            response = self.model.generate_content(prompt)
            return response.text if response else ""
            
        except Exception as e:
            logger.error(f"Error generating email: {str(e)}")
            return ""
    
    def get_draft_preview(self, draft_id):
        """Get a preview of the draft email"""
        if draft_id in self.drafts:
            draft = self.drafts[draft_id]
            preview = f"""
📧 DRAFT EMAIL PREVIEW
====================
To: {draft['to']}
Subject: {draft['subject']}

{draft['body']}
====================

Options:
1. Send email
2. Regenerate email
3. Edit manually
4. Cancel
"""
            return preview
        return "Draft not found."

def handle_compose_request(user_input, composer, current_draft=None):
    """Handle email composition requests"""
    logger.info(f"Handling compose request. Input: {user_input}, Current draft: {current_draft}")
    
    if not current_draft:
        if user_input.lower().strip() == "compose":
            draft_id = composer.start_composition()
            logger.info(f"Started new composition with draft_id: {draft_id}")
            return "📧 Who would you like to send the email to?", draft_id
        return None, None
    
    draft = composer.drafts[current_draft]
    logger.info(f"Current draft status: {draft['status']}")
    
    if draft['status'] == 'getting_recipient':
        # Basic email validation
        if '@' not in user_input or '.' not in user_input:
            return "❌ Please enter a valid email address.", current_draft
        draft['to'] = user_input
        draft['status'] = 'getting_subject'
        return "📝 What's the subject of your email?", current_draft
    
    elif draft['status'] == 'getting_subject':
        draft['subject'] = user_input
        draft['status'] = 'getting_context'
        return "💡 Please provide any additional context or specific points you'd like to include in the email:", current_draft
    
    elif draft['status'] == 'getting_context':
        # Generate email using Gemini
        generated_body = composer.generate_email(draft['subject'], user_input)
        draft['body'] = generated_body
        draft['status'] = 'preview'
        return composer.get_draft_preview(current_draft), current_draft
    
    elif draft['status'] == 'preview':
        if user_input == '1':
            # Actually send the email
            result = composer.send_email(current_draft)
            return result, None
        elif user_input == '2':
            draft['status'] = 'getting_context'
            return "💡 Please provide any additional context for regenerating the email:", current_draft
        elif user_input == '3':
            draft['status'] = 'manual_edit'
            return "✏️ Please enter your email content:", current_draft
        elif user_input == '4':
            del composer.drafts[current_draft]
            return "❌ Email composition cancelled.", None
    
    elif draft['status'] == 'manual_edit':
        draft['body'] = user_input
        draft['status'] = 'preview'
        return composer.get_draft_preview(current_draft), current_draft
    
    return "I don't understand. Please follow the prompts or type 'cancel' to start over.", current_draft 