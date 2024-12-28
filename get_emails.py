import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta

# Gmail IMAP configuration
IMAP_SERVER = "imap.gmail.com"
EMAIL_USER = "interns@pluginlive.com"  # Replace with your email
EMAIL_PASS = "ptdo obzr lobc qrke"     # Replace with your app password

# Step 1: Connect to Gmail IMAP server
def connect_to_gmail():
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)  # Secure connection to IMAP server
        mail.login(EMAIL_USER, EMAIL_PASS)    # Log in with email and app password
        return mail
    except Exception as e:
        print(f"Error connecting to Gmail: {e}")
        return None

# Step 2: Fetch recent emails
def fetch_recent_emails(max_emails=20):
    """
    Fetch only the 20 most recent emails
    """
    mail = connect_to_gmail()
    if not mail:
        return []

    try:
        mail.select("inbox")
        # Get all email IDs
        status, messages = mail.search(None, 'ALL')
        email_ids = messages[0].split()
        
        # Get only the most recent 20 emails
        recent_email_ids = email_ids[-max_emails:]
        
        email_data = []
        current_time = datetime.now()
        
        for email_id in recent_email_ids:
            status, msg_data = mail.fetch(email_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    # Parse date to timestamp
                    date_str = msg.get("Date")
                    try:
                        parsed_date = email.utils.parsedate_to_datetime(date_str)
                        timestamp = parsed_date.timestamp()
                    except:
                        timestamp = datetime.now().timestamp()

                    subject = decode_header(msg["Subject"])[0][0]
                    if isinstance(subject, bytes):
                        subject = subject.decode()
                    
                    email_data.append({
                        "subject": subject,
                        "sender": msg.get("From"),
                        "date": date_str,
                        "timestamp": timestamp,
                        "body": extract_email_body(msg)
                    })
        
        # Sort emails by timestamp (most recent first)
        email_data.sort(key=lambda x: x['timestamp'], reverse=True)
        return email_data

    except Exception as e:
        print(f"Error fetching emails: {e}")
        return []
    finally:
        mail.logout()

def extract_email_body(msg):
    """Extract email body with better formatting"""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    part_body = part.get_payload(decode=True).decode()
                    body += clean_email_body(part_body)
                except:
                    continue
    else:
        try:
            body = msg.get_payload(decode=True).decode()
            body = clean_email_body(body)
        except:
            body = "Could not decode email body"
    return body

def clean_email_body(body):
    """Clean and format email body"""
    # Remove extra whitespace and newlines
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    cleaned_body = "\n".join(lines)
    return cleaned_body

# Step 3: Display emails
if __name__ == "__main__":
    emails = fetch_recent_emails()
    for i, email in enumerate(emails, start=1):
        print(f"\nEmail {i}:")
        print("=" * 70)
        print(f"Subject: {email['subject']}")
        print(f"From: {email['sender']}")
        print(f"Date: {email['date']}")
        print("-" * 70)
        print("Body:")
        print(email['body'])
        print("=" * 70)
