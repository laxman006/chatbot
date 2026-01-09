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
from app.jira_processor import process_jira_content
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


def build_jira_vectorstore():
    """Build separate vectorstore for Jira tickets."""
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
    
    print(f"[*] Fetching {JIRA_MAX_ISSUES} recent closed/resolved tickets...")
    
    # Process Jira tickets
    jira_docs = process_jira_content()
    print(f"[OK] Processed {len(jira_docs)} Jira ticket chunks")
    
    if not jira_docs:
        print("[WARNING] No Jira tickets found")
        return None
    
    # Use enhanced pipeline for chunking and deduplication
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
