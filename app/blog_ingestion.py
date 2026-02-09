"""
Run blog ingestion into Weaviate Blogs collection.

Used by the admin UI "Trigger Blog Poll" and by the CLI (scripts/ingest_to_weaviate.py --source blog).
Fetches new posts from the web, chunks, embeds, and inserts into Weaviate.
"""

import logging
from datetime import datetime
from typing import Any

from app.helpers import (
    fetch_latest_web_content,
    fetch_web_content,
    get_last_blog_post_date,
    latest_blog_post_date_from_documents,
    latest_blog_post_info_from_documents,
    load_blog_metadata,
    oldest_blog_post_date_from_documents,
    save_blog_metadata,
)
from app.weaviate_ingestion import WeaviateIngestionPipeline

logger = logging.getLogger(__name__)


def run_blog_ingestion(force_full_backfill: bool = False) -> dict[str, Any]:
    """
    Load blog documents from the web, ingest into Weaviate Blogs collection, and persist metadata.

    Args:
        force_full_backfill: If True, fetch all posts; otherwise incremental (posts after last_blog_post_date).

    Returns:
        Dict with: success (bool), chunks_inserted (int), chunks_processed (int), error (str or None).
    """
    from config import WEB_SOURCE_URL

    result: dict[str, Any] = {
        "success": False,
        "chunks_inserted": 0,
        "chunks_processed": 0,
        "error": None,
    }

    try:
        last_date = None if force_full_backfill else get_last_blog_post_date()
        is_first_run = last_date is None

        if is_first_run:
            logger.info("[BLOG INGEST] Full backfill (first run or force_full_backfill)")
            documents = fetch_web_content(WEB_SOURCE_URL)
            if documents:
                logger.info("[BLOG INGEST] fetched_chunks=%d | mode=full", len(documents))
        else:
            logger.info("[BLOG INGEST] Incremental run → fetching posts after %s", last_date)
            documents = fetch_latest_web_content(WEB_SOURCE_URL, since_date=last_date)
            if documents:
                logger.info("[BLOG INGEST] fetched_chunks=%d | mode=incremental", len(documents))

        documents = documents or []

        # Pipeline: incremental blog = no deletions (append-only)
        pipeline = WeaviateIngestionPipeline(
            enable_summaries=True,
            enable_deduplication=True,
            enable_incremental=True,
            allow_deletions=False,
        )

        ingest_result = pipeline.ingest_from_source(
            source_type="blog",
            documents=documents,
            collection_name="Blogs",
            incremental=True,
        )

        result["success"] = ingest_result.success
        result["chunks_inserted"] = ingest_result.chunks_inserted or 0
        result["chunks_processed"] = ingest_result.chunks_processed or 0

        if result["success"] and documents:
            meta = load_blog_metadata()
            latest_date = latest_blog_post_date_from_documents(documents)
            latest_info = latest_blog_post_info_from_documents(documents)
            if latest_date:
                last_date_ymd = latest_date[:10] if len(latest_date) >= 10 else latest_date
                meta["last_blog_post_date"] = last_date_ymd
                meta["last_run_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                meta["total_chunks_ingested"] = result["chunks_inserted"]
                meta["last_blog_post_url"] = latest_info.get("post_url")
                meta["last_blog_post_title"] = latest_info.get("post_title")
                # Cumulative unique posts (each doc = one post)
                meta["total_posts_ingested_cumulative"] = meta.get("total_posts_ingested_cumulative", 0) + len(documents)
                # Oldest post date: only set on full backfill (we have the full set; incremental batch would give wrong "oldest")
                if is_first_run and not meta.get("oldest_blog_post_date"):
                    oldest_date = oldest_blog_post_date_from_documents(documents)
                    if oldest_date:
                        meta["oldest_blog_post_date"] = oldest_date[:10] if len(oldest_date) >= 10 else oldest_date
                save_blog_metadata(meta)
                logger.info("[BLOG INGEST] Saved last_blog_post_date=%s for next incremental run", last_date_ymd)

        if ingest_result.errors:
            result["error"] = "; ".join(ingest_result.errors[:3])
            if len(ingest_result.errors) > 3:
                result["error"] += f" (+{len(ingest_result.errors) - 3} more)"

    except Exception as e:
        logger.exception("[BLOG INGEST] Failed: %s", e)
        result["error"] = str(e)

    return result
