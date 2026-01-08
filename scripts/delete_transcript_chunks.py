#!/usr/bin/env python3
"""
Delete old transcript chunks from vectorstore before reprocessing.

This script removes all existing transcript chunks from the ChromaDB vectorstore,
allowing you to reprocess transcripts with updated processing logic (e.g., fixed speaker roles).

Usage:
    python scripts/delete_transcript_chunks.py [--dry-run]
    
    --dry-run: Preview what will be deleted without actually deleting
"""

import os
import sys
import argparse

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from config import CHROMA_DB_PATH


def delete_transcript_chunks(dry_run: bool = False):
    """Delete all transcript chunks from vectorstore."""
    print("=" * 70)
    print("DELETE TRANSCRIPT CHUNKS FROM VECTORSTORE")
    print("=" * 70)
    
    if dry_run:
        print("[DRY-RUN MODE] No changes will be made\n")
    
    print("[*] Loading vectorstore...")
    
    try:
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        vectorstore = Chroma(
            persist_directory=CHROMA_DB_PATH,
            embedding_function=embeddings
        )
        
        # Get all transcript documents
        collection = vectorstore._collection
        
        # Get all IDs where source is transcript or kb_tier is secondary
        print("[*] Searching for transcript chunks...")
        transcript_ids = []
        transcript_metadatas = []
        
        try:
            # Try querying by source first
            results = collection.get(
                where={"source": "sharepoint_transcripts"},
                include=["metadatas"]
            )
            transcript_ids.extend(results.get("ids", []))
            transcript_metadatas.extend(results.get("metadatas", []))
            print(f"[*] Found {len(transcript_ids)} chunks by source")
        except Exception as e:
            print(f"[WARNING] Query by source failed: {e}")
        
        try:
            # Also try querying by kb_tier to catch any we might have missed
            results2 = collection.get(
                where={"kb_tier": "secondary"},
                include=["metadatas"]
            )
            ids2 = results2.get("ids", [])
            metas2 = results2.get("metadatas", [])
            # Add only new ones (avoid duplicates)
            for id2, meta2 in zip(ids2, metas2):
                if id2 not in transcript_ids:
                    transcript_ids.append(id2)
                    transcript_metadatas.append(meta2)
            print(f"[*] Found {len(ids2)} chunks by kb_tier (total unique: {len(transcript_ids)})")
        except Exception as e:
            print(f"[WARNING] Query by kb_tier failed: {e}")
        
        # Remove duplicates
        seen = set()
        unique_ids = []
        unique_metas = []
        for id_val, meta_val in zip(transcript_ids, transcript_metadatas):
            if id_val not in seen:
                seen.add(id_val)
                unique_ids.append(id_val)
                unique_metas.append(meta_val)
        
        transcript_ids = unique_ids
        transcript_metadatas = unique_metas
        
        if not transcript_ids:
            print("[INFO] No transcript chunks found to delete")
            return
        
        print(f"[*] Found {len(transcript_ids)} transcript chunks to delete")
        print("\n[*] Sample chunks to be deleted:")
        print("-" * 70)
        
        # Show sample of what will be deleted
        for i, (meta, doc_id) in enumerate(zip(transcript_metadatas[:5], transcript_ids[:5])):
            file_name = meta.get("file_name", "Unknown")
            artifact_type = meta.get("artifact_type", "Unknown")
            kb_tier = meta.get("kb_tier", "Unknown")
            print(f"  [{i+1}] {file_name}")
            print(f"      Type: {artifact_type} | KB Tier: {kb_tier} | ID: {doc_id[:20]}...")
        
        if len(transcript_ids) > 5:
            print(f"  ... and {len(transcript_ids) - 5} more chunks")
        
        print("-" * 70)
        
        if dry_run:
            print("\n[DRY-RUN] Would delete these chunks, but dry-run mode is enabled")
            print("[DRY-RUN] Run without --dry-run to actually delete")
            return
        
        # Confirm deletion
        print(f"\n[*] About to delete {len(transcript_ids)} transcript chunks")
        response = input("   Continue? (yes/no): ").strip().lower()
        
        if response not in ['yes', 'y']:
            print("[CANCELLED] Deletion cancelled by user")
            return
        
        # Delete them
        print("[*] Deleting transcript chunks...")
        collection.delete(ids=transcript_ids)
        
        print(f"[OK] Successfully deleted {len(transcript_ids)} transcript chunks")
        print("\n[OK] You can now reprocess transcripts with:")
        print("   python scripts/process_transcripts_from_sharepoint.py")
        
    except Exception as e:
        print(f"[ERROR] Failed to delete transcript chunks: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Delete old transcript chunks from vectorstore"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview what will be deleted without actually deleting'
    )
    
    args = parser.parse_args()
    delete_transcript_chunks(dry_run=args.dry_run)


if __name__ == "__main__":
    main()

