"""
CLI script for ingesting documents into Weaviate.

Supports ingestion from all sources: SharePoint, Jira, Blogs, Transcripts, Excel, Email.
"""

import sys
import os
import argparse
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.weaviate_ingestion import WeaviateIngestionPipeline
from app.weaviate_client import check_weaviate_health
from app.weaviate_schema import COLLECTIONS, get_source_type_for_collection

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_sharepoint_documents():
    """Load SharePoint documents per config: main site (ENABLE_SHAREPOINT_SOURCE), Presales, Limitations."""
    by_scope = load_sharepoint_documents_by_scope()
    documents = []
    for scope_docs in by_scope.values():
        documents.extend(scope_docs)
    logger.info("[SOURCE] SharePoint total documents loaded: %d", len(documents))
    return documents


def load_sharepoint_documents_by_scope():
    """
    Load SharePoint documents grouped by scope (doc360, presales, limitations).
    Each scope uses its own incremental tracker so enabling sources one-by-one
    does not mark other scopes as "deleted".
    Returns:
        Dict[str, List[Document]]: {"doc360": [...], "presales": [...], "limitations": [...]}
        Only includes keys for enabled sources; empty list if disabled.
    """
    from app.sharepoint_graph_extractor import extract_sharepoint_via_graph
    from app.helpers import (
        fetch_latest_sharepoint_presales,
        fetch_latest_sharepoint_limitations,
    )
    from config import (
        ENABLE_SHAREPOINT_SOURCE,
        ENABLE_SHAREPOINT_PRESALES_SOURCE,
        ENABLE_SHAREPOINT_LIMITATIONS_SOURCE,
    )

    by_scope = {}

    if ENABLE_SHAREPOINT_SOURCE:
        logger.info("[SOURCE] Loading SharePoint DOC360 (main site) documents...")
        by_scope["doc360"] = extract_sharepoint_via_graph()
        logger.info("[SOURCE] DOC360 loaded: %d documents", len(by_scope["doc360"]))
    else:
        logger.info("[SOURCE] Skipping DOC360 (ENABLE_SHAREPOINT_SOURCE=false)")
        by_scope["doc360"] = []

    if ENABLE_SHAREPOINT_PRESALES_SOURCE:
        logger.info("[SOURCE] Loading SharePoint Presales documents...")
        by_scope["presales"] = fetch_latest_sharepoint_presales(max_items=9999)
        logger.info("[SOURCE] Presales loaded: %d documents", len(by_scope["presales"]))
    else:
        logger.info("[SOURCE] Skipping Presales (ENABLE_SHAREPOINT_PRESALES_SOURCE=false)")
        by_scope["presales"] = []

    if ENABLE_SHAREPOINT_LIMITATIONS_SOURCE:
        logger.info("[SOURCE] Loading SharePoint Limitations documents...")
        by_scope["limitations"] = fetch_latest_sharepoint_limitations(max_items=9999)
        logger.info("[SOURCE] Limitations loaded: %d documents", len(by_scope["limitations"]))
    else:
        logger.info("[SOURCE] Skipping Limitations (ENABLE_SHAREPOINT_LIMITATIONS_SOURCE=false)")
        by_scope["limitations"] = []

    return by_scope


def load_jira_documents():
    """Load Jira documents. Returns [] if ENABLE_JIRA_SOURCE is false."""
    from config import ENABLE_JIRA_SOURCE
    if not ENABLE_JIRA_SOURCE:
        logger.info("[SOURCE] Skipping Jira (ENABLE_JIRA_SOURCE=false)")
        return []
    from app.jira_processor import JiraProcessor
    processor = JiraProcessor()
    logger.info("[SOURCE] Loading Jira tickets...")
    return processor.process_jira_content()


def load_blog_documents(force_full_backfill: bool = False):
    """
    Load blog documents from WordPress API.
    First run (no last_blog_post_date): full backfill via fetch_web_content.
    Later runs: incremental via fetch_latest_web_content(since_date=last_date).
    Pass force_full_backfill=True (e.g. --blog-full-backfill) to force full backfill.
    """
    from app.helpers import (
        fetch_latest_web_content,
        fetch_web_content,
        get_last_blog_post_date,
    )
    from config import WEB_SOURCE_URL

    last_date = None if force_full_backfill else get_last_blog_post_date()
    is_first_run = last_date is None

    if is_first_run:
        logger.info("[BLOG INGEST] Full backfill (first run or --blog-full-backfill)")
        documents = fetch_web_content(WEB_SOURCE_URL)
        if documents:
            logger.info("[BLOG INGEST] fetched_chunks=%d | mode=full", len(documents))
    else:
        logger.info("[BLOG INGEST] Incremental run → fetching posts after %s", last_date)
        documents = fetch_latest_web_content(WEB_SOURCE_URL, since_date=last_date)
        if documents:
            logger.info("[BLOG INGEST] fetched_chunks=%d | mode=incremental", len(documents))

    return documents or []


def load_transcript_documents():
    """Load transcript documents."""
    from scripts.process_transcripts_from_sharepoint import process_transcripts
    logger.info("[SOURCE] Loading transcripts...")
    docs, count = process_transcripts()
    return docs


def load_excel_documents():
    """Load Excel documents."""
    from app.excel_processor import process_excel_directory
    from config import EXCEL_SOURCE_DIR
    logger.info(f"[SOURCE] Loading Excel files from {EXCEL_SOURCE_DIR}...")
    return process_excel_directory(EXCEL_SOURCE_DIR)


def load_email_documents():
    """Load email documents."""
    from app.outlook_processor import process_outlook_content
    logger.info("[SOURCE] Loading email threads...")
    return process_outlook_content()


# Source loader mapping
SOURCE_LOADERS = {
    "sharepoint": load_sharepoint_documents,
    "jira": load_jira_documents,
    "blog": load_blog_documents,
    "transcript": load_transcript_documents,
    "excel": load_excel_documents,
    "email": load_email_documents,
}

def _latest_blog_post_date(documents):
    """Extract the latest post_date/created_at from blog chunk metadata (ISO string)."""
    latest = None
    for d in documents or []:
        meta = getattr(d, "metadata", None) or {}
        dt = meta.get("post_date") or meta.get("created_at")
        if dt and isinstance(dt, str) and dt.strip():
            if latest is None or (dt.strip() > latest):
                latest = dt.strip()
    return latest


# Collection mapping
SOURCE_TO_COLLECTION = {
    "sharepoint": "SharePointDocs",
    "jira": "JiraTickets",
    "blog": "Blogs",
    "transcript": "Transcripts",
    "excel": "Spreadsheets",
    "email": "EmailThreads",
}


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="Ingest documents into Weaviate collections"
    )
    parser.add_argument(
        "--source",
        type=str,
        choices=list(SOURCE_LOADERS.keys()),
        required=True,
        help="Source type to ingest from"
    )
    parser.add_argument(
        "--collection",
        type=str,
        choices=COLLECTIONS,
        help="Weaviate collection name (default: inferred from source)"
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        default=True,
        help="Enable incremental ingestion (default: True)"
    )
    parser.add_argument(
        "--no-incremental",
        dest="incremental",
        action="store_false",
        help="Disable incremental ingestion"
    )
    parser.add_argument(
        "--no-summaries",
        dest="enable_summaries",
        action="store_false",
        default=True,
        help="Disable summary generation"
    )
    parser.add_argument(
        "--no-dedup",
        dest="enable_deduplication",
        action="store_false",
        default=True,
        help="Disable deduplication"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode (don't insert into Weaviate)"
    )
    parser.add_argument(
        "--blog-full-backfill",
        action="store_true",
        help="(Blog source only) Force full backfill instead of incremental"
    )
    
    args = parser.parse_args()
    
    # Check Weaviate connection
    print("\n" + "="*60)
    print("Weaviate Document Ingestion")
    print("="*60 + "\n")
    
    if not args.dry_run:
        print("[*] Checking Weaviate connection...")
        if not check_weaviate_health():
            print("[!] ERROR: Weaviate is not available or not healthy")
            print("[!] Make sure Weaviate is running:")
            print("    docker-compose up -d weaviate")
            return 1
        print("[OK] Weaviate connection successful\n")
    
    # Determine collection
    collection_name = args.collection or SOURCE_TO_COLLECTION.get(args.source)
    if not collection_name:
        print(f"[!] ERROR: Could not determine collection for source '{args.source}'")
        return 1
    
    # Get source type
    source_type = get_source_type_for_collection(collection_name)
    
    print(f"[*] Source: {args.source}")
    print(f"[*] Collection: {collection_name}")
    print(f"[*] Source Type: {source_type}")
    print(f"[*] Incremental: {args.incremental}")
    print(f"[*] Summaries: {args.enable_summaries}")
    print(f"[*] Deduplication: {args.enable_deduplication}")
    print(f"[*] Dry Run: {args.dry_run}")
    print()
    
    # Load documents
    loader = SOURCE_LOADERS.get(args.source)
    if not loader:
        print(f"[!] ERROR: No loader found for source '{args.source}'")
        return 1
    
    sharepoint_by_scope = None
    try:
        print(f"[*] Loading documents from {args.source}...")
        if args.source == "blog":
            documents = load_blog_documents(force_full_backfill=getattr(args, "blog_full_backfill", False))
        elif args.source == "sharepoint":
            sharepoint_by_scope = load_sharepoint_documents_by_scope()
            documents = []
            for scope, scope_docs in sharepoint_by_scope.items():
                documents.extend(scope_docs)
                if scope_docs:
                    print(f"[OK] Scope '{scope}': {len(scope_docs)} documents")
        else:
            documents = loader()
        if args.source != "sharepoint":
            print(f"[OK] Loaded {len(documents)} documents (chunks)")
        elif documents:
            print(f"[OK] SharePoint total documents loaded: {len(documents)}")
        if args.source == "blog" and documents:
            doc_ids = set()
            for d in documents:
                meta = getattr(d, "metadata", None) or {}
                doc_id = meta.get("doc_id") or meta.get("post_slug")
                if doc_id:
                    doc_ids.add(doc_id)
            print(f"[OK] Unique blogs (by doc_id): {len(doc_ids)}")
            for bid in sorted(doc_ids)[:20]:
                print(f"     - {bid}")
            if len(doc_ids) > 20:
                print(f"     ... and {len(doc_ids) - 20} more")
        print()
        
        if not documents:
            if args.source == "sharepoint":
                print("[WARNING] No SharePoint documents to ingest (enable at least one scope in .env)")
            elif args.source == "jira":
                print("[WARNING] No Jira documents to ingest (set ENABLE_JIRA_SOURCE=true in .env to enable)")
            else:
                print("[WARNING] No documents to ingest")
            return 0

    except Exception as e:
        print(f"[!] ERROR: Failed to load documents: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Initialize pipeline (disable deletions for blog incremental to avoid partial-fetch deletes)
    allow_deletions = not (args.source == "blog" and not getattr(args, "blog_full_backfill", False))
    pipeline = WeaviateIngestionPipeline(
        enable_summaries=args.enable_summaries,
        enable_deduplication=args.enable_deduplication,
        enable_incremental=args.incremental,
        allow_deletions=allow_deletions,
    )
    
    # Run ingestion
    if args.dry_run:
        print("[DRY RUN] Would ingest documents (skipping actual insertion)")
        if args.source == "sharepoint" and sharepoint_by_scope:
            for scope, scope_docs in sharepoint_by_scope.items():
                if scope_docs:
                    print(f"[DRY RUN] Scope '{scope}': {len(scope_docs)} documents")
        else:
            print(f"[DRY RUN] Documents: {len(documents)}")
        return 0

    try:
        if args.source == "sharepoint" and sharepoint_by_scope:
            # Ingest each scope separately so each uses its own tracker (sharepoint_doc360, sharepoint_presales, sharepoint_limitations)
            combined_success = True
            total_inserted = 0
            total_processed = 0
            total_failed = 0
            all_failed_keys = []
            all_errors = []
            for scope, scope_docs in sharepoint_by_scope.items():
                if not scope_docs:
                    continue
                tracking_source_type = f"sharepoint_{scope}"
                print(f"[*] Ingesting SharePoint scope '{scope}' (tracker: {tracking_source_type})...")
                scope_result = pipeline.ingest_from_source(
                    source_type=tracking_source_type,
                    documents=scope_docs,
                    collection_name=collection_name,
                    incremental=args.incremental,
                )
                combined_success = combined_success and scope_result.success
                total_inserted += scope_result.chunks_inserted or 0
                total_processed += scope_result.chunks_processed or 0
                total_failed += scope_result.chunks_failed or 0
                all_failed_keys.extend(getattr(scope_result, "failed_chunk_keys", []) or [])
                all_errors.extend(getattr(scope_result, "errors", []) or [])
                if scope_result.errors:
                    for err in scope_result.errors[:3]:
                        print(f"     [!] {err}")
            # Build a result-like object for reporting
            class _IngestResult:
                pass
            result = _IngestResult()
            result.success = combined_success
            result.chunks_inserted = total_inserted
            result.chunks_processed = total_processed
            result.chunks_failed = total_failed
            result.processing_time_seconds = 0
            result.failed_chunk_keys = all_failed_keys
            result.errors = all_errors
        else:
            print("[*] Starting ingestion...")
            result = pipeline.ingest_from_source(
                source_type=source_type,
                documents=documents,
                collection_name=collection_name,
                incremental=args.incremental
            )

        # Print results
        print("\n" + "="*60)
        print("INGESTION RESULTS")
        print("="*60)
        print(f"Success: {result.success}")
        print(f"Chunks Processed: {result.chunks_processed}")
        print(f"Chunks Inserted: {result.chunks_inserted}")
        print(f"Chunks Failed: {result.chunks_failed}")
        print(f"Processing Time: {result.processing_time_seconds:.2f}s")
        
        if result.failed_chunk_keys:
            print(f"\nFailed Chunk Keys ({len(result.failed_chunk_keys)}):")
            for key in result.failed_chunk_keys[:10]:  # Show first 10
                print(f"  - {key}")
            if len(result.failed_chunk_keys) > 10:
                print(f"  ... and {len(result.failed_chunk_keys) - 10} more")
        
        if result.errors:
            print(f"\nErrors ({len(result.errors)}):")
            for error in result.errors[:5]:  # Show first 5
                print(f"  - {error}")
            if len(result.errors) > 5:
                print(f"  ... and {len(result.errors) - 5} more")
        
        # Print report
        print("\n" + "="*60)
        print("INGESTION REPORT")
        print("="*60)
        print(pipeline.get_report())

        # Persist blog metadata after successful ingest (for next incremental run)
        if args.source == "blog" and result.success and documents:
            from app.helpers import save_blog_metadata
            latest_date = _latest_blog_post_date(documents)
            if latest_date:
                # Store YYYY-MM-DD only so WordPress after= filter is always applied correctly
                last_date_ymd = latest_date[:10] if len(latest_date) >= 10 else latest_date
                save_blog_metadata({
                    "last_blog_post_date": last_date_ymd,
                    "last_run_at": __import__("datetime").datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "total_chunks_ingested": result.chunks_inserted or 0,
                })
                logger.info("[BLOG INGEST] Saved last_blog_post_date=%s for next incremental run", last_date_ymd)
        
        return 0 if result.success else 1
        
    except Exception as e:
        print(f"[!] ERROR: Ingestion failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # Close Weaviate connection to avoid ResourceWarning / memory leaks
        try:
            from app.weaviate_client import reset_weaviate_client
            reset_weaviate_client()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
