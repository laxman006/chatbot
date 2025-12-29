# -*- coding: utf-8 -*-
from fastapi import APIRouter, Request, HTTPException, Header, Depends, Query, Path, status
from fastapi.responses import PlainTextResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List
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

from app.llm import setup_qa_chain
from app.llm_factory import get_llm
from app.vectorstore import retriever, vectorstore, bm25_retriever
from app.mongodb_memory import (
    mongodb_memory,
    add_to_conversation, get_conversation_context, get_user_chat_history, 
    clear_user_chat_history, save_session, get_all_sessions, get_user_sessions, 
    get_session_by_id, create_shared_chat, get_shared_chat,
    update_user_profile, get_user_profile, get_user_statistics, get_rankers_by_date
)
from app.helpers import strip_markdown, preserve_markdown
from app.langfuse_integration import langfuse_tracker
from app.auth import verify_user_access, require_admin, require_restricted_admin
from app.user_data import get_user_job_title
from app.models.teams import TEAMS_STRUCTURE, get_team_by_name
from config import (
    SYSTEM_PROMPT, MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, MICROSOFT_TENANT,
    ENABLE_INTENT_CLASSIFICATION, ENABLE_QUERY_EXPANSION, ENABLE_CONTEXT_COMPRESSION,
    DENSE_RETRIEVAL_K, BM25_RETRIEVAL_K, FINAL_RETRIEVAL_K,
    DENSE_WEIGHT, BM25_WEIGHT, RERANKER_WEIGHT
)
from langchain_core.prompts import ChatPromptTemplate
import time
from query_expander import QueryExpander
from reranker import CrossEncoderReranker
from context_compressor import ContextCompressor
from contextlib import suppress
from collections import Counter, defaultdict


# ============================================================================
# OPTION E: PERPLEXITY-STYLE RETRIEVAL INITIALIZATION
# ============================================================================

# Initialize Option E components
query_expander = QueryExpander()
cross_reranker = CrossEncoderReranker()
context_compressor = ContextCompressor()

# ============================================================================
# INTENT CLASSIFICATION SYSTEM - Branch-Specific Retrieval
# ============================================================================

# Configuration: Disable intent classification (overridden by config)
# ENABLE_INTENT_CLASSIFICATION is now imported from config

# Define intent branches with their characteristics
INTENT_BRANCHES = {
    "general_business": {
        "description": "General business questions, CloudFuze overview, benefits",
        "keywords": ["business", "help", "benefits", "useful", "value", "cloudfuze", "services", "offer", "advantages"],
        "include_tags": ["blog"],
        "exclude_keywords": ["slack", "teams", "migration", "migrate"],
        "exclude_if_both": [("slack", "teams")],
        "query_expansion": ["cloud solutions", "data migration platform", "SaaS management"]
    },
    "slack_teams_migration": {
        "description": "Slack to Teams migration specific questions",
        "keywords": ["slack", "teams", "slack to teams", "migrate slack", "migration"],
        "include_tags": ["blog", "sharepoint"],
        "require_keywords": [["slack", "teams"], ["slack-to-teams"]],
        "query_expansion": ["channel migration", "workspace transfer", "conversation history"]
    },
    "sharepoint_docs": {
        "description": "SharePoint documents, certificates, policies",
        "keywords": ["certificate", "download", "policy", "document", "soc", "compliance", "security"],
        "include_tags": ["sharepoint"],
        "priority_source": "sharepoint",
        "query_expansion": ["compliance documentation", "security certification", "audit reports"]
    },
    "pricing": {
        "description": "Pricing, costs, payment questions",
        "keywords": ["pricing", "cost", "price", "how much", "payment", "subscription", "plan"],
        "include_tags": ["blog"],
        "query_expansion": ["subscription plans", "licensing", "payment options"]
    },
    "troubleshooting": {
        "description": "Errors, issues, stuck migrations",
        "keywords": ["error", "stuck", "not working", "failed", "issue", "problem", "fix"],
        "include_tags": ["blog", "sharepoint"],
        "query_expansion": ["error resolution", "migration issues", "technical support"]
    },
    "migration_general": {
        "description": "General migration questions (not platform-specific)",
        "keywords": ["migrate", "migration", "transfer", "move data", "cloud migration"],
        "include_tags": ["blog", "sharepoint"],
        "exclude_if_both": [("slack", "teams")],
        "query_expansion": ["data transfer", "cloud-to-cloud migration", "platform migration"]
    },
    "enterprise_solutions": {
        "description": "Enterprise features, large-scale deployments",
        "keywords": ["enterprise", "large scale", "organization", "corporate", "enterprise-grade"],
        "include_tags": ["blog", "sharepoint"],
        "query_expansion": ["enterprise deployment", "large organization", "corporate solutions"]
    },
    "integrations": {
        "description": "API, integrations, third-party connections",
        "keywords": ["api", "integration", "webhook", "connector", "third-party", "integrate with"],
        "include_tags": ["blog", "sharepoint"],
        "query_expansion": ["API integration", "third-party connectors", "platform connectivity"]
    },
    "features": {
        "description": "Product features and capabilities",
        "keywords": ["features", "capabilities", "what can", "functionality", "does it support"],
        "include_tags": ["blog", "sharepoint"],
        "query_expansion": ["product capabilities", "feature list", "platform features"]
    },
    "email_conversations": {
        "description": "Questions about email threads, conversations, and discussions",
        "keywords": ["email", "thread", "conversation", "discussed", "bugs", "participants", "srcs", "what did", "who said"],
        "include_tags": ["email"],
        "query_expansion": ["email thread", "conversation", "discussion"]
    },
    "other": {
        "description": "Fallback for uncategorized queries",
        "keywords": [],
        "include_tags": ["blog", "sharepoint", "email"],
        "query_expansion": []
    }
}


def classify_intent(query: str) -> dict:
    """
    Classify user query intent using LLM-based classification.
    Returns intent name and confidence score.
    """
    query_lower = query.lower()
    
    # Quick keyword-based pre-filter for common cases (faster)
    if any(kw in query_lower for kw in ["email", "thread", "conversation", "bugs raised", "discussed", "srcs folder", "participants"]):
        return {"intent": "email_conversations", "confidence": 0.90, "method": "keyword"}
    
    if any(kw in query_lower for kw in ["certificate", "download", "soc", "policy"]) and "sharepoint" not in query_lower:
        if any(word in query_lower for word in ["certificate", "compliance", "security", "policy"]):
            return {"intent": "sharepoint_docs", "confidence": 0.85, "method": "keyword"}
    
    if "slack" in query_lower and "teams" in query_lower:
        return {"intent": "slack_teams_migration", "confidence": 0.90, "method": "keyword"}
    
    if any(kw in query_lower for kw in ["pricing", "cost", "price", "how much"]):
        return {"intent": "pricing", "confidence": 0.85, "method": "keyword"}
    
    # For ambiguous queries, use LLM classification
    intent_descriptions = "\n".join([f"{i+1}. {key}: {config['description']}" 
                                     for i, (key, config) in enumerate(INTENT_BRANCHES.items())])
    
    classifier_prompt = f"""Classify this user query into ONE of these intents:

{intent_descriptions}

Query: "{query}"

CRITICAL RULES:
- If query asks about emails, conversations, threads, or discusses what was said in emails → "email_conversations"
- If query asks about general business value, benefits, or "what is CloudFuze" WITHOUT mentioning specific platforms → "general_business"
- If query mentions BOTH "Slack" AND "Teams" → "slack_teams_migration"
- If query asks about general migration (without specific platforms) → "migration_general"
- If query asks for certificates, documents, or policies → "sharepoint_docs"
- If query asks about pricing or costs → "pricing"
- If query describes errors or problems → "troubleshooting"
- If query asks about enterprise features or large-scale → "enterprise_solutions"
- If query asks about API, integrations, or connectors → "integrations"
- If query asks about features or capabilities → "features"
- Otherwise → "other"

Respond with EXACTLY this format (no extra text):
intent_name|confidence

Example: general_business|0.92
"""
    
    try:
        llm = get_llm(temperature=0)
        response = llm.invoke(classifier_prompt)
        
        parts = response.content.strip().split('|')
        intent = parts[0].strip()
        confidence = float(parts[1].strip()) if len(parts) > 1 else 0.7
        
        # Validate intent exists
        if intent not in INTENT_BRANCHES:
            intent = "other"
            confidence = 0.5
        
        return {
            "intent": intent,
            "confidence": confidence,
            "method": "llm"
        }
    except Exception as e:
        print(f"[ERROR] Intent classification failed: {e}")
        return {"intent": "other", "confidence": 0.5, "method": "fallback"}


def retrieve_with_branch_filter(query: str, intent: str, k: int = 50):
    """
    Retrieve documents filtered by intent branch.
    This performs semantic search and then filters by metadata tags.
    """
    branch_config = INTENT_BRANCHES.get(intent, INTENT_BRANCHES["other"])
    
    # Get more documents than needed for filtering
    all_docs = vectorstore.similarity_search_with_score(query, k=100)
    
    filtered_docs = []
    
    for doc, score in all_docs:
        doc_tag = doc.metadata.get('tag', '').lower()
        doc_content = doc.page_content.lower()
        doc_title = doc.metadata.get('post_title', '').lower()
        source_type = doc.metadata.get('source_type', '').lower()
        
        # Check inclusion tags
        include_tags = branch_config.get("include_tags", [])
        if include_tags:
            tag_match = any(tag in doc_tag for tag in include_tags)
        else:
            tag_match = True
        
        # For general_business intent: exclude Slack→Teams specific content
        if intent == "general_business":
            # Check if document is Slack→Teams specific
            exclude_keywords = branch_config.get("exclude_keywords", [])
            has_excluded = False
            
            # Strong exclusion: if both "slack" and "teams" appear multiple times
            slack_count = doc_content.count("slack")
            teams_count = doc_content.count("teams")
            if slack_count >= 2 and teams_count >= 2:
                has_excluded = True
            
            # Title-based exclusion
            if "slack to teams" in doc_title or "slack-to-teams" in doc_title:
                has_excluded = True
            
            if has_excluded:
                continue  # Skip this document
        
        # For slack_teams_migration: prioritize relevant content
        elif intent == "slack_teams_migration":
            # Must have both slack and teams keywords
            if "slack" not in doc_content and "slack" not in doc_title:
                tag_match = False
            if "teams" not in doc_content and "teams" not in doc_title:
                tag_match = False
        
        # For sharepoint_docs: prioritize SharePoint source
        elif intent == "sharepoint_docs":
            if source_type == "sharepoint":
                # Boost SharePoint docs by improving their score
                score = score * 0.7  # Lower score = higher priority
        
        # Add document if it passes filters
        if tag_match:
            filtered_docs.append((doc, score))
    
    # Sort by score (lower is better in similarity search)
    filtered_docs.sort(key=lambda x: x[1])
    
    # Return top k
    return filtered_docs[:k]


def calculate_confidence(intent_confidence: float, retrieval_docs: int, avg_similarity: float = None):
    """
    Calculate overall confidence score for the response.
    Combines intent classification confidence with retrieval metrics.
    """
    # Intent confidence weight: 50%
    # Document count weight: 30%
    # Similarity weight: 20%
    
    # Normalize document count (30 is ideal)
    doc_confidence = min(retrieval_docs / 30.0, 1.0)
    
    if avg_similarity is not None:
        # Similarity scores are distances (lower is better), typically 0.3-0.6
        # Convert to confidence: 0.3 → 0.95, 0.6 → 0.4
        similarity_confidence = max(0, 1.0 - avg_similarity)
        
        overall_confidence = (
            intent_confidence * 0.5 +
            doc_confidence * 0.3 +
            similarity_confidence * 0.2
        )
    else:
        overall_confidence = (
            intent_confidence * 0.6 +
            doc_confidence * 0.4
        )
    
    return round(overall_confidence, 3)


# ============================================================================
# ADVANCED RAG IMPROVEMENTS
# ============================================================================

def expand_query_with_intent(query: str, intent: str) -> str:
    """
    Expand query with intent-specific keywords for better retrieval.
    Uses query expansion terms defined in intent branches.
    """
    branch_config = INTENT_BRANCHES.get(intent, {})
    expansion_terms = branch_config.get("query_expansion", [])
    
    if not expansion_terms:
        return query
    
    # Add expansion terms to original query
    expanded = f"{query} {' '.join(expansion_terms[:2])}"  # Add top 2 terms
    
    print(f"[QUERY EXPANSION] Original: '{query}' → Expanded: '{expanded}'")
    
    return expanded


def hybrid_ranking(doc_results, query: str, intent: str, alpha=0.7):
    """
    Hybrid ranking combining semantic similarity + keyword matching.
    alpha: weight for semantic score (1-alpha for keyword score)
    """
    from collections import Counter
    import re
    
    # Get keywords from intent branch
    branch_config = INTENT_BRANCHES.get(intent, {})
    intent_keywords = branch_config.get("keywords", [])
    
    # Extract keywords from query
    query_lower = query.lower()
    query_words = set(re.findall(r'\w+', query_lower))
    
    reranked_docs = []
    
    for doc, semantic_score in doc_results:
        # Semantic score (already normalized, lower is better)
        semantic_component = semantic_score
        
        # Keyword matching score
        doc_text = doc.page_content.lower()
        doc_title = doc.metadata.get('post_title', '').lower()
        
        # Count keyword matches
        keyword_matches = 0
        for keyword in query_words:
            if len(keyword) > 3:  # Skip short words
                keyword_matches += doc_text.count(keyword)
                keyword_matches += doc_title.count(keyword) * 2  # Title matches count more
        
        # Count intent keyword matches
        for intent_kw in intent_keywords:
            if intent_kw in doc_text:
                keyword_matches += 1
        
        # Normalize keyword score (inverse, so lower is better like semantic)
        keyword_score = max(0, 1.0 - (keyword_matches / 20.0))  # Normalize to 0-1
        
        # Hybrid score (lower is better)
        hybrid_score = (alpha * semantic_component) + ((1 - alpha) * keyword_score)
        
        reranked_docs.append((doc, hybrid_score, {
            "semantic": semantic_component,
            "keyword": keyword_score,
            "keyword_matches": keyword_matches
        }))
    
    # Sort by hybrid score
    reranked_docs.sort(key=lambda x: x[1])
    
    # Return in original format (doc, score)
    return [(doc, score) for doc, score, _ in reranked_docs]


def calculate_document_diversity(doc_results):
    """
    Calculate diversity score for retrieved documents.
    Higher diversity = more varied sources and topics.
    """
    sources = set()
    tags = set()
    titles = set()
    
    for doc, score in doc_results[:30]:  # Check top 30
        source_type = doc.metadata.get('source_type', 'unknown')
        tag = doc.metadata.get('tag', 'unknown')
        title = doc.metadata.get('post_title', doc.metadata.get('file_name', ''))
        
        sources.add(source_type)
        tags.add(tag)
        if title:
            titles.add(title[:50])  # First 50 chars to avoid duplicates
    
    # Diversity metrics
    source_diversity = len(sources) / max(len(doc_results[:30]), 1)
    tag_diversity = len(tags) / max(len(doc_results[:30]), 1)
    title_diversity = len(titles) / max(len(doc_results[:30]), 1)
    
    # Overall diversity score (0-1)
    overall_diversity = (source_diversity + tag_diversity + title_diversity) / 3
    
    return {
        "overall": round(overall_diversity, 3),
        "source_diversity": round(source_diversity, 3),
        "tag_diversity": round(tag_diversity, 3),
        "title_diversity": round(title_diversity, 3),
        "unique_sources": len(sources),
        "unique_tags": len(tags),
        "unique_titles": len(titles)
    }


def confidence_based_fallback(doc_results, intent: str, intent_confidence: float, query: str):
    """
    If confidence is low, try fallback retrieval strategies.
    Returns enhanced doc_results or original if fallback not needed.
    """
    # If confidence is already high, no fallback needed
    if intent_confidence >= 0.75:
        return doc_results, "no_fallback"
    
    print(f"[FALLBACK] Low confidence ({intent_confidence:.2f}), trying fallback strategies...")
    
    # Strategy 1: Try with "other" intent (broader search)
    if intent != "other" and intent_confidence < 0.6:
        print(f"[FALLBACK] Strategy 1: Expanding to 'other' branch")
        fallback_docs = retrieve_with_branch_filter(query, "other", k=50)
        
        # Merge with original results (deduplicate)
        seen = set()
        merged = []
        
        for doc, score in doc_results + fallback_docs:
            doc_id = f"{doc.metadata.get('source', '')}_{doc.page_content[:100]}"
            if doc_id not in seen:
                seen.add(doc_id)
                merged.append((doc, score))
        
        # Re-sort and limit
        merged.sort(key=lambda x: x[1])
        return merged[:50], "fallback_other_branch"
    
    # Strategy 2: If still low confidence, use simple semantic search
    if intent_confidence < 0.5:
        print(f"[FALLBACK] Strategy 2: Simple semantic search (no filtering)")
        fallback_docs = vectorstore.similarity_search_with_score(query, k=50)
        return fallback_docs, "fallback_semantic_only"
    
    return doc_results, "no_fallback"


router = APIRouter()

qa_chain = setup_qa_chain(retriever)


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

# File path for corrected responses
CORRECTED_RESPONSES_FILE = "./data/corrected_responses/corrected_responses.json"

def load_corrected_responses():
    """Load corrected responses from JSON file."""
    try:
        if os.path.exists(CORRECTED_RESPONSES_FILE):
            with open(CORRECTED_RESPONSES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('corrected_responses', [])
    except Exception as e:
        print(f"Error loading corrected responses: {e}")
    return []

def find_similar_corrected_response(question: str, threshold: float = 0.7):
    """Check if there's a corrected response for a similar question."""
    from difflib import SequenceMatcher
    
    corrected_responses = load_corrected_responses()
    
    if not corrected_responses:
        return None
    
    # Match against corrected responses directly
    # The feedback_history.json has a nested structure with trace_ids as keys
    try:
        best_match = None
        best_score = 0
        
        # Iterate through corrected responses to find matches
        for corrected in corrected_responses:
            # Get the original question if stored in corrected response
            original_question = corrected.get('original_question', '')
            
            if original_question:
                # Calculate similarity
                similarity = SequenceMatcher(None, question.lower(), original_question.lower()).ratio()
                
                if similarity > best_score and similarity >= threshold:
                    best_score = similarity
                    best_match = {
                        'response': corrected.get('corrected_response'),
                        'similarity': similarity,
                        'original_question': original_question
                    }
        
        if best_match:
            print(f"[OK] Found corrected response (similarity: {best_match['similarity']:.2%})")
            print(f"    Original question: {best_match['original_question']}")
            return best_match['response']
                
    except Exception as e:
        print(f"[WARNING] Error checking corrected responses: {e}")
    
    return None

def classify_query_type(question: str) -> str:
    """Classify query as informational, conversational, or transactional."""
    question_lower = question.lower()
    
    # Conversational indicators
    conversational_patterns = ["how are you", "who are you", "what are you", "your name", "thank you", "thanks", "hi", "hello", "bye"]
    if any(pattern in question_lower for pattern in conversational_patterns):
        return "conversational"
    
    # Transactional indicators
    transactional_patterns = ["download", "buy", "purchase", "subscribe", "sign up", "register", "login"]
    if any(pattern in question_lower for pattern in transactional_patterns):
        return "transactional"
    
    return "informational"

def classify_query_category(question: str) -> str:
    """Classify query into categories like migration, pricing, technical, etc."""
    question_lower = question.lower()
    
    if any(word in question_lower for word in ["price", "cost", "pricing", "fee", "payment", "subscription"]):
        return "pricing"
    elif any(word in question_lower for word in ["migrate", "migration", "transfer", "move data"]):
        return "migration"
    elif any(word in question_lower for word in ["error", "issue", "problem", "not working", "troubleshoot", "fix"]):
        return "support"
    elif any(word in question_lower for word in ["how to", "tutorial", "guide", "steps", "instructions"]):
        return "how_to"
    elif any(word in question_lower for word in ["certificate", "ssl", "security", "authentication", "oauth"]):
        return "security"
    elif any(word in question_lower for word in ["sharepoint", "onedrive", "google drive", "dropbox", "box"]):
        return "platform_specific"
    elif any(word in question_lower for word in ["api", "integration", "webhook", "developer"]):
        return "technical"
    else:
        return "general"

def extract_query_intent(question: str) -> str:
    """Extract user intent from the query."""
    question_lower = question.lower()
    
    if question.endswith("?"):
        if any(word in question_lower for word in ["how", "what", "why", "when", "where"]):
            return "request_information"
        elif any(word in question_lower for word in ["can", "could", "should", "is it possible"]):
            return "request_capability"
    
    if any(word in question_lower for word in ["download", "get", "need", "want"]):
        return "request_resource"
    elif any(word in question_lower for word in ["compare", "difference", "vs", "versus", "better"]):
        return "compare"
    elif any(word in question_lower for word in ["fix", "solve", "troubleshoot", "error"]):
        return "troubleshoot"
    elif any(word in question_lower for word in ["show", "list", "tell me"]):
        return "request_information"
    
    return "general_query"

def get_vectorstore_build_date() -> str:
    """Get the actual vectorstore build date from metadata file."""
    try:
        with open('./data/vectorstore_metadata.json', 'r', encoding='utf-8') as f:
            metadata = json.load(f)
            timestamp = metadata.get('timestamp', '')
            # Convert "2025-11-01T17:27:05.640130" to "2025-11-01"
            return timestamp.split('T')[0] if timestamp else "unknown"
    except FileNotFoundError:
        return "unknown"
    except Exception as e:
        print(f"[WARNING] Failed to read vectorstore metadata: {e}")
        return "unknown"

def is_conversational_query(question: str) -> bool:
    """Determine if a query is conversational/social rather than informational."""
    question_lower = question.lower().strip()
    
    # Common conversational patterns
    conversational_patterns = [
        r'^(hi|hello|hey|hiya|howdy)',
        r'^(how are you|how\'re you|how do you do)',
        r'^(what\'s up|whats up|wassup)',
        r'^(good morning|good afternoon|good evening)',
        r'^(thanks|thank you|thx)',
        r'^(bye|goodbye|see you|farewell)',
        r'^(yes|no|ok|okay|sure|alright)',
        r'^(what|who|where|when|why|how)\s+(are you|is it|was it)',
        r'^(tell me about yourself|who are you)',
        r'^(what can you do|what do you do)',
        r'^(help|can you help)',
        r'^(sorry|excuse me|pardon)',
        r'^(nice|good|great|awesome|cool|wow)',
        r'^(please|pls)',
    ]
    
    # Check if question matches conversational patterns
    for pattern in conversational_patterns:
        if re.match(pattern, question_lower):
            return True
    
    # Check for very short queries (ONLY 1-2 words, no question marks)
    # This ensures queries like "emojis ?" go through RAG, not conversational
    words = question.split()
    has_question_mark = '?' in question
    has_question_word = any(word in question_lower for word in ['what', 'how', 'why', 'when', 'where', 'who', 'which'])
    
    # Only treat as conversational if: very short (1-2 words), no '?', no question words
    if len(words) <= 2 and len(question.strip()) < 6 and not has_question_mark and not has_question_word:
        return True
    
    # Check if it's a simple greeting or social interaction (still allow short social phrases)
    social_words = ['hi', 'hello', 'hey', 'thanks', 'bye', 'good', 'nice', 'great', 'cool', 'awesome']
    if any(word in question_lower for word in social_words) and len(words) <= 2 and not has_question_mark:
        return True
    
    return False

def analyze_retrieved_documents(docs_with_scores):
    """Analyze retrieved documents and extract metadata."""
    if not docs_with_scores:
        return {
            "k_documents_retrieved": 0,
            "k_documents_used": 0,
            "sources_retrieved": {},
            "avg_similarity_score": 0.0,
            "top_similarity_score": 0.0,
            "lowest_similarity_score": 0.0,
            "sharepoint_docs_count": 0,
            "sharepoint_docs_percentage": 0.0,
            "sharepoint_folders": [],
            "blog_docs_count": 0,
            "pdf_docs_count": 0,
            "excel_docs_count": 0,
            "doc_docs_count": 0,
        }
    
    # Extract scores and sources
    scores = [score for _, score in docs_with_scores]
    sources_count = {}
    sharepoint_folders = set()
    sharepoint_count = 0
    blog_count = 0
    pdf_count = 0
    excel_count = 0
    doc_count = 0
    
    for doc, _ in docs_with_scores:
        # Determine source type from metadata
        metadata = doc.metadata if hasattr(doc, 'metadata') else {}
        source_type = metadata.get('source', 'unknown')
        
        # Count by source type
        if 'sharepoint' in source_type.lower():
            sharepoint_count += 1
            # Extract folder path
            tag = metadata.get('tag', '')
            if tag and tag.startswith('sharepoint/'):
                folder_path = tag.replace('sharepoint/', '').replace('/', ' > ')
                sharepoint_folders.add(folder_path)
        elif any(blog_indicator in source_type.lower() for blog_indicator in ['blog', 'wordpress', 'cloudfuze.com']):
            blog_count += 1
        elif 'pdf' in source_type.lower():
            pdf_count += 1
        elif 'excel' in source_type.lower() or 'xlsx' in source_type.lower():
            excel_count += 1
        elif 'doc' in source_type.lower():
            doc_count += 1
    
    total_docs = len(docs_with_scores)
    
    return {
        "k_documents_retrieved": total_docs,
        "k_documents_used": total_docs,  # After deduplication
        "sources_retrieved": {
            "sharepoint": sharepoint_count,
            "blog": blog_count,
            "pdf": pdf_count,
            "excel": excel_count,
            "doc": doc_count
        },
        "avg_similarity_score": round(sum(scores) / len(scores), 3) if scores else 0.0,
        "top_similarity_score": round(max(scores), 3) if scores else 0.0,
        "lowest_similarity_score": round(min(scores), 3) if scores else 0.0,
        "sharepoint_docs_count": sharepoint_count,
        "sharepoint_docs_percentage": round((sharepoint_count / total_docs) * 100, 1) if total_docs > 0 else 0.0,
        "sharepoint_folders": list(sharepoint_folders)[:5],  # Limit to top 5 folders
        "blog_docs_count": blog_count,
        "pdf_docs_count": pdf_count,
        "excel_docs_count": excel_count,
        "doc_docs_count": doc_count,
    }

# ============================================================================
# OPTION E: PERPLEXITY-STYLE RETRIEVAL FUNCTION
# ============================================================================

def perplexity_style_retrieve(
    query: str,
    k_dense: int = None,
    k_bm25: int = None,
    k_final: int = None,
    use_expansion: bool = None,
):
    """
    Perplexity-style retrieval:
      1. Optional LLM-based query expansion
      2. Dense retrieval from Chroma
      3. Sparse retrieval from BM25
      4. Merge + normalize scores
      5. Cross-encoder reranking
    """
    # Use config defaults if not provided
    if k_dense is None:
        k_dense = DENSE_RETRIEVAL_K
    if k_bm25 is None:
        k_bm25 = BM25_RETRIEVAL_K
    if k_final is None:
        k_final = FINAL_RETRIEVAL_K
    if use_expansion is None:
        use_expansion = ENABLE_QUERY_EXPANSION
    
    if not vectorstore:
        return []

    queries = [query]
    if use_expansion:
        try:
            expansions = query_expander.expand(query, n=3)
            print(f"[QUERY EXPANSION] {len(expansions)} expansions: {expansions}")
            queries.extend(expansions)
        except Exception as e:
            print(f"[WARN] Query expansion failed: {e}")

    # ---- 1. Dense retrieval (embeddings) ----
    dense_candidates = []
    for q in queries:
        try:
            # similarity_search_with_score returns (doc, distance) with lower=better
            results = vectorstore.similarity_search_with_score(q, k=k_dense)
            for doc, dist in results:
                dense_candidates.append((doc, float(dist)))
        except Exception as e:
            print(f"[WARN] Dense retrieval failed for query '{q}': {e}")

    # Deduplicate dense docs by id+content (keep best distance)
    dense_map = {}
    for doc, dist in dense_candidates:
        key = (doc.page_content[:120], doc.metadata.get("source_type", ""), doc.metadata.get("page_url", ""))
        if key not in dense_map or dist < dense_map[key][1]:
            dense_map[key] = (doc, dist)
    dense_list = list(dense_map.values())

    if dense_list:
        dists = [d for _, d in dense_list]
        d_min, d_max = min(dists), max(dists)
        def norm_dense(dist):
            # convert distance (0.2–0.8) to similarity (0–1)
            if d_max == d_min:
                return 1.0
            # smaller distance = higher similarity
            return (d_max - dist) / (d_max - d_min)
    else:
        norm_dense = lambda _: 0.0

    # ---- 2. Sparse retrieval (BM25) ----
    bm25_results = []
    if bm25_retriever:
        for q in queries:
            with suppress(Exception):
                bm25_results.extend(bm25_retriever.search(q, k=k_bm25))

        bm25_map = {}
        for doc, score in bm25_results:
            key = (doc.page_content[:120], doc.metadata.get("source_type", ""), doc.metadata.get("page_url", ""))
            if key not in bm25_map or score > bm25_map[key][1]:
                bm25_map[key] = (doc, score)
        bm25_list = list(bm25_map.values())

        if bm25_list:
            s = [s for _, s in bm25_list]
            s_min, s_max = min(s), max(s)
            def norm_bm25(score):
                if s_max == s_min:
                    return 1.0
                return (score - s_min) / (s_max - s_min)
        else:
            norm_bm25 = lambda _: 0.0
    else:
        bm25_list = []
        norm_bm25 = lambda _: 0.0

    # ---- 3. Merge dense + BM25 ----
    combined = {}
    for doc, dist in dense_list:
        key = (doc.page_content[:120], doc.metadata.get("source_type", ""), doc.metadata.get("page_url", ""))
        combined.setdefault(key, {"doc": doc, "dense": [], "bm25": []})
        combined[key]["dense"].append(dist)

    for doc, score in bm25_list:
        key = (doc.page_content[:120], doc.metadata.get("source_type", ""), doc.metadata.get("page_url", ""))
        combined.setdefault(key, {"doc": doc, "dense": [], "bm25": []})
        combined[key]["bm25"].append(score)

    candidates = []
    q_lower = query.lower()  # For metadata matching
    
    for key, info in combined.items():
        doc = info["doc"]
        meta = doc.metadata or {}
        
        if info["dense"]:
            dense_sim = max(norm_dense(d) for d in info["dense"])
        else:
            dense_sim = 0.0
        if info["bm25"]:
            bm25_sim = max(norm_bm25(s) for s in info["bm25"])
        else:
            bm25_sim = 0.0

        # Base score: DENSE_WEIGHT * dense + BM25_WEIGHT * bm25 (0–1)
        base_score = DENSE_WEIGHT * dense_sim + BM25_WEIGHT * bm25_sim
        
        # ---- Metadata-based boosts (generic, not hardcoded intents) ----
        # These boosts help surface relevant SharePoint docs that match query signals
        source_type = (meta.get("source_type") or meta.get("source") or "").lower()
        tag = (meta.get("tag") or "").lower()
        title = (meta.get("title") or meta.get("post_title") or "").lower()
        filename = (meta.get("filename") or "").lower()
        content_lower = doc.page_content.lower()

        # ---- Metadata-based boosting: SharePoint prioritization ----
        # Small general boost for SharePoint docs (internal documentation)
        # This helps prioritize internal docs over blog content
        if "sharepoint" in source_type or tag.startswith("sharepoint/"):
            base_score += 0.05

        candidates.append((doc, base_score))

    # Sort by base score descending
    candidates.sort(key=lambda x: x[1], reverse=True)

    # ---- 4. Cross-encoder reranking ----
    candidates = candidates[: max(k_final * 3, k_final)]  # pre-filter
    reranked = cross_reranker.rerank(query, candidates, top_k=k_final)

    return reranked  # list of (doc, final_score)


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
    """Chat endpoint: returns full answer from vectorstore. PROTECTED - requires valid authentication."""
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

    # FIRST: Check if we have a corrected response for this question
    corrected_answer = find_similar_corrected_response(question)
    
    if corrected_answer:
        # Use the corrected response
        answer = corrected_answer
    # Check if this is a conversational query
    elif is_conversational_query(question):
        # Handle conversational queries directly without document retrieval
        from langchain_core.prompts import ChatPromptTemplate
        
        llm = get_llm(temperature=0.7)
        
        # CloudFuze-focused conversational prompt
        conversational_prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a CloudFuze AI assistant specializing in cloud migration services. For greetings like 'hi', 'hello', 'thanks', 'bye', respond warmly and professionally. For ANY other topics unrelated to CloudFuze, cloud migration, or enterprise services, politely redirect by saying: 'I don't have information about that topic, but I can help you with CloudFuze's migration services or products. What would you like to know?'"),
            ("human", "{question}")
        ])
        
        # Don't use conversation context - treat each question independently
        # conversation_context = await get_conversation_context(conversation_id)
        # enhanced_query = f"{conversation_context}\n\nUser: {question}" if conversation_context else question
        enhanced_query = question  # Use current question only
        
        chain = conversational_prompt | llm
        result = chain.invoke({"question": enhanced_query})
        answer = result.content
    else:
        # Handle informational queries with document retrieval
        # Don't use conversation context - treat each question independently
        # conversation_context = await get_conversation_context(conversation_id)
        enhanced_query = question  # Use current question only
        
        # ============ INTENT CLASSIFICATION ============
        # Classify user intent to enable branch-specific retrieval
        intent_result = classify_intent(question)
        intent = intent_result["intent"]
        intent_confidence = intent_result["confidence"]
        intent_method = intent_result.get("method", "unknown")
        
        print(f"[INTENT] Classified as '{intent}' (confidence: {intent_confidence:.2f}, method: {intent_method})")
        
        # Check if vectorstore is available
        if vectorstore is None:
            print("Warning: Vectorstore not initialized. Using default qa_chain.")
            result = qa_chain.invoke({"query": enhanced_query})
            answer = result["result"]
        else:
            try:
                # ============ QUERY EXPANSION ============
                # Expand query with intent-specific terms for better retrieval
                expanded_query = expand_query_with_intent(enhanced_query, intent)
                
                # ============ BRANCH-SPECIFIC RETRIEVAL ============
                # Use intent-based filtering to retrieve relevant documents
                RETRIEVAL_K = 50  # Number of documents to retrieve from vectorstore
                doc_results = retrieve_with_branch_filter(
                    query=expanded_query,
                    intent=intent,
                    k=RETRIEVAL_K
                )
                
                print(f"[RETRIEVAL] Retrieved {len(doc_results)} documents from '{intent}' branch")
                
                # ============ DETAILED VECTORDB LOGGING ============
                print(f"[VECTORDB] Detailed retrieval info:")
                for i, (doc, score) in enumerate(doc_results[:10]):  # Log top 10
                    metadata = doc.metadata if hasattr(doc, 'metadata') else {}
                    tag = metadata.get('tag', 'N/A')
                    source_type = metadata.get('source_type', 'N/A')
                    title = metadata.get('post_title', metadata.get('title', 'N/A'))
                    content_preview = doc.page_content[:100] if hasattr(doc, 'page_content') else 'N/A'
                    print(f"  [{i+1}] Score: {score:.4f} | Tag: {tag} | Source: {source_type} | Title: {title[:60]}")
                    print(f"      Content preview: {content_preview}...")
                
                # ============ CONFIDENCE-BASED FALLBACK ============
                # If confidence is low, try alternative retrieval strategies
                doc_results, fallback_strategy = confidence_based_fallback(
                    doc_results=doc_results,
                    intent=intent,
                    intent_confidence=intent_confidence,
                    query=enhanced_query
                )
                
                if fallback_strategy != "no_fallback":
                    print(f"[FALLBACK] Applied strategy: {fallback_strategy}, now have {len(doc_results)} docs")
                
                # ============ SOURCE PRIORITIZATION ============
                # Boost SharePoint documents to prioritize internal documentation
                PRIORITIZE_SHAREPOINT = True  # Set to False to disable prioritization
                SHAREPOINT_BOOST = 0.6  # Lower score = higher priority (0.6 = 40% boost)
                EMAIL_BOOST = 0.8  # 20% boost for emails
                
                if PRIORITIZE_SHAREPOINT:
                    boosted_docs = []
                    sharepoint_count = 0
                    email_count = 0
                    blog_count = 0
                    
                    for doc, score in doc_results:
                        metadata = doc.metadata if hasattr(doc, 'metadata') else {}
                        tag = metadata.get('tag', '').lower()
                        source_type = metadata.get('source_type', '').lower()
                        
                        # Apply source-based boosting
                        adjusted_score = score
                        if 'sharepoint' in tag or source_type == 'sharepoint':
                            adjusted_score = score * SHAREPOINT_BOOST
                            sharepoint_count += 1
                        elif 'email' in tag or source_type == 'email' or 'outlook' in tag:
                            adjusted_score = score * EMAIL_BOOST
                            email_count += 1
                        else:
                            blog_count += 1
                        
                        boosted_docs.append((doc, adjusted_score))
                    
                    # Re-sort by adjusted scores (lower is better)
                    boosted_docs.sort(key=lambda x: x[1])
                    doc_results = boosted_docs
                    
                    print(f"[PRIORITIZATION] Boosted sources - SharePoint: {sharepoint_count}, Email: {email_count}, Blog: {blog_count}")
                
                # ============ HYBRID RANKING ============
                # Combine semantic similarity with keyword matching
                doc_results = hybrid_ranking(
                    doc_results=doc_results,
                    query=question,  # Use original query for keyword matching
                    intent=intent,
                    alpha=0.7  # 70% semantic, 30% keyword
                )
                
                print(f"[HYBRID RANKING] Reranked {len(doc_results)} documents with semantic + keyword scores")
                
                # ============ DOCUMENT DIVERSITY ============
                # Calculate diversity metrics for retrieved documents
                diversity_metrics = calculate_document_diversity(doc_results)
                print(f"[DIVERSITY] Overall: {diversity_metrics['overall']:.2f}, Sources: {diversity_metrics['unique_sources']}, Tags: {diversity_metrics['unique_tags']}")
                
                final_docs = [doc for doc, score in doc_results]  # Extract just the documents
                
                # Format the documents for the context
                from app.llm import format_docs
                formatted_docs = format_docs(final_docs)
                context = "\n\n".join(formatted_docs)
                
                # Create prompt and get answer
                from langchain_core.prompts import ChatPromptTemplate
                from config import SYSTEM_PROMPT
                
                prompt_template = ChatPromptTemplate.from_messages([
                    ("system", SYSTEM_PROMPT),
                    ("human", "Context: {context}\n\nQuestion: {question}")
                ])
                
                llm = get_llm(
                    temperature=0.1,  # Low temperature for consistent responses
                    max_tokens=1500
                )
                
                chain = prompt_template | llm
                result = chain.invoke({
                    "context": context,
                    "question": enhanced_query
                })
                
                answer = result.content
                
            except Exception as e:
                print(f"[ERROR] Intent-based retrieval failed: {e}")
                # Fallback to original qa_chain if something goes wrong
                result = qa_chain.invoke({"query": enhanced_query})
                answer = result["result"]

    # Track message event for analytics (non-blocking)
    try:
        await mongodb_memory.insert_message_event(user_id, session_id, user_email)
    except Exception as e:
        logger.debug(f"Failed to track message event: {e}")

    # Add both user question and bot response to conversation AFTER processing
    await add_to_conversation(conversation_id, "user", question)
    await add_to_conversation(conversation_id, "assistant", answer)

    # Log to Langfuse for observability
    trace_id = langfuse_tracker.create_trace(
        user_id=conversation_id,
        question=question,
        answer=answer,
        session_id=session_id,
        user_name=user_name,
        user_email=user_email,
        metadata={
            "user_id": user_id or "anonymous",
            "session_id": session_id,
            "user_name": user_name,
            "user_email": user_email,
            "request": {
            "endpoint": "/chat",
                "timestamp": datetime.now().isoformat()
            },
            "query": {
                "is_conversational": is_conversational_query(question)
            }
        }
    )

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

    async def generate_stream():
        try:
            # FIRST: Check if we have a corrected response for this question
            corrected_answer = find_similar_corrected_response(question)
            
            if corrected_answer:
                # Use the corrected response
                yield f"data: {json.dumps({'type': 'thinking_complete'})}\n\n"
                
                # Stream the corrected answer token by token
                full_response = corrected_answer
                for i, char in enumerate(corrected_answer):
                    yield f"data: {json.dumps({'token': char, 'type': 'token'})}\n\n"
                    if i % 5 == 0:  # Add slight delay every 5 characters
                        await asyncio.sleep(0.01)
                
                # Add to conversation
                await add_to_conversation(conversation_id, "user", question)
                await add_to_conversation(conversation_id, "assistant", full_response)
                
                # Log to Langfuse
                trace_id = None
                try:
                    trace_id = langfuse_tracker.create_trace(
                        user_id=conversation_id,
                        question=question,
                        answer=full_response,
                        session_id=session_id,
                        user_name=user_name,
                        user_email=user_email,
                        metadata={
                            "user_id": user_id or "anonymous",
                            "session_id": session_id,
                            "user_name": user_name,
                            "user_email": user_email,
                            "request": {
                            "endpoint": "/chat/stream",
                                "timestamp": datetime.now().isoformat()
                            },
                            "system": {
                            "used_corrected_response": True
                            }
                        }
                    )
                except Exception as e:
                    print(f"Warning: Langfuse logging failed: {e}")
                
                # Generate recommended questions (no docs available for corrected responses)
                recommended_questions = []
                try:
                    from app.llm import generate_recommended_questions_from_docs
                    # For corrected responses, pass empty docs list
                    recommended_questions = generate_recommended_questions_from_docs(
                        user_question=question,
                        retrieved_docs=[],
                        bot_response=full_response
                    )
                except Exception as e:
                    print(f"[WARNING] Failed to generate recommendations: {e}")
                
                # Log trace_id status for debugging
                if trace_id:
                    print(f"[TRACE_ID] ✓ Sending trace_id to frontend: {trace_id}")
                else:
                    print(f"[TRACE_ID] ⚠️ WARNING: trace_id is None - feedback will use fallback ID")
                    print(f"[TRACE_ID] This means Langfuse trace creation failed - check Langfuse configuration")
                
                yield f"data: {json.dumps({'type': 'done', 'full_response': full_response, 'trace_id': trace_id, 'recommended_questions': recommended_questions})}\n\n"
                return
            
            # Don't use conversation context - treat each question independently
            # conversation_context = await get_conversation_context(conversation_id)
            # enhanced_query = f"{conversation_context}\n\nUser: {question}" if conversation_context else question
            enhanced_query = question  # Use current question only
            conversation_context = None  # Set to None for metadata logging
            
            # Check if this is a conversational query
            is_conv = is_conversational_query(question)
            
            if is_conv:
                # Handle conversational queries directly without document retrieval
                yield f"data: {json.dumps({'type': 'thinking_complete'})}\n\n"
                
                from langchain_core.prompts import ChatPromptTemplate
                
                llm = get_llm(
                    streaming=True, 
                    temperature=0.7,
                    max_tokens=500
                )
                
                # CloudFuze-focused conversational prompt
                conversational_prompt = ChatPromptTemplate.from_messages([
                    ("system", "You are a CloudFuze AI assistant specializing in cloud migration services. For greetings like 'hi', 'hello', 'thanks', 'bye', respond warmly and professionally. For ANY other topics unrelated to CloudFuze, cloud migration, or enterprise services, politely redirect by saying: 'I don't have information about that topic, but I can help you with CloudFuze's migration services or products. What would you like to know?'"),
                    ("human", "{question}")
                ])
                
                # Stream the response
                full_response = ""
                messages = conversational_prompt.format_messages(question=enhanced_query)
                async for chunk in llm.astream(messages):
                    if hasattr(chunk, 'content'):
                        token = chunk.content
                        full_response += token
                        yield f"data: {json.dumps({'token': token, 'type': 'token'})}\n\n"
                        await asyncio.sleep(0.01)
                
                # Add to conversation
                await add_to_conversation(conversation_id, "user", question)
                await add_to_conversation(conversation_id, "assistant", full_response)
                
                # Log to Langfuse (don't block response if this fails)
                trace_id = None
                try:
                    trace_id = langfuse_tracker.create_trace(
                        user_id=conversation_id,
                        question=question,
                        answer=full_response,
                        session_id=session_id,
                        user_name=user_name,
                        user_email=user_email,
                        metadata={
                            "user_id": user_id or "anonymous",
                            "session_id": session_id,
                            "user_name": user_name,
                            "user_email": user_email,
                            "request": {
                            "endpoint": "/chat/stream",
                                "timestamp": datetime.now().isoformat()
                            },
                            "query": {
                                "is_conversational": True
                            },
                            "generation": {
                                "model": "gpt-4o-mini",
                            "streaming": True
                            }
                        }
                    )
                except Exception as e:
                    print(f"Langfuse logging failed: {e}")
                
                # Generate recommended questions (no docs for conversational queries)
                recommended_questions = []
                try:
                    from app.llm import generate_recommended_questions_from_docs
                    recommended_questions = generate_recommended_questions_from_docs(
                        user_question=question,
                        retrieved_docs=[],
                        bot_response=full_response
                    )
                except Exception as e:
                    print(f"[WARNING] Failed to generate recommendations: {e}")
                
                # Log trace_id status for debugging
                if trace_id:
                    print(f"[TRACE_ID] ✓ Sending trace_id to frontend: {trace_id}")
                else:
                    print(f"[TRACE_ID] ⚠️ WARNING: trace_id is None - feedback will use fallback ID")
                    print(f"[TRACE_ID] This means Langfuse trace creation failed - check Langfuse configuration")
                
                # Send completion signal with trace_id and recommendations
                yield f"data: {json.dumps({'type': 'done', 'full_response': full_response, 'trace_id': trace_id, 'recommended_questions': recommended_questions})}\n\n"
                return
            
            # ===== START RAG PIPELINE TRACING =====
            # Create structured Langfuse trace for RAG pipeline
            rag_trace = None
            try:
                rag_trace = langfuse_tracker.create_rag_pipeline_trace(
                    user_id=conversation_id,
                    question=question,
                    session_id=session_id,
                    user_name=user_name,
                    user_email=user_email,
                    metadata={
                        "endpoint": "/chat/stream",
                        "conversational_query": False,
                        "streaming": True
                    }
                )
                
                # Start query processing span
                if rag_trace:
                    rag_trace.start_query(enhanced_query, metadata={"has_conversation_context": False})
            except Exception as e:
                print(f"[WARNING] Failed to create RAG trace: {e}")
                rag_trace = None
            
            # PHASE 1: THINKING - Document retrieval and processing
            # This happens while the frontend shows "Thinking..." animation
            
            # Send initial thinking status
            yield f"data: {json.dumps({'type': 'status', 'status': 'analyzing_query', 'message': 'Analyzing query'})}\n\n"
            await asyncio.sleep(0.05)
            
            # Start timing for metadata
            retrieval_start_time = time.time()
            thinking_start_time = time.time()
            
            # Configuration for document retrieval
            RETRIEVAL_K = 50  # Number of documents to retrieve from vectorstore
            
            # Initialize metadata collectors
            query_classification = {
                "query_type": classify_query_type(question),
                "query_category": classify_query_category(question),
                "query_intent": extract_query_intent(question),
                "is_conversational_query": is_conv,
                "query_length_words": len(question.split()),
                "query_length_chars": len(question),
                "has_followup": False,  # Conversation context disabled
            }
            
            try:
                # Send status: Query expansion
                if ENABLE_QUERY_EXPANSION:
                    yield f"data: {json.dumps({'type': 'status', 'status': 'expanding_query', 'message': 'Expanding query for better results'})}\n\n"
                    await asyncio.sleep(0.05)
                
                # Send status: Document retrieval
                yield f"data: {json.dumps({'type': 'status', 'status': 'retrieving_docs', 'message': 'Searching knowledge base'})}\n\n"
                await asyncio.sleep(0.05)
                
                # ====== PERPLEXITY-STYLE RAG (OPTION E) ======
                # Retrieve docs with dense + BM25 + reranker
                doc_results = perplexity_style_retrieve(
                    query=enhanced_query,
                    k_dense=40,
                    k_bm25=40,
                    k_final=8,
                    use_expansion=True,
                )

                final_docs = [doc for doc, score in doc_results]
                
                print(f"[RAG] Retrieved {len(final_docs)} docs using Option E pipeline")
                
                # Send status: Documents found and reranking
                yield f"data: {json.dumps({'type': 'status', 'status': 'reranking_docs', 'message': f'Found {len(doc_results)} documents, reranking for relevance'})}\n\n"
                await asyncio.sleep(0.05)
                
                # You can still compute diversity metrics if you like
                diversity_metrics = calculate_document_diversity(
                    [(doc, 1.0) for doc in final_docs]
                )
                
                # For compatibility with existing code, create fallback variables
                intent = "option_e"
                intent_confidence = 1.0
                intent_method = "perplexity_style"
                fallback_strategy = "no_fallback"
                expanded_query = enhanced_query  # No expansion needed, handled by perplexity_style_retrieve
                    
                # Record retrieval time
                retrieval_time_ms = int((time.time() - retrieval_start_time) * 1000)
                
                # Log what sources we're retrieving (for backend debugging)
                retrieved_sources = {}
                for doc in final_docs:
                    tag = doc.metadata.get('tag', 'unknown')
                    source_type = doc.metadata.get('source_type', 'unknown')
                    if tag not in retrieved_sources:
                        retrieved_sources[tag] = 0
                    retrieved_sources[tag] += 1
                
                print(f"[DEBUG] Retrieved {len(final_docs)} documents from search")
                print(f"[DEBUG] Documents by tag: {retrieved_sources}")
                
                # Add detailed document logging
                print(f"\n[SOURCES] Detailed document breakdown:")
                for i, (doc, score) in enumerate(doc_results[:10]):  # Log top 10
                    metadata = doc.metadata if hasattr(doc, 'metadata') else {}
                    
                    # Extract metadata
                    tag = metadata.get('tag', 'N/A')
                    source_type = metadata.get('source_type', 'N/A')
                    
                    # Get title from various possible fields
                    title = metadata.get('post_title') or metadata.get('title') or metadata.get('file_name') or 'N/A'
                    
                    # Get URL or file path
                    url = metadata.get('url') or metadata.get('file_path') or metadata.get('source') or 'N/A'
                    
                    # Content preview
                    content_preview = doc.page_content[:150] if hasattr(doc, 'page_content') else 'N/A'
                    
                    print(f"  [{i+1}] Score: {score:.4f}")
                    print(f"      Type: {tag} | Source: {source_type}")
                    print(f"      Title: {title[:80]}")
                    print(f"      URL/Path: {url[:100]}")
                    print(f"      Preview: {content_preview}...")
                    print()
                
                # Send status: Reading from sources
                source_list = []
                if retrieved_sources.get('blog', 0) > 0:
                    source_list.append(f"{retrieved_sources['blog']} from blog")
                if retrieved_sources.get('sharepoint', 0) > 0:
                    source_list.append(f"{retrieved_sources['sharepoint']} from SharePoint")
                if source_list:
                    source_message = "Reading " + " and ".join(source_list)
                    yield f"data: {json.dumps({'type': 'status', 'status': 'reading_sources', 'message': source_message})}\n\n"
                    await asyncio.sleep(0.05)
                
                # If no SharePoint documents found, try a more aggressive search for SharePoint content
                has_sharepoint = any(
                    doc.metadata.get('source_type') == 'sharepoint' or 
                    'sharepoint' in doc.metadata.get('tag', '').lower()
                    for doc in final_docs
                )
                
                if not has_sharepoint and any(word in enhanced_query.lower() for word in ['sharepoint', 'document', 'file', 'folder', 'download', 'certificate']):
                    print("[DEBUG] No SharePoint docs found - trying SharePoint-specific search...")
                    try:
                        # Try searching for SharePoint content with modified queries
                        sharepoint_docs = vectorstore.similarity_search(enhanced_query + " SharePoint", k=30)
                        # Filter results to only SharePoint documents
                        sharepoint_docs = [d for d in sharepoint_docs if d.metadata.get('source_type') == 'sharepoint']
                        if sharepoint_docs:
                            print(f"[DEBUG] Found {len(sharepoint_docs)} SharePoint documents with filter")
                            # Add SharePoint docs to results (prioritize them)
                            final_docs = sharepoint_docs[:10] + final_docs
                            print(f"[DEBUG] Updated total: {len(final_docs)} documents")
                    except Exception as e:
                        print(f"[DEBUG] Filtered search failed (this is OK): {e}")
                        # Try search with different query variations
                        try:
                            sharepoint_queries = [
                                enhanced_query + " SharePoint",
                                enhanced_query + " document",
                                enhanced_query.replace("?", "").replace("how", "what")
                            ]
                            for sp_query in sharepoint_queries[:2]:
                                sp_docs = vectorstore.similarity_search(sp_query, k=15)
                                # Filter for SharePoint docs
                                sp_filtered = [d for d in sp_docs if d.metadata.get('source_type') == 'sharepoint']
                                if sp_filtered:
                                    final_docs.extend(sp_filtered[:5])
                                    break
                        except Exception as e2:
                            print(f"[DEBUG] Alternative search failed: {e2}")
            except Exception as e:
                print(f"Error during document search: {e}")
                import traceback
                traceback.print_exc()
                final_docs = []
                # Initialize intent variables if not already set
                if 'intent' not in locals():
                    intent = "other"
                    intent_confidence = 1.0
                    intent_method = "error_fallback"
                if 'fallback_strategy' not in locals():
                    fallback_strategy = "no_retrieval"
            
            # Filter out documents with None page_content
            final_docs = [doc for doc in final_docs if doc.page_content is not None and doc.page_content.strip()]
            print(f"[DEBUG] Final documents for context: {len(final_docs)} (after filtering None content)")
            
            # Deduplicate documents while preserving relevance order (prioritize SharePoint if found)
            seen_ids = set()
            unique_docs = []
            
            # First, add SharePoint documents if any
            for doc in final_docs:
                if doc.metadata.get('source_type') == 'sharepoint':
                    doc_id = f"{doc.metadata.get('source', '')}_{doc.metadata.get('file_name', '')}_{doc.page_content[:100]}"
                    if doc_id not in seen_ids:
                        seen_ids.add(doc_id)
                        unique_docs.append(doc)
            
            # Then add other documents
            for doc in final_docs:
                if doc.metadata.get('source_type') != 'sharepoint':
                    doc_id = f"{doc.metadata.get('source', '')}_{doc.page_content[:100]}"
                    if doc_id not in seen_ids:
                        seen_ids.add(doc_id)
                        unique_docs.append(doc)
            
            # Limit to top 30 documents for LLM processing
            final_docs = unique_docs[:30]
            
            print(f"[DEBUG] Final documents for context: {len(final_docs)} (after deduplication)")
            
            # Send status: Selected top documents
            yield f"data: {json.dumps({'type': 'status', 'status': 'selecting_docs', 'message': f'Selected top {len(final_docs)} most relevant documents'})}\n\n"
            await asyncio.sleep(0.05)
            
            # Analyze final documents after deduplication for accurate metadata
            # We need to pair final_docs with their scores from doc_results
            final_docs_with_scores = []
            for final_doc in final_docs:
                # Find the matching doc in doc_results to get its score
                for doc, score in doc_results:
                    if doc.page_content == final_doc.page_content:
                        final_docs_with_scores.append((final_doc, score))
                        break
            
            # ============ SCORE-BASED RELEVANCE FILTERING ============
            # Filter out documents with poor relevance scores to prevent hallucination
            if final_docs_with_scores:
                scores = [score for _, score in final_docs_with_scores]
                max_score = max(scores)
                avg_score = sum(scores) / len(scores)
                score_margin = max_score - avg_score
                
                print(f"[SCORE FILTERING] Max: {max_score:.3f}, Avg: {avg_score:.3f}, Margin: {score_margin:.3f}")
                
                # Apply quality gates
                # Gate 1: Maximum score must be above threshold
                # Gate 2: There must be sufficient separation (avoid all-mediocre results)
                from config import MIN_SCORE_THRESHOLD, SCORE_MARGIN_THRESHOLD
                
                if max_score < MIN_SCORE_THRESHOLD:
                    print(f"[SCORE FILTERING] ❌ Max score {max_score:.3f} below threshold {MIN_SCORE_THRESHOLD}")
                    print(f"[SCORE FILTERING] All documents deemed irrelevant - returning no context")
                    final_docs_with_scores = []
                    final_docs = []
                elif score_margin < SCORE_MARGIN_THRESHOLD and avg_score < 0:
                    print(f"[SCORE FILTERING] ⚠️ Low score margin {score_margin:.3f} with negative avg {avg_score:.3f}")
                    print(f"[SCORE FILTERING] All documents mediocre - returning no context")
                    final_docs_with_scores = []
                    final_docs = []
                else:
                    # Keep only documents above a reasonable threshold
                    # Use dynamic threshold: avg_score - 1.0 (or MIN_SCORE_THRESHOLD, whichever is higher)
                    dynamic_threshold = max(MIN_SCORE_THRESHOLD, avg_score - 1.0)
                    filtered = [(doc, score) for doc, score in final_docs_with_scores if score > dynamic_threshold]
                    
                    if filtered:
                        final_docs_with_scores = filtered
                        final_docs = [doc for doc, score in filtered]
                        print(f"[SCORE FILTERING] ✅ Kept {len(final_docs)} docs above dynamic threshold {dynamic_threshold:.3f}")
                    else:
                        print(f"[SCORE FILTERING] ❌ All docs below dynamic threshold")
                        final_docs_with_scores = []
                        final_docs = []
            
            doc_analysis = analyze_retrieved_documents(final_docs_with_scores)
            
            # ===== LOG RETRIEVAL TO LANGFUSE =====
            if rag_trace:
                try:
                    # Calculate sources breakdown for tracing
                    trace_sources = {}
                    for doc in final_docs:
                        source_type = doc.metadata.get('source_type', 'unknown')
                        tag = doc.metadata.get('tag', 'unknown')
                        key = f"{source_type}:{tag}"
                        trace_sources[key] = trace_sources.get(key, 0) + 1
                    
                    rag_trace.log_retrieval(
                        query=enhanced_query,
                        retrieved_docs=final_docs,
                        doc_count=len(final_docs),
                        sources_breakdown=trace_sources,
                        metadata={"search_k": 50, "final_k": len(final_docs), "score_filtered": len(final_docs_with_scores) < len(doc_results)}
                    )
                except Exception as e:
                    print(f"[WARNING] Failed to log retrieval: {e}")
            
            # Format the documents properly with metadata using format_docs from llm.py
            forced_no_context = False  # Track if we're forcing no-context response
            try:
                from app.llm import format_docs
                
                if not final_docs:
                    print("[WARNING] No relevant documents after score filtering!")
                    context_text = ""  # Empty context, not "No relevant documents found"
                    forced_no_context = True
                else:
                    formatted_docs = format_docs(final_docs)
                    context_text = "\n\n".join([f"Document {i+1}:\n{formatted_doc}" for i, formatted_doc in enumerate(formatted_docs)])
                    print(f"[DEBUG] Context length: {len(context_text)} characters")
                    print(f"[DEBUG] First 500 chars of context: {context_text[:500]}...")
                    
                    # ============ CONTEXT COMPRESSION (OPTION E) ============
                    if ENABLE_CONTEXT_COMPRESSION and len(context_text) > 8000:
                        print(f"[CONTEXT] Context too long ({len(context_text)} chars), compressing...")
                        try:
                            context_text = context_compressor.compress(final_docs, max_chars=8000)
                            print(f"[CONTEXT] Compressed length: {len(context_text)} chars")
                        except Exception as e:
                            print(f"[WARN] Context compression failed: {e}")
                            # Keep original context if compression fails
            except Exception as e:
                print(f"[ERROR] Failed to format documents: {e}")
                import traceback
                traceback.print_exc()
                # Fallback: use raw document content
                context_text = "\n\n".join([f"Document {i+1}:\n{doc.page_content}" for i, doc in enumerate(final_docs[:10])])
            
            # Extract source information for console logging - only from TOP relevant documents
            # Use top 10 most relevant documents (best similarity scores) to determine sources
            top_relevant_count = min(10, len(final_docs))
            top_relevant_docs = final_docs[:top_relevant_count]
            
            # Track unique sources from top relevant documents only
            sources_seen = set()
            sources_used = []
            for doc in top_relevant_docs:
                tag = doc.metadata.get('tag', 'unknown')
                source_type = doc.metadata.get('source_type', 'unknown')
                
                # Create a clean source identifier
                if source_type == 'sharepoint':
                    folder_path = doc.metadata.get('folder_path', '')
                    if folder_path:
                        # Use full folder path for clarity
                        source_id = f"SharePoint: {folder_path}"
                    else:
                        source_id = 'SharePoint'
                elif tag == 'blog':
                    source_id = 'Blog Content'
                elif tag == 'pdf':
                    source_id = 'PDF Documents'
                elif tag == 'excel':
                    source_id = 'Excel Documents'
                elif tag == 'doc':
                    source_id = 'Word Documents'
                else:
                    source_id = tag.replace('_', ' ').title()
                
                # Only add unique sources
                if source_id not in sources_seen:
                    sources_seen.add(source_id)
                    sources_used.append(source_id)
            
            # Format source info for console
            if sources_used:
                source_info = f"Response generated from: {', '.join(sources_used)}"
            else:
                source_info = "Response generated (sources unknown)"
            
            # Send final status before generation
            yield f"data: {json.dumps({'type': 'status', 'status': 'generating', 'message': 'Generating response'})}\n\n"
            await asyncio.sleep(0.1)
            
            # Send signal that thinking is complete and streaming will start
            thinking_time_ms = int((time.time() - thinking_start_time) * 1000)
            yield f"data: {json.dumps({'type': 'thinking_complete'})}\n\n"
            
            # Send source information for console logging
            yield f"data: {json.dumps({'type': 'sources', 'sources': source_info})}\n\n"
            
            # Collect context preparation metadata
            context_size_chars = len(context_text)
            context_size_tokens = context_size_chars // 4  # Rough approximation
            
            # PHASE 2: STREAMING - Generate and stream response
            # This happens after the frontend clears the "Thinking..." animation
            llm_start_time = time.time()
            
            # Create streaming LLM with low temperature for consistent responses
            llm = get_llm(
                streaming=True, 
                temperature=0.1,  # Low temperature for more consistent, deterministic responses
                max_tokens=1500
            )
            
            # Create the prompt template
            from langchain_core.prompts import ChatPromptTemplate
            from config import SYSTEM_PROMPT
            
            # Adapt prompt based on whether we have relevant context
            if forced_no_context:
                # No relevant documents - explicitly tell LLM
                prompt_template = ChatPromptTemplate.from_messages([
                    ("system", SYSTEM_PROMPT + "\n\nIMPORTANT: No relevant documents were found in the knowledge base for this query."),
                    ("human", "Question: {question}")
                ])
                messages = prompt_template.format_messages(question=enhanced_query)
            else:
                # Normal flow with context
                prompt_template = ChatPromptTemplate.from_messages([
                    ("system", SYSTEM_PROMPT),
                    ("human", "Context: {context}\n\nQuestion: {question}")
                ])
                messages = prompt_template.format_messages(context=context_text, question=enhanced_query)
            
            # ===== START SYNTHESIS SPAN =====
            if rag_trace:
                try:
                    rag_trace.start_synthesis(
                        context=context_text,
                        metadata={
                            "context_length": len(context_text),
                            "document_count": len(final_docs),
                            "model": "gpt-4o-mini",
                            "temperature": 0.1,
                            "forced_no_context": forced_no_context
                        }
                    )
                except Exception as e:
                    print(f"[WARNING] Failed to start synthesis: {e}")
            
            # Stream the response with real-time streaming
            full_response = ""
            # messages already created above based on forced_no_context
            async for chunk in llm.astream(messages):
                if hasattr(chunk, 'content'):
                    token = chunk.content
                    full_response += token
                    yield f"data: {json.dumps({'token': token, 'type': 'token'})}\n\n"
                    # Removed sleep for faster streaming
            
            # Record LLM generation time
            llm_time_ms = int((time.time() - llm_start_time) * 1000)
            streaming_time_ms = llm_time_ms  # In streaming mode, these are the same
            
            # Track message event for analytics (non-blocking)
            try:
                await mongodb_memory.insert_message_event(user_id, session_id, user_email)
            except Exception as e:
                logger.debug(f"Failed to track message event: {e}")
            
            # Add both user question and bot response to conversation AFTER processing
            await add_to_conversation(conversation_id, "user", question)
            await add_to_conversation(conversation_id, "assistant", full_response)
            
            # Calculate total response time
            total_time_ms = thinking_time_ms + llm_time_ms
            
            # Calculate overall confidence score
            avg_similarity = doc_analysis.get("avg_similarity_score", 0.5)
            overall_confidence = calculate_confidence(
                intent_confidence=intent_confidence,
                retrieval_docs=len(final_docs),
                avg_similarity=avg_similarity
            )
            
            # ===== BUILD COMPREHENSIVE METADATA (NESTED STRUCTURE) =====
            comprehensive_metadata = {
                # User info at top level for easy filtering
                "user_id": user_id or "anonymous",
                "session_id": session_id,
                "user_name": user_name,
                "user_email": user_email,
                
                "request": {
                    "endpoint": "/chat/stream",
                    "timestamp": datetime.now().isoformat()
                },
                
                # ===== INTENT CLASSIFICATION (NEW) =====
                "intent": {
                    "detected": intent,
                    "confidence": intent_confidence,
                    "method": intent_method,
                    "branch_description": INTENT_BRANCHES.get(intent, {}).get("description", "Option E: Perplexity-style RAG")
                },
                
                # ===== CONFIDENCE SCORING (NEW) =====
                "confidence": {
                    "overall": overall_confidence,
                    "breakdown": {
                        "intent": intent_confidence,
                        "retrieval": min(len(final_docs) / 30.0, 1.0),
                        "similarity": max(0, 1.0 - avg_similarity) if avg_similarity else 0.5
                    }
                },
                
                "query": {
                    "classification": {
                        "type": query_classification["query_type"],
                        "category": query_classification["query_category"],
                        "intent": query_classification["query_intent"],
                        "is_conversational": query_classification["is_conversational_query"]
                    },
                    "metrics": {
                        "length_words": query_classification["query_length_words"],
                        "length_chars": query_classification["query_length_chars"],
                        "has_followup": query_classification["has_followup"]
                    }
                },
                
                "retrieval": {
                    "method": "advanced_rag_pipeline",
                    "branch": intent,
                    "techniques_applied": ["intent_classification", "query_expansion", "hybrid_ranking", "diversity_scoring"],
                    "fallback_strategy": fallback_strategy,
                    "query_expansion": {
                        "original": question,
                        "expanded": expanded_query if 'expanded_query' in locals() else question,
                        "expansion_terms": INTENT_BRANCHES.get(intent, {}).get("query_expansion", [])
                    },
                    "documents": {
                        "requested": RETRIEVAL_K,
                        "retrieved": doc_analysis["k_documents_retrieved"],
                        "used": doc_analysis["k_documents_used"]
                    },
                    "similarity_scores": {
                        "avg": doc_analysis["avg_similarity_score"],
                        "top": doc_analysis["top_similarity_score"],
                        "lowest": doc_analysis["lowest_similarity_score"]
                    },
                    "diversity": diversity_metrics if diversity_metrics else {},
                    "sources": doc_analysis["sources_retrieved"],
                    "sharepoint": {
                        "count": doc_analysis["sharepoint_docs_count"],
                        "percentage": doc_analysis["sharepoint_docs_percentage"],
                        "folders": doc_analysis["sharepoint_folders"]
                    },
                    "blog_count": doc_analysis["blog_docs_count"],
                    "pdf_count": doc_analysis["pdf_docs_count"],
                    "excel_count": doc_analysis["excel_docs_count"],
                    "doc_count": doc_analysis["doc_docs_count"],
                    "time_ms": retrieval_time_ms
                },
                
                "context": {
                    "size": {
                        "chars": context_size_chars,
                        "tokens": context_size_tokens,
                        "chunks": len(final_docs)
                    },
                    "preparation_ms": retrieval_time_ms,
                    "truncated": len(unique_docs) > 30,
                    "conversation": {
                        "has_history": False,  # Conversation context disabled
                        "turns": 0,
                        "size_chars": 0
                    }
                },
                
                # ===== CONTEXT STRING FOR LLM-AS-A-JUDGE EVALUATION =====
                # This field is used by Langfuse evaluators to assess response quality
                "context_string": "\n\n=== DOCUMENT ===\n\n".join([
                    doc.page_content for doc in final_docs[:10]  # Top 10 most relevant docs
                ]),
                
                "generation": {
                    "model": "gpt-4o-mini",
                    "config": {
                        "temperature": 0.3,
                        "max_tokens": 1500,
                        "streaming": True
                    },
                    "response": {
                        "length_words": len(full_response.split()),
                        "length_chars": len(full_response)
                    },
                    "time_ms": llm_time_ms
                },
                
                "performance": {
                    "total_ms": total_time_ms,
                    "breakdown": {
                        "retrieval_ms": retrieval_time_ms,
                        "llm_ms": llm_time_ms,
                        "thinking_ms": thinking_time_ms,
                        "streaming_ms": streaming_time_ms
                    }
                },
                
                "system": {
                    "vectorstore_available": vectorstore is not None,
                    "documents_found": len(final_docs) > 0,
                    "vectorstore_version": get_vectorstore_build_date()
                }
            }
            
            # ===== COMPLETE RAG PIPELINE TRACE =====
            trace_id = None
            try:
                if rag_trace:
                    # Log LLM generation
                    rag_trace.log_llm_generation(
                        prompt=str(messages),
                        response=full_response,
                        model="gpt-4o-mini",
                        metadata={
                            "temperature": 0.3,
                            "max_tokens": 1500,
                            "response_length": len(full_response)
                        }
                    )
                    
                    # Log final response generation
                    rag_trace.log_response_generation(
                        final_response=full_response,
                        metadata={
                            **comprehensive_metadata,
                            "sources_used": sources_used if sources_used else [],
                        }
                    )
                    
                    # Complete the trace with comprehensive metadata
                    trace_id = rag_trace.complete(full_response, metadata=comprehensive_metadata)
                else:
                    # Fallback to simple trace if RAG trace failed
                    trace_id = langfuse_tracker.create_trace(
                        user_id=conversation_id,
                        question=question,
                        answer=full_response,
                        session_id=session_id,
                        user_name=user_name,
                        user_email=user_email,
                        metadata=comprehensive_metadata
                    )
            except Exception as e:
                print(f"[WARNING] Langfuse logging failed: {e}")
            
            # Generate recommended questions using RAG-based approach
            recommended_questions = []
            try:
                from app.llm import generate_recommended_questions_from_docs
                # Use the same documents we retrieved for answering
                recommended_questions = generate_recommended_questions_from_docs(
                    user_question=question,
                    retrieved_docs=final_docs if 'final_docs' in locals() else [],
                    bot_response=full_response
                )
                print(f"[RECOMMENDATIONS] Generated {len(recommended_questions)} follow-up questions")
            except Exception as e:
                print(f"[WARNING] Failed to generate recommendations: {e}")
            
            # Log trace_id status for debugging
            if trace_id:
                print(f"[TRACE_ID] ✓ Sending trace_id to frontend: {trace_id}")
            else:
                print(f"[TRACE_ID] ⚠️ WARNING: trace_id is None - feedback will use fallback ID")
                print(f"[TRACE_ID] This means Langfuse trace creation failed - check Langfuse configuration")
            
            # Send completion signal with trace_id and recommendations
            yield f"data: {json.dumps({'type': 'done', 'full_response': full_response, 'trace_id': trace_id, 'recommended_questions': recommended_questions})}\n\n"
            
        except Exception as e:
            print(f"[ERROR] ERROR in generate_stream: {e}")
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'error': str(e), 'type': 'error'})}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
        }
    )

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
        users_cursor = mongodb_memory.collection.find(
            {"messages": {"$exists": True, "$ne": []}},
            {"user_id": 1, "messages": 1, "last_updated": 1}
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
            
            # Get first user message as title
            first_message = next((msg for msg in messages if msg.get("role") == "user"), None)
            title = first_message["content"][:50] + "..." if first_message else "Chat conversation"
            
            # Get timestamp
            last_updated = user_doc.get("last_updated")
            timestamp = int(last_updated.timestamp() * 1000) if last_updated else 0
            
            sessions.append({
                "session_id": f"user_chat_{user_id}",
                "user_id": user_id,
                "user_email": user_id,  # Using user_id as email for now
                "user_name": user_id.split("@")[0] if "@" in user_id else user_id,
                "title": title,
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
    """Get a specific chat session by ID."""
    try:
        session = await get_session_by_id(session_id, include_messages)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}

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
        session = await get_session_by_id(actual_session_id, include_messages=True)
        if not session:
            print(f"[SHARE] Session {actual_session_id} not found")
            raise HTTPException(
                status_code=404, 
                detail=f"Session not found. Make sure the chat is saved before sharing."
            )
        
        # Debug: Check if session has messages
        message_count = len(session.get("messages", []))
        print(f"[SHARE] Session {actual_session_id} has {message_count} messages")
        if message_count == 0:
            print(f"[SHARE] ⚠️ WARNING: Sharing a chat with no messages!")
        
        # Verify user owns this session (skip check for others' chats - they're sharing the original owner's chat)
        if not is_others_chat and session.get("user_id") != auth_user["user_id"]:
            print(f"[SHARE] User {auth_user['email']} tried to share chat owned by {session.get('user_id')}")
            raise HTTPException(
                status_code=403,
                detail="You can only share chats in your account"
            )
        
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
        original_session = await get_session_by_id(shared_chat["session_id"], include_messages=True)
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
        start_date = None
        end_date = None
        if from_date:
            try:
                start_date = datetime.strptime(from_date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid from_date format. Use YYYY-MM-DD")
        
        if to_date:
            try:
                end_date = datetime.strptime(to_date, "%Y-%m-%d")
                end_date = end_date.replace(hour=23, minute=59, second=59)
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
                        timeout=30.0
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
                    
                    # Process traces and assign to teams
                    for trace in traces:
                        metadata = trace.get("metadata", {})
                        user_email = metadata.get("user_email")
                        question = trace.get("input", "")
                        
                        if user_email:
                            user_email_str = str(user_email) if isinstance(user_email, list) else user_email
                            normalized_email = user_email_str.lower().strip()
                            if not normalized_email:
                                continue
                            
                            # ✅ PRIORITY: Check user_activity.team_name first, then fallback to email matching
                            team_name = None
                            try:
                                # Try to get team from user_activity (onboarded users)
                                user_profile = await get_user_profile(normalized_email)
                                if user_profile and user_profile.get("team_name"):
                                    team_name = user_profile.get("team_name")
                                    logger.debug(f"[ANALYTICS] User {normalized_email} assigned to team via profile: {team_name}")
                            except Exception as e:
                                logger.debug(f"[ANALYTICS] Could not get user profile for {normalized_email}: {e}")
                            
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
                                
                                if question:
                                    teams_data[team_name]["total_questions"] += 1
                                    teams_data[team_name]["questions_list"].append(str(question))
                    
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
        logger.info(f"[LANGFUSE ANALYTICS] Total teams: {len(team_stats)}")
        logger.info(f"[LANGFUSE ANALYTICS] Active teams (with questions): {total_active_teams}")
        logger.info(f"[LANGFUSE ANALYTICS] Total questions across all teams: {total_questions}")
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
                        timeout=30.0
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
                        timeout=30.0  # Reduced timeout for filtered queries
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
                        timeout=30.0  # Reduced timeout
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
                        timeout=30.0  # Reduced timeout
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
                        timeout=30.0  # Reduced timeout
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
        # CRITICAL: Retrieve relevant documents from vectorstore for context
        # This ensures the corrected response is based on actual knowledge base
        if vectorstore is None:
            print("Warning: Vectorstore not initialized. Cannot retrieve context for improved response.")
            relevant_docs = []
        else:
            relevant_docs = vectorstore.similarity_search(user_query, k=25)
        
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


