# -*- coding: utf-8 -*-
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.endpoints import router as chat_router
from app.routes.suggested_questions import router as questions_router
from app.routes.jira_sync import router as jira_sync_router
from app.mongodb_memory import close_mongodb_connection
import uvicorn
import asyncio
from contextlib import asynccontextmanager
import os
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import atexit

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Initialize scheduler for Jira sync
scheduler = BackgroundScheduler()

def scheduled_jira_sync():
    """
    Background job for scheduled Jira sync.
    Runs daily at 2 AM to sync new/updated tickets.
    """
    try:
        from app.jira_vectorstore import add_jira_tickets_incrementally
        from app.jira_sync_tracker import update_last_sync_time
        
        logger.info("[SCHEDULER] 🔄 Starting scheduled Jira sync...")
        
        result = add_jira_tickets_incrementally()
        
        if result:
            total_docs = result._collection.count()
            logger.info(f"[SCHEDULER] ✅ Sync completed successfully. Total documents: {total_docs}")
        else:
            logger.info("[SCHEDULER] ℹ️  No new tickets to sync")
            
    except Exception as e:
        error_msg = str(e)
        logger.error(f"[SCHEDULER] ❌ Sync failed: {error_msg}", exc_info=True)
        
        # Record failure for admin alerts
        try:
            from app.jira_sync_tracker import update_last_sync_time
            update_last_sync_time(status="failed", documents_added=0, error_message=error_msg)
        except:
            pass

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
    
    # Start Jira sync scheduler
    try:
        sync_hour = int(os.getenv("JIRA_SYNC_HOUR", "2"))  # Default: 2 AM
        
        scheduler.add_job(
            func=scheduled_jira_sync,
            trigger=CronTrigger(hour=sync_hour, minute=0),  # Daily at specified hour
            id='jira_sync_job',
            name='Daily Jira Ticket Sync',
            replace_existing=True
        )
        scheduler.start()
        logger.info(f"[STARTUP] ✅ Jira sync scheduler started (runs daily at {sync_hour}:00 AM)")
    except Exception as e:
        logger.error(f"[STARTUP] ❌ Failed to start Jira sync scheduler: {e}", exc_info=True)
    
    yield
    
    # Shutdown
    try:
        logger.info("[SHUTDOWN] Stopping Jira sync scheduler...")
        scheduler.shutdown()
        logger.info("[SHUTDOWN] ✅ Jira sync scheduler stopped")
    except Exception as e:
        logger.warning(f"[SHUTDOWN] ⚠️  Error stopping scheduler: {e}")
    
    try:
        logger.info("[SHUTDOWN] Closing MongoDB memory storage...")
        await close_mongodb_connection()
        logger.info("[SHUTDOWN] ✅ MongoDB memory storage closed")
    except Exception as e:
        logger.warning(f"[SHUTDOWN] ⚠️  Error closing MongoDB memory storage: {e}")


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
app.include_router(jira_sync_router)

# Mount static directories for images and other assets
app.mount("/images", StaticFiles(directory="images"), name="images")
# Only mount /data if the directory exists
if os.path.exists("data"):
    app.mount("/data", StaticFiles(directory="data"), name="data")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)