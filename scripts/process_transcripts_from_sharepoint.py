#!/usr/bin/env python3
"""
Process transcripts from SharePoint and add to knowledge base

Extracts transcript Word documents from SharePoint folder, processes them into
both raw conversation and Q/A pairs, and adds them to the vectorstore.

Usage:
    python scripts/process_transcripts_from_sharepoint.py [--dry-run] [--folder-path PATH] [--site-url URL]
    
    --dry-run: Preview what will be processed without adding to vectorstore
    --folder-path: Override transcript folder path (default: from config)
    --site-url: Override SharePoint site URL (default: from config)

Example:
    python scripts/process_transcripts_from_sharepoint.py
    python scripts/process_transcripts_from_sharepoint.py --dry-run
    python scripts/process_transcripts_from_sharepoint.py --folder-path "Neutara Labs/Transcripts"
"""

import os
import sys
import argparse
from typing import List, Optional

# Add parent directory to path to import from app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from langchain_core.documents import Document
from app.transcript_processor import TranscriptProcessor, extract_transcripts_from_sharepoint
from config import ENABLE_TRANSCRIPT_PROCESSING


def process_transcripts(
    folder_path: Optional[str] = None,
    site_url: Optional[str] = None,
    dry_run: bool = False
) -> tuple[List[Document], int]:
    """
    Process transcripts from SharePoint.
    
    Args:
        folder_path: Override folder path
        site_url: Override site URL
        dry_run: If True, only extract and preview, don't add to vectorstore
    
    Returns:
        Tuple of (documents, count of transcripts processed)
    """
    print("=" * 70)
    print("SHAREPOINT TRANSCRIPT PROCESSING")
    print("=" * 70)
    
    if dry_run:
        print("[DRY RUN] Preview mode - transcripts will NOT be added to vectorstore")
    
    # Initialize processor
    processor = TranscriptProcessor(
        site_url=site_url,
        folder_path=folder_path
    )
    
    # Extract transcripts
    print("\n[*] Extracting transcripts from SharePoint...")
    documents = processor.extract_transcripts_from_sharepoint()
    
    if not documents:
        print("\n[WARNING] No transcript documents extracted")
        return [], 0
    
    # Count unique transcripts (by file_name)
    unique_transcripts = set()
    for doc in documents:
        file_name = doc.metadata.get('file_name')
        if file_name:
            unique_transcripts.add(file_name)
    
    transcript_count = len(unique_transcripts)
    
    print(f"\n[*] Extraction Summary:")
    print(f"   Transcript files: {transcript_count}")
    print(f"   Total documents: {len(documents)}")
    
    # Count by document type
    doc_types = {
        'Q&A pairs': sum(1 for d in documents if d.metadata.get('document_type') == 'qa_pairs'),
        'Objection-response': sum(1 for d in documents if d.metadata.get('document_type') == 'objection_response'),
        'Feature capabilities': sum(1 for d in documents if d.metadata.get('document_type') == 'feature_capability'),
        'Decision drivers': sum(1 for d in documents if d.metadata.get('document_type') == 'decision_driver'),
        'Raw transcripts': sum(1 for d in documents if d.metadata.get('document_type') == 'raw_transcript')
    }
    
    for doc_type, count in doc_types.items():
        if count > 0:
            print(f"   {doc_type}: {count}")
    
    if dry_run:
        print("\n[DRY RUN] Preview of documents to be processed:")
        for i, doc in enumerate(documents[:10], 1):  # Show first 10
            print(f"\n   {i}. {doc.metadata.get('file_name')}")
            print(f"      Type: {doc.metadata.get('document_type')} ({doc.metadata.get('artifact_type', 'N/A')})")
            print(f"      KB Tier: {doc.metadata.get('kb_tier', 'primary')}")
            print(f"      Customer: {doc.metadata.get('customer', 'N/A')}")
            print(f"      Industry: {doc.metadata.get('industry', 'N/A')}")
            print(f"      Topics: {doc.metadata.get('topic', 'N/A')}")
            print(f"      Title: {doc.metadata.get('meeting_title', 'N/A')}")
            print(f"      Date: {doc.metadata.get('meeting_date', 'N/A')}")
            print(f"      Content length: {len(doc.page_content)} chars")
            if doc.metadata.get('qa_count'):
                print(f"      Q/A pairs: {doc.metadata.get('qa_count')}")
            if doc.metadata.get('objection_count'):
                print(f"      Objections: {doc.metadata.get('objection_count')}")
            if doc.metadata.get('feature_count'):
                print(f"      Features: {doc.metadata.get('feature_count')}")
            if doc.metadata.get('driver_count'):
                print(f"      Decision drivers: {doc.metadata.get('driver_count')}")
        
        if len(documents) > 10:
            print(f"\n   ... and {len(documents) - 10} more documents")
        
        print("\n[DRY RUN] For Weaviate ingestion run: python scripts/ingest_to_weaviate.py --source transcript")
        return documents, transcript_count
    
    # Return documents for Weaviate ingestion (chunking/embedding done by WeaviateIngestionPipeline)
    print("\n[OK] Documents ready for Weaviate ingestion.")
    print("      Run: python scripts/ingest_to_weaviate.py --source transcript")
    return documents, transcript_count


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Process transcripts from SharePoint and add to knowledge base"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview what will be processed without adding to vectorstore'
    )
    parser.add_argument(
        '--folder-path',
        type=str,
        default=None,
        help='Override transcript folder path (default: from config)'
    )
    parser.add_argument(
        '--site-url',
        type=str,
        default=None,
        help='Override SharePoint site URL (default: from config)'
    )
    
    args = parser.parse_args()
    
    # Check if transcript processing is enabled
    if not ENABLE_TRANSCRIPT_PROCESSING and not args.dry_run:
        print("[WARNING] Transcript processing is disabled in config")
        print("   Set ENABLE_TRANSCRIPT_PROCESSING=true to enable")
        print("   Or use --dry-run to preview without processing")
        sys.exit(1)
    
    # Check for required environment variables
    import os
    if not os.getenv("MICROSOFT_CLIENT_ID") or not os.getenv("MICROSOFT_CLIENT_SECRET"):
        print("[ERROR] SharePoint authentication credentials not found")
        print("   Required environment variables:")
        print("   - MICROSOFT_CLIENT_ID")
        print("   - MICROSOFT_CLIENT_SECRET")
        print("   - MICROSOFT_TENANT (optional, defaults to cloudfuze.com)")
        print("\n   Please set these in your .env file or environment variables")
        sys.exit(1)
    
    try:
        documents, count = process_transcripts(
            folder_path=args.folder_path,
            site_url=args.site_url,
            dry_run=args.dry_run
        )
        
        if not args.dry_run:
            print(f"\n[OK] Successfully processed {count} transcript(s)")
            print(f"   Total documents added: {len(documents)}")
        else:
            print(f"\n[OK] Preview complete - {count} transcript(s) would be processed")
            print(f"   Total documents that would be added: {len(documents)}")
    
    except KeyboardInterrupt:
        print("\n[INFO] Processing interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Processing failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

