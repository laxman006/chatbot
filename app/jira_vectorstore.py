# -*- coding: utf-8 -*-
"""
Separate Vectorstore for Jira Tickets
Used for issue resolution queries - supplements main vectorstore
"""

import os
import shutil
import time
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


class SyncLock:
    """File-based lock to prevent concurrent sync operations that could corrupt ChromaDB."""
    LOCK_FILE = "./data/jira_sync.lock"
    LOCK_TIMEOUT = 300  # 5 minutes max lock time
    
    @staticmethod
    def acquire():
        """
        Acquire sync lock. Returns True if acquired, False if already locked.
        
        Prevents concurrent syncs that could corrupt the ChromaDB database.
        """
        try:
            os.makedirs("./data", exist_ok=True)
            
            # Check if lock file exists and is stale
            if os.path.exists(SyncLock.LOCK_FILE):
                lock_age = time.time() - os.path.getmtime(SyncLock.LOCK_FILE)
                if lock_age > SyncLock.LOCK_TIMEOUT:
                    print(f"[WARN] Stale lock file detected (age: {lock_age:.0f}s), removing...")
                    try:
                        os.remove(SyncLock.LOCK_FILE)
                    except Exception as e:
                        print(f"[WARN] Could not remove stale lock: {e}")
                        return False
                else:
                    # Lock is active - another sync is running
                    return False
            
            # Create lock file with PID
            try:
                with open(SyncLock.LOCK_FILE, 'w') as f:
                    f.write(str(os.getpid()))
                    f.flush()
                    # Force write to disk (Unix/Linux)
                    if hasattr(os, 'fsync'):
                        os.fsync(f.fileno())
                return True
            except Exception as e:
                print(f"[WARN] Could not create lock file: {e}")
                return False
        except Exception as e:
            print(f"[WARN] Could not acquire sync lock: {e}")
            return False
    
    @staticmethod
    def release():
        """Release sync lock by removing lock file."""
        try:
            if os.path.exists(SyncLock.LOCK_FILE):
                os.remove(SyncLock.LOCK_FILE)
        except Exception as e:
            print(f"[WARN] Could not release sync lock: {e}")


def add_jira_tickets_incrementally():
    """
    Add new/updated Jira tickets to existing vectorstore (incremental update).
    Only fetches tickets updated since last sync.
    
    Uses file-based locking to prevent concurrent syncs that could corrupt ChromaDB.
    """
    if not JIRA_PROCESSOR_AVAILABLE:
        print("[ERROR] Cannot sync Jira tickets: Jira processor not available")
        return None
    
    # Acquire lock to prevent concurrent syncs
    if not SyncLock.acquire():
        print("[WARN] Another sync is already running. Skipping this sync to prevent database corruption.")
        print("[INFO] If no sync is actually running, delete ./data/jira_sync.lock and try again.")
        return None
    
    try:
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
    
    # Convert ISO timestamp to datetime format for JQL
    from datetime import datetime, timedelta
    last_sync_dt = datetime.fromisoformat(last_sync)
    # Subtract 1 minute to catch tickets updated at the exact sync time
    # This ensures we don't miss tickets that were updated right when sync ran
    since_datetime = last_sync_dt - timedelta(minutes=1)
    # Format as YYYY-MM-DD HH:mm for Jira JQL (supports datetime format)
    since_date = since_datetime.strftime('%Y-%m-%d %H:%M')
    
    print(f"[*] Last sync: {last_sync_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[*] Fetching tickets updated since {since_date}...")
    print(f"[DEBUG] Query will look for tickets updated >= '{since_date}'")
    
    # Fetch only new/updated tickets
    from app.jira_processor import JiraProcessor
    processor = JiraProcessor()
    new_tickets = processor.fetch_tickets_since(since_date, max_issues=1000)
    
    if not new_tickets:
        print("[INFO] No new tickets found in Jira (query returned 0 results)")
        print(f"[DEBUG] This could mean:")
        print(f"[DEBUG]   1. No tickets were updated since {since_date}")
        print(f"[DEBUG]   2. JQL query might have an issue")
        print(f"[DEBUG]   3. Jira API might be filtering results")
        update_last_sync_time(status="no_updates", documents_added=0)
        return None
    
    print(f"[OK] Found {len(new_tickets)} new/updated tickets from Jira")
    # Log sample ticket keys for debugging
    if len(new_tickets) > 0:
        sample_keys = [t['key'] for t in new_tickets[:5]]
        print(f"[DEBUG] Sample ticket keys: {', '.join(sample_keys)}")
    
    # Load existing vectorstore
    existing_vectorstore = load_jira_vectorstore()
    
    if not existing_vectorstore:
        print("[ERROR] Existing vectorstore not found. Run build_jira_vectorstore() first.")
        return None
    
    # Skip duplicate check - just process all tickets directly
    # ChromaDB will handle duplicates via explicit document IDs (upsert behavior)
    print(f"[INFO] Processing {len(new_tickets)} tickets directly (no duplicate check)")
    
    # For updated tickets, delete old documents first using ChromaDB's where filter
    # This is much faster than loading all documents
    ticket_keys = [ticket['key'] for ticket in new_tickets]
    
    if ticket_keys:
        print(f"[*] Deleting old documents for {len(ticket_keys)} tickets (if they exist)...")
        total_deleted = 0
        for ticket_key in ticket_keys:
            try:
                # Use ChromaDB's where filter to find and delete documents by ticket_key
                matching_docs = existing_vectorstore._collection.get(
                    where={"ticket_key": ticket_key},
                    include=["ids"]
                )
                if matching_docs and 'ids' in matching_docs and len(matching_docs['ids']) > 0:
                    existing_vectorstore.delete(ids=matching_docs['ids'])
                    total_deleted += len(matching_docs['ids'])
            except Exception as e:
                # If where filter fails, continue - documents will be added with explicit IDs
                # ChromaDB will handle duplicates via ID matching
                print(f"[DEBUG] Could not delete old documents for {ticket_key}: {e}")
        
        if total_deleted > 0:
            print(f"[OK] Deleted {total_deleted} old document chunks")
        else:
            print(f"[INFO] No old documents found to delete (tickets may be new)")
    
    # Process all tickets into documents
    all_new_docs = []
    
    for ticket in new_tickets:
        field_docs = processor.format_ticket_documents(ticket)
        all_new_docs.extend(field_docs)
    
    print(f"[OK] Processed {len(new_tickets)} tickets into {len(all_new_docs)} document chunks")
    
    if not all_new_docs:
        print("[INFO] No new documents to add")
        update_last_sync_time(status="no_updates", documents_added=0)
        return existing_vectorstore
    
    print(f"[OK] Processing {len(all_new_docs)} new document chunks...")
    
    # Use enhanced pipeline for chunking and deduplication
    builder = EnhancedVectorstoreBuilder()
    chunks = builder.process_documents(all_new_docs, source_type="jira")
    
    print(f"[OK] Processed into {len(chunks)} chunks after enhancement")
    
    if len(chunks) == 0:
        print("[WARNING] Enhanced pipeline returned 0 chunks - this might indicate an issue")
        update_last_sync_time(status="no_updates", documents_added=0)
        return existing_vectorstore
    
    # Add explicit IDs to chunks for proper updates
    # Format: jira_{ticket_key}_{section}_{chunk_idx}
    # Track chunk indices per ticket+section combination
    chunk_counters = {}  # (ticket_key, section) -> counter
    
    chunks_with_ids = []
    ids_list = []
    
    for chunk in chunks:
        ticket_key = chunk.metadata.get('ticket_key', 'unknown')
        section = chunk.metadata.get('section', 'unknown')
        
        # Get or initialize counter for this ticket+section
        key = (ticket_key, section)
        if key not in chunk_counters:
            chunk_counters[key] = 0
        else:
            chunk_counters[key] += 1
        
        chunk_idx = chunk_counters[key]
        doc_id = f"jira_{ticket_key}_{section}_{chunk_idx}"
        
        chunks_with_ids.append(chunk)
        ids_list.append(doc_id)
    
    # Add to existing vectorstore in batches to avoid token limit (300k tokens max)
    # Jira chunks average ~600 tokens each, so batch size of 250 = ~150k tokens (safe margin)
    try:
        batch_size = 250
        total_batches = (len(chunks_with_ids) + batch_size - 1) // batch_size
        total_added = 0
        
        if len(chunks_with_ids) > batch_size:
            print(f"[*] Adding {len(chunks_with_ids)} chunks in {total_batches} batches (to avoid token limit)...")
        
        for i in range(0, len(chunks_with_ids), batch_size):
            batch_chunks = chunks_with_ids[i:i + batch_size]
            batch_ids = ids_list[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            
            if len(chunks_with_ids) > batch_size:
                print(f"   [*] Adding batch {batch_num}/{total_batches} ({len(batch_chunks)} chunks)...")
            
            existing_vectorstore.add_documents(
                documents=batch_chunks,
                ids=batch_ids
            )
            total_added += len(batch_chunks)
        
        print(f"[OK] Added {total_added} chunks to existing vectorstore")
        
        # Update sync time with success status
        update_last_sync_time(status="success", documents_added=total_added)
        
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
    finally:
        # Always release lock, even if sync fails
        SyncLock.release()


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


# Initialize Jira vectorstore (lazy loading - only when needed)
# Don't load at module import time to avoid ChromaDB corruption issues
jira_vectorstore = None
jira_retriever = None

def _get_jira_vectorstore_cached():
    """Get cached Jira vectorstore, loading it if needed."""
    global jira_vectorstore, jira_retriever
    if jira_vectorstore is None:
        jira_vectorstore = get_jira_vectorstore()
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
    return jira_vectorstore
