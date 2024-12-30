import google.generativeai as genai
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import PyPDF2
import time
from datetime import datetime, timedelta
from get_emails import fetch_recent_emails
from collections import defaultdict
import logging

# Add logging configuration
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize clients and models
genai.configure(api_key="AIzaSyDVgLmMTa4ycj7muEtUWH20O6LgGQsi6sQ")
model = genai.GenerativeModel("gemini-1.5-flash")
embeddingModel = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')

# Initialize FAISS index
dimension = 384  # Dimension of embeddings from all-MiniLM-L6-v2
faiss_index = faiss.IndexFlatL2(dimension)  # L2 distance for similarity search

# Store chunks and their embeddings
chunks = []
embeddings = []
chunk_metadata = {}
metadata_index = None  # Assuming a separate metadata_index is needed

# Initialize metadata index class
class EmailMetadataIndex:
    def __init__(self):
        self.date_index = defaultdict(list)  # {date: [chunk_ids]}
    
    def add_email(self, chunk_id, timestamp, date, emails_count):
        """Only add if it's today or yesterday"""
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        
        if date in [today, yesterday]:
            self.date_index[date].append({
                'chunk_id': chunk_id,
                'timestamp': timestamp,
                'emails_count': emails_count
            })
    
    def get_chunks_by_date(self, target_date):
        """Get chunks for today or yesterday only"""
        return [item['chunk_id'] for item in self.date_index.get(target_date, [])]

# Add to global variables (after other initializations)
metadata_index = EmailMetadataIndex()

# Add EmailMetadata to the global scope
class EmailMetadata:
    def __init__(self):
        self.emails = {
            'today': [],
            'yesterday': []
        }
        self.counts = {
            'today': 0,
            'yesterday': 0
        }
    
    def add_email(self, email):
        timestamp = float(email['timestamp'])
        email_date = datetime.fromtimestamp(timestamp).date()
        today = datetime.now().date()
        
        if email_date == today:
            self.emails['today'].append(email)
            self.counts['today'] += 1
        elif email_date == today - timedelta(days=1):
            self.emails['yesterday'].append(email)
            self.counts['yesterday'] += 1
    
    def get_total_count(self):
        return self.counts['today'] + self.counts['yesterday']
    
    def get_status_string(self):
        return f"Today: {self.counts['today']} emails, Yesterday: {self.counts['yesterday']} emails"

# Initialize metadata tracker at global scope
email_metadata = EmailMetadata()

def get_email_count():
    """Get accurate count of stored emails"""
    return email_metadata.get_total_count()

def get_email_status():
    """Get detailed status of stored emails"""
    return email_metadata.get_status_string()

def clear_vector_db():
    """Clear all data from the vector database"""
    global chunks, embeddings, chunk_metadata, faiss_index, metadata_index
    chunks.clear()
    embeddings.clear()
    chunk_metadata.clear()
    faiss_index = faiss.IndexFlatL2(dimension)
    metadata_index = EmailMetadataIndex()  # Reset metadata index

def should_store_email(timestamp):
    """
    Check if email should be stored (only today and yesterday)
    """
    email_date = datetime.fromtimestamp(timestamp).date()
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    return email_date in [today, yesterday]

def chunk_emails_by_date(emails):
    """
    Create chunks for today and yesterday only
    """
    # Sort emails by timestamp (most recent first)
    sorted_emails = sorted(emails, key=lambda x: float(x['timestamp']), reverse=True)
    
    # Filter and group emails by date (today and yesterday only)
    date_groups = defaultdict(list)
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    
    for email in sorted_emails:
        email_timestamp = float(email['timestamp'])
        email_date = datetime.fromtimestamp(email_timestamp).date()
        
        # Only process emails from today and yesterday
        if email_date not in [today, yesterday]:
            continue
        
        email_text = f"""
[Email from {datetime.fromtimestamp(email_timestamp).strftime('%Y-%m-%d %I:%M %p')}]
From: {email['sender']}
Subject: {email['subject']}
---
{email['body']}
==========
"""
        date_groups[email_date].append({
            'text': email_text,
            'timestamp': email_timestamp,
            'metadata': {
                'sender': email['sender'],
                'subject': email['subject'],
                'date': email_date
            }
        })
    
    # Create chunks for each date
    chunks_with_metadata = []
    for date, emails_in_day in date_groups.items():
        if emails_in_day:  # Only create chunks if there are emails
            day_texts = [email['text'] for email in emails_in_day]
            newest_timestamp = max(email['timestamp'] for email in emails_in_day)
            oldest_timestamp = min(email['timestamp'] for email in emails_in_day)
            
            chunks_with_metadata.append({
                'text': "\n".join(day_texts),
                'timestamp': newest_timestamp,
                'date_range': {
                    'start': oldest_timestamp,
                    'end': newest_timestamp
                },
                'date': date,
                'emails_count': len(emails_in_day)
            })
    
    return chunks_with_metadata

def read_pdf(file_path):
    """
    Extract text from a PDF file.
    
    Args:
        file_path (str): Path to the PDF file.
        
    Returns:
        str: Extracted text from the PDF.
    """
    try:
        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            text = ""
            for page_num in range(len(reader.pages)):
                page = reader.pages[page_num]
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return ""

def add_document_to_vector_db(doc_id, email_data):
    """
    Add email to vector database with improved metadata tracking
    """
    global chunks, embeddings, faiss_index, chunk_metadata, metadata_index, email_metadata
    
    # Convert single email to list if needed
    emails_list = [email_data] if isinstance(email_data, dict) else email_data
    
    # Reset email metadata for new batch
    email_metadata = EmailMetadata()
    
    # First pass: collect and organize emails by date
    for email in emails_list:
        if should_store_email(float(email['timestamp'])):
            email_metadata.add_email(email)
    
    # Create chunks only if we have emails to store
    if email_metadata.get_total_count() == 0:
        return 0
    
    # Create date-based chunks
    doc_chunks = []
    
    # Process today's emails
    if email_metadata.emails['today']:
        chunk_data = create_chunk_with_metadata(
            emails=email_metadata.emails['today'],
            status='today',
            doc_id=doc_id
        )
        doc_chunks.append(chunk_data)
    
    # Process yesterday's emails
    if email_metadata.emails['yesterday']:
        chunk_data = create_chunk_with_metadata(
            emails=email_metadata.emails['yesterday'],
            status='yesterday',
            doc_id=doc_id
        )
        doc_chunks.append(chunk_data)
    
    # Generate embeddings and store chunks
    if doc_chunks:
        texts_to_embed = [chunk['text'] for chunk in doc_chunks]
        doc_embeddings = embeddingModel.encode(texts_to_embed)
        
        for i, chunk_data in enumerate(doc_chunks):
            chunk_id = f"{doc_id}_{chunk_data['status']}"
            chunks.append(chunk_data['text'])
            
            chunk_metadata[len(chunks)-1] = {
                'doc_id': doc_id,
                'chunk_id': chunk_id,
                'timestamp': chunk_data['timestamp'],
                'status': chunk_data['status'],
                'date': chunk_data['date'],
                'emails_count': chunk_data['emails_count']
            }
        
        embeddings.extend(doc_embeddings)
        faiss_index.add(np.array(doc_embeddings))
    
    return email_metadata.get_total_count()

def format_chunk_for_response(result):
    """Format chunk with clear metadata and error handling"""
    try:
        metadata = result.get('metadata', {})
        text = result.get('text', '')
        timestamp = metadata.get('timestamp', time.time())
        
        formatted_response = f"""[Email from {datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %I:%M %p')}]
{text}
"""
        return formatted_response
        
    except Exception as e:
        logger.error(f"Error formatting response: {str(e)}")
        # Return raw text if formatting fails
        return result.get('text', 'Error formatting response')

def retrieve_relevant_chunks(query, top_k=3):
    """
    Retrieve chunks with focus on today and yesterday
    """
    try:
        query_lower = query.lower()
        
        # Get all chunks from today and yesterday
        candidate_chunks = set()
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        
        # Always include both today and yesterday's chunks for recent queries
        for date in [today, yesterday]:
            for idx, meta in chunk_metadata.items():
                chunk_date = datetime.fromtimestamp(meta['timestamp']).date()
                if chunk_date == date:
                    candidate_chunks.add(idx)
        
        if not candidate_chunks:
            logger.warning("No chunks found for today or yesterday")
            return []
        
        # Convert to list and ensure we have integers
        candidate_indices = list(map(int, candidate_chunks))
        
        # Get embeddings for candidates
        candidate_embeddings = np.array([embeddings[i] for i in candidate_indices])
        query_embedding = embeddingModel.encode([query])
        
        # Create temporary index for search
        temp_index = faiss.IndexFlatL2(candidate_embeddings.shape[1])
        temp_index.add(candidate_embeddings)
        
        # Perform search
        distances, indices = temp_index.search(query_embedding, min(top_k, len(candidate_embeddings)))
        
        # Map back to original indices
        original_indices = [candidate_indices[idx] for idx in indices[0]]
        
        # Prepare results
        results = []
        current_time = time.time()
        
        for idx, distance in zip(original_indices, distances[0]):
            metadata = chunk_metadata[idx]
            chunk_time = metadata['timestamp']
            
            # Calculate scores
            days_old = (current_time - chunk_time) / (24 * 3600)
            time_score = np.exp(-days_old / 7)
            semantic_score = 1.0 / (1.0 + float(distance))
            
            # Combined score (prioritize recency for "recent" queries)
            if 'recent' in query_lower:
                final_score = 0.7 * time_score + 0.3 * semantic_score
            else:
                final_score = 0.3 * time_score + 0.7 * semantic_score
            
            results.append({
                'text': chunks[idx],
                'score': final_score,
                'metadata': metadata
            })
        
        # Sort by score
        results.sort(key=lambda x: x['score'], reverse=True)
        
        # Add logging to debug
        logger.info(f"Found {len(results)} relevant chunks")
        for r in results:
            logger.info(f"Chunk timestamp: {datetime.fromtimestamp(r['metadata']['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Format results
        return [format_chunk_for_response(r) for r in results[:top_k]]
        
    except Exception as e:
        logger.error(f"Error in retrieve_relevant_chunks: {str(e)}")
        return []

def generate_response(conversation_history, question):
    """
    Generate a response with improved formatting and readability.
    """
    try:
        # Get relevant chunks with error handling
        relevant_chunks = retrieve_relevant_chunks(question)
        
        if not relevant_chunks:
            return "I couldn't find any relevant emails for your query. Try rephrasing or use 'refresh' to check for new emails."
        
        combined_text = '\n\n'.join(relevant_chunks)
        
        prompt = f"""Based on the following email contents and conversation history, provide a clear and well-formatted response.

CONVERSATION HISTORY:
{conversation_history}

RELEVANT EMAIL CONTENTS:
{combined_text}

QUESTION: {question}

Please format your response using this structure:
📥 EMAIL SUMMARY ({datetime.now().strftime('%Y-%m-%d')})
-------------------

For each email:
1. 🕒 Time: [HH:MM AM/PM]
2. 👤 From: [Sender]
3. 📌 Subject: [Subject]
4. 📝 Summary: [Brief summary in 1-2 lines]
-------------------

Additional formatting rules:
- Group emails by time period (e.g., "Recent Emails", "Earlier Today", etc.)
- List emails chronologically, newest first
- Use bullet points for clarity
- Keep summaries concise but informative
- Highlight important details with emojis
- Add "❗" for seemingly important emails
- Add "📎" if there are attachments mentioned"""

        response = model.generate_content(prompt, generation_config={
            'max_output_tokens': 3000,
            'temperature': 0.7
        })
        
        if not response or not response.text:
            return "I apologize, but I couldn't generate a proper response. Please try again."
        
        # Add a header to the response
        formatted_response = f"""📬 EMAIL ASSISTANT
===================
{response.text}

💡 Commands:
• Type 'refresh' to check for new emails
• Type 'clear' to reset conversation
==================="""
        
        return formatted_response
        
    except Exception as e:
        logger.error(f"Error in generate_response: {str(e)}")
        return f"An error occurred while processing your request: {str(e)}"

def create_chunk_with_metadata(emails, status, doc_id):
    """
    Create a chunk with metadata for a group of emails
    Args:
        emails: List of emails for this chunk
        status: 'today' or 'yesterday'
        doc_id: Document identifier
    Returns:
        dict: Chunk data with metadata
    """
    # Sort emails by timestamp (newest first)
    sorted_emails = sorted(emails, key=lambda x: float(x['timestamp']), reverse=True)
    
    # Create the chunk text
    email_texts = []
    newest_timestamp = float(sorted_emails[0]['timestamp'])
    oldest_timestamp = float(sorted_emails[-1]['timestamp'])
    
    for email in sorted_emails:
        timestamp = float(email['timestamp'])
        email_text = f"""
[Email from {datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %I:%M %p')}]
From: {email['sender']}
Subject: {email['subject']}
---
{email['body']}
==========
"""
        email_texts.append(email_text)
    
    return {
        'text': "\n".join(email_texts),
        'timestamp': newest_timestamp,
        'status': status,
        'date': datetime.fromtimestamp(newest_timestamp).date(),
        'emails_count': len(emails),
        'date_range': {
            'start': oldest_timestamp,
            'end': newest_timestamp
        }
    }

def debug_database_state():
    """Print current state of the vector database"""
    print("\nDatabase State:")
    print(f"Total chunks: {len(chunks)}")
    print(f"Total embeddings: {len(embeddings)}")
    print("\nChunk Metadata:")
    for idx, meta in chunk_metadata.items():
        date = datetime.fromtimestamp(meta['timestamp']).date()
        print(f"Chunk {idx}: Date={date}, Status={meta.get('status', 'unknown')}, Emails={meta.get('emails_count', 0)}")
    print("\nEmail Status:")
    print(get_email_status())