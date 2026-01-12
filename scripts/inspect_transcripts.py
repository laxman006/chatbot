#!/usr/bin/env python3
"""
Inspect and Export Processed Transcripts

This script allows you to view and export processed transcripts from the knowledge base.
You can see the normalized text, extracted artifacts (Q&A, objections, features), and chunks.

Usage:
    python scripts/inspect_transcripts.py [--export-dir DIR] [--format json|text|both]
    
    --export-dir: Directory to save exported files (default: ./transcript_exports)
    --format: Export format - json, text, or both (default: both)
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from config import CHROMA_DB_PATH


def load_transcript_documents() -> List[Dict[str, Any]]:
    """Load all transcript documents from vectorstore."""
    print("[*] Loading transcript documents from vectorstore...")
    
    try:
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        vectorstore = Chroma(
            persist_directory=CHROMA_DB_PATH,
            embedding_function=embeddings
        )
        
        # Try to get all documents using ChromaDB collection directly
        transcript_docs = []
        try:
            # Access the underlying collection
            collection = vectorstore._collection
            
            # Get all documents with metadata filter for transcripts
            # Use where clause to filter for transcript documents
            results = collection.get(
                where={
                    "$or": [
                        {"source_type": "transcript"},
                        {"kb_tier": "secondary"}
                    ]
                },
                include=["documents", "metadatas"]
            )
            
            # Process results
            if results and results.get('ids'):
                for i, doc_id in enumerate(results['ids']):
                    content = results['documents'][i] if results.get('documents') else ""
                    metadata = results['metadatas'][i] if results.get('metadatas') else {}
                    
                    # Double-check it's a transcript
                    if (metadata.get('source_type') == 'transcript' or 
                        'transcript' in metadata.get('tag', '').lower() or
                        metadata.get('kb_tier') == 'secondary'):
                        transcript_docs.append({
                            'content': content,
                            'metadata': metadata
                        })
            
        except Exception as e:
            print(f"   [INFO] Direct collection access failed, using similarity search: {e}")
            # Fallback: Use similarity search with a broad query
            # Search for common transcript terms to get relevant docs
            search_queries = ["transcript", "customer demo", "meeting", "qa", "question answer"]
            all_docs = []
            seen_ids = set()
            
            for query in search_queries:
                docs = vectorstore.similarity_search(query, k=1000)
                for doc in docs:
                    # Create a unique ID from content hash
                    doc_id = hash(doc.page_content[:100])
                    if doc_id not in seen_ids:
                        seen_ids.add(doc_id)
                        all_docs.append(doc)
            
            # Filter for transcript documents
            for doc in all_docs:
                metadata = doc.metadata
                if (metadata.get('source_type') == 'transcript' or 
                    'transcript' in metadata.get('tag', '').lower() or
                    metadata.get('kb_tier') == 'secondary'):
                    transcript_docs.append({
                        'content': doc.page_content,
                        'metadata': metadata
                    })
        
        print(f"[OK] Found {len(transcript_docs)} transcript documents")
        return transcript_docs
        
    except Exception as e:
        print(f"[ERROR] Failed to load documents: {e}")
        import traceback
        traceback.print_exc()
        return []


def group_documents_by_file(documents: List[Dict]) -> Dict[str, List[Dict]]:
    """Group documents by original file name."""
    grouped = {}
    for doc in documents:
        file_name = doc['metadata'].get('file_name', 'unknown')
        if file_name not in grouped:
            grouped[file_name] = []
        grouped[file_name].append(doc)
    return grouped


def export_transcripts(
    documents: List[Dict],
    export_dir: str,
    format: str = "both"
):
    """Export processed transcripts to files."""
    export_path = Path(export_dir)
    export_path.mkdir(parents=True, exist_ok=True)
    
    # Group by file
    grouped = group_documents_by_file(documents)
    
    print(f"\n[*] Exporting {len(grouped)} transcript files...")
    
    for file_name, docs in grouped.items():
        # Clean filename for filesystem
        safe_name = "".join(c for c in file_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_name = safe_name[:100]  # Limit length
        
        # Group by artifact type
        # Normalize artifact types to handle variations (e.g., "Decision Driver" vs "DecisionDriver")
        by_type = {
            'Q&A': [],
            'Objection': [],
            'Feature': [],
            'DecisionDriver': [],
            'RawTranscript': []
        }
        
        # Mapping to normalize different artifact type formats
        artifact_type_mapping = {
            'Decision Driver': 'DecisionDriver',
            'DecisionDriver': 'DecisionDriver',
            'Q&A': 'Q&A',
            'Q&A pairs': 'Q&A',
            'Objection': 'Objection',
            'Feature': 'Feature',
            'Raw Transcript': 'RawTranscript',
            'RawTranscript': 'RawTranscript',
            None: 'RawTranscript'  # Default for missing artifact_type
        }
        
        for doc in docs:
            artifact_type = doc['metadata'].get('artifact_type', 'RawTranscript')
            # Normalize the artifact type
            normalized_type = artifact_type_mapping.get(artifact_type, 'RawTranscript')
            # Handle case where key might not exist
            if normalized_type not in by_type:
                normalized_type = 'RawTranscript'  # Fallback
            by_type[normalized_type].append(doc)
        
        # Export JSON
        if format in ['json', 'both']:
            json_data = {
                'source_file': file_name,
                'export_date': datetime.now().isoformat(),
                'metadata': docs[0]['metadata'] if docs else {},
                'artifacts': {
                    'qa_pairs': [
                        {
                            'content': d['content'],
                            'metadata': d['metadata']
                        }
                        for d in by_type['Q&A']
                    ],
                    'objections': [
                        {
                            'content': d['content'],
                            'metadata': d['metadata']
                        }
                        for d in by_type['Objection']
                    ],
                    'features': [
                        {
                            'content': d['content'],
                            'metadata': d['metadata']
                        }
                        for d in by_type['Feature']
                    ],
                    'decision_drivers': [
                        {
                            'content': d['content'],
                            'metadata': d['metadata']
                        }
                        for d in by_type['DecisionDriver']
                    ],
                    'raw_transcript': [
                        {
                            'content': d['content'],
                            'metadata': d['metadata']
                        }
                        for d in by_type['RawTranscript']
                    ]
                },
                'summary': {
                    'total_documents': len(docs),
                    'qa_count': len(by_type['Q&A']),
                    'objection_count': len(by_type['Objection']),
                    'feature_count': len(by_type['Feature']),
                    'decision_driver_count': len(by_type['DecisionDriver']),
                    'raw_transcript_count': len(by_type['RawTranscript'])
                }
            }
            
            json_file = export_path / f"{safe_name}_processed.json"
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
            print(f"   [OK] Exported JSON: {json_file.name}")
        
        # Export Text
        if format in ['text', 'both']:
            text_file = export_path / f"{safe_name}_processed.txt"
            with open(text_file, 'w', encoding='utf-8') as f:
                # Header
                f.write("=" * 80 + "\n")
                f.write(f"PROCESSED TRANSCRIPT: {file_name}\n")
                f.write("=" * 80 + "\n\n")
                
                # Metadata
                if docs:
                    meta = docs[0]['metadata']
                    f.write("METADATA:\n")
                    f.write(f"  Customer: {meta.get('customer', 'N/A')}\n")
                    f.write(f"  Industry: {meta.get('industry', 'N/A')}\n")
                    f.write(f"  Meeting Date: {meta.get('meeting_date', 'N/A')}\n")
                    f.write(f"  Meeting Title: {meta.get('meeting_title', 'N/A')}\n")
                    f.write(f"  Participants: {meta.get('participants', 'N/A')}\n")
                    f.write(f"  Topics: {meta.get('topic', 'N/A')}\n")
                    f.write(f"  KB Tier: {meta.get('kb_tier', 'primary')}\n")
                    f.write(f"  Contains Pricing: {meta.get('contains_pricing', False)}\n")
                    f.write("\n")
                
                # Q&A Pairs
                if by_type['Q&A']:
                    f.write("\n" + "=" * 80 + "\n")
                    f.write("Q&A PAIRS\n")
                    f.write("=" * 80 + "\n\n")
                    for i, doc in enumerate(by_type['Q&A'], 1):
                        f.write(f"--- Q&A Pair {i} ---\n")
                        f.write(doc['content'])
                        f.write("\n\n")
                
                # Objections
                if by_type['Objection']:
                    f.write("\n" + "=" * 80 + "\n")
                    f.write("OBJECTIONS & RESPONSES\n")
                    f.write("=" * 80 + "\n\n")
                    for i, doc in enumerate(by_type['Objection'], 1):
                        f.write(f"--- Objection {i} ---\n")
                        f.write(doc['content'])
                        f.write("\n\n")
                
                # Features
                if by_type['Feature']:
                    f.write("\n" + "=" * 80 + "\n")
                    f.write("FEATURE CAPABILITIES\n")
                    f.write("=" * 80 + "\n\n")
                    for i, doc in enumerate(by_type['Feature'], 1):
                        f.write(f"--- Feature {i} ---\n")
                        f.write(doc['content'])
                        f.write("\n\n")
                
                # Decision Drivers
                if by_type['DecisionDriver']:
                    f.write("\n" + "=" * 80 + "\n")
                    f.write("DECISION DRIVERS\n")
                    f.write("=" * 80 + "\n\n")
                    for i, doc in enumerate(by_type['DecisionDriver'], 1):
                        f.write(f"--- Decision Driver {i} ---\n")
                        f.write(doc['content'])
                        f.write("\n\n")
                
                # Raw Transcript
                if by_type['RawTranscript']:
                    f.write("\n" + "=" * 80 + "\n")
                    f.write("RAW NORMALIZED TRANSCRIPT\n")
                    f.write("=" * 80 + "\n\n")
                    for i, doc in enumerate(by_type['RawTranscript'], 1):
                        f.write(f"--- Transcript Chunk {i} ---\n")
                        f.write(doc['content'])
                        f.write("\n\n")
            
            print(f"   [OK] Exported Text: {text_file.name}")


def print_summary(documents: List[Dict]):
    """Print a summary of processed transcripts."""
    grouped = group_documents_by_file(documents)
    
    print("\n" + "=" * 80)
    print("PROCESSED TRANSCRIPTS SUMMARY")
    print("=" * 80)
    print(f"\nTotal transcript files: {len(grouped)}")
    print(f"Total documents: {len(documents)}")
    
    # Count by type
    type_counts = {}
    for doc in documents:
        artifact_type = doc['metadata'].get('artifact_type', 'RawTranscript')
        type_counts[artifact_type] = type_counts.get(artifact_type, 0) + 1
    
    print("\nDocuments by type:")
    for artifact_type, count in sorted(type_counts.items()):
        print(f"  {artifact_type}: {count}")
    
    # Per-file breakdown
    print("\n" + "-" * 80)
    print("Per-File Breakdown:")
    print("-" * 80)
    for file_name, docs in sorted(grouped.items()):
        print(f"\n📄 {file_name}")
        print(f"   Total documents: {len(docs)}")
        
        # Count by type for this file
        file_types = {}
        for doc in docs:
            artifact_type = doc['metadata'].get('artifact_type', 'RawTranscript')
            file_types[artifact_type] = file_types.get(artifact_type, 0) + 1
        
        for artifact_type, count in sorted(file_types.items()):
            print(f"   - {artifact_type}: {count}")
        
        # Show metadata
        if docs:
            meta = docs[0]['metadata']
            print(f"   Customer: {meta.get('customer', 'N/A')}")
            print(f"   Topics: {meta.get('topic', 'N/A')}")
            print(f"   Date: {meta.get('meeting_date', 'N/A')}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Inspect and export processed transcripts from knowledge base"
    )
    parser.add_argument(
        '--export-dir',
        type=str,
        default='./transcript_exports',
        help='Directory to save exported files (default: ./transcript_exports)'
    )
    parser.add_argument(
        '--format',
        type=str,
        choices=['json', 'text', 'both'],
        default='both',
        help='Export format (default: both)'
    )
    parser.add_argument(
        '--no-export',
        action='store_true',
        help='Only show summary, do not export files'
    )
    
    args = parser.parse_args()
    
    # Load documents
    documents = load_transcript_documents()
    
    if not documents:
        print("[WARNING] No transcript documents found in vectorstore")
        print("   Make sure you've processed transcripts first using:")
        print("   python scripts/process_transcripts_from_sharepoint.py")
        sys.exit(1)
    
    # Print summary
    print_summary(documents)
    
    # Export if requested
    if not args.no_export:
        export_transcripts(documents, args.export_dir, args.format)
        print(f"\n[OK] Export complete! Files saved to: {args.export_dir}")


if __name__ == "__main__":
    main()

