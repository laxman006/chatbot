"""
Quick script to remove duplicate Jira tickets from vectorstore.
Keeps the first occurrence of each ticket_key, removes duplicates.
"""
import os
import sys

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

JIRA_VECTORSTORE_PATH = "./data/jira_chroma_db"

def remove_duplicates():
    """Remove duplicate Jira tickets from vectorstore."""
    print("=" * 70)
    print("REMOVING DUPLICATE JIRA TICKETS")
    print("=" * 70)
    
    # Load vectorstore
    print(f"[*] Loading Jira vectorstore from {JIRA_VECTORSTORE_PATH}...")
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    vectorstore = Chroma(
        persist_directory=JIRA_VECTORSTORE_PATH,
        embedding_function=embeddings,
        collection_metadata={
            "hnsw:space": "cosine",
            "hnsw:construction_ef": 200,
            "hnsw:search_ef": 100,
            "hnsw:M": 48,
        }
    )
    
    initial_count = vectorstore._collection.count()
    print(f"[OK] Loaded vectorstore with {initial_count} chunks")
    
    # Get all documents with IDs and metadata
    print("[*] Fetching all documents...")
    all_docs = vectorstore.get(include=["metadatas"])
    doc_ids = all_docs.get("ids", [])
    metadatas = all_docs.get("metadatas", [])
    
    print(f"[OK] Retrieved {len(doc_ids)} documents")
    
    # Track seen tickets and IDs to delete
    seen_tickets = {}  # ticket_key -> first occurrence ID
    seen_sections = {}  # (ticket_key, section) -> first occurrence ID
    ids_to_delete = []
    
    print("[*] Identifying duplicates...")
    for doc_id, metadata in zip(doc_ids, metadatas):
        ticket_key = metadata.get("ticket_key")
        section = metadata.get("section", "unknown")
        
        if not ticket_key:
            # Not a Jira ticket, skip
            continue
        
        # Create unique key for this ticket section
        section_key = (ticket_key, section)
        
        if section_key in seen_sections:
            # This is a duplicate - mark for deletion
            ids_to_delete.append(doc_id)
        else:
            # First time seeing this ticket section - keep it
            seen_sections[section_key] = doc_id
    
    print(f"[OK] Found {len(ids_to_delete)} duplicate chunks to remove")
    
    if not ids_to_delete:
        print("[INFO] No duplicates found!")
        return
    
    # Delete duplicates in batches
    print("[*] Removing duplicates...")
    batch_size = 1000
    for i in range(0, len(ids_to_delete), batch_size):
        batch = ids_to_delete[i:i + batch_size]
        vectorstore._collection.delete(ids=batch)
        print(f"   Deleted batch {i//batch_size + 1}/{(len(ids_to_delete) + batch_size - 1)//batch_size} ({len(batch)} chunks)")
    
    final_count = vectorstore._collection.count()
    print(f"[OK] Cleanup complete!")
    print(f"[OK] Before: {initial_count} chunks")
    print(f"[OK] After: {final_count} chunks")
    print(f"[OK] Removed: {initial_count - final_count} duplicate chunks")
    
    print("=" * 70)
    print("[OK] DUPLICATE REMOVAL COMPLETE!")
    print("=" * 70)

if __name__ == "__main__":
    try:
        remove_duplicates()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
