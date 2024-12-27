import imaplib
import email
from email.header import decode_header

# Step 1: Connect to the email server
def connect_to_email():
    # Gmail's IMAP server address
    imap_server = "imap.gmail.com"
    email_user = "vedantnadhe069@gmail.com"
    email_pass = "jkns dsef asfp imhr"

    # Connect to the server and log in
    mail = imaplib.IMAP4_SSL(imap_server)
    mail.login(email_user, email_pass)
    return mail

# Step 2: Fetch recent emails
def fetch_recent_emails():
    mail = connect_to_email()
    # Select the mailbox you want to use
    mail.select("inbox")

    # Search for all emails (you can filter by criteria, e.g., unseen emails)
    status, messages = mail.search(None, "ALL")

    # Convert messages to a list of email IDs
    email_ids = messages[0].split()
    recent_emails = email_ids[-5:]  # Fetch the last 5 emails

    email_data = []
    for email_id in recent_emails:
        # Fetch the email by ID
        status, msg_data = mail.fetch(email_id, "(RFC822)")

        for response_part in msg_data:
            if isinstance(response_part, tuple):
                # Parse the email
                msg = email.message_from_bytes(response_part[1])
                subject, encoding = decode_header(msg["Subject"])[0]
                if isinstance(subject, bytes):
                    # Decode the subject
                    subject = subject.decode(encoding or "utf-8")
                sender = msg.get("From")

                # Extract the email body
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode()
                            break
                else:
                    body = msg.get_payload(decode=True).decode()

                email_data.append({
                    "subject": subject,
                    "sender": sender,
                    "body": body[:100]  # First 100 characters as a snippet
                })

    # Close the connection
    mail.logout()
    return email_data

# Step 3: Display the emails
if __name__ == '__main__':
    emails = fetch_recent_emails()
    for i, email in enumerate(emails, start=1):
        print(f"Email {i}:")
        print(f"Subject: {email['subject']}")
        print(f"Sender: {email['sender']}")
        print(f"Snippet: {email['body']}")
        print("-" * 50)
