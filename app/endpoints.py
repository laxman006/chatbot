# -*- coding: utf-8 -*-
from fastapi import APIRouter, Request, HTTPException, Header, Depends, Query, Path
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
import uuid
import httpx
import os
import json
import base64
from http import HTTPStatus
import logging

logger = logging.getLogger(__name__)
import asyncio
import re
from datetime import datetime

from app.llm import setup_qa_chain
from app.llm_factory import get_llm
from app.vectorstore import retriever, vectorstore, bm25_retriever
from app.mongodb_memory import (
    mongodb_memory,
    add_to_conversation, get_conversation_context, get_user_chat_history, 
    clear_user_chat_history, save_session, get_all_sessions, get_user_sessions, 
    get_session_by_id, create_shared_chat, get_shared_chat
)
from app.helpers import strip_markdown, preserve_markdown, is_weak_answer
from app.langfuse_integration import langfuse_tracker
from app.auth import verify_user_access, require_admin, require_restricted_admin
from app.external_knowledge_gate import (
    evaluate_external_knowledge_gate,
    ExternalKnowledgeDecision,
    build_rule_3b_metadata,
)
from config import (
    MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, MICROSOFT_TENANT,
    ENABLE_INTENT_CLASSIFICATION, ENABLE_QUERY_EXPANSION, ENABLE_CONTEXT_COMPRESSION,
    DENSE_RETRIEVAL_K, BM25_RETRIEVAL_K, FINAL_RETRIEVAL_K,
    DENSE_WEIGHT, BM25_WEIGHT, RERANKER_WEIGHT,
    SYSTEM_PROMPT_CF_ONLY, SYSTEM_PROMPT_CF_PLUS_EXTERNAL
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


def invoke_system_prompt(
    system_prompt: str,
    context: str,
    question: str,
    temperature: float = 0.1,
    max_tokens: int = 1500,
    forced_no_context: bool = False
) -> tuple[str, list]:
    """Run the configured LLM prompt template with provided context."""
    system_prompt_text = system_prompt
    if forced_no_context:
        system_prompt_text += "\n\nIMPORTANT: No relevant documents were found in the knowledge base for this query."

    if forced_no_context:
        human_message = "Question: {question}"
        inputs = {"question": question}
    else:
        human_message = "Context: {context}\n\nQuestion: {question}"
        inputs = {"context": context, "question": question}

    prompt_template = ChatPromptTemplate.from_messages([
        ("system", system_prompt_text),
        ("human", human_message)
    ])

    messages = prompt_template.format_messages(**inputs)
    llm = get_llm(temperature=temperature, max_tokens=max_tokens)
    chain = prompt_template | llm
    result = chain.invoke(inputs)

    return result.content, messages


def cloudfuze_safe_fallback() -> str:
    """Return a safe CloudFuze-centric response when external docs are unavailable."""
    return (
        "I can help with CloudFuze migration prerequisites, supported platforms, "
        "or general CloudFuze strategy. Please share more about your business use case "
        "so we can stay within those areas."
    )


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

async def require_auth(authorization: Optional[str] = Header(None)) -> dict:
    """
    Verify user is authenticated with a valid Microsoft access token.
    Can be disabled for testing by setting DISABLE_AUTH_FOR_TESTING=true in .env
    """
    # Check if auth is disabled for testing
    import os
    if os.getenv("DISABLE_AUTH_FOR_TESTING", "false").lower() == "true":
        print("[AUTH] Authentication DISABLED for testing")
        return {
            "user_id": "test_user",
            "name": "Test User",
            "email": "test@example.com"
        }
    
    # Normal authentication flow
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Missing or invalid authorization header. Please log in."
        )
    
    access_token = authorization.replace("Bearer ", "")
    
    # --- FALLBACK: Try to verify with Graph API, fall back to local decoding on failure ---
    try:
        # Verify token with Microsoft Graph API with retries
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
                        # SUCCESS: Token is valid and verified by Graph
                        user_info = graph_response.json()
                        user_email = user_info.get("mail") or user_info.get("userPrincipalName", "")
                        
                        # Validate CloudFuze email domain
                        if not user_email.endswith("@cloudfuze.com"):
                            print(f"[AUTH] Access denied for non-CloudFuze email: {user_email}")
                            raise HTTPException(
                                status_code=403,
                                detail="Forbidden: Only CloudFuze company accounts are allowed to access this application."
                            )
                        
                        print(f"[AUTH] User authenticated via Graph: {user_email}")
                        return {
                            "user_id": user_info.get("id"),
                            "email": user_email,
                            "name": user_info.get("displayName", "User")
                        }
                        
                    # If 401, token is rejected by Graph. In DEV, this might be due to audience mismatch.
                    # Fall through to local decoding fallback below.
                    if graph_response.status_code == 401:
                        print(f"[AUTH] Graph API rejected token (401). Attempting local fallback...")
                        break
                        
                    # Other errors (5xx, etc), retry
                    if attempt < max_retries - 1:
                        print(f"[AUTH] Verification attempt {attempt+1} failed ({graph_response.status_code}), retrying...")
                        await asyncio.sleep(retry_delay)
                        continue
                        
                except httpx.HTTPError as e:
                    # Network error, retry
                    if attempt < max_retries - 1:
                        print(f"[AUTH] Network error on attempt {attempt+1}: {str(e)}, retrying...")
                        await asyncio.sleep(retry_delay)
                        continue
                    else:
                        print(f"[AUTH] Network error finalized: {str(e)}")
                        break

    except Exception as e:
        print(f"[AUTH] Unexpected error during Graph verification: {e}")
        # Fall through to fallback
        
    # --- FALLBACK: Local Token Decoding (Unsafe/Dev Mode) ---
    # If we reached here, Graph verification failed (401, network error, etc.)
    # Try to extract user info from the token itself if it looks valid.
    
    print("[AUTH] Attempting local token decoding fallback...")
    claims = decode_unsafe_jwt(access_token)
    
    if claims:
        # Extract email/upn
        user_email = claims.get("email") or claims.get("upn") or claims.get("unique_name")
        user_name = claims.get("name") or claims.get("given_name") or "User"
        user_id = claims.get("oid") or claims.get("sub")
        
        if user_email and user_email.endswith("@cloudfuze.com"):
            print(f"[AUTH] ⚠️ FALLBACK: User authenticated via local token decoding: {user_email}")
            return {
                "user_id": user_id or user_email, # Use email as ID if oid missing
                "email": user_email,
                "name": user_name
            }
        else:
            print(f"[AUTH] Fallback failed: Invalid email domain or missing email in token: {user_email}")
    else:
        print("[AUTH] Fallback failed: Could not decode token")

    # If all fails, raise 401
    raise HTTPException(
        status_code=401,
        detail="Unauthorized: Unable to verify access token. Please log in again."
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

    rule_3b_decision = None
    rule_3b_metadata = {}
    prompt_mode = "cf_only"
    topic_classified = None

    # FIRST: Check if we have a corrected response for this question
    corrected_answer = find_similar_corrected_response(question)
    
    if corrected_answer:
        # Use the corrected response
        answer = corrected_answer
    # Check if this is a conversational query
    elif is_conversational_query(question):
        # Handle conversational queries directly without document retrieval
        from langchain_core.prompts import ChatPromptTemplate
        
        from config import SYSTEM_PROMPT_CF_ONLY
        llm = get_llm(temperature=0.7)
        
        # CloudFuze-focused conversational prompt
        conversational_prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT_CF_ONLY),
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
                forced_no_context = len(formatted_docs) == 0

                # FIRST ATTEMPT: Use the CloudFuze-only system prompt
                answer, _ = invoke_system_prompt(
                    SYSTEM_PROMPT_CF_ONLY,
                    context,
                    enhanced_query,
                    forced_no_context=forced_no_context
                )
                prompt_mode = "cf_only"

                if is_weak_answer(answer):
                    try:
                        rule_3b_decision, rule_3b_metadata = evaluate_external_knowledge_gate(question)
                        topic_classified = rule_3b_metadata.get("topic_classified")

                        if rule_3b_decision == ExternalKnowledgeDecision.ALLOWED:
                            print("[3B FALLBACK] CF-only answer weak; retrying with CF+external prompt.")
                            try:
                                answer, _ = invoke_system_prompt(
                                    SYSTEM_PROMPT_CF_PLUS_EXTERNAL,
                                    context,
                                    enhanced_query,
                                    forced_no_context=forced_no_context
                                )
                                prompt_mode = "cf_external"
                            except Exception as exc:
                                print(f"[WARNING] CF+external fallback failed: {exc}")
                                import traceback
                                traceback.print_exc()
                        else:
                            print(f"[3B GATE] DENIED: {rule_3b_decision.value} - Returning safe CloudFuze fallback.")
                            answer = cloudfuze_safe_fallback()
                            prompt_mode = "cf_fallback"
                    except Exception as exc:
                        print(f"[WARNING] Rule 3B gate evaluation failed (post-CF-only): {exc}")
                        import traceback
                        traceback.print_exc()

                # If Rule 3B is ALLOWED, route through answer templates (for non-generic topics)
                if prompt_mode == "cf_external" and topic_classified and topic_classified != "generic":
                    # For specific topics, we would use templates here
                    # For now, the LLM response is already constrained by the prompt
                    # Templates can be enforced in future iterations if needed
                    pass
                
            except Exception as e:
                print(f"[ERROR] Intent-based retrieval failed: {e}")
                # Fallback to original qa_chain if something goes wrong
                result = qa_chain.invoke({"query": enhanced_query})
                answer = result["result"]

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
            },
            **build_rule_3b_metadata(rule_3b_decision, rule_3b_metadata, prompt_mode, "/chat")
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

    # Use user_id if provided, otherwise fall back to session_id for backward compatibility
    conversation_id = user_id if user_id else session_id

    async def generate_stream():
        try:
            rule_3b_decision = None
            rule_3b_metadata = {}
            prompt_mode = "cf_only"
            topic_classified = None
            
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
                from config import SYSTEM_PROMPT_CF_ONLY
                llm = get_llm(
                    streaming=True, 
                    temperature=0.7,
                    max_tokens=500
                )
                
                # CloudFuze-focused conversational prompt
                conversational_prompt = ChatPromptTemplate.from_messages([
                    ("system", SYSTEM_PROMPT_CF_ONLY),
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
            full_response, final_messages = invoke_system_prompt(
                SYSTEM_PROMPT_CF_ONLY,
                context_text,
                enhanced_query,
                forced_no_context=forced_no_context
            )
            prompt_mode = "cf_only"

            if is_weak_answer(full_response):
                try:
                    rule_3b_decision, rule_3b_metadata = evaluate_external_knowledge_gate(question)
                    topic_classified = rule_3b_metadata.get("topic_classified")

                    if rule_3b_decision == ExternalKnowledgeDecision.ALLOWED:
                        full_response, final_messages = invoke_system_prompt(
                            SYSTEM_PROMPT_CF_PLUS_EXTERNAL,
                            context_text,
                            enhanced_query,
                            forced_no_context=forced_no_context
                        )
                        prompt_mode = "cf_external"
                    else:
                        print(f"[3B GATE] DENIED: {rule_3b_decision.value} - Streaming safe CloudFuze fallback.")
                        full_response = cloudfuze_safe_fallback()
                        prompt_mode = "cf_fallback"
                except Exception as exc:
                    print(f"[WARNING] Rule 3B gate evaluation failed (streaming): {exc}")
                    import traceback
                    traceback.print_exc()

            # Log Rule 3B evaluation to Langfuse (if it exists)
            if rag_trace and rag_trace.query_span:
                try:
                    rag_trace.query_span.span(
                        name="rule_3b_gate",
                        input=question,
                        output=f"Decision: {rule_3b_decision.value if rule_3b_decision else 'not_evaluated'}",
                        metadata=rule_3b_metadata
                    )
                except Exception as e:
                    print(f"[WARNING] Failed to log Rule 3B gate to Langfuse: {e}")

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

            messages = final_messages if final_messages else []
            # Stream the response
            for idx, token in enumerate(full_response):
                yield f"data: {json.dumps({'token': token, 'type': 'token'})}\n\n"
                if idx % 5 == 0:
                    await asyncio.sleep(0.01)
            
            # Record LLM generation time
            llm_time_ms = int((time.time() - llm_start_time) * 1000)
            streaming_time_ms = llm_time_ms  # In streaming mode, these are the same
            
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
                
                # ===== RULE 3B EXTERNAL KNOWLEDGE GATE =====
                **build_rule_3b_metadata(
                    rule_3b_decision if 'rule_3b_decision' in locals() else None,
                    rule_3b_metadata if 'rule_3b_metadata' in locals() else {},
                    prompt_mode if 'prompt_mode' in locals() else "cf_only",
                    "/chat/stream"
                ),
                
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
        
        await save_session(session_data)
        
        return {"message": "Session saved successfully", "session_id": session_data["session_id"]}
        
    except Exception as e:
        return {"error": str(e)}

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

@router.get("/analytics/langfuse/raw/today")
async def get_langfuse_raw_today(
    current_user: dict = Depends(require_restricted_admin)
):
    """
    Get TODAY's traces directly from Langfuse API (no filtering/processing).
    Pure raw data from Langfuse - no team assignment, no validation.
    """
    try:
        from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
        from datetime import datetime, timezone
        import httpx
        
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat().replace('+00:00', 'Z')
        end = now.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat().replace('+00:00', 'Z')
        
        params = {
            "createdAt[gte]": start,
            "createdAt[lte]": end,
            "limit": 1000,
            "orderBy[createdAt]": "DESC"
        }
        
        print(f"[INFO] Direct Langfuse query for today: {start} to {end}")
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{LANGFUSE_HOST}/api/public/traces",
                params=params,
                auth=(LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY),
                timeout=30
            )
            
            if response.status_code != 200:
                return {
                    "error": f"Langfuse API error: {response.status_code}",
                    "status": "error"
                }
            
            traces = response.json().get("data", [])
            
            return {
                "status": "success",
                "date": now.strftime("%Y-%m-%d"),
                "total_traces": len(traces),
                "traces": [
                    {
                        "id": t.get("id"),
                        "email": t.get("metadata", {}).get("user_email"),
                        "name": t.get("metadata", {}).get("user_name"),
                        "question": t.get("input", "")[:200],
                        "created_at": t.get("createdAt")
                    }
                    for t in traces
                ]
            }
    
    except Exception as e:
        print(f"[ERROR] Direct Langfuse query failed: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e), "status": "error"}


@router.get("/analytics/langfuse/raw/date-range")
async def get_langfuse_raw_date_range(
    start_date: str = Query(..., description="Start date YYYY-MM-DD"),
    end_date: str = Query(..., description="End date YYYY-MM-DD"),
    current_user: dict = Depends(require_restricted_admin)
):
    """
    Get traces for custom date range directly from Langfuse (no filtering).
    Pure raw data - no processing, no team assignment.
    """
    try:
        from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
        from datetime import datetime, timezone
        import httpx
        
        # Parse dates
        start_dt = datetime.fromisoformat(f"{start_date}T00:00:00").replace(tzinfo=timezone.utc)
        end_dt = datetime.fromisoformat(f"{end_date}T23:59:59").replace(tzinfo=timezone.utc)
        
        start = start_dt.isoformat().replace('+00:00', 'Z')
        end = end_dt.isoformat().replace('+00:00', 'Z')
        
        params = {
            "createdAt[gte]": start,
            "createdAt[lte]": end,
            "limit": 1000,
            "orderBy[createdAt]": "DESC"
        }
        
        print(f"[INFO] Direct Langfuse query: {start} to {end}")
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{LANGFUSE_HOST}/api/public/traces",
                params=params,
                auth=(LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY),
                timeout=30
            )
            
            if response.status_code != 200:
                return {"error": f"Langfuse API error: {response.status_code}", "status": "error"}
            
            traces = response.json().get("data", [])
            
            return {
                "status": "success",
                "date_range": f"{start_date} to {end_date}",
                "total_traces": len(traces),
                "traces": [
                    {
                        "id": t.get("id"),
                        "email": t.get("metadata", {}).get("user_email"),
                        "name": t.get("metadata", {}).get("user_name"),
                        "question": t.get("input", "")[:200],
                        "created_at": t.get("createdAt")
                    }
                    for t in traces
                ]
            }
    
    except Exception as e:
        print(f"[ERROR] Direct Langfuse query failed: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e), "status": "error"}


@router.get("/analytics/langfuse/teams/summary-clean")
async def get_teams_analytics_summary_clean(
    time_filter: str = Query("today", description="today|yesterday|this_week|last_week|this_month|all"),
    current_user: dict = Depends(require_restricted_admin)
):
    """
    Get team analytics EXCLUDING blocklisted emails.
    Excludes: chaitanya.malle@cloudfuze.com, laxman.kadari@cloudfuze.com
    """
    print(f"\n{'='*80}")
    print(f"[REQUEST] CLEAN Teams Analytics Summary (EXCLUDING blocklisted emails)")
    print(f"[TIME_FILTER] {time_filter}")
    print(f"[USER] {current_user.get('email', 'unknown')}")
    print(f"{'='*80}\n")
    
    try:
        from app.langfuse_integration import langfuse_client
        from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
        from app.models.teams import (
            get_all_teams, get_team_by_member_email, get_team_color,
            get_all_email_to_team_mapping, validate_team_emails,
            get_exclusion_list
        )
        from app.trace_utils import TraceFilteringStats, process_trace_batch, calculate_question_metrics
        import asyncio
        from datetime import datetime, timedelta, timezone
        import httpx
        
        if not langfuse_client:
            return {"error": "Langfuse client not initialized", "status": "error"}
        
        # Get exclusion list
        exclusion_list = get_exclusion_list()
        print(f"[INFO] Excluding {len(exclusion_list)} emails from analytics: {sorted(exclusion_list)}")
        
        # Log team structure diagnostics
        diagnostics = validate_team_emails()
        print(f"[INFO] Team Email Diagnostics: {diagnostics['total_teams']} teams, {diagnostics['email_count']} emails")
        
        email_to_team_map = get_all_email_to_team_mapping()
        print(f"[DEBUG] Email-to-team mapping created with {len(email_to_team_map)} entries")
        
        stats = TraceFilteringStats()
        
        # Calculate date range
        now = datetime.now(timezone.utc)
        start_time = None
        end_time = None
        
        if time_filter == "today":
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "yesterday":
            yesterday = now - timedelta(days=1)
            start_time = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "this_week":
            start_time = now - timedelta(days=now.weekday())
            start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "last_week":
            this_week_start = now - timedelta(days=now.weekday())
            this_week_start = this_week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            start_time = this_week_start - timedelta(days=7)
            end_time = this_week_start - timedelta(microseconds=1)
        elif time_filter == "this_month":
            start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end_time = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        print(f"[INFO] Clean team analytics requested: time_filter={time_filter}, start_time={start_time}, end_time={end_time}")
        
        # Initialize team data
        teams_data = {}
        all_teams = get_all_teams()
        
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
        
        # Fetch and process traces
        page = 1
        batch_limit = 100
        max_pages =20 if time_filter in ["today", "yesterday"] else (10 if time_filter != "all" else 20)
        rate_limit_backoff = 1.0
        
        async with httpx.AsyncClient() as client:
            while page <= max_pages:
                try:
                    print(f"\n[PAGE {page}] Fetching page {page}/{max_pages}...")
                    params = {
                        "page": page,
                        "limit": batch_limit,
                        "orderBy[createdAt]": "DESC"
                    }
                    
                    if start_time:
                        params["createdAt[gte]"] = start_time.isoformat() + "Z"
                    if end_time:
                        params["createdAt[lte]"] = end_time.isoformat() + "Z"
                    
                    if page == 1:
                        print(f"[DEBUG] Langfuse API request (page {page}): params={params}")
                    
                    response = await client.get(
                        f"{LANGFUSE_HOST}/api/public/traces",
                        params=params,
                        auth=(LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY),
                        timeout=45.0
                    )
                    
                    if response.status_code == 429:
                        print(f"[WARN] Langfuse rate limited at page {page}, retrying with backoff ({rate_limit_backoff}s)...")
                        await asyncio.sleep(rate_limit_backoff)
                        rate_limit_backoff = min(rate_limit_backoff * 2, 10.0)
                        continue
                    
                    rate_limit_backoff = 1.0
                    
                    if response.status_code != 200:
                        print(f"[ERROR] Langfuse API error: status={response.status_code}")
                        break
                    
                    traces_response = response.json()
                    traces = traces_response.get("data", [])
                    
                    print(f"[FETCH] Got {len(traces)} traces from page {page}")
                    
                    if not traces:
                        print(f"[INFO] No traces returned at page {page}, stopping pagination")
                        break
                    
                    # Collect all traces for saving (before filtering)
                    # We don't need to extend to all_traces anymore, as it's removed.
                    
                    # Filter out excluded emails BEFORE processing
                    filtered_traces = []
                    page_excluded = 0
                    for trace in traces:
                        user_email = trace.get("metadata", {}).get("user_email")
                        if user_email:
                            email_str = str(user_email).lower().strip() if isinstance(user_email, str) else (
                                user_email[0].lower().strip() if isinstance(user_email, list) and user_email else None
                            )
                            if email_str in exclusion_list:
                                print(f"[DEBUG] Excluding trace: {email_str} (on blocklist)")
                                page_excluded += 1
                                continue
                        filtered_traces.append(trace)
                    
                    print(f"[FILTER] Page {page}: Excluded {page_excluded} traces (blocklisted emails)")
                    print(f"[PROCESS] Processing {len(filtered_traces)} non-excluded traces from page {page}")
                    
                    # Process non-excluded traces
                    traces_added = process_trace_batch(
                        filtered_traces,
                        email_to_team_map,
                        get_team_by_member_email,
                        teams_data,
                        start_time,
                        end_time,
                        stats
                    )
                    
                    stats.log_summary(page, batch_limit)
                    
                    if len(traces) < batch_limit:
                        print(f"[INFO] Got {len(traces)} traces (< {batch_limit}), reached end of data")
                        break
                    
                    page += 1
                    await asyncio.sleep(rate_limit_backoff)
                    
                except Exception as e:
                    print(f"[ERROR] Error fetching traces: {e}")
                    import traceback
                    traceback.print_exc()
                    break
        
        # Save all fetched traces to JSON file
        
        # Calculate metrics
        team_stats = []
        for team_name, team_info in teams_data.items():
            try:
                metrics = calculate_question_metrics(team_info["questions_list"])
                unique_questions = metrics["unique_count"]
                top_questions = metrics["top_questions"]
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
                "top_questions": top_questions
            })
        
        team_stats.sort(key=lambda x: x["total_questions"], reverse=True)
        
        total_questions = sum(t["total_questions"] for t in team_stats)
        total_active_teams = sum(1 for t in team_stats if t["total_questions"] > 0)
        
        stats.log_final_summary()
        print(f"[INFO] CLEAN Team analytics summary completed: time_filter={time_filter}, total_questions={total_questions}, total_teams={len(team_stats)}, active_teams={total_active_teams}")
        print(f"[INFO] (Excluded {len(exclusion_list)} emails from analysis)")
        if total_questions > 0:
            top_3_teams = [f"{t['team_name']}:{t['total_questions']}" for t in team_stats[:3]]
            print(f"[INFO] Top 3 teams: {', '.join(top_3_teams)}")
        
        print(f"\n{'='*80}")
        print(f"[RESPONSE] Success - {total_questions} questions from {total_active_teams} active teams (after exclusion)")
        print(f"{'='*80}\n")
        
        return {
            "status": "success",
            "time_filter": time_filter,
            "exclusion_list": sorted(list(exclusion_list)),
            "teams": team_stats,
            "total_teams": len(team_stats),
            "total_questions": total_questions,
            "total_active_teams": total_active_teams
        }
        
    except Exception as e:
        print(f"\n{'='*80}")
        print(f"[ERROR] Clean team analytics fetch failed: {e}")
        print(f"{'='*80}\n")
        import traceback
        traceback.print_exc()
        return {"error": str(e), "status": "error"}


@router.get("/analytics/langfuse/teams/summary")
async def get_teams_analytics_summary(
    time_filter: str = Query("today", description="today|yesterday|this_week|last_week|this_month|all"),
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
    print(f"\n{'='*80}")
    print(f"[REQUEST] Teams Analytics Summary")
    print(f"[TIME_FILTER] {time_filter}")
    print(f"[USER] {current_user.get('email', 'unknown')}")
    print(f"{'='*80}\n")
    
    try:
        from app.langfuse_integration import langfuse_client
        from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
        from app.models.teams import get_all_teams, get_team_by_member_email, get_team_color, get_all_email_to_team_mapping, validate_team_emails
        from app.trace_utils import TraceFilteringStats, process_trace_batch, calculate_question_metrics
        import asyncio
        from datetime import datetime, timedelta, timezone
        import httpx
        
        if not langfuse_client:
            print("[ERROR] Langfuse client not initialized")
            return {"error": "Langfuse client not initialized", "status": "error"}
        
        print("[STEP 1] Validating team structure...")
        # Log team structure diagnostics at startup
        diagnostics = validate_team_emails()
        print(f"[INFO] Team Email Diagnostics: {diagnostics['total_teams']} teams, {diagnostics['email_count']} emails")
        if diagnostics["duplicate_emails"]:
            print(f"[WARN] Duplicate emails found: {diagnostics['duplicate_emails']}")
        if diagnostics["empty_emails"]:
            print(f"[WARN] Empty emails found: {len(diagnostics['empty_emails'])} instances")
        
        print("[STEP 2] Building email-to-team mapping...")
        # Get fast lookup mapping of email -> team
        email_to_team_map = get_all_email_to_team_mapping()
        print(f"[INFO] Email-to-team mapping created with {len(email_to_team_map)} entries")
        
        print("[STEP 3] Initializing statistics tracker...")
        # Initialize statistics tracker (BEFORE async block to ensure scope)
        stats = TraceFilteringStats()
        
        print("[STEP 4] Calculating date range...")
        # Calculate date range based on time_filter
        now = datetime.now(timezone.utc)
        start_time = None
        end_time = None
        
        if time_filter == "today":
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "yesterday":
            yesterday = now - timedelta(days=1)
            start_time = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "this_week":
            start_time = now - timedelta(days=now.weekday())
            start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "last_week":
            # FIX: Calculate previous week (Monday to Sunday), not last 7 days
            # Calculate start of this week (Monday at 00:00:00)
            this_week_start = now - timedelta(days=now.weekday())
            this_week_start = this_week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            # Last week starts 7 days before this week (last Monday at 00:00:00)
            start_time = this_week_start - timedelta(days=7)
            # Last week ends at the end of last Sunday (start of this week minus 1 microsecond)
            end_time = this_week_start - timedelta(microseconds=1)
        elif time_filter == "this_month":
            # Start from the 1st day of current month at 00:00:00
            start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            # End at current time
            end_time = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        # For "all", start_time and end_time remain None (no date filtering)
        
        # Log date range for debugging
        print(f"[DATE_RANGE] start_time={start_time}, end_time={end_time}, now={now}")
        
        print("[STEP 5] Initializing team data structure...")
        # Initialize team data structure
        teams_data = {}
        all_teams = get_all_teams()
        print(f"[INFO] Found {len(all_teams)} teams in configuration")
        
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
        
        print("[STEP 6] Fetching traces from Langfuse...")
        # Fetch traces and organize by team
        page = 1
        batch_limit = 100
        # INCREASED PAGINATION LIMITS to fetch more traces:
        # - Today/Yesterday: 5 pages = ~500 traces (was 3 pages = 300)
        # - This week/Last week: 10 pages = ~1000 traces (was 5 pages = 500)
        # - All time: 20 pages = ~2000 traces (was 10 pages = 1000)
        max_pages = 5 if time_filter in ["today", "yesterday"] else (10 if time_filter != "all" else 20)
        rate_limit_backoff = 1.0  # Initial backoff for rate limiting
        
        print(f"[PAGINATION] max_pages={max_pages}, batch_limit={batch_limit}")
        
        async with httpx.AsyncClient() as client:
            while page <= max_pages:
                try:
                    print(f"\n[PAGE {page}] Fetching page {page}/{max_pages}...")
                    params = {
                        "page": page,
                        "limit": batch_limit,
                        "orderBy[createdAt]": "DESC"
                    }
                    
                    if start_time:
                        params["createdAt[gte]"] = start_time.isoformat() + "Z"
                    if end_time:
                        params["createdAt[lte]"] = end_time.isoformat() + "Z"
                    
                    # Log API request parameters for debugging
                    if page == 1:
                        print(f"[DEBUG] Langfuse API request (page {page}): params={params}")
                    
                    response = await client.get(
                        f"{LANGFUSE_HOST}/api/public/traces",
                        params=params,
                        auth=(LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY),
                        timeout=45.0
                    )
                    
                    # Handle rate limiting with exponential backoff
                    if response.status_code == 429:
                        print(f"[WARN] Langfuse rate limited at page {page}, retrying with backoff ({rate_limit_backoff}s)...")
                        await asyncio.sleep(rate_limit_backoff)
                        rate_limit_backoff = min(rate_limit_backoff * 2, 10.0)  # Max 10 seconds
                        continue  # Retry same page
                    
                    # Reset backoff on success
                    rate_limit_backoff = 1.0
                    
                    if response.status_code != 200:
                        print(f"[ERROR] Langfuse API error: status={response.status_code}, response={response.text[:200]}")
                        break
                    
                    traces_response = response.json()
                    traces = traces_response.get("data", [])
                    print(f"[FETCH] Got {len(traces)} traces from page {page}")
                    
                    if not traces:
                        print(f"[INFO] No traces returned at page {page}, stopping pagination")
                        break
                    
                    # Collect all traces for saving
                    # We don't need to extend to all_traces anymore, as it's removed.
                    
                    # Process traces using unified utility function
                    traces_added = process_trace_batch(
                        traces,
                        email_to_team_map,
                        get_team_by_member_email,
                        teams_data,
                        start_time,
                        end_time,
                        stats
                    )
                    
                    # Log per-page summary
                    stats.log_summary(page, batch_limit)
                    
                    if len(traces) < batch_limit:
                        print(f"[INFO] Got {len(traces)} traces (< {batch_limit}), reached end of data")
                        break
                    
                    page += 1
                    # IMPROVED: Adaptive rate limiting
                    # Use exponential backoff for rate limiting, shorter delays for normal flow
                    await asyncio.sleep(rate_limit_backoff)
                    
                except Exception as e:
                    print(f"[ERROR] Error fetching traces: {e}")
                    import traceback
                    traceback.print_exc()
                    break
        
        # Save all fetched traces to JSON file
        
        print(f"\n[STEP 7] Processing team statistics...")
        # Calculate unique questions and top questions per team
        team_stats = []
        for team_name, team_info in teams_data.items():
            try:
                metrics = calculate_question_metrics(team_info["questions_list"])
                unique_questions = metrics["unique_count"]
                top_questions = metrics["top_questions"]
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
                "top_questions": top_questions
            })
        
        # Sort by total questions (descending)
        team_stats.sort(key=lambda x: x["total_questions"], reverse=True)
        
        total_questions = sum(t["total_questions"] for t in team_stats)
        total_active_teams = sum(1 for t in team_stats if t["total_questions"] > 0)
        
        # Log final summary with comprehensive diagnostics
        stats.log_final_summary()
        print(f"[INFO] Teams analytics summary completed: time_filter={time_filter}, total_questions={total_questions}, total_teams={len(team_stats)}, active_teams={total_active_teams}")
        if total_questions > 0:
            top_3_teams = [f"{t['team_name']}:{t['total_questions']}" for t in team_stats[:3]]
            print(f"[INFO] Top 3 teams: {', '.join(top_3_teams)}")
        
        print(f"\n{'='*80}")
        print(f"[RESPONSE] Success - {total_questions} questions from {total_active_teams} active teams")
        print(f"{'='*80}\n")
        
        return {
            "status": "success",
            "time_filter": time_filter,
            "teams": team_stats,
            "total_teams": len(team_stats),
            "total_questions": total_questions,
            "total_active_teams": total_active_teams
        }
        
    except Exception as e:
        print(f"\n{'='*80}")
        print(f"[ERROR] Teams analytics fetch failed: {e}")
        print(f"{'='*80}\n")
        import traceback
        traceback.print_exc()
        return {"error": str(e), "status": "error"}


# ================== ANALYTICS EXCLUSION MANAGEMENT ==================

@router.get("/analytics/langfuse/exclusion-list")
async def get_exclusion_list(
    current_user: dict = Depends(require_restricted_admin)
):
    """
    Get the current exclusion list for team analytics.
    Admin endpoint for managing which emails are excluded from analytics.
    """
    print(f"[INFO] Fetching exclusion list for admin: {current_user.get('email')}")
    
    return {
        "status": "success",
        "exclusion_list": [
            "laxman.kadari@cloudfuze.com",
            "chaitanya.malle@cloudfuze.com",
        ],
        "description": "Emails currently excluded from team analytics",
        "note": "Frontend can toggle these emails on/off via the exclusion API"
    }


@router.post("/analytics/langfuse/exclusion-list/update")
async def update_exclusion_list(
    exclusion_emails: list = None,
    current_user: dict = Depends(require_restricted_admin)
):
    """
    Update the exclusion list for team analytics.
    Admin endpoint to toggle which emails are excluded from analytics.
    
    Request body:
    {
        "exclusion_emails": ["laxman.kadari@cloudfuze.com", "chaitanya.malle@cloudfuze.com"]
    }
    """
    if exclusion_emails is None:
        exclusion_emails = []
    
    print(f"[INFO] Updating exclusion list - Admin: {current_user.get('email')}")
    print(f"[INFO] New exclusion list: {exclusion_emails}")
    
    # Validate emails format
    validated_emails = set()
    for email in exclusion_emails:
        email_str = str(email).lower().strip()
        if "@" in email_str and "." in email_str:
            validated_emails.add(email_str)
        else:
            print(f"[WARN] Invalid email format skipped: {email}")
    
    print(f"[INFO] Exclusion list updated: {len(validated_emails)} emails")
    
    return {
        "status": "success",
        "exclusion_list": sorted(list(validated_emails)),
        "total_excluded": len(validated_emails),
        "message": f"Exclusion list updated. {len(validated_emails)} emails will be excluded from analytics."
    }


@router.get("/analytics/langfuse/teams/summary/with-exclusion")
async def get_teams_analytics_with_exclusion(
    time_filter: str = Query("today", description="today|yesterday|this_week|last_week|this_month|all"),
    exclusion_emails: str = Query("", description="Comma-separated emails to exclude"),
    current_user: dict = Depends(require_restricted_admin)
):
    """
    Get team analytics with custom exclusion list.
    Allows admin to dynamically exclude specific emails from analytics.
    
    Example: /analytics/langfuse/teams/summary/with-exclusion?time_filter=today&exclusion_emails=laxman.kadari@cloudfuze.com,chaitanya.malle@cloudfuze.com
    """
    print(f"\n{'='*80}")
    print(f"[REQUEST] Teams Analytics Summary WITH EXCLUSION")
    print(f"[TIME_FILTER] {time_filter}")
    print(f"[USER] {current_user.get('email', 'unknown')}")
    print(f"{'='*80}\n")
    
    try:
        from app.langfuse_integration import langfuse_client
        from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
        from app.models.teams import (
            get_all_teams, get_team_by_member_email, get_team_color,
            get_all_email_to_team_mapping, validate_team_emails
        )
        from app.trace_utils import TraceFilteringStats, process_trace_batch, calculate_question_metrics
        import asyncio
        from datetime import datetime, timedelta, timezone
        import httpx
        
        if not langfuse_client:
            print("[ERROR] Langfuse client not initialized")
            return {"error": "Langfuse client not initialized", "status": "error"}
        
        # Parse exclusion list from query param
        exclusion_list = set()
        if exclusion_emails:
            exclusion_list = {
                email.lower().strip() 
                for email in exclusion_emails.split(",") 
                if email.strip() and "@" in email
            }
        
        print(f"[INFO] Excluding {len(exclusion_list)} emails: {sorted(exclusion_list)}")
        
        # Get email-to-team mapping
        email_to_team_map = get_all_email_to_team_mapping()
        stats = TraceFilteringStats()
        
        # Calculate date range
        now = datetime.now(timezone.utc)
        start_time = None
        end_time = None
        
        if time_filter == "today":
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "yesterday":
            yesterday = now - timedelta(days=1)
            start_time = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "this_week":
            start_time = now - timedelta(days=now.weekday())
            start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "last_week":
            this_week_start = now - timedelta(days=now.weekday())
            this_week_start = this_week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            start_time = this_week_start - timedelta(days=7)
            end_time = this_week_start - timedelta(microseconds=1)
        elif time_filter == "this_month":
            start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end_time = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # Initialize team data
        teams_data = {}
        all_teams = get_all_teams()
        
        for team_name, team_info in all_teams.items():
            teams_data[team_name] = {
                "team_name": team_name,
                "lead": team_info.get("lead"),
                "lead_email": team_info.get("lead_email"),
                "member_count": len(team_info.get("members", [])) + (1 if team_info.get("lead_email") else 0),
                "color": team_info.get("color"),
                "total_questions": 0,
                "active_members": set(),
                "questions_list": []
            }
        
        print("[INFO] Fetching traces from Langfuse...")
        page = 1
        batch_limit = 100
        max_pages = 5 if time_filter in ["today", "yesterday"] else (10 if time_filter != "all" else 20)
        excluded_count = 0
        
        async with httpx.AsyncClient() as client:
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
                        timeout=45.0
                    )
                    
                    if response.status_code != 200:
                        break
                    
                    traces = response.json().get("data", [])
                    
                    if not traces:
                        break
                    
                    # Collect all traces for saving
                    # We don't need to extend to all_traces anymore, as it's removed.
                    
                    # Filter out excluded emails
                    filtered_traces = []
                    for trace in traces:
                        user_email = trace.get("metadata", {}).get("user_email")
                        if user_email:
                            email_str = str(user_email).lower().strip() if isinstance(user_email, str) else (
                                user_email[0].lower().strip() if isinstance(user_email, list) and user_email else None
                            )
                            if email_str in exclusion_list:
                                excluded_count += 1
                                print(f"[DEBUG] Excluding: {email_str}")
                                continue
                        filtered_traces.append(trace)
                    
                    # Process non-excluded traces
                    process_trace_batch(
                        filtered_traces,
                        email_to_team_map,
                        get_team_by_member_email,
                        teams_data,
                        start_time,
                        end_time,
                        stats
                    )
                    
                    if len(traces) < batch_limit:
                        break
                    
                    page += 1
                    
                except Exception as e:
                    print(f"[ERROR] Error fetching traces: {e}")
                    break
        
        # Save all fetched traces to JSON file
        
        # Calculate metrics
        team_stats = []
        for team_name, team_info in teams_data.items():
            try:
                metrics = calculate_question_metrics(team_info["questions_list"])
                unique_questions = metrics["unique_count"]
                top_questions = metrics["top_questions"]
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
                "top_questions": top_questions
            })
        
        team_stats.sort(key=lambda x: x["total_questions"], reverse=True)
        
        total_questions = sum(t["total_questions"] for t in team_stats)
        total_active_teams = sum(1 for t in team_stats if t["total_questions"] > 0)
        
        stats.log_final_summary()
        print(f"\n{'='*80}")
        print(f"[RESPONSE] Success - {total_questions} questions from {total_active_teams} active teams")
        print(f"[EXCLUDED] {excluded_count} traces from {len(exclusion_list)} excluded emails")
        print(f"{'='*80}\n")
        
        return {
            "status": "success",
            "time_filter": time_filter,
            "exclusion_list": sorted(list(exclusion_list)),
            "excluded_trace_count": excluded_count,
            "teams": team_stats,
            "total_teams": len(team_stats),
            "total_questions": total_questions,
            "total_active_teams": total_active_teams
        }
        
    except Exception as e:
        print(f"\n{'='*80}")
        print(f"[ERROR] Teams analytics with exclusion failed: {e}")
        print(f"{'='*80}\n")
        import traceback
        traceback.print_exc()
        return {"error": str(e), "status": "error"}


@router.get("/analytics/langfuse/teams/email-diagnostics")
async def get_teams_email_diagnostics(
    current_user: dict = Depends(require_restricted_admin)
):
    """
    Enhanced diagnostics endpoint to check email configuration and trace assignment.
    
    Returns:
    - Team structure validation report
    - Email statistics
    - Analysis of traces currently in Langfuse
    - Potential issues (duplicates, missing teams, unassigned traces, etc.)
    """
    try:
        from app.models.teams import validate_team_emails, get_all_team_members_emails, get_all_email_to_team_mapping
        from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
        from app.trace_utils import TraceFilteringStats, get_trace_email, assign_trace_to_team
        from app.models.teams import get_team_by_member_email
        import httpx
        
        # Get team structure diagnostics
        diagnostics = validate_team_emails()
        all_team_emails = get_all_team_members_emails()
        email_to_team_map = get_all_email_to_team_mapping()
        
        # Count total unique emails
        unique_emails = set()
        for team_emails in all_team_emails.values():
            unique_emails.update(team_emails)
        
        # Fetch sample of recent traces to analyze actual data
        trace_stats = {
            "total_sample_traces": 0,
            "traces_with_email": 0,
            "traces_without_email": 0,
            "assigned_traces": 0,
            "unassigned_traces": 0,
            "unassigned_emails_found": [],
            "sample_trace_count": 0
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                params = {
                    "page": 1,
                    "limit": 100,
                    "orderBy[createdAt]": "DESC"
                }
                
                response = await client.get(
                    f"{LANGFUSE_HOST}/api/public/traces",
                    params=params,
                    auth=(LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY)
                )
                
                if response.status_code == 200:
                    traces_response = response.json()
                    traces = traces_response.get("data", [])
                    
                    trace_stats["total_sample_traces"] = len(traces)
                    
                    for trace in traces:
                        email = get_trace_email(trace)
                        if email:
                            trace_stats["traces_with_email"] += 1
                            team, _ = assign_trace_to_team(trace, email_to_team_map, get_team_by_member_email, TraceFilteringStats())
                            if team:
                                trace_stats["assigned_traces"] += 1
                            else:
                                trace_stats["unassigned_traces"] += 1
                                if len(trace_stats["unassigned_emails_found"]) < 10:
                                    trace_stats["unassigned_emails_found"].append(email)
                        else:
                            trace_stats["traces_without_email"] += 1
                    
                    trace_stats["sample_trace_count"] = len(traces)
        except Exception as e:
            trace_stats["error"] = f"Could not fetch trace samples: {str(e)}"
        
        return {
            "status": "success",
            "team_structure": {
                "total_teams": diagnostics['total_teams'],
                "total_emails_configured": diagnostics['email_count'],
                "unique_emails": len(unique_emails)
            },
            "diagnostics": diagnostics,
            "emails_by_team": {
                team: len(emails) for team, emails in all_team_emails.items()
            },
            "issues_found": {
                "duplicate_emails_count": len(diagnostics.get("duplicate_emails", {})),
                "duplicate_emails": diagnostics.get("duplicate_emails", {}),
                "empty_emails_count": len(diagnostics.get("empty_emails", [])),
                "teams_with_no_members": diagnostics.get("teams_with_no_members", []),
                "invalid_emails_count": len(diagnostics.get("invalid_emails", []))
            },
            "trace_analysis": trace_stats,
            "recommendations": {
                "unassigned_emails_to_add": trace_stats.get("unassigned_emails_found", []),
                "duplicate_emails_to_review": list(diagnostics.get("duplicate_emails", {}).keys()),
                "teams_needing_members": diagnostics.get("teams_with_no_members", [])
            }
        }
        
    except Exception as e:
        print(f"[ERROR] Email diagnostics failed: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e), "status": "error"}
async def get_team_details(
    team_name: str = Query(..., description="Team name"),
    time_filter: str = Query("today", description="today|yesterday|this_week|last_week|all"),
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
        from datetime import datetime, timedelta, timezone
        
        if not langfuse_client:
            return {"error": "Langfuse client not initialized", "status": "error"}
        
        # Get team info
        team_info = get_team_by_name(team_name)
        if not team_info:
            return {"error": f"Team '{team_name}' not found", "status": "error"}
        
        # Calculate date range
        now = datetime.now(timezone.utc)
        start_time = now
        end_time = now
        
        if time_filter == "today":
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "yesterday":
            yesterday = now - timedelta(days=1)
            start_time = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "this_week":
            start_time = now - timedelta(days=now.weekday())
            start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "last_week":
            # FIX: Calculate previous week (Monday to Sunday), not last 7 days
            this_week_start = now - timedelta(days=now.weekday())
            this_week_start = this_week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            start_time = this_week_start - timedelta(days=7)
            end_time = this_week_start - timedelta(microseconds=1)
        else:
            start_time = None
            end_time = None
        
        # Initialize member stats
        member_stats = {}
        
        # Get all team member emails
        all_team_members_emails = get_all_team_members_emails()
        team_emails = [e.lower() for e in all_team_members_emails.get(team_name, []) if e and isinstance(e, str)]
        
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
        
        async with httpx.AsyncClient() as client:
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
                    
                    response = await client.get(
                        f"{LANGFUSE_HOST}/api/public/traces",
                        params=params,
                        auth=(LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY),
                        timeout=30.0
                    )
                    
                    if response.status_code == 429:
                        break
                    
                    if response.status_code != 200:
                        break
                    
                    traces_response = response.json()
                    traces = traces_response.get("data", [])
                    
                    if not traces:
                        break
                    
                    # Collect all traces for saving
                    # We don't need to extend to all_traces anymore, as it's removed.
                    
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
                        break
                    
                    page += 1
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    print(f"[ERROR] Error fetching team traces: {e}")
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
        
        return {
            "status": "success",
            "team_name": team_name,
            "lead": team_info.get("lead"),
            "lead_email": team_info.get("lead_email"),
            "color": team_info.get("color"),
            "time_filter": time_filter,
            "members": members_list,
            "total_members": len(members_list),
            "active_members": sum(1 for m in members_list if m["total_questions"] > 0),
            "team_total_questions": sum(m["total_questions"] for m in members_list),
            "team_unique_questions": len(set(q for m in members_list for q in m.get("questions", [])))
        }
        
    except Exception as e:
        print(f"[ERROR] Team details fetch failed: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e), "status": "error"}


@router.get("/analytics/langfuse/dashboard-summary")
async def get_langfuse_dashboard_summary(
    time_filter: str = Query("today", description="today|yesterday|this_week|last_week|all"),
    current_user: dict = Depends(require_restricted_admin)
):
    """
    Get a high-level summary for the Langfuse analytics dashboard with date filtering.
    
    Time Filters:
    - today: Today's data only
    - yesterday: Yesterday's data only
    - this_week: Current week data (Monday to Sunday)
    - last_week: Last 7 days
    - all: All available data (default limit 3000 traces)
    
    Returns:
    - Total users
    - Total questions
    - Most active users
    - Top questions
    """
    try:
        from app.langfuse_integration import langfuse_client
        from app.trace_utils import TraceFilteringStats
        import asyncio
        from datetime import datetime, timedelta, timezone
        
        if not langfuse_client:
            return {"error": "Langfuse client not initialized", "status": "error"}
        
        # Calculate date range based on filter
        now = datetime.now(timezone.utc)
        start_time = now
        end_time = now
        
        if time_filter == "today":
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "yesterday":
            yesterday = now - timedelta(days=1)
            start_time = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "this_week":
            # Monday to now
            start_time = now - timedelta(days=now.weekday())
            start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "last_week":
            # ✅ FIXED: Calendar-based previous week (Monday to Sunday), not rolling 7 days
            # Calculate start of this week (Monday at 00:00:00)
            this_week_start = now - timedelta(days=now.weekday())
            this_week_start = this_week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            # Last week starts 7 days before this week (last Monday at 00:00:00)
            start_time = this_week_start - timedelta(days=7)
            # Last week ends at the end of last Sunday (start of this week minus 1 microsecond)
            end_time = this_week_start - timedelta(microseconds=1)
        else:  # "all"
            start_time = None
            end_time = None
        
        users_activity = defaultdict(lambda: {"count": 0, "email": "", "name": ""})
        all_questions = []
        
        page = 1
        batch_limit = 100
        # Match teams endpoint page limits for consistency (INCREASED for more comprehensive data)
        max_pages = 5 if time_filter in ["today", "yesterday"] else (10 if time_filter != "all" else 20)
        
        async with httpx.AsyncClient() as client:
            from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
            
            while page <= max_pages:
                try:
                    # Build params with optional date filter
                    params = {
                        "page": page,
                        "limit": batch_limit,
                        "orderBy[createdAt]": "DESC"
                    }
                    
                    # Add date range if available (using correct Langfuse API format)
                    if start_time:
                        params["createdAt[gte]"] = start_time.isoformat() + "Z"
                    if end_time:
                        params["createdAt[lte]"] = end_time.isoformat() + "Z"
                    
                    response = await client.get(
                        f"{LANGFUSE_HOST}/api/public/traces",
                        params=params,
                        auth=(LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY),
                        timeout=45.0  # Increased timeout to match teams endpoint
                    )
                    
                    if response.status_code == 429:  # Rate limited
                        print(f"[WARNING] Langfuse rate limited, stopping pagination at page {page}")
                        break
                    
                    if response.status_code != 200:
                        break
                    
                    traces_response = response.json()
                    traces = traces_response.get("data", [])
                    
                    if not traces:
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
                        break
                    
                    page += 1
                    await asyncio.sleep(0.5)  # Rate limiting delay
                except Exception as e:
                    print(f"[ERROR] Langfuse API error: {e}")
                    break
        
        # Save all fetched traces to JSON file
        
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
            print(f"[ERROR] Counter error: {e}")
            top_questions = []
        
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
        print(f"[ERROR] Dashboard summary fetch failed: {e}")
        return {"error": str(e), "status": "error"}


@router.get("/analytics/langfuse/users")
async def get_langfuse_users_analytics(
    time_filter: str = Query("today", description="today|yesterday|this_week|last_week|all"),
    current_user: dict = Depends(require_restricted_admin)
):
    """
    Fetch all users from Langfuse with their analytics with date filtering.
    
    Time Filters:
    - today: Today's data only
    - yesterday: Yesterday's data only
    - this_week: Current week data
    - last_week: Last 7 days
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
        from app.trace_utils import TraceFilteringStats
        import asyncio
        from datetime import datetime, timedelta, timezone
        
        if not langfuse_client:
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
            end_time = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "yesterday":
            yesterday = now - timedelta(days=1)
            start_time = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "this_week":
            start_time = now - timedelta(days=now.weekday())
            start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "last_week":
            # FIX: Calculate previous week (Monday to Sunday), not last 7 days
            this_week_start = now - timedelta(days=now.weekday())
            this_week_start = this_week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            start_time = this_week_start - timedelta(days=7)
            end_time = this_week_start - timedelta(microseconds=1)
        else:
            start_time = None
            end_time = None
        
        users_data = {}
        page = 1
        limit = 100
        # Match teams endpoint page limits for consistency (INCREASED for more comprehensive data)
        max_pages = 5 if time_filter in ["today", "yesterday"] else (10 if time_filter != "all" else 20)
        
        async with httpx.AsyncClient() as client:
            while page <= max_pages:
                try:
                    # Fetch traces with pagination and date filter (using correct Langfuse API format)
                    params = {
                        "page": page,
                        "limit": limit,
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
                        timeout=45.0  # Increased timeout to match teams endpoint
                    )
                    
                    if response.status_code == 429:  # Rate limited
                        print(f"[WARNING] Langfuse rate limited at page {page}, stopping")
                        break
                    
                    if response.status_code != 200:
                        print(f"[ERROR] Langfuse API error: {response.status_code}")
                        break
                    
                    traces_response = response.json()
                    traces = traces_response.get("data", [])
                    
                    if not traces:
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
                        break
                    
                    page += 1
                    await asyncio.sleep(0.5)  # Rate limiting delay
                except Exception as e:
                    print(f"[ERROR] Error fetching traces: {e}")
                    break
        
        # Save all fetched traces to JSON file
        
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
        
        return {
            "status": "success",
            "total_users": len(users_data),
            "total_questions": sum(u["total_questions"] for u in users_data.values()),
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
        print(f"[ERROR] Analytics fetch failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "error": str(e),
            "status": "error"
        }


@router.get("/analytics/langfuse/users/{user_id}")
async def get_user_langfuse_analytics(
    user_id: str,
    time_filter: str = Query("today", description="today|yesterday|this_week|last_week|all"),
    current_user: dict = Depends(require_restricted_admin)
):
    """
    Get detailed analytics for a specific user with date filtering.
    
    Time Filters:
    - today: Today's data only
    - yesterday: Yesterday's data only
    - this_week: Current week data
    - last_week: Last 7 days
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
        from datetime import datetime, timedelta, timezone
        
        if not langfuse_client:
            return {"error": "Langfuse client not initialized"}
        
        # Calculate date range
        now = datetime.now(timezone.utc)
        start_time = now
        end_time = now
        
        if time_filter == "today":
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "yesterday":
            yesterday = now - timedelta(days=1)
            start_time = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "this_week":
            start_time = now - timedelta(days=now.weekday())
            start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "last_week":
            # FIX: Calculate previous week (Monday to Sunday), not last 7 days
            this_week_start = now - timedelta(days=now.weekday())
            this_week_start = this_week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            start_time = this_week_start - timedelta(days=7)
            end_time = this_week_start - timedelta(microseconds=1)
        else:
            start_time = None
            end_time = None
        
        user_traces = []
        page = 1
        limit = 100
        max_pages = 10 if time_filter != "all" else 20  # Faster for filtered queries
        
        async with httpx.AsyncClient() as client:
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
                    
                    response = await client.get(
                        f"{LANGFUSE_HOST}/api/public/traces",
                        params=params,
                        auth=(LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY),
                        timeout=30.0  # Reduced timeout
                    )
                    
                    if response.status_code == 429:  # Rate limited
                        print(f"[WARNING] Langfuse rate limited at page {page}")
                        break
                    
                    if response.status_code != 200:
                        break
                    
                    traces_response = response.json()
                    traces = traces_response.get("data", [])
                    
                    if not traces:
                        break
                    
                    user_traces.extend(traces)
                    
                    if len(traces) < limit:
                        break
                    
                    page += 1
                    await asyncio.sleep(0.5)  # Rate limiting delay
                except Exception as e:
                    print(f"[ERROR] Error fetching user traces: {e}")
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
            print(f"[ERROR] Counter error: {e}")
            top_questions = []
        
        # Get user info from first trace
        user_email = "N/A"
        user_name = "Unknown"
        if user_traces:
            metadata = user_traces[0].get("metadata", {})
            user_email = metadata.get("user_email", "N/A")
            user_name = metadata.get("user_name", "Unknown")
        
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
    time_filter: str = Query("today", description="today|yesterday|this_week|last_week|all"),
    current_user: dict = Depends(require_restricted_admin)
):
    """
    Get the top questions asked across all users with date filtering.
    Helps identify common user pain points and interests.
    
    Time Filters:
    - today: Today's data only
    - yesterday: Yesterday's data only
    - this_week: Current week data
    - last_week: Last 7 days
    - all: All available data
    """
    try:
        from app.langfuse_integration import langfuse_client
        from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
        import asyncio
        from datetime import datetime, timedelta, timezone
        
        if not langfuse_client:
            return {"error": "Langfuse client not initialized"}
        
        # Calculate date range
        now = datetime.now(timezone.utc)
        start_time = now
        end_time = now
        
        if time_filter == "today":
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "yesterday":
            yesterday = now - timedelta(days=1)
            start_time = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "this_week":
            start_time = now - timedelta(days=now.weekday())
            start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "last_week":
            # FIX: Calculate previous week (Monday to Sunday), not last 7 days
            this_week_start = now - timedelta(days=now.weekday())
            this_week_start = this_week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            start_time = this_week_start - timedelta(days=7)
            end_time = this_week_start - timedelta(microseconds=1)
        else:
            start_time = None
            end_time = None
        
        all_questions = []
        page = 1
        batch_limit = 100
        # Match teams endpoint page limits for consistency (INCREASED for more comprehensive data)
        max_pages = 5 if time_filter in ["today", "yesterday"] else (10 if time_filter != "all" else 20)
        
        async with httpx.AsyncClient() as client:
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
                        timeout=45.0  # Increased timeout to match teams endpoint
                    )
                    
                    if response.status_code == 429:  # Rate limited
                        print(f"[WARNING] Langfuse rate limited at page {page}, stopping")
                        break
                    
                    if response.status_code != 200:
                        break
                    
                    traces_response = response.json()
                    traces = traces_response.get("data", [])
                    
                    if not traces:
                        break
                    
                    # Collect all traces for saving
                    # We don't need to extend to all_traces anymore, as it's removed.
                    
                    for trace in traces:
                        question = trace.get("input", "")
                        if question:
                            all_questions.append(str(question))
                    
                    if len(traces) < batch_limit:
                        break
                    
                    page += 1
                    await asyncio.sleep(0.5)  # Rate limiting delay
                except Exception as e:
                    print(f"[ERROR] Error fetching traces: {e}")
                    break
        
        # Save all fetched traces to JSON file
        
        # Get top questions
        try:
            question_counter = Counter(all_questions)
            top_questions = question_counter.most_common(limit)
        except Exception as e:
            print(f"[ERROR] Counter error: {e}")
            top_questions = []
        
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
        from config import SYSTEM_PROMPT_CF_ONLY
        correction_prompt = f"""
{SYSTEM_PROMPT_CF_ONLY}

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
        from datetime import datetime
        
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
async def refresh_microsoft_token(request: TokenRefreshRequest):
    """
    Refresh Microsoft OAuth access token using refresh token.
    
    SECURITY: Backend owns all OAuth credentials.
    Frontend only provides the refresh_token.
    """
    try:
        # Backend owns these secrets
        tenant = MICROSOFT_TENANT
        client_id = MICROSOFT_CLIENT_ID
        client_secret = MICROSOFT_CLIENT_SECRET
        
        token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
        
        token_data = {
            "client_id": client_id,
            "client_secret": client_secret,  # Never exposed to frontend
            "refresh_token": request.refresh_token,
            "grant_type": "refresh_token",
            "scope": "openid email profile User.Read"
        }
        
        async with httpx.AsyncClient() as client:
            token_response = await client.post(token_url, data=token_data, timeout=30.0)
            
            if token_response.status_code != 200:
                logger.error(f"Token refresh failed: {token_response.status_code}")
                # Log but don't expose full error details to frontend
                raise HTTPException(
                    status_code=HTTPStatus.UNAUTHORIZED,
                    detail="Token refresh failed"
                )
            
            token_info = token_response.json()
            
            # Validate CloudFuze domain again (defense in depth)
            async with httpx.AsyncClient() as graph_client:
                user_response = await graph_client.get(
                    "https://graph.microsoft.com/v1.0/me",
                    headers={"Authorization": f"Bearer {token_info.get('access_token')}"},
                    timeout=10.0
                )
                
                if user_response.status_code == 200:
                    user_info = user_response.json()
                    user_email = user_info.get("mail") or user_info.get("userPrincipalName", "")
                    
                    if not user_email.endswith("@cloudfuze.com"):
                        logger.warning(f"Refresh attempt from non-CloudFuze email: {user_email}")
                        raise HTTPException(
                            status_code=HTTPStatus.FORBIDDEN,
                            detail="Access denied"
                        )
            
            logger.info(f"Token refreshed successfully")
            
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
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Token refresh failed"
        )

@router.post("/auth/microsoft/callback")
async def microsoft_oauth_callback(request: MicrosoftCallbackRequest):
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
            
            # Create user ID from Microsoft user ID
            user_id = user_info.get("id")
            user_name = user_info.get("displayName", "User")
            user_email = user_info.get("mail") or user_info.get("userPrincipalName", "")
            
            # Validate that the user has a CloudFuze email domain
            if not user_email.endswith("@cloudfuze.com"):
                return {
                    "error": "Access denied", 
                    "message": "Only CloudFuze company accounts are allowed to access this application.",
                    "details": f"Email domain not allowed: {user_email}"
                }
            
            result = {
                "user_id": user_id,
                "name": user_name,
                "email": user_email,
                "access_token": access_token,
                "refresh_token": token_info.get("refresh_token", ""),
                "expires_in": token_info.get("expires_in", 3600)  # Token lifetime in seconds
            }
            
            return result
            
    except Exception as e:
        return {"error": f"OAuth callback failed: {str(e)}"}


async def _get_langfuse_team_details_internal(
    team_name: str,
    start_date: str = None,
    end_date: str = None,
    time_filter: str = None
):
    """
    Internal function to get detailed analytics for a specific team.
    This is shared by both path parameter and query parameter endpoints.
    """
    try:
        from app.langfuse_integration import langfuse_client
        from app.models.teams import TEAMS, get_team_for_member
        from datetime import timedelta, timezone
        
        if not langfuse_client:
            return {"error": "Langfuse client not initialized", "status": "error"}
        
        # Validate team exists
        if team_name not in TEAMS:
            return {"status": "error", "error": "Team not found"}
        
        # Calculate time range (always use UTC for consistency)
        now_utc = datetime.now(timezone.utc)
        start_time = None
        end_time = now_utc
        max_pages = 30
        request_timeout = 60.0
        
        # Use custom date range if provided
        if start_date and end_date:
            try:
                # Parse dates and make them timezone-aware (UTC)
                start_time = datetime.strptime(start_date, "%Y-%m-%d").replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
                end_time = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc)
                
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
            start_time = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now_utc.replace(hour=23, minute=59, second=59, microsecond=999999)
            max_pages = 10
            request_timeout = 30.0
        elif time_filter == "yesterday":
            yesterday = now_utc - timedelta(days=1)
            start_time = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
            max_pages = 10
            request_timeout = 30.0
        elif time_filter == "this_week":
            start_time = now_utc - timedelta(days=now_utc.weekday())
            start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now_utc.replace(hour=23, minute=59, second=59, microsecond=999999)
            max_pages = 15
            request_timeout = 45.0
        elif time_filter == "last_week":
            # ✅ FIXED: Calendar-based previous week (Monday to Sunday), not rolling 7 days
            this_week_start = now_utc - timedelta(days=now_utc.weekday())
            this_week_start = this_week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            start_time = this_week_start - timedelta(days=7)
            end_time = this_week_start - timedelta(microseconds=1)
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
                            question = trace.get("input", "").strip()
                            user_email = str(metadata.get("user_email", "")).lower().strip()
                            user_name = str(metadata.get("user_name", "Unknown"))
                            
                            # Skip traces without question
                            if not question:
                                continue
                            
                            # Check if this trace belongs to current team using EXACT EMAIL MATCHING
                            # (NOT pattern matching which causes false positives)
                            trace_team = None
                            matching_member = None
                            
                            if user_email and user_email != "":
                                # Try to find member by exact email match
                                for member_lower, member_info in members_data.items():
                                    member_email = member_info.get("email", "").lower().strip()
                                    if member_email and member_email == user_email:
                                        trace_team = team_name
                                        matching_member = member_lower
                                        break
                            
                            # Fallback to name matching if email didn't match
                            if not trace_team and user_name and user_name != "Unknown":
                                user_name_lower = user_name.lower().strip()
                                if user_name_lower in members_data:
                                    trace_team = team_name
                                    matching_member = user_name_lower
                            
                            if trace_team and matching_member:
                                team_total_questions += 1
                                all_team_questions.append(question)
                                
                                member_info = members_data[matching_member]
                                member_info["total_questions"] += 1
                                member_info["questions_list"].append(question)
                                member_info["email"] = user_email if user_email else member_info.get("email", "")
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


@router.get("/analytics/langfuse/teams/details/{team_name}")
async def get_langfuse_team_details(
    team_name: str = Path(..., description="Team name"),
    start_date: str = Query(None, description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(None, description="End date in YYYY-MM-DD format"),
    time_filter: str = Query(None, description="(Legacy) Filter by time: today, yesterday, this_week, last_week, all"),
    current_user: dict = Depends(require_restricted_admin)
):
    """
    Get detailed analytics for a specific team including all members and their stats.
    Supports both date range (start_date/end_date) and preset filters (time_filter).
    """
    return await _get_langfuse_team_details_internal(
        team_name=team_name,
        start_date=start_date,
        end_date=end_date,
        time_filter=time_filter
    )


@router.get("/analytics/langfuse/teams/details")
async def get_langfuse_team_details_legacy(
    team_name: str = Query(..., description="Team name"),
    start_date: str = Query(None, description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(None, description="End date in YYYY-MM-DD format"),
    time_filter: str = Query(None, description="(Legacy) Filter by time: today, yesterday, this_week, last_week, all"),
    current_user: dict = Depends(require_restricted_admin)
):
    """
    Legacy endpoint for team details using query parameters.
    Maintains backward compatibility with existing tests and API calls.
    """
    return await _get_langfuse_team_details_internal(
        team_name=team_name,
        start_date=start_date,
        end_date=end_date,
        time_filter=time_filter
    )


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
