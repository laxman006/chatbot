# -*- coding: utf-8 -*-
"""
Compiled LangGraph for the Weaviate Retrieval Core Flow.

Flow: classify_intent -> (factual|complex|procedural) -> retrieve -> rerank
-> validate_context -> (pass|retry|compress_anyway) -> compress_context
-> generate_response -> extract_citations -> END.
Image attachment removed; only document content is ingested.
"""

from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import StateGraph, END

from app.rag.state import RAGState
from app.rag import nodes

logger = logging.getLogger(__name__)


def _route_intent(state: RAGState) -> Literal["retrieve_documents", "expand_query", "decompose_query"]:
    intent = state.get("intent") or "factual"
    if intent == "complex":
        return "expand_query"
    if intent == "procedural":
        return "decompose_query"
    return "retrieve_documents"


def _route_after_validate(state: RAGState) -> Literal["refuse_response", "compress_context", "apply_corrective_action"]:
    """Route after validate: refuse when insufficient (RAG-wide), else proceed or retry."""
    retry = state.get("retry_count") or 0
    docs = state.get("reranked_docs") or state.get("retrieved_docs") or []
    no_sufficient = state.get("no_sufficient_context", False)
    val = state.get("validation_result") or {}
    quality = val.get("quality_score", 0.0)
    action = state.get("corrective_action") or "none"
    # Refuse path: insufficient retrieval and (max retries or no docs)
    if no_sufficient and (retry >= 2 or len(docs) == 0):
        return "refuse_response"
    if action == "none" or quality >= 0.5 or retry >= 2:
        return "compress_context"
    return "apply_corrective_action"


def build_rag_graph(checkpointer=None):
    """Build and compile the RAG LangGraph. Pass checkpointer for streaming/checkpointing."""
    g = StateGraph(RAGState)

    g.add_node("classify_intent", nodes.classify_intent)
    g.add_node("expand_query", nodes.expand_query)
    g.add_node("decompose_query", nodes.decompose_query)
    g.add_node("retrieve_documents", nodes.retrieve_documents)
    g.add_node("rerank_results", nodes.rerank_results)
    g.add_node("validate_context", nodes.validate_context)
    g.add_node("refuse_response", nodes.refuse_response)
    g.add_node("apply_corrective_action", nodes.apply_corrective_action)
    g.add_node("compress_context", nodes.compress_context)
    g.add_node("generate_response", nodes.generate_response)
    g.add_node("extract_citations", nodes.extract_citations)

    g.set_entry_point("classify_intent")
    g.add_conditional_edges("classify_intent", _route_intent)
    g.add_edge("expand_query", "retrieve_documents")
    g.add_edge("decompose_query", "retrieve_documents")
    g.add_edge("retrieve_documents", "rerank_results")
    g.add_edge("rerank_results", "validate_context")
    g.add_conditional_edges("validate_context", _route_after_validate, {
        "refuse_response": "refuse_response",
        "compress_context": "compress_context",
        "apply_corrective_action": "apply_corrective_action",
    })
    g.add_edge("refuse_response", "extract_citations")
    g.add_edge("apply_corrective_action", "retrieve_documents")
    g.add_edge("compress_context", "generate_response")
    g.add_edge("generate_response", "extract_citations")
    g.add_edge("extract_citations", END)

    if checkpointer is not None:
        return g.compile(checkpointer=checkpointer)
    return g.compile()


# Singleton compiled graph for sync invoke
_rag_graph = None


def get_rag_graph():
    """Return the compiled RAG graph (lazy init)."""
    global _rag_graph
    if _rag_graph is None:
        _rag_graph = build_rag_graph()
    return _rag_graph
