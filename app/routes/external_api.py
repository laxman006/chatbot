# -*- coding: utf-8 -*-
"""
External API Endpoint

Simple API-key-authenticated endpoint for external consumers.
Friends / integrations can POST a question and receive an answer
without going through Microsoft OAuth.

Usage:
    curl -X POST https://your-server/api/external/chat \
         -H "Authorization: Bearer <API_KEY>" \
         -H "Content-Type: application/json" \
         -d '{"question": "What is CloudFuze Migrate?"}'
"""

from fastapi import APIRouter, HTTPException, Header, status
from pydantic import BaseModel, Field
from typing import Optional
import os
import uuid
import logging
import time
from datetime import datetime
from langchain_core.messages import SystemMessage, HumanMessage

from app.llm_factory import get_llm
from app.vectorstore import retriever, vectorstore, bm25_retriever
from config import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/external", tags=["external-api"])

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

_API_KEYS: Optional[set] = None


def _load_api_keys() -> set:
    global _API_KEYS
    if _API_KEYS is None:
        raw = os.getenv("EXTERNAL_API_KEYS", "")
        _API_KEYS = {k.strip() for k in raw.split(",") if k.strip()}
    return _API_KEYS


def _verify_api_key(authorization: Optional[str] = Header(None)):
    """Validate the Bearer API key from the Authorization header."""
    keys = _load_api_keys()
    if not keys:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="External API is not configured. Set EXTERNAL_API_KEYS in .env",
        )

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header. Use: Authorization: Bearer <key>",
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization format. Use: Authorization: Bearer <key>",
        )

    if token not in keys:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )

    return token


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ExternalChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = Field(
        default=None,
        description="Optional session id to maintain conversation continuity",
    )


class ExternalChatResponse(BaseModel):
    answer: str
    session_id: str
    elapsed_ms: int


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/chat",
    response_model=ExternalChatResponse,
    summary="Ask the CloudFuze chatbot a question",
    description="Send a question and receive an answer from the CloudFuze knowledge base. "
                "Requires a valid API key in the Authorization header.",
)
async def external_chat(
    body: ExternalChatRequest,
    _key: str = Header(None, alias="Authorization", include_in_schema=False),
):
    _verify_api_key(_key)

    start = time.perf_counter()
    session_id = body.session_id or str(uuid.uuid4())
    question = body.question.strip()

    logger.info(f"[EXTERNAL-API] Question received (session {session_id[:8]}...): {question[:80]}")

    try:
        answer = await _generate_answer(question)
    except Exception as exc:
        logger.error(f"[EXTERNAL-API] Failed to generate answer: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate an answer. Please try again later.",
        )

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    logger.info(f"[EXTERNAL-API] Answered in {elapsed_ms}ms")

    return ExternalChatResponse(
        answer=answer,
        session_id=session_id,
        elapsed_ms=elapsed_ms,
    )


# ---------------------------------------------------------------------------
# Core answer generation (simplified RAG pipeline)
# ---------------------------------------------------------------------------

async def _generate_answer(question: str) -> str:
    """Run retrieval + LLM to produce an answer."""

    from app.llm import format_docs
    from app.endpoints import (
        classify_intent,
        retrieve_with_branch_filter,
        hybrid_ranking,
        is_conversational_query,
    )

    if is_conversational_query(question):
        llm = get_llm(temperature=0.7)
        result = llm.invoke([
            SystemMessage(content="You are a helpful CloudFuze AI assistant."),
            HumanMessage(content=question),
        ])
        return result.content

    intent_result = classify_intent(question)
    intent = intent_result["intent"]

    if vectorstore is None:
        llm = get_llm(temperature=0.3)
        result = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=question),
        ])
        return result.content

    doc_results = retrieve_with_branch_filter(query=question, intent=intent, k=50)
    doc_results = hybrid_ranking(doc_results=doc_results, query=question, intent=intent, alpha=0.7)

    final_docs = [doc for doc, _score in doc_results]
    formatted_docs = format_docs(final_docs)
    context = "\n\n".join(formatted_docs)

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"Use the following context to answer.\n\n<context>\n{context}\n</context>\n\nUser Question:\n{question}"),
    ]

    llm = get_llm(temperature=0.1, max_tokens=1500)
    result = llm.invoke(messages)
    return result.content
