# -*- coding: utf-8 -*-
"""
Blog Polling Scheduler

Scheduled task that automatically polls for new blog posts and ingests them into Weaviate.
"""

import logging
from datetime import datetime
from app.blog_ingestion import run_blog_ingestion

logger = logging.getLogger(__name__)


def scheduled_blog_poll():
    """
    Background job for scheduled blog polling.
    Runs at the configured interval to check for new blog posts and ingest them.
    
    This is a synchronous function that can be called by APScheduler.
    """
    try:
        logger.info("="*70)
        logger.info("[BLOG POLL] 🔄 Starting scheduled blog polling...")
        logger.info(f"[BLOG POLL] Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("="*70)
        
        # Run blog ingestion (incremental mode)
        result = run_blog_ingestion(force_full_backfill=False)
        
        if result.get("success"):
            chunks_inserted = result.get("chunks_inserted", 0)
            chunks_processed = result.get("chunks_processed", 0)
            
            logger.info("="*70)
            logger.info(f"[BLOG POLL] ✅ Blog polling completed successfully")
            logger.info(f"[BLOG POLL] 📊 Processed: {chunks_processed} chunks")
            logger.info(f"[BLOG POLL] ➕ Inserted: {chunks_inserted} new chunks")
            logger.info("="*70)
        else:
            error = result.get("error", "Unknown error")
            logger.warning("="*70)
            logger.warning(f"[BLOG POLL] ⚠️  Blog polling completed with errors: {error}")
            logger.warning("="*70)
    
    except Exception as e:
        error_msg = str(e)
        logger.error(f"[BLOG POLL] ❌ Blog polling failed: {error_msg}", exc_info=True)
