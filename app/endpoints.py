# -*- coding: utf-8 -*-
from fastapi import APIRouter, Request, HTTPException, Header, Depends, Query, Path, status
from fastapi.responses import PlainTextResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Tuple
import uuid
import httpx
import os
import json
import base64
import asyncio
import re
import logging
from datetime import datetime, timezone

# Configure logging
logger = logging.getLogger(__name__)

from app.llm_factory import get_llm
from app.weaviate_client import get_weaviate_client
from app.weaviate_retriever import retrieve_from_weaviate
from app.chat_handlers import handle_chat, handle_chat_stream, handle_chat_retry_stream
from app.mongodb_memory import (
    get_response_versions,
    set_current_version,
    get_max_version,
    mark_all_versions_not_current,
    mongodb_memory,
    add_to_conversation, get_conversation_context, get_user_chat_history, 
    clear_user_chat_history, save_session, get_all_sessions, get_user_sessions, 
    get_session_by_id, create_shared_chat, get_shared_chat,
    update_user_profile, get_user_profile, get_user_statistics, get_rankers_by_date,
    save_message, get_last_messages
)
from app.helpers import strip_markdown, preserve_markdown, load_blog_metadata, get_blog_tracking_count
from app.blog_ingestion import run_blog_ingestion
from app.langfuse_integration import langfuse_tracker
from app.auth import verify_user_access, require_admin, require_restricted_admin
from app.user_data import get_user_job_title
from app.models.teams import TEAMS_STRUCTURE, get_team_by_name
from config import (
    SYSTEM_PROMPT, MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, MICROSOFT_TENANT,
    ENABLE_INTENT_CLASSIFICATION, ENABLE_QUERY_EXPANSION, ENABLE_CONTEXT_COMPRESSION,
    DENSE_RETRIEVAL_K, BM25_RETRIEVAL_K, FINAL_RETRIEVAL_K,
    DENSE_WEIGHT, BM25_WEIGHT, RERANKER_WEIGHT,
    PRIMARY_KB_PRIORITY_BOOST, SECONDARY_KB_PRIORITY_BOOST, TRANSCRIPT_ARTIFACT_BOOST,
    PRIMARY_KB_TIER, TRANSCRIPT_KB_TIER,
    # Retry Mode Configuration (Teammate's Feature)
    RETRY_ATTEMPT_1_K_DENSE, RETRY_ATTEMPT_1_K_BM25, RETRY_ATTEMPT_1_K_FINAL,
    RETRY_ATTEMPT_2_K_DENSE, RETRY_ATTEMPT_2_K_BM25, RETRY_ATTEMPT_2_K_FINAL,
    RETRY_ATTEMPT_3_PLUS_K_DENSE, RETRY_ATTEMPT_3_PLUS_K_BM25, RETRY_ATTEMPT_3_PLUS_K_FINAL,
    RETRY_DENSE_WEIGHT, RETRY_BM25_WEIGHT, RETRY_FORCE_EXPANSION, RETRY_SCORE_THRESHOLD_ADJUSTMENT,
    ENABLE_ANSWER_QUALITY_CHECK, ANSWER_QUALITY_LLM_TEMPERATURE,
    # Intelligent Routing Configuration (Your Feature)
    ENABLE_INTELLIGENT_ROUTING, ROUTING_TOTAL_BUDGET, ROUTING_FINAL_K,
    ROUTING_MIN_CONFIDENCE, ROUTING_ENABLE_DEDUPLICATION,
    # Context Synthesis Configuration
    USE_CONTEXT_SYNTHESIS, SYNTHESIS_MAX_CONTEXT_LENGTH, SYNTHESIS_MAX_OUTPUT_LENGTH, SYNTHESIS_TEMPERATURE
)
from config import (
    BLOG_POLLING_ENABLED,
    BLOG_POLLING_INTERVAL,
    BLOG_LAST_POLL_FILE,
    WEB_SOURCE_URL,
    ENABLE_WEB_SOURCE,
)
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.documents import Document
import time
from contextlib import suppress
from collections import Counter, defaultdict


router = APIRouter()


# ============================================================================
# AUTHENTICATION MIDDLEWARE - Verify Microsoft Access Tokens
# ============================================================================

def decode_unsafe_jwt(token: str) -> Optional[dict]:
    """Decode JWT payload without verifying signature (fallback for dev)."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        
        # Decode payload
        payload = parts[1]
        # Fix padding
        payload += "=" * ((4 - len(payload) % 4) % 4)
        
        decoded_bytes = base64.urlsafe_b64decode(payload)
        decoded_str = decoded_bytes.decode("utf-8")
        return json.loads(decoded_str)
    except Exception as e:
        print(f"[AUTH] Failed to decode token locally: {e}")
        return None

async def require_auth(
    request: Request,
    authorization: Optional[str] = Header(None)
) -> dict:
    """
    ✅ NEW: Session-based authentication (no Graph API calls on every request).
    
    Priority:
    1. Session cookie (preferred - no Graph API call)
    2. Bearer token (legacy fallback - calls Graph API)
    
    Can be disabled for testing by setting DISABLE_AUTH_FOR_TESTING=true in .env
    """
    import os
    
    # Check if auth is disabled for testing
    if os.getenv("DISABLE_AUTH_FOR_TESTING", "false").lower() == "true":
        logger.info("[AUTH] Authentication DISABLED for testing")
        return {
            "user_id": "test_user",
            "name": "Test User",
            "email": "test@example.com"
        }
    
    # ✅ FIX 1: Always define session_id first (prevents UnboundLocalError)
    session_id = request.cookies.get("session_id")
    
    # PRIORITY 1: Try session-based auth (no Graph API call)
    if session_id:
        try:
            from app.session_store import session_store
            await session_store.connect()
            
            session = await session_store.get_session(session_id)
            
            if session:
                # ✅ STRICT IDENTITY: Validate session has required fields
                user_email = session.get("user_email", "")
                user_id = session.get("user_id", "")
                user_name = session.get("user_name", "")
                
                if not user_email or not user_email.strip():
                    logger.error(f"[AUTH] Session {session_id[:8]}... has invalid email, rejecting")
                    raise HTTPException(
                        status_code=401,
                        detail="Invalid session: missing user email"
                    )
                
                # ✅ IDENTITY RULE: Ensure user_id is email (migrate old sessions)
                if user_id != user_email.lower().strip():
                    logger.warning(f"[AUTH] Session user_id mismatch: {user_id} != {user_email}, using email")
                    user_id = user_email.lower().strip()
                
                # Check if token needs refresh (non-blocking check)
                token_expires_at = session.get("token_expires_at")
                if token_expires_at and isinstance(token_expires_at, datetime):
                    from datetime import timedelta
                    now = datetime.utcnow()
                    margin = timedelta(minutes=5)
                    
                    if token_expires_at - now < margin:
                        # Token expiring soon - log for background refresh
                        logger.info(f"[AUTH] Token expiring soon for session {session_id[:8]}... (will refresh on next request)")
                
                logger.debug(f"[AUTH] User authenticated via session: {user_email}")
                return {
                    "user_id": user_id,  # ✅ Always email
                    "email": user_email,
                    "name": user_name if user_name else user_email.split("@")[0]
                }
        except Exception as e:
            logger.warning(f"[AUTH] Session validation failed: {e}, falling back to token auth")
    
    # ✅ FIX: If no session, return proper 401 (not crash)
    if not session_id:
        logger.debug("[AUTH] No session_id cookie found")
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: No active session. Please log in."
        )
    
    # PRIORITY 2: Fallback to token-based auth (legacy - for backward compatibility during migration)
    # ⚠️ NOTE: This is temporary - remove once all clients use sessions
    if authorization and authorization.startswith("Bearer "):
        logger.warning("[AUTH] Using legacy token-based auth (should migrate to sessions)")
        access_token = authorization.replace("Bearer ", "")
        
        # Verify token with Microsoft Graph API (ONLY as fallback)
        try:
            max_retries = 3
            retry_delay = 1.0
            
            async with httpx.AsyncClient() as client:
                for attempt in range(max_retries):
                    try:
                        graph_response = await client.get(
                            "https://graph.microsoft.com/v1.0/me",
                            headers={"Authorization": f"Bearer {access_token}"},
                            timeout=15.0
                        )
                        
                        if graph_response.status_code == 200:
                            user_info = graph_response.json()
                            user_email = user_info.get("mail") or user_info.get("userPrincipalName", "")
                            
                            # ✅ STRICT IDENTITY: Email is mandatory
                            if not user_email or not user_email.strip():
                                logger.error("[AUTH] Token auth failed: No email in Graph response")
                                raise HTTPException(
                                    status_code=401,
                                    detail="Authentication failed: email missing"
                                )
                            
                            if not user_email.endswith("@cloudfuze.com"):
                                raise HTTPException(
                                    status_code=403,
                                    detail="Forbidden: Only CloudFuze company accounts are allowed."
                                )
                            
                            # ✅ IDENTITY RULE: Use email as user_id
                            user_id = user_email.lower().strip()
                            user_name = user_info.get("displayName", "")
                            if not user_name or not user_name.strip():
                                user_name = user_email.split("@")[0].replace(".", " ").title()
                            
                            logger.info(f"[AUTH] User authenticated via token (legacy): {user_email}")
                            return {
                                "user_id": user_id,  # ✅ Always email
                                "email": user_email,
                                "name": user_name
                            }
                        
                        if graph_response.status_code == 401:
                            break  # Token invalid, don't retry
                        
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                            continue
                            
                    except httpx.HTTPError as e:
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                            continue
                        break
        except Exception as e:
            logger.error(f"[AUTH] Token verification error: {e}")
        
        # ❌ REMOVED: Unsafe JWT decoding fallback (security risk in production)
        # This was causing inconsistent auth behavior
        # Production should NEVER use unsafe token decoding
        is_development = os.getenv("ENVIRONMENT", "production").lower() == "development"
        
        if is_development:
            # Only allow unsafe decoding in development
            logger.warning("[AUTH] Development mode: Attempting unsafe JWT decoding (NOT for production)")
            claims = decode_unsafe_jwt(access_token)
            
            if claims:
                user_email = claims.get("email") or claims.get("upn") or claims.get("unique_name")
                
                # ✅ STRICT IDENTITY: Email is mandatory - fail if missing
                if not user_email or not user_email.strip():
                    logger.error("[AUTH] Unsafe JWT fallback failed: No email in claims")
                    raise HTTPException(
                        status_code=401,
                        detail="Authentication failed: email missing"
                    )
                
                if not user_email.endswith("@cloudfuze.com"):
                    raise HTTPException(
                        status_code=403,
                        detail="Forbidden: Only CloudFuze company accounts are allowed."
                    )
                
                # ✅ IDENTITY RULE: Use email as user_id (never oid/sub)
                user_id = user_email.lower().strip()
                user_name = claims.get("name") or claims.get("given_name", "")
                if not user_name or not user_name.strip():
                    user_name = user_email.split("@")[0].replace(".", " ").title()
                
                logger.warning(f"[AUTH] ⚠️ DEV FALLBACK: User authenticated via unsafe JWT: {user_email}")
                return {
                    "user_id": user_id,  # ✅ Always email
                    "email": user_email,
                    "name": user_name
                }
    
    # If all fails, raise 401
    raise HTTPException(
        status_code=401,
        detail="Unauthorized: No valid session or token. Please log in again."
    )


class ChatRequest(BaseModel):
    question: str
    user_id: str = None
    session_id: str = None  # Keep for backward compatibility
    user_name: str = None  # User's display name
    user_email: str = None  # User's email

class FeedbackRequest(BaseModel):
    trace_id: str
    rating: str  # "thumbs_up" or "thumbs_down"
    comment: str = None
    categories: list = []  # List of feedback categories (e.g., ["Not factually correct", "Being lazy"])

@router.post("/chat")
async def chat(request: Request, auth_user: dict = Depends(require_auth)):
    """Chat endpoint: returns full answer from RAG (Weaviate + LangGraph). PROTECTED - requires valid authentication."""
    data = await request.json()
    question = data.get("question", "")
    session_id = data.get("session_id", str(uuid.uuid4()))
    
    # SECURITY: Check if trying to modify a read-only (others') session
    if session_id and isinstance(session_id, str) and session_id.startswith('user_chat_'):
        print(f"[SECURITY] Attempted to send message to read-only session: {session_id}")
        return {
            "error": "Cannot send messages to read-only chats. Use 'Continue in thread' to create an editable copy.",
            "status": 403
        }
    
    # Use VERIFIED user info from auth token, NOT from request body
    user_id = auth_user["user_id"]
    user_name = auth_user["name"]
    user_email = auth_user["email"]

    # Use user_id if provided, otherwise fall back to session_id for backward compatibility
    conversation_id = user_id if user_id else session_id

    # Antigravity: delegate to shared handler (stub until LangGraph is wired in step 5)
    answer, trace_id = await handle_chat(
        question=question,
        session_id=session_id,
        user_id=user_id,
        user_name=user_name,
        user_email=user_email,
        conversation_id=conversation_id,
    )
    try:
        await mongodb_memory.insert_message_event(user_id, session_id, user_email)
    except Exception as e:
        logger.debug("Failed to track message event: %s", e)
    try:
        await save_message(session_id, "user", question)
        await save_message(session_id, "assistant", answer)
    except Exception as e:
        logger.warning("Failed to save messages to chat_messages: %s", e)
    await add_to_conversation(conversation_id, "user", question)
    await add_to_conversation(conversation_id, "assistant", answer)
    clean_answer = preserve_markdown(answer)
    return {"answer": clean_answer, "user_id": user_id, "session_id": session_id, "trace_id": trace_id}

# ---------------- Streaming Chat Endpoint ----------------

@router.post("/chat/stream")
async def chat_stream(request: Request, auth_user: dict = Depends(require_auth)):
    """Streaming chat endpoint. PROTECTED - requires valid authentication."""
    data = await request.json()
    question = data.get("question", "")
    session_id = data.get("session_id", str(uuid.uuid4()))
    
    # Use VERIFIED user info from auth token, NOT from request body
    user_id = auth_user["user_id"]
    user_name = auth_user["name"]
    user_email = auth_user["email"]

    # ✅ STRICT IDENTITY: user_id is mandatory - fail fast if missing
    if not user_id or not user_id.strip():
        logger.error(f"[AUTH] ⚠️ Invalid user_id in auth_user: {auth_user}")
        raise HTTPException(
            status_code=401,
            detail="Invalid user identity. Please log in again."
        )
    
    # ✅ IDENTITY RULE: conversation_id = user_id (always email, never session_id)
    conversation_id = user_id

    return StreamingResponse(
        handle_chat_stream(
            question=question,
            session_id=session_id,
            user_id=user_id,
            user_name=user_name,
            user_email=user_email,
            conversation_id=conversation_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
        }
    )


# ============================================================================
# RETRY ENDPOINTS - Self-Healing RAG with Auto-Reranking
# ============================================================================

class RetryRequest(BaseModel):
    question: str
    session_id: str
    previous_trace_id: str
    retry_attempt: int = 1  # Optional, defaults to 1


@router.post("/chat/retry/stream")
async def chat_retry_stream(request: Request, auth_user: dict = Depends(require_auth)):
    """
    Retry endpoint with streaming - regenerates response with improved retrieval.
    Uses gradual step-up retrieval to improve results.
    """
    data = await request.json()
    question = data.get("question", "")
    session_id = data.get("session_id", str(uuid.uuid4()))
    previous_trace_id = data.get("previous_trace_id", "")
    retry_attempt = data.get("retry_attempt", 1)
    
    # Use VERIFIED user info from auth token
    user_id = auth_user["user_id"]
    user_name = auth_user["name"]
    user_email = auth_user["email"]
    
    if not user_id or not user_id.strip():
        logger.error(f"[AUTH] ⚠️ Invalid user_id in auth_user: {auth_user}")
        raise HTTPException(
            status_code=401,
            detail="Invalid user identity. Please log in again."
        )
    
    conversation_id = user_id

    return StreamingResponse(
        handle_chat_retry_stream(
            question=question,
            session_id=session_id,
            previous_trace_id=previous_trace_id,
            retry_attempt=retry_attempt,
            user_id=user_id,
            user_name=user_name,
            user_email=user_email,
            conversation_id=conversation_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
        }
    )


@router.get("/chat/response-versions")
async def get_response_versions_endpoint(
    parent_trace_id: str,
    metadata_only: bool = Query(False, description="If true, only return version count and current version metadata"),
    auth_user: dict = Depends(require_auth)
):
    """
    Get all response versions for a given parent_trace_id.
    
    Args:
        parent_trace_id: Parent trace ID linking all versions
        metadata_only: If true, only return count and current version info (no content)
        
    Returns:
        List of version documents with version number, content, model, etc.
    """
    try:
        if metadata_only:
            # Lightweight query: only get count and current version
            from app.mongodb_memory import mongodb_memory
            await mongodb_memory.connect()
            chat_messages_collection = mongodb_memory.database["chat_messages"]
            
            # Count total versions
            total_count = await chat_messages_collection.count_documents(
                {"parent_trace_id": parent_trace_id, "role": "assistant"}
            )
            
            # Get current version
            current_version_doc = await chat_messages_collection.find_one(
                {"parent_trace_id": parent_trace_id, "role": "assistant", "is_current": True},
                {"response_version": 1, "model_used": 1}
            )
            
            return {
                "parent_trace_id": parent_trace_id,
                "total_versions": total_count,
                "current_version": current_version_doc.get("response_version", 1) if current_version_doc else 1,
                "current_model": current_version_doc.get("model_used", "gpt-4o-mini") if current_version_doc else "gpt-4o-mini",
                "versions": []  # Empty for metadata_only
            }
        else:
            versions = await get_response_versions(parent_trace_id)
            return {
                "parent_trace_id": parent_trace_id,
                "versions": versions,
                "total_versions": len(versions)
            }
    except Exception as e:
        logger.error(f"Error getting response versions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve versions: {str(e)}")

# ---------------- User Chat History Endpoints ----------------

@router.get("/chat/history/{user_id}")
async def get_chat_history(
    user_id: str,
    current_user: dict = Depends(verify_user_access)
):
    """Get chat history for authenticated user only. Protected against IDOR."""
    try:
        history = await get_user_chat_history(user_id)
        return {"user_id": user_id, "history": history}
    except Exception as e:
        return {"error": str(e)}

@router.delete("/chat/history/{user_id}")
async def clear_chat_history(
    user_id: str,
    current_user: dict = Depends(verify_user_access)
):
    """Clear chat history for authenticated user only. Protected against IDOR."""
    try:
        await clear_user_chat_history(user_id)
        return {"message": f"Chat history cleared for user {user_id}"}
    except Exception as e:
        return {"error": str(e)}

@router.post("/chat/history/rebuild")
async def rebuild_chat_history(
    request: Request,
    current_user: dict = Depends(verify_user_access)
):
    """Rebuild chat history for a user after message editing. Protected against IDOR."""
    try:
        body = await request.json()
        user_id = body.get("user_id")
        messages = body.get("messages", [])
        
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")
        
        # Clear existing history first
        await clear_user_chat_history(user_id)
        
        # Re-add all messages in order
        for message in messages:
            role = message.get("role")
            content = message.get("content")
            
            if role and content:
                await add_to_conversation(user_id, role, content)
        
        return {"message": f"Chat history rebuilt for user {user_id}", "message_count": len(messages)}
    except Exception as e:
        return {"error": str(e)}

# ---------------- Chat Session Endpoints ----------------

@router.post("/chat/sessions/save")
async def save_chat_session(
    request: Request,
    auth_user: dict = Depends(require_auth)
):
    """Save or update a chat session with metadata and messages."""
    try:
        data = await request.json()
        
        session_data = {
            "session_id": data.get("session_id"),
            "user_id": auth_user["user_id"],
            "user_email": auth_user["email"],
            "user_name": auth_user["name"],
            "title": data.get("title"),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at", data.get("created_at")),
            "message_count": data.get("message_count", 0)
        }
        
        # Include messages if provided
        if "messages" in data:
            session_data["messages"] = data["messages"]
            # Update message count based on actual messages
            session_data["message_count"] = len(data["messages"])
        
        if not session_data["session_id"] or not session_data["title"] or not session_data["created_at"]:
            raise HTTPException(status_code=400, detail="session_id, title, and created_at are required")
        
        # ✅ Add timeout protection and better error handling
        import asyncio
        try:
            await asyncio.wait_for(
                save_session(session_data),
                timeout=30.0  # 30 second timeout
            )
            logger.info(f"Successfully saved session {session_data['session_id']} with {session_data['message_count']} messages")
            return {"message": "Session saved successfully", "session_id": session_data["session_id"]}
        except asyncio.TimeoutError:
            logger.error(f"Timeout saving session {session_data['session_id']} - MongoDB may be slow or unresponsive")
            raise HTTPException(
                status_code=504,
                detail="Session save timed out - please try again"
            )
        except Exception as db_error:
            logger.error(f"Database error saving session {session_data['session_id']}: {str(db_error)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save session: {str(db_error)}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in save_chat_session: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

@router.get("/chat/sessions/all")
async def get_all_chat_sessions(
    limit: int = 15,
    auth_user: dict = Depends(require_auth)
):
    """Get recent chat sessions from all users (one most recent chat per user)."""
    try:
        from app.mongodb_memory import mongodb_memory
        
        await mongodb_memory.connect()
        
        # Get all users who have chat history (sorted by last activity)
        # Include _id in the projection to use as conversation_id
        users_cursor = mongodb_memory.collection.find(
            {"messages": {"$exists": True, "$ne": []}},
            {"user_id": 1, "messages": 1, "last_updated": 1, "_id": 1}
        ).sort("last_updated", -1).limit(limit + 10)  # Fetch extra to account for filtering
        
        sessions = []
        current_user_id = auth_user["user_id"]
        
        async for user_doc in users_cursor:
            user_id = user_doc.get("user_id")
            
            # Skip current user
            if user_id == current_user_id:
                continue
                
            messages = user_doc.get("messages", [])
            if not messages:
                continue
            
            # Get MongoDB document _id as conversation_id
            mongo_id_obj = user_doc.get("_id")
            if not mongo_id_obj:
                continue  # Skip if no _id
            
            # Convert ObjectId to string (24 hex characters)
            mongo_id = str(mongo_id_obj)
            
            # Get first user message as title
            first_message = next((msg for msg in messages if msg.get("role") == "user"), None)
            title = first_message["content"][:50] + "..." if first_message else "Chat conversation"
            
            # Get timestamp
            last_updated = user_doc.get("last_updated")
            timestamp = int(last_updated.timestamp() * 1000) if last_updated else 0
            
            sessions.append({
                "session_id": mongo_id,  # Use conversation_id as session_id for URL routing
                "user_id": user_id,
                "user_email": user_id,  # Using user_id as email for now
                "user_name": user_id.split("@")[0] if "@" in user_id else user_id,
                "title": title,
                "conversation_id": mongo_id,  # MongoDB _id as conversation identifier
                "created_at": timestamp,
                "updated_at": timestamp,
                "message_count": len(messages)
            })
            
            if len(sessions) >= limit:
                break
        
        return {"sessions": sessions, "count": len(sessions)}
    except Exception as e:
        return {"error": str(e)}

@router.get("/chat/sessions/user/{user_id}")
async def get_user_chat_sessions(
    user_id: str,
    limit: int = 50,
    include_messages: bool = False,
    current_user: dict = Depends(verify_user_access)
):
    """Get chat sessions for a specific user. Protected against IDOR."""
    try:
        sessions = await get_user_sessions(user_id, limit, include_messages)
        return {"sessions": sessions, "count": len(sessions)}
    except Exception as e:
        return {"error": str(e)}

@router.get("/chat/sessions/{session_id}")
async def get_chat_session(
    session_id: str,
    include_messages: bool = False,
    auth_user: dict = Depends(require_auth)
):
    """Get a specific chat session by ID (only if it belongs to the authenticated user)."""
    try:
        session = await get_session_by_id(
            session_id=session_id,
            user_id=auth_user["user_id"],
            include_messages=include_messages
        )
        
        if not session:
            # ✅ Use 404 to avoid leaking session existence
            raise HTTPException(status_code=404, detail="Session not found")
        
        return session
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/chat/sessions/{session_id}")
async def delete_chat_session(
    session_id: str,
    auth_user: dict = Depends(require_auth)
):
    """Delete a chat session (soft delete - only if it belongs to the authenticated user)."""
    try:
        from app.mongodb_memory import delete_session
        
        deleted = await delete_session(
            session_id=session_id,
            user_id=auth_user["user_id"]
        )
        
        if not deleted:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return {"message": "Session deleted successfully", "session_id": session_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting session {session_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete session: {str(e)}"
        )

@router.get("/chat/sessions/messages/{user_id}")
async def get_user_chat_messages(
    user_id: str,
    auth_user: dict = Depends(require_auth)
):
    """Get chat messages for a specific user (for read-only viewing)."""
    try:
        from app.mongodb_memory import mongodb_memory
        
        await mongodb_memory.connect()
        
        # Get user's chat history
        user_doc = await mongodb_memory.collection.find_one({"user_id": user_id})
        
        if not user_doc:
            return {"messages": [], "title": "No chat history"}
        
        messages = user_doc.get("messages", [])
        
        # Get title from first user message
        first_message = next((msg for msg in messages if msg.get("role") == "user"), None)
        title = first_message["content"][:50] + "..." if first_message else "Chat conversation"
        
        # Format messages for frontend
        formatted_messages = []
        for msg in messages:
            formatted_messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })
        
        return {
            "messages": formatted_messages,
            "title": title,
            "user_id": user_id,
            "message_count": len(formatted_messages)
        }
        
    except Exception as e:
        return {"error": str(e)}

@router.get("/chat/sessions/by-conversation/{conversation_id}")
async def get_user_by_conversation_id(
    conversation_id: str,
    auth_user: dict = Depends(require_auth)
):
    """Get user_id and messages from MongoDB conversation_id (_id)."""
    try:
        from bson import ObjectId
        from bson.errors import InvalidId
        from app.mongodb_memory import mongodb_memory
        
        await mongodb_memory.connect()
        
        # Log the incoming conversation_id for debugging
        print(f"[CONVERSATION] Loading conversation_id: {conversation_id}")
        
        # Find user document by MongoDB _id
        try:
            mongo_object_id = ObjectId(conversation_id)
        except (InvalidId, ValueError, TypeError) as e:
            print(f"[CONVERSATION] Invalid conversation_id format: {conversation_id}, error: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid conversation ID format: {conversation_id}")
        
        user_doc = await mongodb_memory.collection.find_one({"_id": mongo_object_id})
        
        if not user_doc:
            print(f"[CONVERSATION] Conversation not found: {conversation_id}")
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        user_id = user_doc.get("user_id")
        messages = user_doc.get("messages", [])
        
        if not user_id:
            print(f"[CONVERSATION] No user_id found for conversation: {conversation_id}")
            raise HTTPException(status_code=404, detail="User not found for this conversation")
        
        # Get title from first user message
        first_message = next((msg for msg in messages if msg.get("role") == "user"), None)
        title = first_message["content"][:50] + "..." if first_message else "Chat conversation"
        
        # Format messages for frontend
        formatted_messages = []
        for msg in messages:
            formatted_messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })
        
        print(f"[CONVERSATION] Successfully loaded conversation: {conversation_id}, user: {user_id}, messages: {len(formatted_messages)}")
        
        return {
            "messages": formatted_messages,
            "title": title,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "message_count": len(formatted_messages)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[CONVERSATION] Error loading conversation {conversation_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# ---------------- User Profile Endpoints ----------------

@router.get("/user/profile")
async def get_user_profile_endpoint(
    auth_user: dict = Depends(require_auth)
):
    """Get current user's profile including team, manager, and role."""
    try:
        user_id = auth_user.get("user_id") or auth_user.get("email")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in auth")
        
        profile = await get_user_profile(user_id)
        
        if not profile:
            # User doesn't have profile yet - return empty structure
            return {
                "user_id": user_id,
                "user_email": auth_user.get("email", ""),
                "user_name": auth_user.get("name", ""),
                "team_name": None,
                "manager_email": None,
                "manager_name": None,
                "role": None,
                "needs_onboarding": True
            }
        
        # Check if onboarding is needed
        needs_onboarding = not profile.get("team_name") or not profile.get("role")
        
        return {
            "user_id": profile.get("user_id", user_id),
            "user_email": profile.get("user_email", auth_user.get("email", "")),
            "user_name": profile.get("user_name", auth_user.get("name", "")),
            "team_name": profile.get("team_name"),
            "manager_email": profile.get("manager_email"),
            "manager_name": profile.get("manager_name"),
            "role": profile.get("role"),
            "needs_onboarding": needs_onboarding
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user profile: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting user profile: {str(e)}")


class UserProfileUpdate(BaseModel):
    team_name: str
    role: Optional[str] = None


@router.post("/user/profile")
async def update_user_profile_endpoint(
    profile_data: UserProfileUpdate,
    auth_user: dict = Depends(require_auth)
):
    """Update user profile with team, manager, and role."""
    try:
        user_id = auth_user.get("user_id") or auth_user.get("email")
        user_email = auth_user.get("email", "")
        
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in auth")
        
        # Validate team exists
        team_info = get_team_by_name(profile_data.team_name)
        if not team_info:
            raise HTTPException(
                status_code=400,
                detail=f"Team '{profile_data.team_name}' not found"
            )
        
        # Get manager info from team lead (optional - team may not have a lead)
        manager_email = team_info.get("lead_email", "") or ""
        manager_name = team_info.get("lead", "") or ""
        
        # Manager is optional - empty strings are acceptable
        
        # Get role from users.json if not provided
        role = profile_data.role
        if not role:
            role = get_user_job_title(user_email) or ""
        
        # Update user profile
        success = await update_user_profile(
            user_id=user_id,
            team_name=profile_data.team_name,
            manager_email=manager_email,
            manager_name=manager_name,
            role=role
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update user profile")
        
        return {
            "success": True,
            "message": "Profile updated successfully",
            "profile": {
                "team_name": profile_data.team_name,
                "manager_email": manager_email,
                "manager_name": manager_name,
                "role": role
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user profile: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating user profile: {str(e)}")


@router.get("/teams/list")
async def get_teams_list(
    auth_user: dict = Depends(require_auth)
):
    """Get list of all teams for onboarding dropdown."""
    try:
        teams_list = []
        
        for team_name, team_info in TEAMS_STRUCTURE.items():
            teams_list.append({
                "team_name": team_name,
                "lead_name": team_info.get("lead", ""),
                "lead_email": team_info.get("lead_email", ""),
                "color": team_info.get("color", "#6B7280"),
                "description": team_info.get("description", "")
            })
        
        return {
            "teams": teams_list,
            "total": len(teams_list)
        }
        
    except Exception as e:
        logger.error(f"Error getting teams list: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting teams list: {str(e)}")

# ---------------- Share Chat Endpoints ----------------

@router.post("/chat/share/{session_id}")
async def share_chat_session(
    session_id: str,
    auth_user: dict = Depends(require_auth)
):
    """Generate a shareable link for a chat session.
    
    Users can share:
    - Their own chats (cf.conversation.*)
    - Chats they've copied from others (user_chat_*)
    
    The important thing is that the user must own/have access to the chat.
    """
    try:
        print(f"[SHARE] Attempting to share session {session_id} for user {auth_user['email']}")
        
        # Handle user_chat_* format (others' chats - virtual view)
        actual_session_id = session_id
        is_others_chat = False
        target_user_id = None  # Initialize for potential use
        
        if session_id.startswith("user_chat_"):
            # Extract user_id from user_chat_{user_id} format
            target_user_id = session_id.replace("user_chat_", "")
            print(f"[SHARE] Detected user_chat_ format, extracting user_id: {target_user_id}")
            
            # Get the most recent session from that user
            from app.mongodb_memory import get_user_sessions
            user_sessions = await get_user_sessions(target_user_id, limit=1, include_messages=False)
            
            if not user_sessions or len(user_sessions) == 0:
                print(f"[SHARE] No sessions found for user {target_user_id}")
                raise HTTPException(
                    status_code=404,
                    detail="No chat sessions found for this user."
                )
            
            # Use the most recent session
            actual_session_id = user_sessions[0]["session_id"]
            is_others_chat = True
            print(f"[SHARE] Using most recent session from user {target_user_id}: {actual_session_id}")
        
        # Get session to verify it exists
        # ✅ For regular sessions, verify ownership at query level
        # ✅ For others' chats (user_chat_*), we need to get the owner's session
        if is_others_chat:
            # For others' chats, use the target_user_id we extracted
            owner_user_id = target_user_id
        else:
            # For regular sessions, use the authenticated user's ID
            owner_user_id = auth_user["user_id"]
        
        session = await get_session_by_id(
            session_id=actual_session_id,
            user_id=owner_user_id,
            include_messages=True
        )
        if not session:
            print(f"[SHARE] Session {actual_session_id} not found for user {owner_user_id}")
            raise HTTPException(
                status_code=404, 
                detail=f"Session not found. Make sure the chat is saved before sharing."
            )
        
        # Debug: Check if session has messages
        message_count = len(session.get("messages", []))
        print(f"[SHARE] Session {actual_session_id} has {message_count} messages")
        if message_count == 0:
            print(f"[SHARE] ⚠️ WARNING: Sharing a chat with no messages!")
        
        # ✅ Ownership already verified at query level - no need for additional check
        
        # Generate unique share token
        share_token = str(uuid.uuid4())
        
        # Create shared chat entry in database (use actual_session_id)
        await create_shared_chat(actual_session_id, auth_user["email"], share_token)
        
        print(f"[SHARE] ✅ Chat {actual_session_id} shared by {auth_user['email']} with token {share_token}")
        
        return {
            "share_token": share_token,
            "share_url": f"/chat/shared/{share_token}",
            "message": "Share link created successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SHARE] ❌ Error sharing chat {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create share link: {str(e)}")

@router.get("/chat/shared/{share_token}")
async def get_shared_chat_session(
    share_token: str,
    auth_user: dict = Depends(require_auth)
):
    """Retrieve and copy a shared chat to the authenticated user's sessions."""
    try:
        from app.mongodb_memory import get_shared_chat  # , find_session_by_share_token
        
        # Get shared chat info
        shared_chat = await get_shared_chat(share_token)
        if not shared_chat:
            raise HTTPException(status_code=404, detail="Shared chat not found or expired")
        
        # ============================================================
        # DUPLICATE PREVENTION - COMMENTED OUT FOR NOW
        # Uncomment this section to prevent duplicate copies
        # ============================================================
        # Check if user already has a copy of this shared chat
        # existing_copy = await find_session_by_share_token(
        #     user_id=auth_user["user_id"],
        #     share_token=share_token
        # )
        # 
        # if existing_copy:
        #     # User already has this chat, return existing copy
        #     print(f"[SHARE] User {auth_user['email']} already has copy of this chat: {existing_copy['session_id']}")
        #     return {
        #         "session_id": existing_copy["session_id"],
        #         "title": existing_copy["title"],
        #         "messages": existing_copy.get("messages", []),
        #         "created_at": existing_copy["created_at"],
        #         "updated_at": existing_copy["updated_at"],
        #         "original_owner": shared_chat["user_email"],
        #         "message": "Redirecting to your existing copy",
        #         "is_existing": True  # Flag to indicate this is not a new copy
        #     }
        # ============================================================
        
        # Get the original session with messages
        # ✅ First get the owner's user_id from the session, then fetch with ownership check
        from app.mongodb_memory import get_session_owner_id
        owner_user_id = await get_session_owner_id(shared_chat["session_id"])
        
        if not owner_user_id:
            raise HTTPException(status_code=404, detail="Original session not found")
        
        original_session = await get_session_by_id(
            session_id=shared_chat["session_id"],
            user_id=owner_user_id,  # ✅ owner of shared chat
            include_messages=True
        )
        if not original_session:
            raise HTTPException(status_code=404, detail="Original session not found")
        
        # Debug: Log message count
        message_count = len(original_session.get("messages", []))
        print(f"[SHARE] Original session {shared_chat['session_id']} has {message_count} messages")
        
        # Create a new session ID for the current user
        timestamp = datetime.now().strftime("%Y%m%d")
        random_id = str(uuid.uuid4())[:10]
        new_session_id = f"cf.conversation.{timestamp}.{random_id}"
        
        # Smart title generation with share counter
        original_title = original_session['title']
        
        # Check if title already has "Shared (N):" pattern
        shared_pattern = r'^Shared \((\d+)\):\s*(.+)$'
        match = re.match(shared_pattern, original_title)
        
        if match:
            # Title already has a counter, increment it
            current_count = int(match.group(1))
            clean_title = match.group(2)
            new_title = f"Shared ({current_count + 1}): {clean_title}"
        elif original_title.startswith("Shared: "):
            # Title has "Shared:" but no counter, make it (2)
            clean_title = original_title[8:]  # Remove "Shared: " prefix
            new_title = f"Shared (2): {clean_title}"
        else:
            # Original chat, first share
            new_title = f"Shared: {original_title}"
        
        print(f"[SHARE] Title: '{original_title}' → '{new_title}'")
        
        # Copy session to current user
        new_session_data = {
            "session_id": new_session_id,
            "user_id": auth_user["user_id"],
            "user_email": auth_user["email"],
            "user_name": auth_user["name"],
            "title": new_title,
            "created_at": int(datetime.now().timestamp() * 1000),
            "updated_at": int(datetime.now().timestamp() * 1000),
            "messages": original_session.get("messages", []),
            "message_count": len(original_session.get("messages", []))
            # NOTE: source_share_token and source_session_id commented out
            # Uncomment these when enabling duplicate prevention:
            # "source_share_token": share_token,  # Track which share token this came from
            # "source_session_id": shared_chat["session_id"]  # Track original session
        }
        
        # Save the copied session
        await save_session(new_session_data)
        
        print(f"[SHARE] Created new copy for user {auth_user['email']}: {new_session_id}")
        
        return {
            "session_id": new_session_id,
            "title": new_session_data["title"],
            "messages": new_session_data["messages"],
            "created_at": new_session_data["created_at"],
            "updated_at": new_session_data["updated_at"],
            "original_owner": shared_chat["user_email"],
            "message": "Chat copied successfully to your chats",
            "is_existing": False  # Flag to indicate this is a new copy
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SHARE] ❌ Error retrieving shared chat: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve shared chat: {str(e)}")

# ---------------- Feedback Endpoint ----------------

@router.post("/feedback")
async def submit_feedback(request: FeedbackRequest):
    """Submit user feedback (👍/👎) for a chat interaction."""
    try:
        print(f"\n[FEEDBACK] Received feedback request:")
        print(f"  - trace_id: {request.trace_id}")
        print(f"  - rating: {request.rating}")
        print(f"  - categories: {request.categories}")
        print(f"  - comment: {request.comment or '(none)'}")
        
        # ✅ STRICT VALIDATION: trace_id is REQUIRED (no fallback)
        if not request.trace_id or request.trace_id.strip() == "":
            print(f"[FEEDBACK] ✗ Missing trace_id - feedback rejected")
            raise HTTPException(
                status_code=400,
                detail="trace_id is required. Feedback cannot be submitted without a valid trace_id."
            )
        
        # ✅ REJECT fallback trace_ids (they don't exist in Langfuse)
        if request.trace_id.startswith('feedback_fallback_'):
            print(f"[FEEDBACK] ✗ Rejected fallback trace_id: {request.trace_id}")
            raise HTTPException(
                status_code=400,
                detail="Invalid trace_id. Feedback cannot be submitted with a fallback trace_id. Please ensure the chat response included a valid trace_id."
            )
        
        # Validate rating
        if request.rating not in ["thumbs_up", "thumbs_down"]:
            print(f"[FEEDBACK] ✗ Invalid rating: {request.rating}")
            raise HTTPException(
                status_code=400,
                detail="Invalid rating. Must be 'thumbs_up' or 'thumbs_down'"
            )
        
        # Build comprehensive feedback comment
        feedback_comment = request.comment or ""
        if request.categories and len(request.categories) > 0:
            categories_str = ", ".join(request.categories)
            if feedback_comment:
                feedback_comment = f"Categories: {categories_str}\nComment: {feedback_comment}"
            else:
                feedback_comment = f"Categories: {categories_str}"
        
        print(f"[FEEDBACK] Final comment to log: {feedback_comment or '(empty)'}")
        
        # Log feedback to Langfuse with categories
        success = langfuse_tracker.add_feedback(
            trace_id=request.trace_id,
            rating=request.rating,
            comment=feedback_comment
        )
        
        # COMMENTED OUT: Auto-correction workflow (now using manual correction)
        # await track_feedback_history(request.trace_id, request.rating, request.comment)
        # 
        # # If thumbs down, trigger auto-correction immediately
        # if request.rating == "thumbs_down":
        #     try:
        #         # Get the original question and response from the trace
        #         original_data = await get_trace_data(request.trace_id)
        #         if original_data:
        #             # Trigger auto-correction
        #             corrected_response = await trigger_auto_correction_workflow(
        #                 trace_id=request.trace_id,
        #                 user_query=original_data.get("question", ""),
        #                 bad_response=original_data.get("response", ""),
        #                 user_comment=request.comment
        #             )
        #     except Exception as e:
        #         print(f"Auto-correction failed: {e}")
        
        if success:
            print(f"[FEEDBACK] ✓ Feedback successfully logged to Langfuse for trace {request.trace_id}")
            return {
                "status": "success",
                "message": "Feedback recorded successfully",
                "trace_id": request.trace_id,
                "auto_correction_triggered": False  # Manual correction will be used instead
            }
        else:
            print(f"[FEEDBACK] ✗ Failed to log feedback to Langfuse for trace {request.trace_id}")
            return {
                "status": "error",
                "message": "Failed to record feedback"
            }
            
    except Exception as e:
        print(f"[FEEDBACK] ✗ Exception submitting feedback: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"error": f"Failed to submit feedback: {str(e)}"}

# ---------------- Auto-Correction System ----------------

async def track_feedback_history(trace_id: str, rating: str, comment: str = None):
    """Track feedback history for smart auto-correction decisions."""
    try:
        feedback_file = "./data/feedback_history.json"
        
        # Load existing data
        if os.path.exists(feedback_file):
            with open(feedback_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {"feedback_history": {}}
        
        # Initialize trace data if not exists
        if trace_id not in data["feedback_history"]:
            data["feedback_history"][trace_id] = {
                "negative_count": 0,
                "positive_count": 0,
                "total_count": 0,
                "question_asked_before": False,
                "feedback_history": []
            }
        
        # Update counts
        trace_data = data["feedback_history"][trace_id]
        trace_data["total_count"] += 1
        
        if rating == "thumbs_down":
            trace_data["negative_count"] += 1
        else:
            trace_data["positive_count"] += 1
        
        # Add to feedback history
        feedback_entry = {
            "rating": rating,
            "comment": comment,
            "timestamp": datetime.now().isoformat()
        }
        trace_data["feedback_history"].append(feedback_entry)
        
        # Save updated data
        with open(feedback_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
    except Exception as e:
        print(f"Error tracking feedback history: {e}")

async def should_trigger_auto_correction(trace_id: str, user_comment: str = None) -> bool:
    """Simplified auto-correction logic - more effective and predictable."""
    try:
        # Load feedback history
        feedback_stats = await get_feedback_stats_for_question(trace_id)
        negative_count = feedback_stats.get('negative_count', 0)
        
        # SIMPLIFIED RULES - More predictable and effective
        
        # Rule 1: Always correct if user provides specific feedback
        if user_comment and len(user_comment.strip()) > 15:
            return True
        
        # Rule 2: Correct if 2+ negative feedbacks (simple threshold)
        if negative_count >= 2:
            return True
        
        # Rule 3: Correct if this is a recurring problem (same question, multiple negatives)
        if negative_count >= 1 and feedback_stats.get('question_asked_before', False):
            return True
        
        # Rule 4: Don't correct for single negative feedback
        return False
            
    except Exception as e:
        print(f"Error in auto-correction logic: {e}")
        return False

async def get_feedback_stats_for_question(trace_id: str) -> dict:
    """Get feedback statistics for a question to make smart decisions."""
    try:
        # In a real implementation, you'd query Langfuse API for feedback history
        # For now, we'll simulate with local data
        
        # Check if we have feedback data for this trace
        feedback_file = "./data/feedback_history.json"
        
        if os.path.exists(feedback_file):
            with open(feedback_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Find feedback for this trace
            trace_feedback = data.get('feedback_history', {}).get(trace_id, {})
            return trace_feedback
        else:
            # No history, treat as first time
            return {
                'negative_count': 0,
                'total_count': 0,
                'question_asked_before': False
            }
            
    except Exception as e:
        print(f"Error getting feedback stats: {e}")
        return {
            'negative_count': 0,
            'total_count': 0,
            'question_asked_before': False
        }

async def trigger_auto_correction(trace_id: str, user_comment: str = None):
    """Trigger auto-correction for a thumbs down feedback."""
    try:
        # Get the original trace data from Langfuse
        # For now, we'll simulate getting the original question and answer
        # In a real implementation, you'd fetch this from Langfuse API
        
        # Create auto-correction prompt
        correction_prompt = f"""
        The user gave negative feedback (👎) on this response. Please provide a better, improved version.
        
        Original question: [QUESTION_PLACEHOLDER]
        Original answer: [ANSWER_PLACEHOLDER]
        User feedback: {user_comment or "User indicated the response was not helpful"}
        
        Please provide an improved response that:
        1. Directly addresses the user's question
        2. Is more helpful and accurate
        3. Provides specific, actionable information
        4. Is clear and well-structured
        
        Improved response:
        """
        
        # Use LLM to generate improved response
        from langchain_core.prompts import ChatPromptTemplate
        
        llm = get_llm(temperature=0.3)
        
        # For now, we'll create a generic improved response
        # In a real implementation, you'd fetch the original Q&A from Langfuse
        improved_response = await generate_improved_response(correction_prompt, llm)
        
        # Save to dataset
        # Note: This doesn't have the original question - would need Langfuse integration to get it
        save_corrected_response(trace_id, improved_response, user_comment, None)
        
    except Exception as e:
        print(f"Auto-correction failed: {e}")
        raise e

async def generate_improved_response(prompt: str, llm):
    """Generate an improved response using LLM."""
    try:
        # Create a simple prompt template
        template = ChatPromptTemplate.from_messages([
            ("system", "You are an expert AI assistant. Improve the given response to be more helpful and accurate."),
            ("human", "{prompt}")
        ])
        
        chain = template | llm
        result = chain.invoke({"prompt": prompt})
        return result.content
        
    except Exception as e:
        print(f"Error generating improved response: {e}")
        return "I apologize, but I'm having trouble generating an improved response at the moment."

def save_corrected_response(trace_id: str, corrected_response: str, user_comment: str = None, original_question: str = None):
    """Save the corrected response to the dataset."""
    try:
        # Create dataset directory if it doesn't exist
        dataset_dir = "./data/corrected_responses"
        os.makedirs(dataset_dir, exist_ok=True)
        
        # Create dataset entry
        dataset_entry = {
            "trace_id": trace_id,
            "corrected_response": corrected_response,
            "original_question": original_question,  # Store the original question for similarity matching
            "user_comment": user_comment,
            "timestamp": datetime.now().isoformat(),
            "status": "corrected"
        }
        
        # Save to JSON file
        dataset_file = f"{dataset_dir}/corrected_responses.json"
        
        # Load existing data
        if os.path.exists(dataset_file):
            with open(dataset_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {"corrected_responses": []}
        
        # Add new entry
        data["corrected_responses"].append(dataset_entry)
        
        # Save back to file
        with open(dataset_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
    except Exception as e:
        print(f"Error saving corrected response: {e}")


# ---------------- Admin Insights: Most Asked Questions ----------------

async def _aggregate_top_questions(collection, limit: int, min_length: int) -> List[dict]:
    """Aggregate most frequently asked user questions from a MongoDB collection."""
    if collection is None:
        return []
    
    pipeline = [
        {"$match": {"messages": {"$exists": True, "$ne": []}}},
        {"$unwind": "$messages"},
        {
            "$match": {
                "messages.role": "user",
                "messages.content": {"$type": "string", "$ne": ""}
            }
        },
        {
            "$addFields": {
                "normalized_question": {
                    "$toLower": {
                        "$trim": {"input": "$messages.content"}
                    }
                },
                "asked_at": {
                    "$ifNull": [
                        "$messages.timestamp",
                        "$updated_at",
                        "$created_at",
                        datetime.utcnow()
                    ]
                },
                "raw_question": "$messages.content"
            }
        },
        {
            "$match": {
                "normalized_question": {"$ne": ""},
                "$expr": {"$gte": [{"$strLenCP": "$normalized_question"}, min_length]}
            }
        },
        {"$sort": {"asked_at": -1}},
        {
            "$group": {
                "_id": "$normalized_question",
                "count": {"$sum": 1},
                "last_asked": {"$first": "$asked_at"},
                "question_example": {"$first": "$raw_question"}
            }
        },
        {"$sort": {"count": -1, "last_asked": -1}},
        {"$limit": limit}
    ]
    
    results = await collection.aggregate(pipeline).to_list(length=limit)
    formatted = []
    for doc in results:
        last_asked = doc.get("last_asked")
        if isinstance(last_asked, datetime):
            last_asked = last_asked.isoformat()
        
        formatted.append({
            "question": doc.get("question_example") or doc.get("_id"),
            "count": doc.get("count", 0),
            "last_asked": last_asked
        })
    
    return formatted


@router.get("/admin/top-questions")
async def get_most_asked_questions(
    limit: int = Query(default=15, ge=1, le=200),
    min_length: int = Query(default=6, ge=3, le=200),
    source: str = Query(default="auto", description="auto | chat_sessions | conversations"),
    current_user: dict = Depends(require_restricted_admin)
):
    """
    Return the most frequently asked user questions and their counts.
    
    - Restricted to a small admin allowlist.
    - Primary source: chat_sessions collection (includes saved sessions).
    - Fallback source: legacy conversations collection.
    """
    await mongodb_memory.connect()
    db = mongodb_memory.database
    
    if db is None:
        raise HTTPException(status_code=503, detail="Database connection not available")
    
    normalized_source = (source or "auto").lower()
    valid_sources = {"auto", "chat_sessions", "conversations"}
    
    if normalized_source not in valid_sources:
        raise HTTPException(status_code=400, detail=f"Invalid source '{source}'. Use one of {sorted(valid_sources)}")
    
    sources_to_try = ["chat_sessions", "conversations"] if normalized_source == "auto" else [normalized_source]
    questions: List[dict] = []
    used_source = None
    errors: List[str] = []
    
    for src in sources_to_try:
        try:
            if src == "chat_sessions":
                collection = db["chat_sessions"]
            else:
                # Legacy in-memory conversation collection
                collection = mongodb_memory.collection
            
            questions = await _aggregate_top_questions(collection, limit, min_length)
            used_source = src
            
            if questions:
                break
        except Exception as e:
            errors.append(f"{src}: {e}")
            continue
    
    return {
        "used_source": used_source,
        "limit": limit,
        "count": len(questions),
        "questions": questions,
        "errors": errors
    }


# ---------------- Admin Blog: Status, Stats, Poll (Weaviate Blogs) ----------------

try:
    from weaviate.classes.aggregate import GroupByAggregate
except Exception:
    GroupByAggregate = None


def _blogs_collection_count() -> int:
    """Return total chunk count in Weaviate Blogs collection, or 0 if unavailable."""
    try:
        client = get_weaviate_client()
        if client is None:
            return 0
        if not client.collections.exists("Blogs"):
            return 0
        coll = client.collections.get("Blogs")
        agg = coll.aggregate.over_all(total_count=True)
        return int(agg.total_count) if getattr(agg, "total_count", None) is not None else 0
    except Exception:
        return 0


def _blogs_unique_post_count() -> int:
    """Return count of unique blog posts (distinct doc_id) in Weaviate Blogs collection, or 0 if unavailable."""
    if GroupByAggregate is None:
        return 0
    try:
        client = get_weaviate_client()
        if client is None:
            return 0
        if not client.collections.exists("Blogs"):
            return 0
        coll = client.collections.get("Blogs")
        response = coll.aggregate.over_all(group_by=GroupByAggregate(prop="doc_id"))
        groups = getattr(response, "groups", None)
        return len(groups) if groups is not None else 0
    except Exception:
        return 0


def _vectorstore_exists() -> bool:
    """Return True if Weaviate is healthy and Blogs collection exists."""
    try:
        if not get_weaviate_client():
            return False
        return get_weaviate_client().collections.exists("Blogs")
    except Exception:
        return False


@router.get("/admin/blog/status")
async def get_admin_blog_status(current_user: dict = Depends(require_admin)):
    """
    Get blog polling status and last run metadata for the admin blog UI.
    blog_post_count = max(Weaviate unique posts, ingestion-tracking count) so UI reflects full tracked set.
    """
    meta = load_blog_metadata()
    last_run = meta.get("last_run_at")
    weaviate_count = _blogs_unique_post_count()
    tracking_count = get_blog_tracking_count()
    post_count = max(weaviate_count, tracking_count)
    return {
        "polling_enabled": BLOG_POLLING_ENABLED,
        "polling_interval_seconds": BLOG_POLLING_INTERVAL,
        "polling_interval_minutes": BLOG_POLLING_INTERVAL // 60,
        "last_poll_file": BLOG_LAST_POLL_FILE,
        "last_poll_time": last_run,
        "last_blog_poll": last_run,
        "blog_post_count": post_count,
        "last_blog_post_date": meta.get("last_blog_post_date"),
        "vectorstore_exists": _vectorstore_exists(),
    }


@router.get("/admin/blog/stats")
async def get_admin_blog_stats(current_user: dict = Depends(require_admin)):
    """
    Get blog source and Weaviate Blogs collection stats for the admin blog UI.
    blog_post_count / unique_blog_posts = max(Weaviate distinct doc_id, ingestion-tracking count).
    total_blog_chunks = total chunk count in Weaviate.
    """
    meta = load_blog_metadata()
    total_chunks = _blogs_collection_count()
    weaviate_unique = _blogs_unique_post_count()
    tracking_count = get_blog_tracking_count()
    unique_posts = max(weaviate_unique, tracking_count)
    return {
        "source_url": WEB_SOURCE_URL,
        "web_source_enabled": ENABLE_WEB_SOURCE,
        "vectorstore_exists": _vectorstore_exists(),
        "blog_post_count": unique_posts,
        "unique_blog_posts": unique_posts,
        "total_blog_chunks": total_chunks,
        "last_blog_poll": meta.get("last_run_at"),
        "last_blog_post_date": meta.get("last_blog_post_date"),
        "last_blog_post_url": meta.get("last_blog_post_url"),
        "last_blog_post_title": meta.get("last_blog_post_title"),
        "oldest_post_date": meta.get("oldest_blog_post_date"),
        "newest_post_date": meta.get("last_blog_post_date"),
        "vectorstore_build_date": meta.get("last_run_at"),
    }


@router.post("/admin/blog/poll")
async def post_admin_blog_poll(current_user: dict = Depends(require_admin)):
    """
    Trigger blog ingestion: fetch new posts from the web and store them in Weaviate Blogs collection.
    Runs in a thread so the request does not time out.
    """
    try:
        result = await asyncio.to_thread(run_blog_ingestion, False)
        if result.get("error"):
            raise HTTPException(
                status_code=500,
                detail=result["error"] or "Blog ingestion failed",
            )
        return {
            "success": result.get("success", False),
            "chunks_inserted": result.get("chunks_inserted", 0),
            "chunks_processed": result.get("chunks_processed", 0),
            "message": "Blog poll completed. New posts have been added to the vectorstore.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Blog poll failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------- Admin Dashboard: User Statistics ----------------


@router.get("/admin/users/summary")
async def get_admin_users_summary(
    exclude_users: Optional[str] = Query(None, description="Comma-separated list of user emails/names to exclude"),
    current_user: dict = Depends(require_admin)
):
    """
    Get ALL-TIME user statistics from user_activity collection.
    Returns pre-calculated lifetime metrics (no date filtering).
    
    This endpoint is used by the admin dashboard for the "All Time" view.
    """
    try:
        # Parse exclude_users if provided
        exclude_list = None
        if exclude_users:
            exclude_list = [u.strip() for u in exclude_users.split(",") if u.strip()]
        
        # Get statistics from MongoDB
        users = await get_user_statistics(exclude_users=exclude_list)
        
        return {
            "total_users": len(users),
            "users": users,
            "generated_at": datetime.utcnow().isoformat(),
            "data_source": "user_activity",
            "time_range": "all_time",
            "filters_applied": {
                "excluded_users_count": len(exclude_list) if exclude_list else 0
            }
        }
    except Exception as e:
        logger.error(f"Error getting admin users summary: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve user statistics: {str(e)}"
        )


@router.get("/admin/rankers")
async def get_admin_rankers(
    from_date: Optional[str] = Query(None, description="Start date in YYYY-MM-DD format"),
    to_date: Optional[str] = Query(None, description="End date in YYYY-MM-DD format"),
    exclude_users: Optional[str] = Query(None, description="Comma-separated list of user emails/names to exclude"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of rankers to return"),
    current_user: dict = Depends(require_admin)
):
    """
    Get date-based user rankers from message_events collection.
    Returns time-filtered analytics for specific date ranges.
    
    This endpoint is used by the admin dashboard for date-filtered views.
    """
    try:
        # Parse dates if provided
        start_date = None
        end_date = None
        if from_date:
            try:
                start_date = datetime.strptime(from_date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid from_date format. Use YYYY-MM-DD")
        
        if to_date:
            try:
                # Set to end of day for inclusive end date
                end_date = datetime.strptime(to_date, "%Y-%m-%d")
                end_date = end_date.replace(hour=23, minute=59, second=59)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid to_date format. Use YYYY-MM-DD")
        
        # Parse exclude_users if provided
        exclude_list = None
        if exclude_users:
            exclude_list = [u.strip() for u in exclude_users.split(",") if u.strip()]
        
        # Get rankers from MongoDB
        rankers = await get_rankers_by_date(
            start_date=start_date,
            end_date=end_date,
            exclude_users=exclude_list,
            limit=limit
        )
        
        return {
            "total_rankers": len(rankers),
            "rankers": rankers,
            "generated_at": datetime.utcnow().isoformat(),
            "data_source": "message_events",
            "filters_applied": {
                "from_date": from_date,
                "to_date": to_date,
                "excluded_users_count": len(exclude_list) if exclude_list else 0
            },
            "time_range": f"{from_date or 'all'} to {to_date or 'all'}" if from_date or to_date else "all"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting admin rankers: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve rankers: {str(e)}"
        )


# ---------------- Admin Teams Dashboard: MongoDB-based Team Analytics ----------------


@router.get("/admin/teams/summary")
async def get_teams_summary_mongodb(
    from_date: Optional[str] = Query(None, description="Start date in YYYY-MM-DD format"),
    to_date: Optional[str] = Query(None, description="End date in YYYY-MM-DD format"),
    exclude_users: Optional[str] = Query(None, description="Comma-separated list of user emails/names to exclude"),
    current_user: dict = Depends(require_admin)
):
    """
    Get team-wise statistics from MongoDB.
    - If dates provided: Uses message_events collection (date-filtered)
    - If no dates: Uses user_activity collection (all-time aggregated)
    
    This endpoint is used by the admin teams dashboard.
    """
    try:
        await mongodb_memory.connect()
        
        # Parse dates if provided
        # Note: Dates are parsed as UTC to match how message_events stores created_at (naive UTC from datetime.utcnow())
        # We explicitly create UTC datetimes by parsing as UTC timezone-aware, then converting to naive UTC
        start_date = None
        end_date = None
        if from_date:
            try:
                # Parse date string and create timezone-aware UTC datetime, then convert to naive UTC
                # This ensures the datetime represents UTC time regardless of server timezone
                parsed_naive = datetime.strptime(from_date, "%Y-%m-%d")
                # Create timezone-aware UTC datetime
                parsed_utc = datetime(parsed_naive.year, parsed_naive.month, parsed_naive.day, 0, 0, 0, 0, tzinfo=timezone.utc)
                # Convert to naive UTC (remove timezone info but keep UTC time values)
                start_date = parsed_utc.replace(tzinfo=None)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid from_date format. Use YYYY-MM-DD")
        
        if to_date:
            try:
                # Parse date string and create timezone-aware UTC datetime for end of day
                parsed_naive = datetime.strptime(to_date, "%Y-%m-%d")
                # Create timezone-aware UTC datetime for end of day
                parsed_utc = datetime(parsed_naive.year, parsed_naive.month, parsed_naive.day, 23, 59, 59, 0, tzinfo=timezone.utc)
                # Convert to naive UTC (remove timezone info but keep UTC time values)
                end_date = parsed_utc.replace(tzinfo=None)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid to_date format. Use YYYY-MM-DD")
        
        # Parse exclude_users if provided
        exclude_list = None
        if exclude_users:
            exclude_list = [u.strip().lower() for u in exclude_users.split(",") if u.strip()]
        
        # Determine data source based on date filter
        if start_date or end_date:
            # Date-based: Query message_events collection
            logger.info(f"[TEAMS] Date-based query: {start_date} to {end_date}")
            message_events_collection = mongodb_memory.database["message_events"]
            user_activity_collection = mongodb_memory.database["user_activity"]
            
            # Build date filter
            # Note: created_at is stored as naive UTC datetime (from datetime.utcnow())
            # MongoDB handles naive datetime comparisons correctly, but we'll keep dates as naive UTC for consistency
            date_filter = {}
            if start_date or end_date:
                date_range = {}
                if start_date:
                    # Keep as naive UTC (datetime.utcnow() creates naive UTC)
                    # MongoDB will compare correctly
                    date_range["$gte"] = start_date
                if end_date:
                    # Keep as naive UTC, but ensure it's end of day
                    date_range["$lte"] = end_date
                if date_range:
                    date_filter["created_at"] = date_range
                    logger.info(f"[TEAMS] Date filter: {date_range}")
            
            # Build exclusion filter
            exclude_filter = {}
            if exclude_list:
                exclude_emails_lower = [email.lower() for email in exclude_list]
                exclude_filter["user_email"] = {"$nin": exclude_emails_lower}
            
            # Aggregate messages by user_id from message_events
            # Note: message_events collection doesn't have event_type field - it only contains message events
            match_filter = {**date_filter, **exclude_filter}
            
            pipeline = [
                {"$match": match_filter},
                {"$group": {
                    "_id": "$user_id",
                    "user_email": {"$first": "$user_email"},
                    "total_messages": {"$sum": 1}
                }},
                {"$project": {
                    "_id": 0,
                    "user_id": "$_id",
                    "user_email": 1,
                    "total_messages": 1
                }}
            ]
            
            # Debug: Check total documents in collection
            total_docs = await message_events_collection.count_documents({})
            logger.info(f"[TEAMS] Total documents in message_events: {total_docs}")
            
            # Debug: Check documents in date range (without grouping)
            sample_docs = await message_events_collection.find(match_filter).limit(5).to_list(length=5)
            logger.info(f"[TEAMS] Sample documents matching filter: {len(sample_docs)}")
            if sample_docs:
                logger.info(f"[TEAMS] Sample doc created_at: {sample_docs[0].get('created_at')}, type: {type(sample_docs[0].get('created_at'))}")
            
            user_messages = await message_events_collection.aggregate(pipeline).to_list(length=None)
            logger.info(f"[TEAMS] Found {len(user_messages)} users with messages in date range")
            
            # Get team assignments from user_activity, with fallback to teams.py
            from app.models.teams import get_team_by_member_email
            teams_data = {}
            for user_msg in user_messages:
                user_id = user_msg.get("user_id")  # This is the GUID (e.g., "aad-12345")
                user_email = (user_msg.get("user_email") or "").lower()
                total_messages = user_msg.get("total_messages", 0)
                
                # Try to get team_name from user_activity first
                # user_activity uses user_id (GUID) as the key, but also has user_email field
                team_name = None
                user_doc = None
                
                # Try lookup by user_id (GUID) first
                if user_id:
                    user_doc = await user_activity_collection.find_one(
                        {"user_id": user_id},
                        {"team_name": 1, "user_email": 1, "user_name": 1}
                    )
                
                # If not found by user_id, try by user_email
                if not user_doc and user_email:
                    user_doc = await user_activity_collection.find_one(
                        {"user_email": user_email},
                        {"team_name": 1, "user_email": 1, "user_name": 1}
                    )
                
                if user_doc:
                    team_name = user_doc.get("team_name")
                    user_name = user_doc.get("user_name", "")
                
                # Fallback to teams.py if not found in user_activity
                if not team_name or team_name.strip() == "":
                    if user_email:
                        team_name = get_team_by_member_email(user_email)
                        if team_name == "Unassigned":
                            team_name = None
                            logger.debug(f"[TEAMS] User {user_email} (ID: {user_id}) not found in teams.py, skipping")
                    else:
                        logger.debug(f"[TEAMS] User ID {user_id} has no email, cannot assign team, skipping")
                
                # Skip users without team assignment
                if not team_name or team_name.strip() == "":
                    continue
                
                # Initialize team if not exists
                if team_name not in teams_data:
                    teams_data[team_name] = {
                        "team_name": team_name,
                        "total_messages": 0,
                        "active_members": set(),
                        "member_details": []
                    }
                
                # Aggregate team data
                teams_data[team_name]["total_messages"] += total_messages
                teams_data[team_name]["active_members"].add(user_email)
                teams_data[team_name]["member_details"].append({
                    "email": user_email,
                    "name": user_name,
                    "messages": total_messages
                })
            
            data_source = "message_events"
            time_range = f"{from_date or 'all'} to {to_date or 'all'}" if from_date or to_date else "all"
        else:
            # All-time: Use user_activity collection
            logger.info(f"[TEAMS] All-time query from user_activity")
            user_activity_collection = mongodb_memory.database["user_activity"]
            
            # Get all user_activity documents
            cursor = user_activity_collection.find({})
            all_users = await cursor.to_list(length=None)
            
            logger.info(f"[TEAMS] Found {len(all_users)} users in user_activity collection")
            
            # Group users by team_name
            from app.models.teams import get_team_by_member_email
            teams_data = {}
            
            for user_doc in all_users:
                user_email = user_doc.get("user_email", "").lower()
                user_name = user_doc.get("user_name", "")
                team_name = user_doc.get("team_name")
                total_messages = user_doc.get("total_messages", 0)
                
                # Skip excluded users
                if exclude_list:
                    if user_email in exclude_list or user_name.lower() in exclude_list:
                        continue
                    # Also check if any excluded email/name is contained
                    if any(excluded in user_email or excluded in user_name.lower() for excluded in exclude_list):
                        continue
                
                # Fallback to teams.py if team_name not found in user_activity
                if not team_name or team_name.strip() == "":
                    team_name = get_team_by_member_email(user_email)
                    if team_name == "Unassigned":
                        team_name = None
                        logger.debug(f"[TEAMS] User {user_email} not found in teams.py, skipping")
                
                # Skip users without team assignment
                if not team_name or team_name.strip() == "":
                    continue
                
                # Initialize team if not exists
                if team_name not in teams_data:
                    teams_data[team_name] = {
                        "team_name": team_name,
                        "total_messages": 0,
                        "active_members": set(),
                        "member_details": []
                    }
                
                # Aggregate team data
                teams_data[team_name]["total_messages"] += total_messages
                teams_data[team_name]["active_members"].add(user_email)
                teams_data[team_name]["member_details"].append({
                    "email": user_email,
                    "name": user_name,
                    "messages": total_messages
                })
            
            data_source = "user_activity"
            time_range = "all_time"
        
        # Convert to list format and get team info from teams.py
        from app.models.teams import get_team_by_name, get_all_teams, get_team_color
        
        teams_list = []
        for team_name, team_data in teams_data.items():
            # Get team info from teams.py
            team_info = get_team_by_name(team_name)
            if not team_info:
                # Team not found in teams.py, use defaults
                team_info = {
                    "lead": None,
                    "lead_email": None,
                    "members": [],
                    "color": "#6B7280",  # Gray fallback
                    "description": team_name
                }
            
            teams_list.append({
                "team_name": team_name,
                "lead": team_info.get("lead"),
                "lead_email": team_info.get("lead_email"),
                "color": get_team_color(team_name) or team_info.get("color", "#6B7280"),
                "description": team_info.get("description", team_name),
                "total_messages": team_data["total_messages"],
                "total_questions": team_data["total_messages"],  # Map messages to questions for frontend compatibility
                "unique_questions": 0,  # Not available from user_activity, set to 0
                "top_questions": [],  # Not available from user_activity, empty array
                "active_members_count": len(team_data["active_members"]),
                "member_count": len(team_info.get("members", [])),
                "members": team_data["member_details"]
            })
        
        # Sort by total_messages descending
        teams_list.sort(key=lambda x: x["total_messages"], reverse=True)
        
        logger.info(f"[TEAMS] Returning {len(teams_list)} teams with data out of {len(TEAMS_STRUCTURE)} total teams in database")
        
        return {
            "status": "success",
            "total_teams": len(TEAMS_STRUCTURE),  # Total teams in database, not just teams with activity
            "teams": teams_list,
            "generated_at": datetime.utcnow().isoformat(),
            "data_source": data_source,
            "time_range": time_range,
            "filters_applied": {
                "from_date": from_date,
                "to_date": to_date,
                "excluded_users_count": len(exclude_list) if exclude_list else 0
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting teams summary from MongoDB: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve team statistics: {str(e)}"
        )


@router.get("/dataset/corrected-responses")
async def get_corrected_responses(current_user: dict = Depends(require_admin)):
    """Get all corrected responses from the dataset. Requires admin access."""
    try:
        dataset_file = "./data/corrected_responses/corrected_responses.json"
        
        if not os.path.exists(dataset_file):
            return {"corrected_responses": [], "count": 0}
        
        with open(dataset_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return {
            "corrected_responses": data.get("corrected_responses", []),
            "count": len(data.get("corrected_responses", []))
        }
        
    except Exception as e:
        return {"error": f"Failed to load corrected responses: {str(e)}"}

@router.delete("/dataset/corrected-responses")
async def clear_corrected_responses(current_user: dict = Depends(require_admin)):
    """Clear all corrected responses from the dataset. Requires admin access."""
    try:
        dataset_file = "./data/corrected_responses/corrected_responses.json"
        
        if os.path.exists(dataset_file):
            os.remove(dataset_file)
            return {"message": "Corrected responses dataset cleared"}
        else:
            return {"message": "No dataset found to clear"}
            
    except Exception as e:
        return {"error": f"Failed to clear dataset: {str(e)}"}


# ============================================================================
# LANGFUSE ANALYTICS ENDPOINTS
# ============================================================================

@router.get("/analytics/langfuse/teams/summary")
async def get_teams_analytics_summary(
    time_filter: str = Query("today", description="today|yesterday|this_week|last_week|last_7_days|all"),
    current_user: dict = Depends(require_restricted_admin)
):
    """
    Get analytics summary organized by teams.
    
    Returns:
    - Team-wise user activity
    - Team-wise questions
    - Team leads and member count
    - Overall team statistics
    """
    try:
        from app.langfuse_integration import langfuse_client
        from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
        from app.models.teams import get_all_teams, get_team_by_member_email, get_team_color
        import asyncio
        from datetime import datetime, timezone, timedelta, timezone
        
        logger.info("[LANGFUSE ANALYTICS] ===== Teams Summary Request Started =====")
        logger.info(f"[LANGFUSE ANALYTICS] Endpoint: /analytics/langfuse/teams/summary")
        logger.info(f"[LANGFUSE ANALYTICS] Time Filter: {time_filter}")
        logger.info(f"[LANGFUSE ANALYTICS] Requested by: {current_user.get('email', 'unknown')}")
        
        if not langfuse_client:
            logger.error("[LANGFUSE ANALYTICS] Langfuse client not initialized")
            return {"error": "Langfuse client not initialized", "status": "error"}
        
        # Calculate date range
        now = datetime.now(timezone.utc)
        start_time = now
        end_time = now
        
        if time_filter == "today":
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now
        elif time_filter == "yesterday":
            yesterday = now - timedelta(days=1)
            start_time = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "this_week":
            start_time = now - timedelta(days=now.weekday())
            start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now
        elif time_filter == "last_week":
            days_since_monday = now.weekday()
            last_monday = now - timedelta(days=days_since_monday + 7)
            start_time = last_monday.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = (last_monday + timedelta(days=6)).replace(
                hour=23, minute=59, second=59, microsecond=999999
            )
        elif time_filter == "last_7_days":
            start_time = now - timedelta(days=7)
            end_time = now
        else:
            start_time = None
            end_time = None
        
        # Log time frame details
        if start_time and end_time:
            logger.info(f"[LANGFUSE ANALYTICS] Date Range: {start_time.isoformat()} to {end_time.isoformat()}")
            logger.info(f"[LANGFUSE ANALYTICS] Time Span: {(end_time - start_time).total_seconds() / 86400:.2f} days")
        else:
            logger.info("[LANGFUSE ANALYTICS] Date Range: ALL (no time filter)")
        
        logger.info(f"[LANGFUSE ANALYTICS] Fetching: Team-wise analytics (activity, questions, member stats)")
        
        # Initialize team data structure
        teams_data = {}
        all_teams = get_all_teams()
        
        logger.info(f"[LANGFUSE ANALYTICS] Total teams in system: {len(all_teams)}")
        
        for team_name, team_info in all_teams.items():
            teams_data[team_name] = {
                "team_name": team_name,
                "lead": team_info.get("lead"),
                "lead_email": team_info.get("lead_email"),
                "member_count": len(team_info.get("members", [])) + (1 if team_info.get("lead_email") else 0),
                "color": team_info.get("color"),
                "total_questions": 0,
                "unique_questions": 0,
                "active_members": set(),
                "questions_list": []
            }
        
        # Fetch traces and organize by team
        page = 1
        batch_limit = 100
        max_pages = 10 if time_filter != "all" else 30
        
        logger.info(f"[LANGFUSE ANALYTICS] Pagination: max_pages={max_pages}, batch_limit={batch_limit}")
        
        # Collect all unique emails first for batch profile fetching
        all_emails_set = set()
        traces_data = []  # Store traces temporarily
        traces_with_email = 0
        traces_without_email = 0
        
        async with httpx.AsyncClient() as client:
            total_traces_fetched = 0
            total_pages_fetched = 0
            
            # First pass: Collect all traces and unique emails
            while page <= max_pages:
                try:
                    params = {
                        "page": page,
                        "limit": batch_limit
                    }
                    
                    if start_time:
                        params["fromTimestamp"] = start_time.isoformat()
                    if end_time:
                        params["toTimestamp"] = end_time.isoformat()
                    
                    logger.info(f"[LANGFUSE ANALYTICS] Fetching page {page}/{max_pages} from Langfuse API")
                    logger.debug(f"[LANGFUSE ANALYTICS] API Request params: {params}")
                    
                    response = await client.get(
                        f"{LANGFUSE_HOST}/api/public/traces",
                        params=params,
                        auth=(LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY),
                        timeout=90.0  # Increased from 30s - Langfuse API can be slow
                    )
                    
                    logger.info(f"[LANGFUSE ANALYTICS] API Response: status={response.status_code}, page={page}")
                        
                    if response.status_code == 429:
                        logger.warning(f"[LANGFUSE ANALYTICS] Rate limited at page {page}, stopping pagination")
                        break
                    
                    if response.status_code != 200:
                        logger.error(f"[LANGFUSE ANALYTICS] API error: status={response.status_code}, stopping at page {page}")
                        break
                    
                    traces_response = response.json()
                    traces = traces_response.get("data", [])
                    
                    logger.info(f"[LANGFUSE ANALYTICS] Page {page}: Received {len(traces)} traces")
                    total_traces_fetched += len(traces)
                    total_pages_fetched = page
                    
                    if not traces:
                        logger.info(f"[LANGFUSE ANALYTICS] No more traces at page {page}, stopping pagination")
                        break
                    
                    # Log sample traces for debugging
                    for trace in traces[:3]:
                        metadata = trace.get("metadata", {})
                        logger.debug(
                            "[LANGFUSE ANALYTICS] Trace sample - id=%s email=%s question=%s",
                            trace.get("id"),
                            metadata.get("user_email"),
                            str(trace.get("input", ""))[:50] + "..." if len(str(trace.get("input", ""))) > 50 else trace.get("input", ""),
                        )
                    
                    # Store traces and collect emails
                    for trace in traces:
                        metadata = trace.get("metadata", {})
                        user_email = metadata.get("user_email")
                        if user_email:
                            user_email_str = str(user_email) if isinstance(user_email, list) else user_email
                            normalized_email = user_email_str.lower().strip()
                            if normalized_email:
                                all_emails_set.add(normalized_email)
                        traces_data.append(trace)
                    
                    if len(traces) < batch_limit:
                        logger.info(f"[LANGFUSE ANALYTICS] Last page reached (received {len(traces)} < {batch_limit} traces)")
                        break
                    
                    page += 1
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"[LANGFUSE ANALYTICS] Error fetching traces at page {page}: {e}")
                    import traceback
                    logger.error(f"[LANGFUSE ANALYTICS] Traceback: {traceback.format_exc()}")
                    break
            
            # Batch fetch all user profiles at once
            logger.info(f"[LANGFUSE ANALYTICS] Batch fetching profiles for {len(all_emails_set)} unique users")
            user_profiles_cache = {}
            
            if all_emails_set:
                try:
                    await mongodb_memory.connect()
                    user_activity_collection = mongodb_memory.database["user_activity"]
                    
                    # Fetch all profiles in a single query using $in
                    profiles_cursor = user_activity_collection.find(
                        {"user_id": {"$in": list(all_emails_set)}},
                        {
                            "user_id": 1,
                            "user_email": 1,
                            "team_name": 1
                        }
                    )
                    
                    async for profile_doc in profiles_cursor:
                        user_id = profile_doc.get("user_id", "").lower()
                        if user_id:
                            user_profiles_cache[user_id] = profile_doc.get("team_name")
                    
                    logger.info(f"[LANGFUSE ANALYTICS] Loaded {len(user_profiles_cache)} user profiles from cache")
                except Exception as e:
                    logger.warning(f"[LANGFUSE ANALYTICS] Error batch fetching profiles: {e}, falling back to individual lookups")
                    user_profiles_cache = {}
            
            # Second pass: Process traces with cached profiles
            logger.info(f"[LANGFUSE ANALYTICS] Processing {len(traces_data)} traces with cached profiles")
            
            for trace in traces_data:
                metadata = trace.get("metadata", {})
                user_email = metadata.get("user_email")
                question = trace.get("input", "")
                
                if user_email:
                    user_email_str = str(user_email) if isinstance(user_email, list) else user_email
                    normalized_email = user_email_str.lower().strip()
                    if not normalized_email:
                        traces_without_email += 1
                        continue
                    
                    traces_with_email += 1
                    
                    # Get team from cache first
                    team_name = user_profiles_cache.get(normalized_email)
                    
                    # Fallback to email matching if no profile team found
                    if not team_name:
                        team_name = get_team_by_member_email(normalized_email)
                        if team_name and team_name != "Unassigned":
                            logger.debug(f"[ANALYTICS] User {normalized_email} assigned to team via email matching: {team_name}")
                    
                    # If still no team, assign to "Unassigned"
                    if not team_name:
                        team_name = "Unassigned"
                        
                    if team_name in teams_data:
                        teams_data[team_name]["active_members"].add(normalized_email)
                        
                        # Count ALL traces with user_email, even if question is empty
                        teams_data[team_name]["total_questions"] += 1
                        
                        # Only add to questions_list if question exists (to avoid empty strings)
                        if question:
                            teams_data[team_name]["questions_list"].append(str(question))
                else:
                    traces_without_email += 1
            
            logger.info(f"[LANGFUSE ANALYTICS] Traces with user_email: {traces_with_email}, Traces without user_email: {traces_without_email}")
        
        # Calculate unique questions and top questions per team
        team_stats = []
        for team_name, team_info in teams_data.items():
            try:
                unique_questions = len(set(team_info["questions_list"]))
                question_counter = Counter(team_info["questions_list"])
                top_questions = question_counter.most_common(5)
            except:
                unique_questions = 0
                top_questions = []
            
            team_stats.append({
                "team_name": team_name,
                "lead": team_info["lead"],
                "lead_email": team_info["lead_email"],
                "member_count": team_info["member_count"],
                "active_members_count": len(team_info["active_members"]),
                "color": team_info["color"],
                "total_questions": team_info["total_questions"],
                "unique_questions": unique_questions,
                "top_questions": [
                    {"question": q[0], "count": q[1]} for q in top_questions
                ]
            })
        
        # Sort by total questions (descending)
        team_stats.sort(key=lambda x: x["total_questions"], reverse=True)
        
        total_questions = sum(t["total_questions"] for t in team_stats)
        total_active_teams = sum(1 for t in team_stats if t["total_questions"] > 0)
        
        # Log summary
        logger.info(f"[LANGFUSE ANALYTICS] ===== Teams Summary Results =====")
        logger.info(f"[LANGFUSE ANALYTICS] Total pages fetched: {total_pages_fetched}")
        logger.info(f"[LANGFUSE ANALYTICS] Total traces fetched: {total_traces_fetched}")
        logger.info(f"[LANGFUSE ANALYTICS] Total traces with user_email: {traces_with_email}")
        logger.info(f"[LANGFUSE ANALYTICS] Total teams: {len(team_stats)}")
        logger.info(f"[LANGFUSE ANALYTICS] Active teams (with traces): {total_active_teams}")
        logger.info(f"[LANGFUSE ANALYTICS] Total traces across all teams: {total_questions}")
        logger.info(f"[LANGFUSE ANALYTICS] ===== Teams Summary Request Completed =====")
        
        return {
            "status": "success",
            "time_filter": time_filter,
            "teams": team_stats,
            "total_teams": len(team_stats),
            "total_questions": total_questions,
            "total_active_teams": total_active_teams
        }
        
    except Exception as e:
        logger.error(f"[LANGFUSE ANALYTICS] Teams analytics fetch failed: {e}")
        import traceback
        logger.error(f"[LANGFUSE ANALYTICS] Traceback: {traceback.format_exc()}")
        traceback.print_exc()
        return {"error": str(e), "status": "error"}


@router.get("/analytics/langfuse/teams/details")
async def get_team_details(
    team_name: str = Query(..., description="Team name"),
    time_filter: str = Query("today", description="today|yesterday|this_week|last_week|last_7_days|all"),
    current_user: dict = Depends(require_restricted_admin)
):
    """
    Get detailed analytics for a specific team.
    
    Returns:
    - All team members with their individual stats
    - Team-wide question analysis
    - Member engagement metrics
    """
    try:
        from app.langfuse_integration import langfuse_client
        from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
        from app.models.teams import get_team_by_name, get_all_team_members_emails
        import asyncio
        from datetime import datetime, timezone, timedelta, timezone
        
        logger.info("[LANGFUSE ANALYTICS] ===== Team Details Request Started =====")
        logger.info(f"[LANGFUSE ANALYTICS] Endpoint: /analytics/langfuse/teams/details")
        logger.info(f"[LANGFUSE ANALYTICS] Team Name: {team_name}")
        logger.info(f"[LANGFUSE ANALYTICS] Time Filter: {time_filter}")
        logger.info(f"[LANGFUSE ANALYTICS] Requested by: {current_user.get('email', 'unknown')}")
        
        if not langfuse_client:
            logger.error("[LANGFUSE ANALYTICS] Langfuse client not initialized")
            return {"error": "Langfuse client not initialized", "status": "error"}
        
        # Get team info
        team_info = get_team_by_name(team_name)
        if not team_info:
            logger.error(f"[LANGFUSE ANALYTICS] Team '{team_name}' not found")
            return {"error": f"Team '{team_name}' not found", "status": "error"}
        
        logger.info(f"[LANGFUSE ANALYTICS] Team found: {team_name} with {len(team_info.get('members', []))} members")
        
        # Calculate date range
        now = datetime.now(timezone.utc)
        start_time = now
        end_time = now
        
        if time_filter == "today":
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now
        elif time_filter == "yesterday":
            yesterday = now - timedelta(days=1)
            start_time = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "this_week":
            start_time = now - timedelta(days=now.weekday())
            start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now
        elif time_filter == "last_week":
            days_since_monday = now.weekday()
            last_monday = now - timedelta(days=days_since_monday + 7)
            start_time = last_monday.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = (last_monday + timedelta(days=6)).replace(
                hour=23, minute=59, second=59, microsecond=999999
            )
        elif time_filter == "last_7_days":
            start_time = now - timedelta(days=7)
            end_time = now
        else:
            start_time = None
            end_time = None
        
        # Log time frame details
        if start_time and end_time:
            logger.info(f"[LANGFUSE ANALYTICS] Date Range: {start_time.isoformat()} to {end_time.isoformat()}")
            logger.info(f"[LANGFUSE ANALYTICS] Time Span: {(end_time - start_time).total_seconds() / 86400:.2f} days")
        else:
            logger.info("[LANGFUSE ANALYTICS] Date Range: ALL (no time filter)")
        
        logger.info(f"[LANGFUSE ANALYTICS] Fetching: Team details (member stats, questions, engagement)")
        
        # Initialize member stats
        member_stats = {}
        
        # Get all team member emails
        all_team_members_emails = get_all_team_members_emails()
        team_emails = [e.lower() for e in all_team_members_emails.get(team_name, [])]
        
        # Initialize stats for all team members
        for member in team_info.get("members", []):
            email = member.get("email", "").lower()
            member_stats[email] = {
                "name": member.get("name"),
                "email": member.get("email"),
                "total_questions": 0,
                "questions": []
            }
        
        # Add lead
        if team_info.get("lead_email"):
            lead_email = team_info.get("lead_email").lower()
            member_stats[lead_email] = {
                "name": team_info.get("lead"),
                "email": team_info.get("lead_email"),
                "is_lead": True,
                "total_questions": 0,
                "questions": []
            }
        
        # Fetch traces for team members
        page = 1
        batch_limit = 100
        max_pages = 10 if time_filter != "all" else 20
        
        logger.info(f"[LANGFUSE ANALYTICS] Pagination: max_pages={max_pages}, batch_limit={batch_limit}")
        logger.info(f"[LANGFUSE ANALYTICS] Team member emails to filter: {len(team_emails)}")
        
        async with httpx.AsyncClient() as client:
            total_traces_fetched = 0
            total_pages_fetched = 0
            
            while page <= max_pages:
                try:
                    params = {
                        "page": page,
                        "limit": batch_limit
                    }
                    
                    if start_time:
                        params["fromTimestamp"] = start_time.isoformat()
                    if end_time:
                        params["toTimestamp"] = end_time.isoformat()
                    
                    logger.info(f"[LANGFUSE ANALYTICS] Fetching page {page}/{max_pages} from Langfuse API for team {team_name}")
                    logger.debug(f"[LANGFUSE ANALYTICS] API Request params: {params}")
                    
                    response = await client.get(
                        f"{LANGFUSE_HOST}/api/public/traces",
                        params=params,
                        auth=(LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY),
                        timeout=90.0  # Increased from 30s - Langfuse API can be slow
                    )
                    
                    logger.info(f"[LANGFUSE ANALYTICS] API Response: status={response.status_code}, page={page}")
                        
                    if response.status_code == 429:
                        logger.warning(f"[LANGFUSE ANALYTICS] Rate limited at page {page}, stopping pagination")
                        break
                    
                    if response.status_code != 200:
                        logger.error(f"[LANGFUSE ANALYTICS] API error: status={response.status_code}, stopping at page {page}")
                        break
                    
                    traces_response = response.json()
                    traces = traces_response.get("data", [])
                    
                    logger.info(f"[LANGFUSE ANALYTICS] Page {page}: Received {len(traces)} traces")
                    total_traces_fetched += len(traces)
                    total_pages_fetched = page
                    
                    if not traces:
                        logger.info(f"[LANGFUSE ANALYTICS] No more traces at page {page}, stopping pagination")
                        break
                    
                    # Log sample traces for debugging
                    for trace in traces[:3]:
                        metadata = trace.get("metadata", {})
                        logger.debug(
                            "[LANGFUSE ANALYTICS] Trace sample - team=%s id=%s email=%s question=%s",
                            team_name,
                            trace.get("id"),
                            metadata.get("user_email"),
                            str(trace.get("input", ""))[:50] + "..." if len(str(trace.get("input", ""))) > 50 else trace.get("input", ""),
                        )
                
                    # Process traces
                    for trace in traces:
                        metadata = trace.get("metadata", {})
                        user_email = metadata.get("user_email")
                        question = trace.get("input", "")
                        
                        if user_email:
                            user_email_str = str(user_email).lower() if isinstance(user_email, list) else str(user_email).lower()
                            
                            # Check if this user is in the team
                            if user_email_str in member_stats:
                                if question:
                                    member_stats[user_email_str]["total_questions"] += 1
                                    member_stats[user_email_str]["questions"].append(str(question))
                    
                    if len(traces) < batch_limit:
                        logger.info(f"[LANGFUSE ANALYTICS] Last page reached (received {len(traces)} < {batch_limit} traces)")
                        break
                    
                    page += 1
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"[LANGFUSE ANALYTICS] Error fetching team traces at page {page}: {e}")
                    import traceback
                    logger.error(f"[LANGFUSE ANALYTICS] Traceback: {traceback.format_exc()}")
                    break
        
        # Calculate top questions per member and sort
        members_list = []
        for email, stats in member_stats.items():
            try:
                question_counter = Counter(stats["questions"])
                top_questions = question_counter.most_common(3)
            except:
                top_questions = []
            
            members_list.append({
                "name": stats.get("name"),
                "email": stats.get("email"),
                "is_lead": stats.get("is_lead", False),
                "total_questions": stats["total_questions"],
                "top_questions": [{"question": q[0], "count": q[1]} for q in top_questions]
            })
        
        # Sort by total questions
        members_list.sort(key=lambda x: x["total_questions"], reverse=True)
        
        active_members = sum(1 for m in members_list if m["total_questions"] > 0)
        team_total_questions = sum(m["total_questions"] for m in members_list)
        
        # Log summary
        logger.info(f"[LANGFUSE ANALYTICS] ===== Team Details Results =====")
        logger.info(f"[LANGFUSE ANALYTICS] Total pages fetched: {total_pages_fetched}")
        logger.info(f"[LANGFUSE ANALYTICS] Total traces fetched: {total_traces_fetched}")
        logger.info(f"[LANGFUSE ANALYTICS] Team: {team_name}")
        logger.info(f"[LANGFUSE ANALYTICS] Total members: {len(members_list)}")
        logger.info(f"[LANGFUSE ANALYTICS] Active members: {active_members}")
        logger.info(f"[LANGFUSE ANALYTICS] Team total questions: {team_total_questions}")
        logger.info(f"[LANGFUSE ANALYTICS] ===== Team Details Request Completed =====")
        
        return {
            "status": "success",
            "team_name": team_name,
            "lead": team_info.get("lead"),
            "lead_email": team_info.get("lead_email"),
            "color": team_info.get("color"),
            "time_filter": time_filter,
            "members": members_list,
            "total_members": len(members_list),
            "active_members": active_members,
            "team_total_questions": team_total_questions,
            "team_unique_questions": len(set(q for m in members_list for q in m.get("questions", [])))
        }
        
    except Exception as e:
        logger.error(f"[LANGFUSE ANALYTICS] Team details fetch failed: {e}")
        import traceback
        logger.error(f"[LANGFUSE ANALYTICS] Traceback: {traceback.format_exc()}")
        traceback.print_exc()
        return {"error": str(e), "status": "error"}


@router.get("/analytics/langfuse/dashboard-summary")
async def get_langfuse_dashboard_summary(
    time_filter: str = Query("today", description="today|yesterday|this_week|last_week|last_7_days|all"),
    current_user: dict = Depends(require_restricted_admin)
):
    """
    Get a high-level summary for the Langfuse analytics dashboard with date filtering.
    
    Time Filters:
    - today: Today's data only
    - yesterday: Yesterday's data only
    - this_week: Current week data (Monday to Sunday)
    - last_week: Previous calendar week (Monday to Sunday of last week)
    - last_7_days: Rolling 7 days from now
    - all: All available data (default limit 3000 traces)
    
    Returns:
    - Total users
    - Total questions
    - Most active users
    - Top questions
    """
    try:
        from app.langfuse_integration import langfuse_client
        import asyncio
        from datetime import datetime, timezone, timedelta, timezone
        
        logger.info("[LANGFUSE ANALYTICS] ===== Dashboard Summary Request Started =====")
        logger.info(f"[LANGFUSE ANALYTICS] Endpoint: /analytics/langfuse/dashboard-summary")
        logger.info(f"[LANGFUSE ANALYTICS] Time Filter: {time_filter}")
        logger.info(f"[LANGFUSE ANALYTICS] Requested by: {current_user.get('email', 'unknown')}")
        
        if not langfuse_client:
            logger.error("[LANGFUSE ANALYTICS] Langfuse client not initialized")
            return {"error": "Langfuse client not initialized", "status": "error"}
        
        # Calculate date range based on filter
        now = datetime.now(timezone.utc)
        start_time = now
        end_time = now
        
        if time_filter == "today":
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now
        elif time_filter == "yesterday":
            yesterday = now - timedelta(days=1)
            start_time = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "this_week":
            # Monday to now
            start_time = now - timedelta(days=now.weekday())
            start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now
        elif time_filter == "last_week":
            # Previous calendar week (Monday to Sunday of last week)
            days_since_monday = now.weekday()
            # Go back to last Monday
            last_monday = now - timedelta(days=days_since_monday + 7)
            start_time = last_monday.replace(hour=0, minute=0, second=0, microsecond=0)
            # Last Sunday (end of last week)
            end_time = last_monday + timedelta(days=6)
            end_time = end_time.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "last_7_days":
            # Rolling 7 days
            start_time = now - timedelta(days=7)
            end_time = now
        else:  # "all"
            start_time = None
            end_time = None
        
        # Log time frame details
        if start_time and end_time:
            logger.info(f"[LANGFUSE ANALYTICS] Date Range: {start_time.isoformat()} to {end_time.isoformat()}")
            logger.info(f"[LANGFUSE ANALYTICS] Time Span: {(end_time - start_time).total_seconds() / 86400:.2f} days")
        else:
            logger.info("[LANGFUSE ANALYTICS] Date Range: ALL (no time filter)")
        
        logger.info(f"[LANGFUSE ANALYTICS] Fetching: Dashboard summary (users, questions, top users, top questions)")
        
        users_activity = defaultdict(lambda: {"count": 0, "email": "", "name": ""})
        all_questions = []
        
        page = 1
        batch_limit = 100
        max_pages = 10 if time_filter != "all" else 30  # Faster for filtered queries
        
        logger.info(f"[LANGFUSE ANALYTICS] Pagination: max_pages={max_pages}, batch_limit={batch_limit}")
        
        async with httpx.AsyncClient() as client:
            from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
            
            total_traces_fetched = 0
            total_pages_fetched = 0
            
            while page <= max_pages:
                try:
                    # Build params with optional date filter
                    params = {
                        "page": page,
                        "limit": batch_limit
                    }
                    
                    # Add date range if available
                    if start_time:
                        params["fromTimestamp"] = start_time.isoformat()
                    if end_time:
                        params["toTimestamp"] = end_time.isoformat()
                    
                    logger.info(f"[LANGFUSE ANALYTICS] Fetching page {page}/{max_pages} from Langfuse API")
                    logger.debug(f"[LANGFUSE ANALYTICS] API Request params: {params}")
                    
                    response = await client.get(
                        f"{LANGFUSE_HOST}/api/public/traces",
                        params=params,
                        auth=(LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY),
                        timeout=90.0  # Increased timeout - Langfuse API can be slow
                    )
                    
                    logger.info(f"[LANGFUSE ANALYTICS] API Response: status={response.status_code}, page={page}")
                    
                    if response.status_code == 429:  # Rate limited
                        logger.warning(f"[LANGFUSE ANALYTICS] Rate limited at page {page}, stopping pagination")
                        break
                    
                    if response.status_code != 200:
                        logger.error(f"[LANGFUSE ANALYTICS] API error: status={response.status_code}, stopping at page {page}")
                        break
                    
                    traces_response = response.json()
                    traces = traces_response.get("data", [])
                    
                    logger.info(f"[LANGFUSE ANALYTICS] Page {page}: Received {len(traces)} traces")
                    total_traces_fetched += len(traces)
                    total_pages_fetched = page
                    
                    if not traces:
                        logger.info(f"[LANGFUSE ANALYTICS] No more traces at page {page}, stopping pagination")
                        break
                    
                    for trace in traces:
                        user_id = trace.get("userId")
                        metadata = trace.get("metadata", {})
                        question = trace.get("input", "")
                        
                        if user_id:
                            users_activity[user_id]["count"] += 1
                            # Safely extract email (could be string or list)
                            user_email = metadata.get("user_email", "N/A")
                            if isinstance(user_email, list):
                                user_email = user_email[0] if user_email else "N/A"
                            users_activity[user_id]["email"] = str(user_email)
                            
                            # Safely extract name
                            user_name = metadata.get("user_name", "Unknown")
                            if isinstance(user_name, list):
                                user_name = user_name[0] if user_name else "Unknown"
                            users_activity[user_id]["name"] = str(user_name)
                        
                        if question:
                            all_questions.append(str(question))
                    
                    if len(traces) < batch_limit:
                        logger.info(f"[LANGFUSE ANALYTICS] Last page reached (received {len(traces)} < {batch_limit} traces)")
                        break
                    
                    page += 1
                    await asyncio.sleep(0.5)  # Rate limiting delay
                except Exception as e:
                    logger.error(f"[LANGFUSE ANALYTICS] API error at page {page}: {e}")
                    import traceback
                    logger.error(f"[LANGFUSE ANALYTICS] Traceback: {traceback.format_exc()}")
                    break
        
        # Get most active users (top 10)
        most_active = sorted(
            users_activity.items(),
            key=lambda x: x[1]["count"],
            reverse=True
        )[:10]
        
        # Get top questions - safely handle Counter
        try:
            question_counter = Counter(all_questions)
            top_questions = question_counter.most_common(5)
        except Exception as e:
            logger.error(f"[LANGFUSE ANALYTICS] Counter error: {e}")
            top_questions = []
        
        # Log summary
        logger.info(f"[LANGFUSE ANALYTICS] ===== Dashboard Summary Results =====")
        logger.info(f"[LANGFUSE ANALYTICS] Total pages fetched: {total_pages_fetched}")
        logger.info(f"[LANGFUSE ANALYTICS] Total traces fetched: {total_traces_fetched}")
        logger.info(f"[LANGFUSE ANALYTICS] Total unique users: {len(users_activity)}")
        logger.info(f"[LANGFUSE ANALYTICS] Total questions: {len(all_questions)}")
        logger.info(f"[LANGFUSE ANALYTICS] Unique questions: {len(question_counter) if 'question_counter' in locals() else 0}")
        logger.info(f"[LANGFUSE ANALYTICS] Most active users (top 10): {len(most_active)}")
        logger.info(f"[LANGFUSE ANALYTICS] Top questions (top 5): {len(top_questions)}")
        logger.info(f"[LANGFUSE ANALYTICS] ===== Dashboard Summary Request Completed =====")
        
        return {
            "status": "success",
            "summary": {
                "total_users": len(users_activity),
                "total_questions": len(all_questions),
                "unique_questions": len(question_counter),
                "average_questions_per_user": round(len(all_questions) / len(users_activity), 2) if users_activity else 0
            },
            "most_active_users": [
                {
                    "user_id": user[0],
                    "email": user[1]["email"],
                    "name": user[1]["name"],
                    "questions_asked": user[1]["count"]
                }
                for user in most_active
            ],
            "top_questions": [
                {
                    "question": q[0],
                    "times_asked": q[1]
                }
                for q in top_questions
            ]
        }
    
    except Exception as e:
        logger.error(f"[LANGFUSE ANALYTICS] Dashboard summary fetch failed: {e}")
        import traceback
        logger.error(f"[LANGFUSE ANALYTICS] Traceback: {traceback.format_exc()}")
        return {"error": str(e), "status": "error"}


@router.get("/analytics/langfuse/users")
async def get_langfuse_users_analytics(
    time_filter: str = Query("today", description="today|yesterday|this_week|last_week|last_7_days|all"),
    current_user: dict = Depends(require_restricted_admin)
):
    """
    Fetch all users from Langfuse with their analytics with date filtering.
    
    Time Filters:
    - today: Today's data only
    - yesterday: Yesterday's data only
    - this_week: Current week data
    - last_week: Previous calendar week (Monday to Sunday of last week)
    - last_7_days: Rolling 7 days from now
    - all: All available data
    
    Returns:
    - User ID and email
    - Total questions asked
    - Top questions
    - Last activity
    """
    try:
        from app.langfuse_integration import langfuse_client
        from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
        import asyncio
        from datetime import datetime, timezone, timedelta, timezone
        
        logger.info("[LANGFUSE ANALYTICS] ===== Users Analytics Request Started =====")
        logger.info(f"[LANGFUSE ANALYTICS] Endpoint: /analytics/langfuse/users")
        logger.info(f"[LANGFUSE ANALYTICS] Time Filter: {time_filter}")
        logger.info(f"[LANGFUSE ANALYTICS] Requested by: {current_user.get('email', 'unknown')}")
        
        if not langfuse_client:
            logger.error("[LANGFUSE ANALYTICS] Langfuse client not initialized")
            return {
                "error": "Langfuse client not initialized",
                "status": "error"
            }
        
        # Calculate date range
        now = datetime.now(timezone.utc)
        start_time = now
        end_time = now
        
        if time_filter == "today":
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now
        elif time_filter == "yesterday":
            yesterday = now - timedelta(days=1)
            start_time = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "this_week":
            start_time = now - timedelta(days=now.weekday())
            start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now
        elif time_filter == "last_week":
            days_since_monday = now.weekday()
            last_monday = now - timedelta(days=days_since_monday + 7)
            start_time = last_monday.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = (last_monday + timedelta(days=6)).replace(
                hour=23, minute=59, second=59, microsecond=999999
            )
        elif time_filter == "last_7_days":
            start_time = now - timedelta(days=7)
            end_time = now
        else:
            start_time = None
            end_time = None
        
        # Log time frame details
        if start_time and end_time:
            logger.info(f"[LANGFUSE ANALYTICS] Date Range: {start_time.isoformat()} to {end_time.isoformat()}")
            logger.info(f"[LANGFUSE ANALYTICS] Time Span: {(end_time - start_time).total_seconds() / 86400:.2f} days")
        else:
            logger.info("[LANGFUSE ANALYTICS] Date Range: ALL (no time filter)")
        
        logger.info(f"[LANGFUSE ANALYTICS] Fetching: All users with their analytics (questions, top questions, activity)")
        
        users_data = {}
        page = 1
        limit = 100
        max_pages = 10 if time_filter != "all" else 30  # Faster for filtered queries
        
        logger.info(f"[LANGFUSE ANALYTICS] Pagination: max_pages={max_pages}, limit={limit}")
        
        async with httpx.AsyncClient() as client:
            total_traces_fetched = 0
            total_pages_fetched = 0
            
            while page <= max_pages:
                try:
                    # Fetch traces with pagination and date filter
                    params = {
                        "page": page,
                        "limit": limit
                    }
                    
                    if start_time:
                        params["fromTimestamp"] = start_time.isoformat()
                    if end_time:
                        params["toTimestamp"] = end_time.isoformat()
                    
                    logger.info(f"[LANGFUSE ANALYTICS] Fetching page {page}/{max_pages} from Langfuse API")
                    logger.debug(f"[LANGFUSE ANALYTICS] API Request params: {params}")
                    
                    response = await client.get(
                        f"{LANGFUSE_HOST}/api/public/traces",
                        params=params,
                        auth=(LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY),
                        timeout=90.0  # Increased timeout - Langfuse API can be slow
                    )
                    
                    logger.info(f"[LANGFUSE ANALYTICS] API Response: status={response.status_code}, page={page}")
                    
                    if response.status_code == 429:  # Rate limited
                        logger.warning(f"[LANGFUSE ANALYTICS] Rate limited at page {page}, stopping")
                        break
                    
                    if response.status_code != 200:
                        logger.error(f"[LANGFUSE ANALYTICS] API error: status={response.status_code}, stopping at page {page}")
                        break
                    
                    traces_response = response.json()
                    traces = traces_response.get("data", [])
                    
                    logger.info(f"[LANGFUSE ANALYTICS] Page {page}: Received {len(traces)} traces")
                    total_traces_fetched += len(traces)
                    total_pages_fetched = page
                    
                    if not traces:
                        logger.info(f"[LANGFUSE ANALYTICS] No more traces at page {page}, stopping pagination")
                        break
                    
                    # Process each trace
                    for trace in traces:
                        # Extract metadata
                        metadata = trace.get("metadata", {})
                        user_id = trace.get("userId") or metadata.get("user_id")
                        user_email = metadata.get("user_email")
                        user_name = metadata.get("user_name")
                        
                        # Safely handle list types
                        if isinstance(user_email, list):
                            user_email = user_email[0] if user_email else None
                        if isinstance(user_name, list):
                            user_name = user_name[0] if user_name else None
                        
                        if not user_id:
                            continue
                        
                        # Initialize user record if not exists
                        if user_id not in users_data:
                            users_data[user_id] = {
                                "user_id": user_id,
                                "email": str(user_email) if user_email else "N/A",
                                "name": str(user_name) if user_name else "Unknown",
                                "total_questions": 0,
                                "questions": [],
                                "first_question_at": None,
                                "last_question_at": None,
                                "metadata": metadata
                            }
                        
                        # Extract question (input) and answer (output)
                        question = trace.get("input") or ""
                        timestamp = trace.get("timestamp")
                        
                        # Update user stats
                        if question:
                            users_data[user_id]["total_questions"] += 1
                            users_data[user_id]["questions"].append({
                                "question": str(question),
                                "asked_at": timestamp
                            })
                            
                            if not users_data[user_id]["first_question_at"]:
                                users_data[user_id]["first_question_at"] = timestamp
                            users_data[user_id]["last_question_at"] = timestamp
                    
                    # Check if there are more pages
                    if len(traces) < limit:
                        logger.info(f"[LANGFUSE ANALYTICS] Last page reached (received {len(traces)} < {limit} traces)")
                        break
                    
                    page += 1
                    await asyncio.sleep(0.5)  # Rate limiting delay
                except Exception as e:
                    logger.error(f"[LANGFUSE ANALYTICS] Error fetching traces at page {page}: {e}")
                    import traceback
                    logger.error(f"[LANGFUSE ANALYTICS] Traceback: {traceback.format_exc()}")
                    break
        
        # Process data - find top questions
        for user_id, user_info in users_data.items():
            questions = [q["question"] for q in user_info["questions"]]
            
            # Get top 5 most asked questions
            if questions:
                question_counter = Counter(questions)
                top_questions = question_counter.most_common(5)
                user_info["top_questions"] = [
                    {
                        "question": q[0],
                        "count": q[1]
                    }
                    for q in top_questions
                ]
            else:
                user_info["top_questions"] = []
            
            # Remove raw questions list (keep only aggregated data)
            user_info.pop("questions", None)
        
        # Group by department
        users_by_department = defaultdict(list)
        for user_id, user_info in users_data.items():
            dept = user_info["metadata"].get("department", "Unassigned")
            users_by_department[dept].append(user_info)
        
        # Log summary
        total_questions = sum(u["total_questions"] for u in users_data.values())
        logger.info(f"[LANGFUSE ANALYTICS] ===== Users Analytics Results =====")
        logger.info(f"[LANGFUSE ANALYTICS] Total pages fetched: {total_pages_fetched}")
        logger.info(f"[LANGFUSE ANALYTICS] Total traces fetched: {total_traces_fetched}")
        logger.info(f"[LANGFUSE ANALYTICS] Total unique users: {len(users_data)}")
        logger.info(f"[LANGFUSE ANALYTICS] Total questions: {total_questions}")
        logger.info(f"[LANGFUSE ANALYTICS] Departments found: {len(users_by_department)}")
        logger.info(f"[LANGFUSE ANALYTICS] ===== Users Analytics Request Completed =====")
        
        return {
            "status": "success",
            "total_users": len(users_data),
            "total_questions": total_questions,
            "users": list(users_data.values()),
            "users_by_department": dict(users_by_department),
            "department_summary": {
                dept: {
                    "user_count": len(users),
                    "total_questions": sum(u["total_questions"] for u in users)
                }
                for dept, users in users_by_department.items()
            }
        }
    
    except Exception as e:
        logger.error(f"[LANGFUSE ANALYTICS] Users analytics fetch failed: {e}")
        import traceback
        logger.error(f"[LANGFUSE ANALYTICS] Traceback: {traceback.format_exc()}")
        traceback.print_exc()
        return {
            "error": str(e),
            "status": "error"
        }


@router.get("/analytics/langfuse/users/{user_id}")
async def get_user_langfuse_analytics(
    user_id: str,
    time_filter: str = Query("today", description="today|yesterday|this_week|last_week|last_7_days|all"),
    current_user: dict = Depends(require_restricted_admin)
):
    """
    Get detailed analytics for a specific user with date filtering.
    
    Time Filters:
    - today: Today's data only
    - yesterday: Yesterday's data only
    - this_week: Current week data
    - last_week: Previous calendar week (Monday to Sunday of last week)
    - last_7_days: Rolling 7 days from now
    - all: All available data
    
    Returns:
    - All questions asked
    - Top 10 questions
    - Activity timeline
    """
    try:
        from app.langfuse_integration import langfuse_client
        from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
        import asyncio
        from datetime import datetime, timezone, timedelta, timezone
        
        logger.info("[LANGFUSE ANALYTICS] ===== User Analytics Request Started =====")
        logger.info(f"[LANGFUSE ANALYTICS] Endpoint: /analytics/langfuse/users/{user_id}")
        logger.info(f"[LANGFUSE ANALYTICS] User ID: {user_id}")
        logger.info(f"[LANGFUSE ANALYTICS] Time Filter: {time_filter}")
        logger.info(f"[LANGFUSE ANALYTICS] Requested by: {current_user.get('email', 'unknown')}")
        
        if not langfuse_client:
            logger.error("[LANGFUSE ANALYTICS] Langfuse client not initialized")
            return {"error": "Langfuse client not initialized"}
        
        # Calculate date range
        now = datetime.now(timezone.utc)
        start_time = now
        end_time = now
        
        if time_filter == "today":
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now
        elif time_filter == "yesterday":
            yesterday = now - timedelta(days=1)
            start_time = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "this_week":
            start_time = now - timedelta(days=now.weekday())
            start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now
        elif time_filter == "last_week":
            days_since_monday = now.weekday()
            last_monday = now - timedelta(days=days_since_monday + 7)
            start_time = last_monday.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = (last_monday + timedelta(days=6)).replace(
                hour=23, minute=59, second=59, microsecond=999999
            )
        elif time_filter == "last_7_days":
            start_time = now - timedelta(days=7)
            end_time = now
        else:
            start_time = None
            end_time = None
        
        # Log time frame details
        if start_time and end_time:
            logger.info(f"[LANGFUSE ANALYTICS] Date Range: {start_time.isoformat()} to {end_time.isoformat()}")
            logger.info(f"[LANGFUSE ANALYTICS] Time Span: {(end_time - start_time).total_seconds() / 86400:.2f} days")
        else:
            logger.info("[LANGFUSE ANALYTICS] Date Range: ALL (no time filter)")
        
        logger.info(f"[LANGFUSE ANALYTICS] Fetching: User-specific analytics (questions, answers, activity timeline)")
        
        user_traces = []
        page = 1
        limit = 100
        max_pages = 10 if time_filter != "all" else 20  # Faster for filtered queries
        
        logger.info(f"[LANGFUSE ANALYTICS] Pagination: max_pages={max_pages}, limit={limit}")
        
        async with httpx.AsyncClient() as client:
            total_traces_fetched = 0
            total_pages_fetched = 0
            
            while page <= max_pages:
                try:
                    params = {
                        "page": page,
                        "limit": limit,
                        "userId": user_id
                    }
                    
                    if start_time:
                        params["fromTimestamp"] = start_time.isoformat()
                    if end_time:
                        params["toTimestamp"] = end_time.isoformat()
                    
                    logger.info(f"[LANGFUSE ANALYTICS] Fetching page {page}/{max_pages} from Langfuse API for user {user_id}")
                    logger.debug(f"[LANGFUSE ANALYTICS] API Request params: {params}")
                    
                    response = await client.get(
                        f"{LANGFUSE_HOST}/api/public/traces",
                        params=params,
                        auth=(LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY),
                        timeout=90.0  # Increased timeout - Langfuse API can be slow
                    )
                    
                    logger.info(f"[LANGFUSE ANALYTICS] API Response: status={response.status_code}, page={page}")
                    
                    if response.status_code == 429:  # Rate limited
                        logger.warning(f"[LANGFUSE ANALYTICS] Rate limited at page {page}, stopping")
                        break
                    
                    if response.status_code != 200:
                        logger.error(f"[LANGFUSE ANALYTICS] API error: status={response.status_code}, stopping at page {page}")
                        break
                    
                    traces_response = response.json()
                    traces = traces_response.get("data", [])
                    
                    logger.info(f"[LANGFUSE ANALYTICS] Page {page}: Received {len(traces)} traces for user {user_id}")
                    total_traces_fetched += len(traces)
                    total_pages_fetched = page
                    
                    if not traces:
                        logger.info(f"[LANGFUSE ANALYTICS] No more traces at page {page}, stopping pagination")
                        break
                    
                    user_traces.extend(traces)
                    
                    if len(traces) < limit:
                        logger.info(f"[LANGFUSE ANALYTICS] Last page reached (received {len(traces)} < {limit} traces)")
                        break
                    
                    page += 1
                    await asyncio.sleep(0.5)  # Rate limiting delay
                except Exception as e:
                    logger.error(f"[LANGFUSE ANALYTICS] Error fetching user traces at page {page}: {e}")
                    import traceback
                    logger.error(f"[LANGFUSE ANALYTICS] Traceback: {traceback.format_exc()}")
                    break
        
        # Aggregate data
        questions_list = []
        for trace in user_traces:
            question = trace.get("input", "")
            answer = trace.get("output", "")
            timestamp = trace.get("timestamp")
            metadata = trace.get("metadata", {})
            
            if question:
                # Safely handle list types
                intent = metadata.get("intent", {})
                if isinstance(intent, list):
                    intent = intent[0] if intent else {}
                
                confidence = metadata.get("confidence", {})
                if isinstance(confidence, list):
                    confidence = confidence[0] if confidence else {}
                
                questions_list.append({
                    "question": str(question),
                    "answer": str(answer[:500]) if answer else "N/A",  # First 500 chars
                    "asked_at": timestamp,
                    "intent": intent.get("detected") if isinstance(intent, dict) else None,
                    "confidence": confidence.get("overall") if isinstance(confidence, dict) else None
                })
        
        # Get top questions - safely
        try:
            question_counter = Counter([q["question"] for q in questions_list])
            top_questions = question_counter.most_common(10)
        except Exception as e:
            logger.error(f"[LANGFUSE ANALYTICS] Counter error: {e}")
            top_questions = []
        
        # Get user info from first trace
        user_email = "N/A"
        user_name = "Unknown"
        if user_traces:
            metadata = user_traces[0].get("metadata", {})
            user_email = metadata.get("user_email", "N/A")
            user_name = metadata.get("user_name", "Unknown")
        
        # Log summary
        logger.info(f"[LANGFUSE ANALYTICS] ===== User Analytics Results =====")
        logger.info(f"[LANGFUSE ANALYTICS] Total pages fetched: {total_pages_fetched}")
        logger.info(f"[LANGFUSE ANALYTICS] Total traces fetched: {total_traces_fetched}")
        logger.info(f"[LANGFUSE ANALYTICS] User: {user_name} ({user_email})")
        logger.info(f"[LANGFUSE ANALYTICS] Total questions: {len(questions_list)}")
        logger.info(f"[LANGFUSE ANALYTICS] Top questions (top 10): {len(top_questions)}")
        logger.info(f"[LANGFUSE ANALYTICS] ===== User Analytics Request Completed =====")
        
        return {
            "status": "success",
            "user_id": user_id,
            "email": user_email,
            "name": user_name,
            "total_questions": len(questions_list),
            "total_traces": len(user_traces),
            "top_questions": [
                {
                    "question": q[0],
                    "frequency": q[1]
                }
                for q in top_questions
            ],
            "recent_questions": questions_list[-20:],  # Last 20 questions
            "all_questions": questions_list
        }
    
    except Exception as e:
        print(f"[ERROR] User analytics fetch failed: {e}")
        return {"error": str(e), "status": "error"}


@router.get("/analytics/langfuse/top-questions")
async def get_top_questions_global(
    limit: int = Query(20, ge=1, le=100),
    time_filter: str = Query("today", description="today|yesterday|this_week|last_week|last_7_days|all"),
    current_user: dict = Depends(require_restricted_admin)
):
    """
    Get the top questions asked across all users with date filtering.
    Helps identify common user pain points and interests.
    
    Time Filters:
    - today: Today's data only
    - yesterday: Yesterday's data only
    - this_week: Current week data
    - last_week: Previous calendar week (Monday to Sunday of last week)
    - last_7_days: Rolling 7 days from now
    - all: All available data
    """
    try:
        from app.langfuse_integration import langfuse_client
        from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
        import asyncio
        from datetime import datetime, timezone, timedelta, timezone
        
        logger.info("[LANGFUSE ANALYTICS] ===== Top Questions Request Started =====")
        logger.info(f"[LANGFUSE ANALYTICS] Endpoint: /analytics/langfuse/top-questions")
        logger.info(f"[LANGFUSE ANALYTICS] Limit: {limit}")
        logger.info(f"[LANGFUSE ANALYTICS] Time Filter: {time_filter}")
        logger.info(f"[LANGFUSE ANALYTICS] Requested by: {current_user.get('email', 'unknown')}")
        
        if not langfuse_client:
            logger.error("[LANGFUSE ANALYTICS] Langfuse client not initialized")
            return {"error": "Langfuse client not initialized"}
        
        # Calculate date range
        now = datetime.now(timezone.utc)
        start_time = now
        end_time = now
        
        if time_filter == "today":
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now
        elif time_filter == "yesterday":
            yesterday = now - timedelta(days=1)
            start_time = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "this_week":
            start_time = now - timedelta(days=now.weekday())
            start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now
        elif time_filter == "last_week":
            days_since_monday = now.weekday()
            last_monday = now - timedelta(days=days_since_monday + 7)
            start_time = last_monday.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = (last_monday + timedelta(days=6)).replace(
                hour=23, minute=59, second=59, microsecond=999999
            )
        elif time_filter == "last_7_days":
            start_time = now - timedelta(days=7)
            end_time = now
        else:
            start_time = None
            end_time = None
        
        # Log time frame details
        if start_time and end_time:
            logger.info(f"[LANGFUSE ANALYTICS] Date Range: {start_time.isoformat()} to {end_time.isoformat()}")
            logger.info(f"[LANGFUSE ANALYTICS] Time Span: {(end_time - start_time).total_seconds() / 86400:.2f} days")
        else:
            logger.info("[LANGFUSE ANALYTICS] Date Range: ALL (no time filter)")
        
        logger.info(f"[LANGFUSE ANALYTICS] Fetching: Top {limit} questions across all users")
        
        all_questions = []
        page = 1
        batch_limit = 100
        max_pages = 10 if time_filter != "all" else 30  # Faster for filtered queries
        
        logger.info(f"[LANGFUSE ANALYTICS] Pagination: max_pages={max_pages}, batch_limit={batch_limit}")
        
        async with httpx.AsyncClient() as client:
            total_traces_fetched = 0
            total_pages_fetched = 0
            
            while page <= max_pages:
                try:
                    params = {
                        "page": page,
                        "limit": batch_limit
                    }
                    
                    if start_time:
                        params["fromTimestamp"] = start_time.isoformat()
                    if end_time:
                        params["toTimestamp"] = end_time.isoformat()
                    
                    logger.info(f"[LANGFUSE ANALYTICS] Fetching page {page}/{max_pages} from Langfuse API")
                    logger.debug(f"[LANGFUSE ANALYTICS] API Request params: {params}")
                    
                    response = await client.get(
                        f"{LANGFUSE_HOST}/api/public/traces",
                        params=params,
                        auth=(LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY),
                        timeout=90.0  # Increased timeout - Langfuse API can be slow
                    )
                    
                    logger.info(f"[LANGFUSE ANALYTICS] API Response: status={response.status_code}, page={page}")
                    
                    if response.status_code == 429:  # Rate limited
                        logger.warning(f"[LANGFUSE ANALYTICS] Rate limited at page {page}, stopping")
                        break
                    
                    if response.status_code != 200:
                        logger.error(f"[LANGFUSE ANALYTICS] API error: status={response.status_code}, stopping at page {page}")
                        break
                    
                    traces_response = response.json()
                    traces = traces_response.get("data", [])
                    
                    logger.info(f"[LANGFUSE ANALYTICS] Page {page}: Received {len(traces)} traces")
                    total_traces_fetched += len(traces)
                    total_pages_fetched = page
                    
                    if not traces:
                        logger.info(f"[LANGFUSE ANALYTICS] No more traces at page {page}, stopping pagination")
                        break
                    
                    for trace in traces:
                        question = trace.get("input", "")
                        if question:
                            all_questions.append(str(question))
                    
                    if len(traces) < batch_limit:
                        logger.info(f"[LANGFUSE ANALYTICS] Last page reached (received {len(traces)} < {batch_limit} traces)")
                        break
                    
                    page += 1
                    await asyncio.sleep(0.5)  # Rate limiting delay
                except Exception as e:
                    logger.error(f"[LANGFUSE ANALYTICS] Error fetching traces at page {page}: {e}")
                    import traceback
                    logger.error(f"[LANGFUSE ANALYTICS] Traceback: {traceback.format_exc()}")
                    break
        
        # Get top questions
        try:
            question_counter = Counter(all_questions)
            top_questions = question_counter.most_common(limit)
        except Exception as e:
            logger.error(f"[LANGFUSE ANALYTICS] Counter error: {e}")
            top_questions = []
            question_counter = Counter()
        
        # Log summary
        logger.info(f"[LANGFUSE ANALYTICS] ===== Top Questions Results =====")
        logger.info(f"[LANGFUSE ANALYTICS] Total pages fetched: {total_pages_fetched}")
        logger.info(f"[LANGFUSE ANALYTICS] Total traces fetched: {total_traces_fetched}")
        logger.info(f"[LANGFUSE ANALYTICS] Total questions asked: {len(all_questions)}")
        logger.info(f"[LANGFUSE ANALYTICS] Total unique questions: {len(question_counter)}")
        logger.info(f"[LANGFUSE ANALYTICS] Top questions returned: {len(top_questions)}")
        logger.info(f"[LANGFUSE ANALYTICS] ===== Top Questions Request Completed =====")
        
        return {
            "status": "success",
            "total_unique_questions": len(question_counter),
            "total_questions_asked": len(all_questions),
            "top_questions": [
                {
                    "question": q[0],
                    "times_asked": q[1],
                    "percentage": round((q[1] / len(all_questions)) * 100, 2) if all_questions else 0
                }
                for q in top_questions
            ]
        }
    
    except Exception as e:
        print(f"[ERROR] Top questions fetch failed: {e}")
        return {"error": str(e), "status": "error"}

# ---------------- Manual Fine-Tuning System ----------------

@router.post("/fine-tuning/trigger")
async def trigger_manual_fine_tuning(current_user: dict = Depends(require_admin)):
    """Manually trigger fine-tuning when needed. Requires admin access."""
    try:
        # Check if we have enough data for fine-tuning
        dataset_status = await check_dataset_quality()
        
        if not dataset_status["ready_for_training"]:
            return {
                "status": "insufficient_data",
                "message": f"Not enough data for fine-tuning. Need at least {dataset_status['min_required']} samples, have {dataset_status['current_count']}",
                "recommendations": dataset_status["recommendations"]
            }
        
        # Start fine-tuning process
        fine_tuning_result = await start_fine_tuning_process()
        
        return {
            "status": "success",
            "message": "Fine-tuning process started",
            "dataset_info": dataset_status,
            "process_id": fine_tuning_result["process_id"]
        }
        
    except Exception as e:
        return {"error": f"Failed to trigger fine-tuning: {str(e)}"}

@router.get("/fine-tuning/status")
async def get_fine_tuning_status(current_user: dict = Depends(require_admin)):
    """Get the status of fine-tuning process. Requires admin access."""
    try:
        # Check dataset quality
        dataset_status = await check_dataset_quality()
        
        # Check if fine-tuning is in progress
        training_status = await get_training_status()
        
        return {
            "dataset_quality": dataset_status,
            "training_status": training_status,
            "recommendations": await get_fine_tuning_recommendations()
        }
        
    except Exception as e:
        return {"error": f"Failed to get fine-tuning status: {str(e)}"}

async def check_dataset_quality():
    """Check if dataset is ready for fine-tuning."""
    try:
        dataset_file = "./data/corrected_responses/corrected_responses.json"
        
        if not os.path.exists(dataset_file):
            return {
                "ready_for_training": False,
                "current_count": 0,
                "min_required": 10,
                "recommendations": ["Collect more negative feedback data"]
            }
        
        with open(dataset_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        corrected_responses = data.get("corrected_responses", [])
        current_count = len(corrected_responses)
        min_required = 10  # Minimum samples needed
        
        # Quality checks
        quality_score = 0
        recommendations = []
        
        if current_count >= min_required:
            quality_score += 40
        else:
            recommendations.append(f"Need {min_required - current_count} more samples")
        
        # Check for diverse feedback
        unique_questions = len(set([item.get("original_question", "") for item in corrected_responses]))
        if unique_questions >= 5:
            quality_score += 30
        else:
            recommendations.append("Need more diverse question types")
        
        # Check for recent data
        recent_count = 0
        for item in corrected_responses:
            timestamp = datetime.fromisoformat(item.get("timestamp", ""))
            if (datetime.now() - timestamp).days <= 7:
                recent_count += 1
        
        if recent_count >= 3:
            quality_score += 30
        else:
            recommendations.append("Need more recent feedback data")
        
        return {
            "ready_for_training": quality_score >= 70,
            "current_count": current_count,
            "min_required": min_required,
            "quality_score": quality_score,
            "unique_questions": unique_questions,
            "recent_samples": recent_count,
            "recommendations": recommendations
        }
        
    except Exception as e:
        return {
            "ready_for_training": False,
            "error": str(e),
            "recommendations": ["Fix dataset issues"]
        }

async def start_fine_tuning_process():
    """Start the fine-tuning process."""
    try:
        # Generate a unique process ID
        process_id = f"ft_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # In a real implementation, you would:
        # 1. Export data from Langfuse
        # 2. Prepare training data
        # 3. Start fine-tuning job
        # 4. Monitor progress
        
        # For now, simulate the process
        training_status = {
            "process_id": process_id,
            "status": "started",
            "start_time": datetime.now().isoformat(),
            "estimated_completion": (datetime.now().timestamp() + 3600),  # 1 hour from now
            "progress": 0
        }
        
        # Save training status
        status_file = "./data/fine_tuning_status.json"
        with open(status_file, 'w', encoding='utf-8') as f:
            json.dump(training_status, f, indent=2, ensure_ascii=False)
        
        return training_status
        
    except Exception as e:
        print(f"Failed to start fine-tuning: {e}")
        raise e

async def get_training_status():
    """Get current training status."""
    try:
        status_file = "./data/fine_tuning_status.json"
        
        if not os.path.exists(status_file):
            return {"status": "no_training", "message": "No fine-tuning in progress"}
        
        with open(status_file, 'r', encoding='utf-8') as f:
            status = json.load(f)
        
        return status
        
    except Exception as e:
        return {"status": "error", "message": str(e)}

async def get_fine_tuning_recommendations():
    """Get recommendations for when to run fine-tuning."""
    try:
        dataset_status = await check_dataset_quality()
        
        recommendations = []
        
        if not dataset_status["ready_for_training"]:
            recommendations.append("[FAIL] Not ready for fine-tuning - insufficient data")
            recommendations.extend(dataset_status["recommendations"])
        else:
            recommendations.append("[OK] Ready for fine-tuning!")
            recommendations.append("Consider running fine-tuning when you have 20+ samples")
            recommendations.append("Run fine-tuning weekly for best results")
        
        return recommendations
        
    except Exception as e:
        return [f"Error getting recommendations: {str(e)}"]

# ---------------- Auto-Correction Workflow ----------------

async def get_trace_data(trace_id: str):
    """Get original question and response from trace data."""
    try:
        # In a real implementation, you would retrieve this from Langfuse
        # For now, we'll simulate it
        return {
            "question": "Sample question from trace",
            "response": "Sample response from trace"
        }
    except Exception as e:
        print(f"Error retrieving trace data: {e}")
        return None

async def trigger_auto_correction_workflow(trace_id: str, user_query: str, bad_response: str, user_comment: str = None):
    """Complete auto-correction workflow."""
    try:
        # Step 1: Generate improved response using LLM
        improved_response = await generate_improved_response(user_query, bad_response, user_comment)
        
        # Step 2: Save to correction dataset
        await save_correction_to_dataset(user_query, bad_response, improved_response, trace_id, user_comment)
        
        # Step 3: Update Langfuse trace (optional)
        await update_langfuse_trace(trace_id, improved_response)
        
        return improved_response
        
    except Exception as e:
        print(f"Auto-correction workflow failed: {e}")
        raise e

async def generate_improved_response(user_query: str, bad_response: str, user_comment: str = None):
    """Use LLM with RAG to generate an improved response using the knowledge base."""
    try:
        # CRITICAL: Retrieve relevant documents from Weaviate for context
        # This ensures the corrected response is based on actual knowledge base
        if get_weaviate_client() is None:
            print("Warning: Weaviate not initialized. Cannot retrieve context for improved response.")
            relevant_docs = []
        else:
            pairs = retrieve_from_weaviate(user_query, k=25)
            relevant_docs = [d for d, _ in pairs]
        
        # Build debug info for context
        context_debug_info = {
            "doc_count": len(relevant_docs),
            "query": user_query,
            "docs": [
                {
                    "doc_number": i + 1,
                    "content_preview": doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content,
                    "content_length": len(doc.page_content),
                    "metadata": doc.metadata,
                    "source": doc.metadata.get('source', 'Unknown')
                }
                for i, doc in enumerate(relevant_docs[:10])  # Save first 10 docs for review
            ]
        }
        
        # Format the retrieved documents as context
        context_text = "\n\n".join([f"Document {i+1}:\n{doc.page_content}" for i, doc in enumerate(relevant_docs)])
        
        # Create LLM for auto-correction
        llm = get_llm(
            temperature=0.5,
            max_tokens=1000
        )
        
        # Create auto-correction prompt WITH knowledge base context
        correction_prompt = f"""
{SYSTEM_PROMPT}

ADDITIONAL CONTEXT FOR CORRECTION:

KNOWLEDGE BASE CONTEXT:
{context_text}

PREVIOUS INTERACTION:
User's Question: "{user_query}"
Bot's Poor Response: "{bad_response}"
{f"User's Feedback: {user_comment}" if user_comment else ""}

CORRECTION TASK:
The previous response was marked as poor quality. Using ONLY the information from the KNOWLEDGE BASE CONTEXT above, provide a much better, more accurate, and helpful response that:

1. Follows ALL the instructions from the system prompt at the top (including link embedding and markdown formatting)
2. Directly answers the user's question about cloud migration services
3. Uses specific information from the knowledge base documents
4. Provides actionable information about CloudFuze's capabilities
5. Is clear, professional, and helpful
6. Includes relevant CloudFuze links.
7. Uses proper Markdown formatting as specified in the system prompt

CRITICAL RULES:
- Base your answer STRICTLY on the knowledge base context provided above
- Use the EXACT same style, tone, and formatting as the system prompt requires
- Include relevant CloudFuze links naturally in the response
- DO NOT invent information not in the knowledge base context
- If information is not in the context, say "I don't have specific information about that"

Improved response:
"""
        
        # Generate improved response with knowledge base context
        improved_response = llm.invoke(correction_prompt).content
        
        # Return both the response and context debug info
        return improved_response, context_debug_info
        
    except Exception as e:
        print(f"Error generating improved response: {e}")
        error_response = f"I apologize for the previous response. Let me provide a better answer to your question: {user_query}. For detailed information about Slack to Teams migration, please contact our CloudFuze support team."
        return error_response, {"error": str(e), "doc_count": 0}

async def save_correction_to_dataset(user_query: str, bad_response: str, improved_response: str, trace_id: str, user_comment: str = None):
    """Save the correction to JSONL dataset."""
    try:
        import os
        from datetime import datetime, timezone
        
        # Create dataset directory if it doesn't exist
        dataset_dir = "./data/fine_tuning_dataset"
        os.makedirs(dataset_dir, exist_ok=True)
        
        # Create JSONL record
        correction_record = {
            "input": user_query,
            "bad_output": bad_response,
            "corrected_output": improved_response,
            "trace_id": trace_id,
            "user_comment": user_comment,
            "timestamp": datetime.now().isoformat(),
            "status": "auto_corrected"
        }
        
        # Save to single JSONL file (append mode)
        jsonl_file = f"{dataset_dir}/corrections.jsonl"
        
        with open(jsonl_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(correction_record, ensure_ascii=False) + '\n')
        
        # Also save to the existing corrected_responses.json for compatibility
        # Pass the original question so similarity matching can work
        save_corrected_response(trace_id, improved_response, user_comment, user_query)
        
    except Exception as e:
        print(f"Error saving correction to dataset: {e}")

async def update_langfuse_trace(trace_id: str, improved_response: str):
    """Update Langfuse trace with corrected response."""
    try:
        if langfuse_tracker and langfuse_tracker.client:
            # Log the auto-correction as a score/annotation
            langfuse_tracker.client.score(
                trace_id=trace_id,
                name="auto_correction",
                value=1,
                comment=f"Auto-corrected response: {improved_response[:200]}..."
            )
    except Exception as e:
        print(f"Could not update Langfuse trace: {e}")

# ---------------- Microsoft OAuth Endpoints ----------------

class MicrosoftCallbackRequest(BaseModel):
    code: str
    redirect_uri: str
    code_verifier: str

class TokenRefreshRequest(BaseModel):
    refresh_token: str

@router.get("/test")
async def test_endpoint():
    """Test endpoint to verify backend connectivity."""
    return {"message": "Backend is working", "status": "success"}

@router.get("/auth/config")
async def get_auth_config():
    """Get OAuth configuration for frontend."""
    return {
        "client_id": MICROSOFT_CLIENT_ID,
        "tenant": MICROSOFT_TENANT
    }

@router.post("/test-post")
async def test_post_endpoint(data: dict):
    """Test POST endpoint to verify CORS and connectivity."""
    return {"message": "POST request received", "data": data, "status": "success"}

@router.post("/auth/microsoft/refresh")
async def refresh_microsoft_token(
    request: Request,
    refresh_request: Optional[TokenRefreshRequest] = None,
    session_id: Optional[str] = None
):
    """
    ✅ NEW: Refresh Microsoft OAuth tokens using session (preferred) or refresh_token (legacy).
    
    Priority:
    1. Session-based refresh (preferred - uses session_id from cookie)
    2. Refresh token (legacy - for backward compatibility)
    
    SECURITY: Backend owns all OAuth credentials.
    """
    from app.session_store import session_store
    
    # PRIORITY 1: Session-based refresh (no refresh_token needed)
    if not session_id:
        session_id = request.cookies.get("session_id")
    
    if session_id:
        try:
            await session_store.connect()
            session = await session_store.get_session(session_id)
            
            if session:
                # Use refresh_token from session
                refresh_token = session.get("refresh_token")
                
                if refresh_token:
                    # Refresh tokens via Microsoft
                    tenant = MICROSOFT_TENANT
                    client_id = MICROSOFT_CLIENT_ID
                    client_secret = MICROSOFT_CLIENT_SECRET
                    
                    token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
                    
                    token_data = {
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token",
                        "scope": "openid email profile User.Read"
                    }
                    
                    async with httpx.AsyncClient() as client:
                        token_response = await client.post(token_url, data=token_data, timeout=30.0)
                        
                        if token_response.status_code != 200:
                            logger.error(f"Token refresh failed for session: {token_response.status_code}")
                            raise HTTPException(
                                status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Token refresh failed"
                            )
                        
                        token_info = token_response.json()
                        
                        # Update session with new tokens
                        await session_store.refresh_session_tokens(
                            session_id=session_id,
                            new_access_token=token_info.get("access_token"),
                            new_refresh_token=token_info.get("refresh_token", refresh_token),
                            token_expires_in=token_info.get("expires_in", 3600)
                        )
                        
                        logger.info(f"[AUTH] Session tokens refreshed: {session_id[:8]}...")
                        
                        return {
                            "access_token": token_info.get("access_token"),  # For backward compatibility
                            "refresh_token": token_info.get("refresh_token"),  # For backward compatibility
                            "expires_in": token_info.get("expires_in", 3600),
                            "token_type": token_info.get("token_type", "Bearer"),
                            "session_id": session_id  # Return session_id for frontend
                        }
        except Exception as e:
            logger.error(f"[AUTH] Session-based refresh failed: {e}")
            # Fall through to legacy refresh
    
    # PRIORITY 2: Legacy refresh using refresh_token (for backward compatibility)
    if refresh_request and refresh_request.refresh_token:
        logger.warning("[AUTH] Using legacy refresh_token-based refresh")
        try:
            tenant = MICROSOFT_TENANT
            client_id = MICROSOFT_CLIENT_ID
            client_secret = MICROSOFT_CLIENT_SECRET
            
            token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
            
            token_data = {
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_request.refresh_token,
                "grant_type": "refresh_token",
                "scope": "openid email profile User.Read"
            }
            
            async with httpx.AsyncClient() as client:
                token_response = await client.post(token_url, data=token_data, timeout=30.0)
                
                if token_response.status_code != 200:
                    logger.error(f"Token refresh failed: {token_response.status_code}")
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token refresh failed"
                    )
                
                token_info = token_response.json()
                
                logger.info(f"Token refreshed successfully (legacy)")
                
                return {
                    "access_token": token_info.get("access_token"),
                    "refresh_token": token_info.get("refresh_token"),
                    "expires_in": token_info.get("expires_in", 3600),
                    "token_type": token_info.get("token_type", "Bearer")
                }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Token refresh failed"
            )
    
    # No valid session or refresh_token
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized: No valid session or refresh token"
    )


@router.post("/auth/session/refresh")
async def refresh_session(request: Request):
    """
    ✅ NEW: Refresh session tokens automatically (called by frontend token monitor).
    Uses session_id from cookie - no parameters needed.
    """
    from app.session_store import session_store
    
    session_id = request.cookies.get("session_id")
    
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No session found"
        )
    
    try:
        await session_store.connect()
        session = await session_store.get_session(session_id)
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired or invalid"
            )
        
        # Check if token needs refresh
        token_expires_at = session.get("token_expires_at")
        if token_expires_at and isinstance(token_expires_at, datetime):
            from datetime import timedelta
            now = datetime.utcnow()
            margin = timedelta(minutes=5)
            
            if token_expires_at - now < margin:
                # Refresh tokens
                refresh_token = session.get("refresh_token")
                
                tenant = MICROSOFT_TENANT
                client_id = MICROSOFT_CLIENT_ID
                client_secret = MICROSOFT_CLIENT_SECRET
                
                token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
                
                token_data = {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                    "scope": "openid email profile User.Read"
                }
                
                async with httpx.AsyncClient() as client:
                    token_response = await client.post(token_url, data=token_data, timeout=30.0)
                    
                    if token_response.status_code == 200:
                        token_info = token_response.json()
                        
                        # Update session
                        await session_store.refresh_session_tokens(
                            session_id=session_id,
                            new_access_token=token_info.get("access_token"),
                            new_refresh_token=token_info.get("refresh_token", refresh_token),
                            token_expires_in=token_info.get("expires_in", 3600)
                        )
                        
                        logger.info(f"[AUTH] Session tokens refreshed automatically: {session_id[:8]}...")
                        
                        return {
                            "success": True,
                            "expires_in": token_info.get("expires_in", 3600)
                        }
        
        # Token still valid, no refresh needed
        return {
            "success": True,
            "message": "Token still valid"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AUTH] Session refresh error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session refresh failed"
        )


@router.post("/auth/logout")
async def logout(request: Request):
    """
    ✅ NEW: Logout endpoint - deletes session.
    """
    from app.session_store import session_store
    
    session_id = request.cookies.get("session_id")
    
    if session_id:
        try:
            await session_store.connect()
            await session_store.delete_session(session_id)
            logger.info(f"[AUTH] User logged out: {session_id[:8]}...")
        except Exception as e:
            logger.error(f"[AUTH] Logout error: {e}")
    
    # Clear session cookie
    response = JSONResponse(content={"success": True, "message": "Logged out successfully"})
    response.delete_cookie(key="session_id")
    
    return response

@router.post("/auth/microsoft/callback")
async def microsoft_oauth_callback(
    request: MicrosoftCallbackRequest,
    http_request: Request
):
    """Handle Microsoft OAuth callback and exchange code for tokens."""
    try:
        # Get Microsoft OAuth configuration
        client_id = MICROSOFT_CLIENT_ID
        tenant = MICROSOFT_TENANT
        
        # Exchange authorization code for access token
        token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
        
        # For confidential clients (Web apps), we use client_secret
        token_data = {
            "client_id": client_id,
            "client_secret": MICROSOFT_CLIENT_SECRET,
            "code": request.code,
            "redirect_uri": request.redirect_uri,
            "code_verifier": request.code_verifier,
            "grant_type": "authorization_code"
        }
        
        async with httpx.AsyncClient() as client:
            token_response = await client.post(token_url, data=token_data)
            
            if token_response.status_code != 200:
                return {"error": "Failed to exchange code for token", "details": token_response.text}
            
            token_info = token_response.json()
            access_token = token_info.get("access_token")
            
            if not access_token:
                return {"error": "No access token received"}
            
            # Get user information from Microsoft Graph
            graph_response = await client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if graph_response.status_code != 200:
                return {"error": "Failed to get user information", "details": graph_response.text}
            
            user_info = graph_response.json()
            
            # ✅ STRICT IDENTITY: Email is mandatory - fail fast if missing
            user_email = user_info.get("mail") or user_info.get("userPrincipalName", "")
            if not user_email or not user_email.strip():
                logger.error("[AUTH] OAuth callback failed: No email in Microsoft Graph response")
                return {
                    "error": "Authentication failed",
                    "message": "Unable to retrieve user email. Please try logging in again.",
                    "details": "Email missing from Microsoft Graph API response"
                }
            
            # ✅ Validate that the user has a CloudFuze email domain
            if not user_email.endswith("@cloudfuze.com"):
                return {
                    "error": "Access denied", 
                    "message": "Only CloudFuze company accounts are allowed to access this application.",
                    "details": f"Email domain not allowed: {user_email}"
                }
            
            # ✅ IDENTITY RULE: Use email as user_id (stable, consistent, human-readable)
            # This ensures chat history is always stored under the same key
            user_id = user_email.lower().strip()
            
            # ✅ Get name - fail if missing (no default "User")
            user_name = user_info.get("displayName", "")
            if not user_name or not user_name.strip():
                # Extract name from email as last resort
                user_name = user_email.split("@")[0].replace(".", " ").title()
                logger.warning(f"[AUTH] No displayName from Graph API, using email prefix: {user_name}")
            
            # ✅ NEW: Create backend session (Graph API called ONLY here)
            from app.session_store import session_store
            await session_store.connect()
            
            session_id = await session_store.create_session(
                user_id=user_id,
                user_email=user_email,
                user_name=user_name,
                access_token=access_token,
                refresh_token=token_info.get("refresh_token", ""),
                token_expires_in=token_info.get("expires_in", 3600)
            )
            
            logger.info(f"[AUTH] Created session for user: {user_email} (session_id: {session_id[:8]}...)")
            
            # 🔥 CRITICAL FIX: Create Response object FIRST, then set cookie on it
            from app.session_store import SESSION_EXPIRY_HOURS
            import os
            
            # ✅ Cookie settings: Different for dev vs production
            # Development (localhost): SameSite=lax, secure=False (works with Next.js proxy)
            # Production (HTTPS): SameSite=None, secure=True (cross-origin)
            
            # Use http_request (FastAPI Request) to get URL, not request (Pydantic model)
            request_url = str(http_request.url)
            is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"
            is_https = request_url.startswith("https://")
            is_localhost = "localhost" in request_url or "127.0.0.1" in request_url
            
            # Determine cookie settings
            # ✅ PRODUCTION READY: Automatically detects environment and sets correct cookie flags
            if is_production and is_https:
                # Production HTTPS: Check if using proxy (same-origin) or direct (cross-origin)
                # If frontend uses Next.js proxy, requests are same-origin → SameSite=Lax
                # If frontend calls backend directly on different domain → SameSite=None
                # Default to Lax (works with proxy), can be overridden via env var if needed
                use_cross_origin = os.getenv("USE_CROSS_ORIGIN_COOKIES", "false").lower() == "true"
                secure_cookie = True
                samesite_setting = "none" if use_cross_origin else "lax"  # Lax for proxy, None for direct
            else:
                # Development or HTTP: Same-origin cookies (via proxy)
                secure_cookie = False
                samesite_setting = "lax"  # Works with same-origin
            
            # 🔥 CRITICAL: Create JSONResponse FIRST, then set cookie on it
            # ✅ Return only user info (no tokens - session managed via cookie)
            result = {
                "user_id": user_id,
                "name": user_name,
                "email": user_email
            }
            
            response = JSONResponse(content=result)
            
            # 🔥 CRITICAL: Set cookie using FastAPI's set_cookie() method
            response.set_cookie(
                key="session_id",
                value=session_id,
                max_age=3600 * SESSION_EXPIRY_HOURS,  # Cookie expires with session (3600 seconds = 1 hour)
                httponly=True,  # Prevent XSS attacks
                secure=secure_cookie,  # False in dev, True in production HTTPS
                samesite=samesite_setting,  # "lax" in dev, "none" in production
                path="/",  # Explicit path to ensure cookie is sent
                domain=None  # Don't set domain - let browser use current domain
            )
            
            # 🔥 FALLBACK: Manually set Set-Cookie header to ensure it's sent
            # This is a workaround in case FastAPI's set_cookie() doesn't work properly
            # Construct the Set-Cookie header manually
            max_age_seconds = 3600 * SESSION_EXPIRY_HOURS  # 3600 seconds = 1 hour
            set_cookie_parts = [
                f"session_id={session_id}",
                f"Path=/",
                f"Max-Age={max_age_seconds}",
                "HttpOnly",
            ]
            if secure_cookie:
                set_cookie_parts.append("Secure")
            if samesite_setting:
                set_cookie_parts.append(f"SameSite={samesite_setting}")
            
            set_cookie_header = "; ".join(set_cookie_parts)
            response.headers["Set-Cookie"] = set_cookie_header
            
            logger.info(f"[AUTH] ✅ Session cookie configured: secure={secure_cookie}, httponly=True, samesite={samesite_setting}, path=/")
            logger.info(f"[AUTH] ✅ Set-Cookie header manually set: {set_cookie_header[:80]}...")
            logger.info(f"[AUTH] ✅ Session created for user: {user_email} (session_id: {session_id[:8]}...)")
            
            return response
            
    except Exception as e:
        logger.error(f"[AUTH] ❌ OAuth callback exception: {str(e)}", exc_info=True)
        return {"error": f"OAuth callback failed: {str(e)}"}
# ============================================================================
# TEAM-WISE ANALYTICS ENDPOINTS (DUPLICATE - REMOVED)
# The endpoint at line 3482 is the active one
# ============================================================================

# DUPLICATE ENDPOINT - FULLY COMMENTED OUT (using the one at line 3482 instead)
# @router.get("/analytics/langfuse/teams/summary")
# async def get_langfuse_teams_summary(
#     start_date: str = Query(None, description="Start date in YYYY-MM-DD format"),
#     end_date: str = Query(None, description="End date in YYYY-MM-DD format"),
#     time_filter: str = Query(None, description="(Legacy) Filter by time: today, yesterday, this_week, last_week, all"),
#     current_user: dict = Depends(require_restricted_admin)
# ):
#     """
#     Get team-wise analytics summary from Langfuse traces.
#     Returns aggregated statistics for all 8 teams.
#     Supports both date range (start_date/end_date) and preset filters (time_filter).
#     """
#     try:
#         print(f"[TEAMS] Starting teams summary fetch: start_date={start_date}, end_date={end_date}, time_filter={time_filter}")
#         from app.langfuse_integration import langfuse_client
#         from app.models.teams import TEAMS, get_team_for_member, MEMBER_TO_TEAM
#         from datetime import timedelta
#         
#         if not langfuse_client:
#             return {"error": "Langfuse client not initialized", "status": "error"}
#         ... (entire duplicate function body removed - using endpoint at line 3482 instead)


@router.get("/analytics/langfuse/teams/details")
async def get_langfuse_team_details(
    team_name: str = Query(..., description="Team name"),
    start_date: str = Query(None, description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(None, description="End date in YYYY-MM-DD format"),
    time_filter: str = Query(None, description="(Legacy) Filter by time: today, yesterday, this_week, last_week, all"),
    current_user: dict = Depends(require_restricted_admin)
):
    """
    Get detailed analytics for a specific team including all members and their stats.
    Supports both date range (start_date/end_date) and preset filters (time_filter).
    """
    try:
        from app.langfuse_integration import langfuse_client
        from app.models.teams import TEAMS, get_team_for_member
        from datetime import timedelta
        
        if not langfuse_client:
            return {"error": "Langfuse client not initialized", "status": "error"}
        
        # Validate team exists
        if team_name not in TEAMS:
            return {"status": "error", "error": "Team not found"}
        
        # Calculate time range
        start_time = None
        end_time = datetime.utcnow()
        max_pages = 30
        request_timeout = 60.0
        
        # Use custom date range if provided
        if start_date and end_date:
            try:
                start_time = datetime.strptime(start_date, "%Y-%m-%d").replace(hour=0, minute=0, second=0, microsecond=0)
                end_time = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, microsecond=999999)
                
                # Adjust page limits based on date range width
                date_diff = (end_time - start_time).days
                if date_diff <= 1:
                    max_pages = 10
                    request_timeout = 30.0
                elif date_diff <= 7:
                    max_pages = 15
                    request_timeout = 45.0
                elif date_diff <= 30:
                    max_pages = 20
                    request_timeout = 60.0
            except ValueError:
                return {"error": "Invalid date format. Use YYYY-MM-DD", "status": "error"}
        
        # Fallback to legacy time_filter
        elif time_filter == "today":
            start_time = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            max_pages = 10
            request_timeout = 30.0
        elif time_filter == "yesterday":
            start_time = (datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - 
                         timedelta(days=1))
            end_time = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            max_pages = 10
            request_timeout = 30.0
        elif time_filter == "this_week":
            start_time = datetime.utcnow() - timedelta(days=datetime.utcnow().weekday())
            start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            max_pages = 15
            request_timeout = 45.0
        elif time_filter == "last_week":
            utc_now = datetime.utcnow()
            days_since_monday = utc_now.weekday()
            last_monday = utc_now - timedelta(days=days_since_monday + 7)
            start_time = last_monday.replace(hour=0, minute=0, second=0, microsecond=0)
            max_pages = 20
            request_timeout = 45.0
        elif time_filter == "last_7_days":
            start_time = datetime.utcnow() - timedelta(days=7)
            max_pages = 20
            request_timeout = 45.0
        
        # Initialize member data structure
        members_data = {}
        team_info = TEAMS[team_name]
        
        for member_name in team_info.get("Members", []):
            members_data[member_name.lower()] = {
                "name": member_name,
                "email": "",
                "is_lead": False,
                "total_questions": 0,
                "questions_list": [],
                "top_questions": []
            }
        
        # Add lead
        lead_name = team_info.get("Lead")
        if lead_name:
            members_data[lead_name.lower()] = {
                "name": lead_name,
                "email": "",
                "is_lead": True,
                "total_questions": 0,
                "questions_list": [],
                "top_questions": []
            }
        
        team_total_questions = 0
        all_team_questions = []
        
        # Fetch traces
        page = 1
        batch_limit = 100
        
        async with httpx.AsyncClient() as client:
            from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
            
            while page <= max_pages:
                try:
                    params = {
                        "page": page,
                        "limit": batch_limit,
                        "orderBy[createdAt]": "DESC"
                    }
                    if start_time:
                        params["createdAt[gte]"] = start_time.isoformat() + "Z"
                    if end_time:
                        params["createdAt[lte]"] = end_time.isoformat() + "Z"
                    
                    response = await client.get(
                        f"{LANGFUSE_HOST}/api/public/traces",
                        params=params,
                        auth=(LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY),
                        timeout=request_timeout
                    )
                    
                    if response.status_code == 429:
                        break
                    
                    response.raise_for_status()
                    
                    traces_response = response.json()
                    traces = traces_response.get("data", [])
                    
                    if not traces:
                        break
                    
                    for trace in traces:
                        try:
                            metadata = trace.get("metadata", {})
                            question = trace.get("input", "")
                            user_email = str(metadata.get("user_email", ""))
                            user_name = str(metadata.get("user_name", "Unknown"))
                            
                            # Check if this trace belongs to current team using email
                            trace_team = None
                            matching_member = None
                            
                            if user_email and user_email != "":
                                # Try to find the member by email prefix match
                                email_lower = user_email.lower()
                                for member_lower in members_data.keys():
                                    # Try to match: email starts with member name (with dots replacing spaces)
                                    member_pattern = member_lower.replace(" ", ".")
                                    if email_lower.startswith(member_pattern):
                                        trace_team = team_name
                                        matching_member = member_lower
                                        break
                            
                            # Fallback to name matching if email didn't match
                            if not trace_team and user_name and user_name != "Unknown":
                                user_name_lower = user_name.lower()
                                if user_name_lower in members_data:
                                    trace_team = team_name
                                    matching_member = user_name_lower
                            
                            if trace_team and matching_member and question:
                                team_total_questions += 1
                                all_team_questions.append(question)
                                
                                member_info = members_data[matching_member]
                                member_info["total_questions"] += 1
                                member_info["questions_list"].append(question)
                                member_info["email"] = user_email
                        except Exception as trace_err:
                            print(f"[WARN] Error processing trace in team details: {trace_err}")
                            continue
                    
                    if len(traces) < batch_limit:
                        break
                    
                    page += 1
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    print(f"[ERROR] Error fetching team details: {e}")
                    break
        
        # Process members and calculate top questions
        members_list = []
        active_count = 0
        
        for member_lower, member_data in members_data.items():
            if member_data["total_questions"] > 0:
                active_count += 1
                
                # Get top questions for member
                question_counts = Counter(member_data["questions_list"])
                top_questions = question_counts.most_common(3)
                member_data["top_questions"] = [
                    {"question": q, "count": c} for q, c in top_questions
                ]
            
            del member_data["questions_list"]
            members_list.append(member_data)
        
        # Sort members by questions descending
        members_list.sort(key=lambda x: x["total_questions"], reverse=True)
        
        # Calculate unique questions
        unique_questions = len(set(all_team_questions)) if all_team_questions else 0
        
        return {
            "status": "success",
            "team_name": team_name,
            "lead": lead_name or "N/A",
            "lead_email": members_data.get(lead_name.lower(), {}).get("email", "") if lead_name else "",
            "color": get_team_color(team_name),
            "time_filter": time_filter,
            "members": members_list,
            "total_members": len(team_info.get("Members", [])) + (1 if lead_name else 0),
            "active_members": active_count,
            "team_total_questions": team_total_questions,
            "team_unique_questions": unique_questions
        }
        
    except Exception as e:
        print(f"[ERROR] Team details fetch failed: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


def get_team_color(team_name: str) -> str:
    """Get the color hex code for a team."""
    colors = {
        "Content": "#3B82F6",  # Blue
        "Messaging & Email": "#10B981",  # Green
        "CF Manage": "#F59E0B",  # Amber
        "QA": "#EF4444",  # Red
        "Neutara Labs": "#8B5CF6",  # Purple
        "Infra": "#EC4899",  # Pink
        "Pre-Sales": "#06B6D4",  # Cyan
        "Sales Ops": "#14B8A6"  # Teal
    }
    return colors.get(team_name, "#6B7280")  # Gray fallback


