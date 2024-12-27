import google.generativeai as genai
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import PyPDF2

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

def chunk_text(text, chunk_size=500):
    """
    Divide text into chunks of specified word count.
    
    Args:
        text (str): The text to chunk.
        chunk_size (int): Number of words per chunk.
        
    Returns:
        list: A list of text chunks.
    """
    words = text.split()
    chunks = [' '.join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]
    return chunks

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

def add_document_to_vector_db(doc_id, text):
    """
    Add document text to the vector database after chunking and embedding.
    
    Args:
        doc_id (str): Unique identifier for the document.
        text (str): The text content of the document.
    """
    global chunks, embeddings, faiss_index, chunk_metadata
    doc_chunks = chunk_text(text)
    doc_embeddings = embeddingModel.encode(doc_chunks)
    
    # Store chunk metadata with timestamps
    for i, chunk in enumerate(doc_chunks):
        chunk_id = f"{doc_id}_chunk_{i}"
        chunks.append(chunk)
        chunk_metadata[len(chunks)-1] = {
            'doc_id': doc_id,
            'chunk_id': chunk_id,
            'timestamp': doc_id.split('_')[1]  # Extract timestamp from doc_id
        }
    
    embeddings.extend(doc_embeddings)
    faiss_index.add(np.array(doc_embeddings))
    print(f"Document '{doc_id}' has been added to the vector database with {len(doc_chunks)} chunks.")

def retrieve_relevant_chunks(query, top_k=5):
    """
    Retrieve the top K relevant chunks from the vector database based on the query.
    
    Args:
        query (str): The user's search query.
        top_k (int): Number of top similar chunks to retrieve.
        
    Returns:
        list: A list of relevant text chunks.
    """
    query_embedding = embeddingModel.encode([query])
    distances, indices = faiss_index.search(query_embedding, top_k)
    top_chunks = [chunks[idx] for idx in indices[0]]
    return top_chunks

def generate_response(conversation_history, question):
    """
    Generate a response based on the conversation history and question using RAG.
    
    Args:
        conversation_history (str): The history of the conversation.
        question (str): The user's current question.
        
    Returns:
        str: The generated response.
    """
    relevant_chunks = retrieve_relevant_chunks(question)
    combined_text = '\n\n'.join(relevant_chunks)
    if not combined_text:
        return "No relevant information found in the document."

    prompt = f"""Based on the following email contents and conversation history, provide a detailed and accurate response.

CONVERSATION HISTORY:
{conversation_history}

RELEVANT EMAIL CONTENTS:
{combined_text}

QUESTION: {question}

Please provide a comprehensive answer using the information from the emails. If referring to specific emails, mention their details (sender, date, subject) for context."""

    response = model.generate_content(prompt)
    return response.text