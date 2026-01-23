# -*- coding: utf-8 -*-
"""
Separate Vectorstore for Jira Tickets
Used for issue resolution queries - supplements main vectorstore
"""

import os
import shutil
from typing import List, Optional
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document

# Optional Jira processor import - allows backend to start without jira package
try:
    from app.jira_processor import process_jira_content
    JIRA_PROCESSOR_AVAILABLE = True
except ImportError as e:
    JIRA_PROCESSOR_AVAILABLE = False
    process_jira_content = None
    print(f"[WARNING] Jira processor not available: {e}")
from app.enhanced_helpers import EnhancedVectorstoreBuilder
from config import (
    JIRA_VECTORSTORE_PATH, 
    INITIALIZE_JIRA_VECTORSTORE, 
    JIRA_MAX_ISSUES,
    ENABLE_JIRA_VECTORSTORE
)


def load_jira_vectorstore():
    """Load existing Jira vectorstore."""
    if not os.path.exists(JIRA_VECTORSTORE_PATH):
        return None
    
    try:
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
        total_docs = vectorstore._collection.count()
        print(f"[OK] Loaded Jira vectorstore with {total_docs} documents")
        return vectorstore
    except Exception as e:
        print(f"[ERROR] Failed to load Jira vectorstore: {e}")
        return None


def build_jira_vectorstore(use_cache: bool = True):
    """
    Build separate vectorstore for Jira tickets.
    
    Args:
        use_cache: If True, try to load tickets from cache before fetching
    """
    if not JIRA_PROCESSOR_AVAILABLE:
        print("[ERROR] Cannot build Jira vectorstore: Jira processor not available")
        print("[INFO] Install jira package with: pip install jira")
        return None
    
    print("=" * 60)
    print("BUILDING SEPARATE JIRA VECTORSTORE")
    print("=" * 60)
    
    # Delete existing vectorstore to prevent duplicates
    if os.path.exists(JIRA_VECTORSTORE_PATH):
        print(f"[*] Removing existing Jira vectorstore at {JIRA_VECTORSTORE_PATH}...")
        try:
            shutil.rmtree(JIRA_VECTORSTORE_PATH)
            print("[OK] Existing vectorstore removed - will create fresh build")
        except Exception as e:
            print(f"[WARNING] Could not remove existing vectorstore: {e}")
            print("[WARNING] Continuing anyway - duplicates may occur")
    
    # Try to load tickets from cache if enabled
    from app.jira_ticket_cache import load_tickets_from_cache, save_tickets_to_cache, get_cache_info
    
    tickets = None
    processor = None
    
    if use_cache:
        print(f"[*] Checking for cached tickets...")
        cache_info = get_cache_info()
        if cache_info:
            print(f"[CACHE] Found cache: {cache_info.get('ticket_count', 0)} tickets, "
                  f"{cache_info.get('file_size_mb', 0)} MB")
            print(f"[CACHE] Cache created: {cache_info.get('fetch_time', 'unknown')}")
            tickets = load_tickets_from_cache()
            if tickets:
                print(f"[OK] Loaded {len(tickets)} tickets from cache - processing ALL tickets")
        else:
            print(f"[CACHE] No cache found - will fetch from Jira")
    
    # If no cache or cache disabled, fetch from Jira
    if not tickets:
        print(f"[*] Fetching {JIRA_MAX_ISSUES} recent closed/resolved tickets from Jira...")
        
        # Fetch tickets
        from app.jira_processor import JiraProcessor
        processor = JiraProcessor()
        tickets = processor.fetch_tickets()
        
        # Save to cache for future use
        if tickets:
            from datetime import datetime
            save_tickets_to_cache(tickets, {
                "fetch_time": datetime.now().isoformat(),
                "ticket_count": len(tickets),
                "max_issues": JIRA_MAX_ISSUES,
                "source": "Jira API"
            })
    
    # Convert tickets to documents
    if not tickets:
        print("[WARNING] No Jira tickets found")
        return None
    
    print(f"[*] Processing {len(tickets)} tickets into document chunks...")
    print(f"[INFO] Processing ALL tickets (no deduplication)")
    
    # Reuse processor if available, otherwise create one
    if processor is None:
        from app.jira_processor import JiraProcessor
        processor = JiraProcessor()
    
    jira_docs = []
    for ticket in tickets:
        field_docs = processor.format_ticket_documents(ticket)
        jira_docs.extend(field_docs)
    
    print(f"[OK] Processed {len(jira_docs)} Jira ticket chunks from {len(tickets)} tickets")
    
    if not jira_docs:
        print("[WARNING] No Jira tickets found")
        return None
    
    # Use enhanced pipeline for chunking (deduplication is skipped for Jira source_type)
    builder = EnhancedVectorstoreBuilder()
    chunks = builder.process_documents(jira_docs, source_type="jira")
    
    print(f"[OK] Processed into {len(chunks)} chunks after enhancement")
    
    # Build vectorstore (will create new since we deleted it)
    vectorstore = builder.build_vectorstore(
        chunks, persist_directory=JIRA_VECTORSTORE_PATH
    )
    
    report = builder.get_report()
    print("\n===== JIRA VECTORSTORE BUILD REPORT =====")
    print(report)
    print("==========================================\n")
    
    return vectorstore


def add_jira_tickets_incrementally():
    """
    Add new/updated Jira tickets to existing vectorstore (incremental update).
    Only fetches tickets updated since last sync.
    """
    if not JIRA_PROCESSOR_AVAILABLE:
        print("[ERROR] Cannot sync Jira tickets: Jira processor not available")
        return None
    
    print("=" * 60)
    print("INCREMENTAL JIRA VECTORSTORE UPDATE")
    print("=" * 60)
    
    # Import sync tracker
    from app.jira_sync_tracker import get_last_sync_time, update_last_sync_time
    
    # Get last sync time
    last_sync = get_last_sync_time()
    
    if not last_sync:
        print("[WARNING] No previous sync found. Use build_jira_vectorstore() for initial load.")
        return None
    
    # Convert ISO timestamp to YYYY-MM-DD format for JQL
    from datetime import datetime
    last_sync_dt = datetime.fromisoformat(last_sync)
    since_date = last_sync_dt.strftime('%Y-%m-%d')
    
    print(f"[*] Last sync: {last_sync_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[*] Fetching tickets updated since {since_date}...")
    
    # Fetch only new/updated tickets
    from app.jira_processor import JiraProcessor
    processor = JiraProcessor()
    new_tickets = processor.fetch_tickets_since(since_date, max_issues=1000)
    
    if not new_tickets:
        print("[INFO] No new tickets found")
        update_last_sync_time(status="no_updates", documents_added=0)
        return None
    
    print(f"[OK] Found {len(new_tickets)} new/updated tickets")
    
    # Load existing vectorstore
    existing_vectorstore = load_jira_vectorstore()
    
    if not existing_vectorstore:
        print("[ERROR] Existing vectorstore not found. Run build_jira_vectorstore() first.")
        return None
    
    # Check for duplicates by querying existing tickets
    existing_ticket_keys = set()
    try:
        # Get all ticket keys from vectorstore metadata
        all_docs = existing_vectorstore.get()
        if all_docs and 'metadatas' in all_docs:
            for metadata in all_docs['metadatas']:
                if metadata and 'ticket_key' in metadata:
                    existing_ticket_keys.add(metadata['ticket_key'])
        
        print(f"[INFO] Found {len(existing_ticket_keys)} existing tickets in vectorstore")
    except Exception as e:
        print(f"[WARNING] Could not check for duplicates: {e}")
    
    # Filter out tickets that already exist
    truly_new_tickets = [
        ticket for ticket in new_tickets 
        if ticket['key'] not in existing_ticket_keys
    ]
    
    # For existing tickets that were updated, we need to remove old and add new
    updated_tickets = [
        ticket for ticket in new_tickets 
        if ticket['key'] in existing_ticket_keys
    ]
    
    print(f"[INFO] New tickets: {len(truly_new_tickets)}, Updated tickets: {len(updated_tickets)}")
    
    # Process new tickets into documents
    all_new_docs = []
    
    # Add truly new tickets
    for ticket in truly_new_tickets:
        field_docs = processor.format_ticket_documents(ticket)
        all_new_docs.extend(field_docs)
    
    # For updated tickets, we'll add them (ChromaDB handles updates by ID)
    for ticket in updated_tickets:
        field_docs = processor.format_ticket_documents(ticket)
        all_new_docs.extend(field_docs)
    
    if not all_new_docs:
        print("[INFO] No new documents to add")
        update_last_sync_time(status="no_updates", documents_added=0)
        return existing_vectorstore
    
    print(f"[OK] Processing {len(all_new_docs)} new document chunks...")
    
    # Use enhanced pipeline for chunking and deduplication
    builder = EnhancedVectorstoreBuilder()
    chunks = builder.process_documents(all_new_docs, source_type="jira")
    
    print(f"[OK] Processed into {len(chunks)} chunks after enhancement")
    
    # Add to existing vectorstore
    try:
        existing_vectorstore.add_documents(chunks)
        print(f"[OK] Added {len(chunks)} chunks to existing vectorstore")
        
        # Update sync time with success status
        update_last_sync_time(status="success", documents_added=len(chunks))
        
        # Get updated count
        total_docs = existing_vectorstore._collection.count()
        print(f"[OK] Vectorstore now contains {total_docs} total documents")
        
        return existing_vectorstore
        
    except Exception as e:
        error_msg = str(e)
        print(f"[ERROR] Failed to add documents: {error_msg}")
        import traceback
        traceback.print_exc()
        
        # Record failure
        update_last_sync_time(status="failed", documents_added=0, error_message=error_msg)
        return None


def get_jira_vectorstore():
    """Get Jira vectorstore instance."""
    if not ENABLE_JIRA_VECTORSTORE:
        print("[INFO] Jira vectorstore is disabled (ENABLE_JIRA_VECTORSTORE=false)")
        return None
    
    # Try to load existing first
    if os.path.exists(JIRA_VECTORSTORE_PATH):
        print("[*] Loading existing Jira vectorstore...")
        vectorstore = load_jira_vectorstore()
        if vectorstore:
            return vectorstore
    
    # Build if INITIALIZE_JIRA_VECTORSTORE is true
    if INITIALIZE_JIRA_VECTORSTORE:
        print("[*] INITIALIZE_JIRA_VECTORSTORE=true - building Jira vectorstore...")
        return build_jira_vectorstore()
    
    return None


# Initialize Jira vectorstore
jira_vectorstore = get_jira_vectorstore()

# Create retriever for Jira tickets
jira_retriever = None
if jira_vectorstore:
    jira_retriever = jira_vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={
            "k": 10,  # Return top 10 most relevant tickets for issue resolution
        }
    )
    print("[OK] Jira retriever ready for issue resolution queries")
else:
    print("[INFO] No Jira vectorstore available - set INITIALIZE_JIRA_VECTORSTORE=true to create one")
