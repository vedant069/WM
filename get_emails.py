import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta

# Gmail IMAP configuration
IMAP_SERVER = "imap.gmail.com"
EMAIL_USER = "vedantnadhe069@gmail.com"  # Replace with your email
EMAIL_PASS = "jkns dsef asfp imhr"     # Replace with your app password

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
def fetch_recent_emails():
    mail = connect_to_gmail()
    if not mail:
        return []

    try:
        mail.select("inbox")  # Select the inbox folder
        # Search for all emails
        status, messages = mail.search(None, "ALL")
        email_ids = messages[0].split()
        recent_email_ids = email_ids[-20:]  # Increased from 5 to 20 emails

        email_data = []
        for email_id in recent_email_ids:
            # Fetch the email by ID
            status, msg_data = mail.fetch(email_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    # Parse the raw email
                    msg = email.message_from_bytes(response_part[1])

                    # Decode the email subject
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding or "utf-8")
                    else:
                        subject = subject or "No Subject"

                    # Get the sender's email address
                    sender = msg.get("From") or "Unknown Sender"
                    
                    # Get the date
                    date = msg.get("Date") or "No Date"

                    # Extract the complete email body
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                try:
                                    part_body = part.get_payload(decode=True).decode()
                                    body += part_body + "\n"
                                except:
                                    continue
                    else:
                        try:
                            body = msg.get_payload(decode=True).decode()
                        except:
                            body = "Could not decode email body"

                    email_data.append({
                        "subject": subject,
                        "sender": sender,
                        "date": date,
                        "body": body,
                    })
        return email_data
    except Exception as e:
        print(f"Error fetching emails: {e}")
        return []
    finally:
        mail.logout()

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
