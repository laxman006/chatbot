# -*- coding: utf-8 -*-
"""
Chat handlers wired to the antigravity LangGraph + Langfuse pipeline.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator, List, Optional

from app.langfuse_integration import langfuse_tracker
from app.rbac import default_user_context
from config import RBAC_DEFAULT_USER_GROUPS

try:
    from app.mongodb_memory import save_message, add_to_conversation
except Exception:
    save_message = add_to_conversation = None

logger = logging.getLogger(__name__)

PLACEHOLDER_ANSWER = (
    "The RAG pipeline is being upgraded. If you see this, the graph may have failed. "
    "Please try again or contact support."
)


def _run_rag_graph(
    question: str,
    user_id: str,
    session_id: str,
    group_ids: Optional[List[str]] = None,
) -> dict:
    """Run LangGraph RAG pipeline. Returns final state dict or empty dict on failure.

    When group_ids is None, uses RBAC_DEFAULT_USER_GROUPS so retrieval applies RBAC
    (chunks must have permissions containing at least one of the user's groups).
    """
    try:
        from app.rag import get_rag_graph
        graph = get_rag_graph()
        groups = group_ids if group_ids is not None else RBAC_DEFAULT_USER_GROUPS
        user_context = default_user_context(user_id, group_ids=groups)
        state = {
            "query": question,
            "user_id": user_id,
            "session_id": session_id,
            "user_context": user_context,
        }
        logger.info("[RAG] pipeline_start | question_len=%d | query_preview=%s", len(question or ""), (question or "")[:80])
        out = graph.invoke(state)
        out_dict = dict(out) if out else {}
        logger.info("[RAG] pipeline_done | intent=%s | retrieved=%d | response_len=%d",
                    out_dict.get("intent"), len(out_dict.get("retrieved_docs") or []), len(out_dict.get("final_response") or ""))
        return out_dict
    except Exception as e:
        logger.exception("RAG graph invoke failed: %s", e)
        return {}


def _log_rag_trace(rag_trace, out: dict, endpoint: str):
    """Log evaluation spans and complete the RAG trace from graph output."""
    if not rag_trace or not out:
        return
    try:
        rag_trace.start_query(out.get("enhanced_query") or out.get("query") or "", {"endpoint": endpoint})
        rag_trace.log_intent_span(out.get("intent", ""), out.get("intent_confidence", 0.0))
        docs = out.get("retrieved_docs") or []
        if docs:
            from collections import Counter
            breakdown = Counter((getattr(d, "metadata", {}) or {}).get("source_type", "unknown") for d, _ in docs)
            rag_trace.log_retrieval(
                out.get("query", ""),
                [getattr(d, "page_content", str(d))[:200] for d, _ in docs[:5]],
                len(docs),
                dict(breakdown),
                {"top_k": out.get("top_k"), "rerank_top_k": out.get("rerank_top_k")},
            )
        rag_trace.log_rerank_span(
            len(out.get("retrieved_docs") or []),
            out.get("top_k") or 50,
            out.get("rerank_top_k") or 15,
        )
        if out.get("validation_result"):
            rag_trace.log_validate_context_span(out["validation_result"])
        rag_trace.log_compress_context_span(out.get("context_token_count") or 0)
        rag_trace.log_extract_citations_span(
            len(out.get("citations") or []),
            out.get("chunk_keys_cited") or [],
        )
        rag_trace.complete(out.get("final_response") or "", out)
    except Exception as e:
        logger.warning("Langfuse RAG trace logging failed: %s", e)


async def handle_chat(
    *,
    question: str,
    session_id: str,
    user_id: str,
    user_name: str | None,
    user_email: str | None,
    conversation_id: str,
) -> tuple[str, str | None]:
    """Non-streaming chat. Returns (answer, trace_id). Runs LangGraph + Langfuse."""
    rag_trace = None
    try:
        rag_trace = langfuse_tracker.create_rag_pipeline_trace(
            user_id=conversation_id,
            question=question,
            session_id=session_id,
            user_name=user_name,
            user_email=user_email,
            metadata={"endpoint": "/chat"},
        )
    except Exception as e:
        logger.warning("Langfuse RAG trace creation failed: %s", e)

    loop = asyncio.get_event_loop()
    out = await loop.run_in_executor(None, _run_rag_graph, question, user_id, session_id)
    answer = out.get("final_response", "") if out else ""
    trace_id = rag_trace.trace_id if rag_trace else None
    return answer, trace_id


async def handle_chat_stream(
    *,
    question: str,
    session_id: str,
    user_id: str,
    user_name: str | None,
    user_email: str | None,
    conversation_id: str,
) -> AsyncGenerator[str, None]:
    """Streaming chat. Runs LangGraph then streams response token-by-token."""
    try:
        yield f"data: {json.dumps({'type': 'thinking_complete'})}\n\n"
        rag_trace = None
        try:
            rag_trace = langfuse_tracker.create_rag_pipeline_trace(
                user_id=conversation_id,
                question=question,
                session_id=session_id,
                user_name=user_name,
                user_email=user_email,
                metadata={"endpoint": "/chat/stream"},
            )
        except Exception as e:
            logger.warning("Langfuse RAG trace creation failed: %s", e)

        loop = asyncio.get_event_loop()
        out = await loop.run_in_executor(None, _run_rag_graph, question, user_id, session_id)
        full_response = out.get("final_response") or PLACEHOLDER_ANSWER
        trace_id = None
        if rag_trace:
            _log_rag_trace(rag_trace, out, "/chat/stream")
            trace_id = rag_trace.trace_id
        elif not out:
            try:
                trace_id = langfuse_tracker.create_trace(
                    user_id=conversation_id, question=question, answer=full_response,
                    session_id=session_id, user_name=user_name, user_email=user_email,
                    metadata={"endpoint": "/chat/stream", "fallback": True},
                )
            except Exception:
                pass
        images = []  # Image attachment removed; only document content is ingested

        for i, ch in enumerate(full_response):
            yield f"data: {json.dumps({'token': ch, 'type': 'token'})}\n\n"
            if i % 5 == 0:
                await asyncio.sleep(0.01)

        if save_message and add_to_conversation:
            try:
                await save_message(session_id, "user", question)
                await save_message(session_id, "assistant", full_response)
                await add_to_conversation(conversation_id, "user", question)
                await add_to_conversation(conversation_id, "assistant", full_response)
            except Exception as e:
                logger.warning("Failed to save stream messages: %s", e)

        yield f"data: {json.dumps({'type': 'done', 'full_response': full_response, 'trace_id': trace_id, 'recommended_questions': [], 'images': images})}\n\n"
    except Exception as e:
        logger.exception("handle_chat_stream failed: %s", e)
        yield f"data: {json.dumps({'error': str(e), 'type': 'error'})}\n\n"


async def handle_chat_retry_stream(
    *,
    question: str,
    session_id: str,
    previous_trace_id: str,
    retry_attempt: int,
    user_id: str,
    user_name: str | None,
    user_email: str | None,
    conversation_id: str,
) -> AsyncGenerator[str, None]:
    """Retry streaming chat. Runs LangGraph then streams response."""
    try:
        yield f"data: {json.dumps({'type': 'thinking_complete'})}\n\n"
        rag_trace = None
        try:
            rag_trace = langfuse_tracker.create_rag_pipeline_trace(
                user_id=conversation_id,
                question=question,
                session_id=session_id,
                user_name=user_name,
                user_email=user_email,
                metadata={"endpoint": "/chat/retry/stream", "previous_trace_id": previous_trace_id, "retry_attempt": retry_attempt},
            )
        except Exception as e:
            logger.warning("Langfuse RAG trace creation failed: %s", e)

        loop = asyncio.get_event_loop()
        out = await loop.run_in_executor(None, _run_rag_graph, question, user_id, session_id)
        full_response = out.get("final_response") or PLACEHOLDER_ANSWER
        trace_id = None
        if rag_trace:
            _log_rag_trace(rag_trace, out, "/chat/retry/stream")
            trace_id = rag_trace.trace_id
        elif not out:
            try:
                trace_id = langfuse_tracker.create_trace(
                    user_id=conversation_id, question=question, answer=full_response,
                    session_id=session_id, user_name=user_name, user_email=user_email,
                    metadata={"endpoint": "/chat/retry/stream", "fallback": True},
                )
            except Exception:
                pass
        images = []  # Image attachment removed; only document content is ingested

        for i, ch in enumerate(full_response):
            yield f"data: {json.dumps({'token': ch, 'type': 'token'})}\n\n"
            if i % 5 == 0:
                await asyncio.sleep(0.01)

        if save_message and add_to_conversation:
            try:
                await save_message(session_id, "user", question)
                await save_message(session_id, "assistant", full_response)
                await add_to_conversation(conversation_id, "user", question)
                await add_to_conversation(conversation_id, "assistant", full_response)
            except Exception as e:
                logger.warning("Failed to save retry stream messages: %s", e)

        yield f"data: {json.dumps({'type': 'done', 'full_response': full_response, 'trace_id': trace_id, 'recommended_questions': [], 'images': images})}\n\n"
    except Exception as e:
        logger.exception("handle_chat_retry_stream failed: %s", e)
        yield f"data: {json.dumps({'error': str(e), 'type': 'error'})}\n\n"
