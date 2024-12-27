from get_emails import fetch_recent_emails
from rag import add_document_to_vector_db, generate_response, clear_vector_db, get_email_count

def load_emails_to_vectordb(emails):
    """Add emails to the vector database"""
    for i, email in enumerate(emails):
        email_text = f"""
Subject: {email['subject']}
From: {email['sender']}
Date: {email['date']}
Body:
{email['body']}
"""
        doc_id = f"email_{get_email_count() + i}"  # Use current count + index for new emails
        add_document_to_vector_db(doc_id, email_text)

def refresh_emails():
    """Check for new emails and add only the new ones to the vector database"""
    print("\nChecking for new emails...")
    current_count = get_email_count()
    new_emails = fetch_recent_emails()
    
    if len(new_emails) <= current_count:
        print("No new emails to add.")
        return
    
    new_emails_to_add = new_emails[current_count:]
    num_new_emails = len(new_emails_to_add)
    
    if num_new_emails > 0:
        print(f"Adding {num_new_emails} new {'email' if num_new_emails == 1 else 'emails'}...")
        load_emails_to_vectordb(new_emails_to_add)
        print("Database updated successfully!")

def chat_with_emails():
    """Interactive chat interface to query emails"""
    conversation_history = ""
    
    print("\nWelcome to Email Chat! You can ask questions about your emails.")
    print("Special commands:")
    print("- Type 'refresh' to check for new emails")
    print("- Type 'quit' to exit the chat")
    print("\nWhat would you like to know about your emails?\n")
    
    # Initial load of emails
    print("Loading initial emails...")
    initial_emails = fetch_recent_emails()
    load_emails_to_vectordb(initial_emails)
    print(f"Loaded {len(initial_emails)} emails into the database.\n")
    
    while True:
        user_input = input("\nYou: ").strip().lower()
        
        if user_input == 'quit':
            print("Goodbye!")
            break
        
        elif user_input == 'refresh':
            refresh_emails()
            continue
        
        response = generate_response(conversation_history, user_input)
        print("\nAssistant:", response)
        
        conversation_history += f"\nUser: {user_input}\nAssistant: {response}"

if __name__ == "__main__":
    chat_with_emails() 