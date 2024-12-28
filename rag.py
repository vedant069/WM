import google.generativeai as genai
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import PyPDF2
import time
from datetime import datetime, timedelta

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

def get_email_count():
    """Get the current number of emails in the database"""
    return len([meta for meta in chunk_metadata.values() if meta['chunk_id'].endswith('_chunk_0')])

def clear_vector_db():
    """Clear all data from the vector database"""
    global chunks, embeddings, chunk_metadata, faiss_index
    chunks.clear()
    embeddings.clear()
    chunk_metadata.clear()
    faiss_index = faiss.IndexFlatL2(dimension)

def chunk_emails_by_time(emails, chunk_size=3000):
    """
    Create large chunks of emails grouped by recency
    
    Args:
        emails (list): List of email dictionaries
        chunk_size (int): Target size of each chunk in characters
    """
    # Sort emails by timestamp (most recent first)
    sorted_emails = sorted(emails, key=lambda x: float(x['timestamp']), reverse=True)
    
    chunks_with_metadata = []
    current_chunk = []
    current_chunk_size = 0
    
    for email in sorted_emails:
        # Format single email
        email_text = f"""
Time: {datetime.fromtimestamp(float(email['timestamp'])).strftime('%Y-%m-%d %I:%M %p')}
From: {email['sender']}
Subject: {email['subject']}
---
{email['body']}
==========
"""
        email_size = len(email_text)
        
        if current_chunk_size + email_size > chunk_size and current_chunk:
            # Create chunk with metadata
            chunk_text = "\n".join(current_chunk)
            chunks_with_metadata.append({
                'text': chunk_text,
                'timestamp': float(sorted_emails[len(chunks_with_metadata)]['timestamp']),
                'emails_count': len(current_chunk)
            })
            current_chunk = []
            current_chunk_size = 0
        
        current_chunk.append(email_text)
        current_chunk_size += email_size
    
    # Add remaining emails as last chunk
    if current_chunk:
        chunk_text = "\n".join(current_chunk)
        chunks_with_metadata.append({
            'text': chunk_text,
            'timestamp': float(sorted_emails[len(chunks_with_metadata)]['timestamp']),
            'emails_count': len(current_chunk)
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
    Add email to vector database with improved chunking and metadata.
    """
    global chunks, embeddings, faiss_index, chunk_metadata
    
    # Create time-based chunks
    doc_chunks = chunk_emails_by_time([email_data])
    
    # Generate embeddings for chunks
    texts_to_embed = [chunk['text'] for chunk in doc_chunks]
    doc_embeddings = embeddingModel.encode(texts_to_embed)
    
    # Store chunks with metadata
    for i, chunk_data in enumerate(doc_chunks):
        chunk_id = f"{doc_id}_chunk_{i}"
        chunks.append(chunk_data['text'])
        chunk_metadata[len(chunks)-1] = {
            'doc_id': doc_id,
            'chunk_id': chunk_id,
            'timestamp': chunk_data['timestamp'],
            'emails_count': chunk_data['emails_count']
        }
    
    embeddings.extend(doc_embeddings)
    faiss_index.add(np.array(doc_embeddings))

def retrieve_relevant_chunks(query, top_k=3):  # Reduced top_k since chunks are larger
    """
    Retrieve relevant chunks with improved time-aware ranking.
    """
    query_embedding = embeddingModel.encode([query])
    distances, indices = faiss_index.search(query_embedding, top_k * 2)
    
    # Get candidate chunks with their metadata
    candidates = []
    current_time = datetime.now()
    
    for idx in indices[0]:
        chunk = chunks[idx]
        metadata = chunk_metadata[idx]
        timestamp = metadata['timestamp']
        
        candidates.append({
            'text': chunk,
            'score': float(distances[0][indices[0].tolist().index(idx)]),
            'timestamp': timestamp,
            'emails_count': metadata['emails_count']
        })
    
    # Time-aware ranking
    query_lower = query.lower()
    if 'latest' in query_lower or 'recent' in query_lower:
        # Prioritize most recent chunks
        candidates.sort(key=lambda x: (-float(x['timestamp']), x['score']))
    else:
        # Balance between relevance and recency
        for candidate in candidates:
            time_factor = 1.0 / (1.0 + (time.time() - float(candidate['timestamp'])) / 86400)
            candidate['score'] = candidate['score'] * (0.7 + 0.3 * time_factor)
        candidates.sort(key=lambda x: x['score'])
    
    # Return top_k chunks after reranking
    return [format_chunk_for_response(c) for c in candidates[:top_k]]

def format_chunk_for_response(chunk_data):
    """Format chunk with clear metadata"""
    return f"""[Chunk containing {chunk_data['emails_count']} emails from {datetime.fromtimestamp(chunk_data['timestamp']).strftime('%Y-%m-%d %I:%M %p')}]
{chunk_data['text']}
"""

def generate_response(conversation_history, question):
    """
    Generate a response with improved formatting and readability.
    """
    relevant_chunks = retrieve_relevant_chunks(question)
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
- Add "📎" if there are attachments mentioned

Example format:
📥 MOST RECENT EMAILS
• 🕒 10:30 AM
  👤 From: John Doe
  📌 Subject: Project Update
  📝 Summary: Weekly progress report with key metrics
  ❗Important deadlines mentioned
-------------------"""

    response = model.generate_content(prompt, generation_config={
        'max_output_tokens': 3000,
        'temperature': 0.7
    })
    
    # Add a header to the response
    formatted_response = f"""📬 EMAIL ASSISTANT
===================
{response.text}

💡 Commands:
• Type 'refresh' to check for new emails
• Type 'clear' to reset conversation
==================="""
    
    return formatted_response