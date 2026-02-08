# -*- coding: utf-8 -*-
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.endpoints import router as chat_router
from app.routes.suggested_questions import router as questions_router
from app.mongodb_memory import close_mongodb_connection
from app.weaviate_client import reset_weaviate_client
import uvicorn
import asyncio
from contextlib import asynccontextmanager
import os
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import atexit
import pytz

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Initialize scheduler for Jira sync with timezone support
# Get timezone from config or use system local timezone
from config import SCHEDULER_TIMEZONE
scheduler_timezone = None

if SCHEDULER_TIMEZONE:
    try:
        scheduler_timezone = pytz.timezone(SCHEDULER_TIMEZONE)
        logger.info(f"[SCHEDULER] Using configured timezone: {SCHEDULER_TIMEZONE}")
    except Exception as e:
        logger.warning(f"[SCHEDULER] Invalid timezone '{SCHEDULER_TIMEZONE}', using UTC. Error: {e}")
        scheduler_timezone = pytz.UTC
        logger.info(f"[SCHEDULER] Defaulting to UTC timezone")
else:
    # Use UTC by default (can be overridden with SCHEDULER_TIMEZONE env var)
    # Common timezones: 'America/New_York', 'America/Los_Angeles', 'Asia/Kolkata', 'Europe/London'
    scheduler_timezone = pytz.UTC
    logger.info(f"[SCHEDULER] Using UTC timezone (set SCHEDULER_TIMEZONE env var to change, e.g., 'America/New_York')")

scheduler = BackgroundScheduler(timezone=scheduler_timezone)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan events."""
    # Startup
    from app.mongodb_memory import mongodb_memory
    try:
        logger.info("[STARTUP] Initializing MongoDB memory storage...")
        await mongodb_memory.connect()
        logger.info("[STARTUP] ✅ MongoDB memory storage initialized successfully")
        
        # Auto-seed suggested questions if database is empty
        await auto_seed_questions()
    except Exception as e:
        logger.error(f"[STARTUP] ❌ Failed to initialize MongoDB memory storage: {e}", exc_info=True)
    
    # Log Weaviate vectorstore collection counts at startup
    try:
        from app.weaviate_client import get_weaviate_client
        from app.weaviate_schema import COLLECTIONS

        client = get_weaviate_client()
        if client is not None:
            logger.info("[STARTUP] Loading existing vectorstore...")
            total_docs = 0
            for col_name in COLLECTIONS:
                try:
                    if client.collections.exists(col_name):
                        coll = client.collections.get(col_name)
                        agg = coll.aggregate.over_all(total_count=True)
                        count = int(agg.total_count) if getattr(agg, "total_count", None) is not None else 0
                        total_docs += count
                        logger.info(f"[STARTUP]   {col_name}: {count} documents")
                    else:
                        logger.info(f"[STARTUP]   {col_name}: 0 documents (collection not found)")
                except Exception as e:
                    logger.warning(f"[STARTUP]   {col_name}: error reading count ({e})")
            logger.info(f"[STARTUP] Total documents: {total_docs}")
        else:
            logger.warning("[STARTUP] Weaviate not available, skipping vectorstore load summary")
    except Exception as e:
        logger.warning(f"[STARTUP] Failed to log vectorstore counts: {e}")

    # Start scheduler for weekly reports (and future jobs)
    try:
        from config import WEEKLY_REPORT_ENABLED, WEEKLY_REPORT_SEND_HOUR, WEEKLY_REPORT_SEND_MINUTE
        
        if WEEKLY_REPORT_ENABLED:
            from app.weekly_reports_scheduler import scheduled_weekly_reports_sync
            
            # Use the same timezone as scheduler initialization
            timezone_str = SCHEDULER_TIMEZONE if SCHEDULER_TIMEZONE else "system local timezone"
            scheduler.add_job(
                func=scheduled_weekly_reports_sync,
                trigger=CronTrigger(day_of_week='mon', hour=WEEKLY_REPORT_SEND_HOUR, minute=WEEKLY_REPORT_SEND_MINUTE, timezone=scheduler_timezone),
                id='weekly_report_job',
                name='Weekly Team Leaderboard Report',
                replace_existing=True
            )
            scheduler.start()
            logger.info(f"[STARTUP] ✅ Weekly report scheduler started (runs every Monday at {WEEKLY_REPORT_SEND_HOUR:02d}:{WEEKLY_REPORT_SEND_MINUTE:02d} {timezone_str})")
        else:
            logger.info("[STARTUP] Weekly report scheduler is disabled (WEEKLY_REPORT_ENABLED=false)")
    except Exception as e:
        logger.error(f"[STARTUP] ❌ Failed to start weekly report scheduler: {e}", exc_info=True)
    
    yield

    # Shutdown
    try:
        logger.info("[SHUTDOWN] Stopping scheduler...")
        scheduler.shutdown()
        logger.info("[SHUTDOWN] ✅ Scheduler stopped")
    except Exception as e:
        logger.warning(f"[SHUTDOWN] ⚠️  Error stopping scheduler: {e}")
    
    try:
        logger.info("[SHUTDOWN] Closing MongoDB memory storage...")
        await close_mongodb_connection()
        logger.info("[SHUTDOWN] ✅ MongoDB memory storage closed")
    except Exception as e:
        logger.warning(f"[SHUTDOWN] ⚠️  Error closing MongoDB memory storage: {e}")

    # Close Weaviate client to avoid unclosed socket warnings on restart
    try:
        logger.info("[SHUTDOWN] Closing Weaviate client...")
        reset_weaviate_client()
        logger.info("[SHUTDOWN] ✅ Weaviate client closed")
    except Exception as e:
        logger.warning(f"[SHUTDOWN] ⚠️  Error closing Weaviate client: {e}")


async def auto_seed_questions():
    """Automatically seed suggested questions if database is empty"""
    try:
        from app.mongodb_memory import mongodb_memory
        from datetime import datetime
        
        logger.info("[SEED] Checking if suggested questions need to be seeded...")
        
        if mongodb_memory.database is None:
            logger.warning("[SEED] ⚠️  Skipping auto-seed: database not connected")
            return
        
        db = mongodb_memory.database
        collection = db.suggested_questions
        
        # Check if questions already exist
        existing_count = await collection.count_documents({})
        
        if existing_count > 0:
            logger.info(f"[SEED] ✅ Suggested questions already exist ({existing_count} questions in database)")
            logger.debug(f"[SEED] Skipping auto-seed - questions already present")
            return
        
        logger.info("[SEED] 📦 No suggested questions found. Starting auto-seed...")
        
        # Import seed data from the seed script
        from scripts.seed_suggested_questions import INITIAL_QUESTIONS
        
        logger.info(f"[SEED] Imported {len(INITIAL_QUESTIONS)} questions from seed script")
        
        seeded_count = 0
        for q_data in INITIAL_QUESTIONS:
            question_doc = {
                **q_data,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "display_count": 0,
                "click_count": 0,
                "click_rate": 0.0,
                "target_user_roles": [],
                "created_by": "system_auto_seed"
            }
            await collection.insert_one(question_doc)
            seeded_count += 1
            logger.debug(f"[SEED]   ✓ Added: {q_data['question_text'][:50]}...")
        
        # Verify seeding
        final_count = await collection.count_documents({})
        logger.info(f"[SEED] ✅ Successfully seeded {seeded_count} suggested questions")
        logger.info(f"[SEED] 📊 Total questions in database: {final_count}")
        
        # Log breakdown by category
        from collections import Counter
        category_counts = Counter()
        async for q in collection.find({}, {"category": 1}):
            category_counts[q.get("category", "unknown")] += 1
        logger.info(f"[SEED] 📂 Questions by category: {dict(category_counts)}")
        
    except Exception as e:
        logger.error(f"[SEED] ❌ Failed to auto-seed questions: {type(e).__name__}: {e}", exc_info=True)
        logger.warning("[SEED] Application will continue with default fallback questions")

app = FastAPI(lifespan=lifespan)

# ✅ FIX: CORS configuration for session cookies
# When allow_credentials=True, you CANNOT use allow_origins=["*"]
# Must specify exact origins
allowed_origins = [
    "http://localhost:3000",  # Next.js dev server
    "http://127.0.0.1:3000",  # Alternative localhost
    "http://localhost:3001",  # Alternative port
    "https://ai.cloudfuze.com",  # Production
]

# Add development origins from environment if set
dev_origin = os.getenv("FRONTEND_URL")
if dev_origin and dev_origin not in allowed_origins:
    allowed_origins.append(dev_origin)

logger.info(f"[CORS] Allowed origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,  # ✅ FIX: Specific origins (required for credentials)
    allow_credentials=True,  # ⭐ REQUIRED for session cookies
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)

# Add a simple health check endpoint
@app.get("/")
async def root():
    return {"message": "CF Chatbot API is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "Server is running"}

app.include_router(chat_router)
app.include_router(questions_router)

# Mount static directories for images and other assets
app.mount("/images", StaticFiles(directory="images"), name="images")
# Only mount /data if the directory exists
if os.path.exists("data"):
    app.mount("/data", StaticFiles(directory="data"), name="data")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)