# -*- coding: utf-8 -*-
"""
RAG state for the antigravity LangGraph workflow.
"""

from __future__ import annotations

from typing import TypedDict, List, Any, Optional

from langchain_core.documents import Document


class ValidationResult(TypedDict, total=False):
    """Result of CRAG validate_context node."""
    quality_score: float
    relevance_scores: List[float]
    coverage_sufficient: bool
    diversity_score: float
    issues: List[str]
    corrective_action: str  # e.g. "expand_topk", "rewrite_query", "decompose", "ask_clarification"


class RAGState(TypedDict, total=False):
    """State for the Weaviate Retrieval Core Flow graph."""
    # Input
    query: str
    user_id: str
    session_id: str
    user_context: Any  # app.rbac.UserContext for RBAC filter

    # Intent
    intent: str  # "factual" | "complex" | "procedural"
    intent_confidence: float

    # Query shaping
    enhanced_query: str
    expanded_queries: List[str]

    # Retrieval
    retrieved_docs: List[tuple]  # List[(Document, float)]
    reranked_docs: List[tuple]
    top_k: int
    rerank_top_k: int

    # CRAG
    validation_result: ValidationResult
    corrective_action: str
    retry_count: int
    no_sufficient_context: bool  # True when retrieval is insufficient (RAG-wide refuse path)

    # Context and generation
    compressed_context: str
    context_token_count: int
    final_response: str
    citations: List[dict]
    chunk_keys_cited: List[str]

    # Metadata for Langfuse
    trace: Any
    messages: List[Any]
