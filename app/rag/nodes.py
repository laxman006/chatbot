# -*- coding: utf-8 -*-
"""
LangGraph nodes for the Weaviate Retrieval Core Flow.
"""

from __future__ import annotations

import logging
from typing import List, Tuple, Any

from langchain_core.documents import Document

from app.rag.state import RAGState, ValidationResult

logger = logging.getLogger(__name__)

# Default token budget for context compression
DEFAULT_CONTEXT_TOKEN_BUDGET = 6000


# Keep retrieval consistent with app.weaviate_retriever's layer-aware ordering.
# When we merge results across multiple expanded queries, we must re-apply this
# ordering; otherwise raw_content chunks can float to the top by distance alone.
_CHUNK_TYPE_PRIORITY = {
    "feature_capability": 100,
    "definition": 95,
    "limitation": 90,
    "migration_capability_summary": 80,
    "mixed": 70,
    "table_row": 40,
    "raw_content": 10,
}
_DEFAULT_CHUNK_PRIORITY = 50


def _chunk_type_priority(doc: Document) -> int:
    meta = getattr(doc, "metadata", {}) or {}
    ct = meta.get("chunk_type") or ""
    return _CHUNK_TYPE_PRIORITY.get(ct, _DEFAULT_CHUNK_PRIORITY)


def _chunk_key(doc: Document) -> str:
    meta = getattr(doc, "metadata", {}) or {}
    return meta.get("chunk_key") or (f"{meta.get('parent_key', '')}#{meta.get('chunk_id', '')}")


def _safe_lower(s: Any) -> str:
    try:
        return str(s or "").lower()
    except Exception:
        return ""


def _should_two_hop(query: str) -> bool:
    """
    Two-hop retrieval is used to avoid matrix flooding:
    - Hop 1: fetch capabilities (often many chunks)
    - Hop 2: fetch definitions/explanations from the SAME doc_id
    """
    q = _safe_lower(query)
    return any(w in q for w in ("explain", "what is", "meaning", "definition", "describe", "details", "how does"))


def _dominant_sharepoint_doc_id(pairs: List[Tuple[Document, float]]) -> str:
    """Return the most common SharePoint doc_id among retrieved docs (or empty)."""
    counts = {}
    for d, _ in pairs:
        meta = getattr(d, "metadata", {}) or {}
        if (meta.get("source_type") or "") != "sharepoint":
            continue
        doc_id = (meta.get("doc_id") or "").strip()
        if not doc_id:
            continue
        counts[doc_id] = counts.get(doc_id, 0) + 1
    if not counts:
        return ""
    return max(counts.items(), key=lambda kv: kv[1])[0]


def _extract_feature_names(pairs: List[Tuple[Document, float]], limit: int = 12) -> List[str]:
    """Extract feature names from retrieved chunks (non-hardcoded, parsing-based)."""
    out = []
    seen = set()
    for d, _ in pairs:
        txt = (d.page_content or "")
        for line in txt.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.lower().startswith("feature:"):
                feat = line.split(":", 1)[1].strip()
            elif line.lower().startswith("feature name:"):
                feat = line.split(":", 1)[1].strip()
            else:
                continue
            if feat and feat.lower() not in seen:
                seen.add(feat.lower())
                out.append(feat)
                if len(out) >= limit:
                    return out
    return out


def _diversify_pairs(
    pairs: List[Tuple[Document, float]],
    k: int,
    query: str,
) -> List[Tuple[Document, float]]:
    """
    Reduce 'matrix flooding' without hardcoding feature names:
    - limit repeated (parent_key, chunk_type) combinations
    - ensure at least some definition/limitation chunks when query asks to explain/describe
    """
    if not pairs:
        return []
    k = max(1, int(k))
    q = _safe_lower(query)
    want_defs = any(w in q for w in ("explain", "what is", "meaning", "definition", "describe", "details"))
    # Cap per (parent_key, chunk_type) as a function of k (adaptive, not fixed to doc types)
    cap = max(3, k // 4)
    counts = {}
    selected: List[Tuple[Document, float]] = []
    deferred_defs: List[Tuple[Document, float]] = []
    deferred_lims: List[Tuple[Document, float]] = []
    for item in pairs:
        d, dist = item
        meta = getattr(d, "metadata", {}) or {}
        pk = meta.get("parent_key") or meta.get("doc_id") or ""
        ct = meta.get("chunk_type") or ""
        key = f"{pk}::{ct}"
        if counts.get(key, 0) >= cap:
            # Keep some useful types aside for later
            if ct == "definition":
                deferred_defs.append(item)
            elif ct == "limitation":
                deferred_lims.append(item)
            continue
        counts[key] = counts.get(key, 0) + 1
        selected.append(item)
        if len(selected) >= k:
            break
    # If query asks to explain, ensure definitions are present when available
    if want_defs:
        need_defs = max(1, k // 10)
        have_defs = sum(1 for d, _ in selected if (getattr(d, "metadata", {}) or {}).get("chunk_type") == "definition")
        i = 0
        while have_defs < need_defs and i < len(deferred_defs) and len(selected) < k:
            selected.append(deferred_defs[i])
            have_defs += 1
            i += 1
    # Ensure at least 1 limitation chunk if any exist (helps "why/not supported" questions)
    have_lims = any((getattr(d, "metadata", {}) or {}).get("chunk_type") == "limitation" for d, _ in selected)
    if not have_lims and deferred_lims and len(selected) < k:
        selected.append(deferred_lims[0])
    return selected[:k]


# Email drafting: triggers for intent-based detection (Copilot-style). Toggle override uses ui_mode instead.
EMAIL_DRAFT_TRIGGERS = [
    "write a professional email",
    "draft a professional email",
    "draft the email",
    "draft this email",
    "please draft the email",
    "can you draft the email",
    "polish this email",
    "rewrite this email",
    "make this email professional",
    "help me write an email",
    "rephrase this email",
    "email draft",
    # Refinement phrases (so follow-up messages take the email path; Copilot-style)
    "make the tone more formal",
    "shorten the email",
    "shorten the email content",
    "add a thank-you closing",
    "add a thank-you closing line",
    "make it more concise",
    "add a deadline for response",
    "include a request for confirmation",
    "include a contact for support",
]


def classify_intent(state: RAGState) -> RAGState:
    """Classify query intent: email_draft (toggle or triggers), factual, complex, or procedural."""
    query = (state.get("query") or "").strip()
    state["enhanced_query"] = state.get("enhanced_query") or query

    # 1) Toggle override: user explicitly enabled Email Drafting mode
    if state.get("ui_mode") == "email":
        state["intent"] = "email_draft"
        state["intent_confidence"] = 1.0
        logger.info("[RAG] classify_intent | intent=email_draft | ui_mode=email")
        return state

    # 2) Intent-based: trigger phrases (Copilot-style)
    q_lower = (query or "").strip().lower()
    for trigger in EMAIL_DRAFT_TRIGGERS:
        if trigger in q_lower:
            state["intent"] = "email_draft"
            state["intent_confidence"] = 0.9
            logger.info("[RAG] classify_intent | intent=email_draft | trigger=%s", trigger[:40])
            return state

    # 3) RAG path: factual, complex, or procedural
    intent = "factual"
    confidence = 0.8
    if any(w in q_lower for w in ("how do i", "how to", "steps", "procedure", "walk me")):
        intent = "procedural"
        confidence = 0.7
    elif "?" in query and (query.count("?") > 1 or any(w in q_lower for w in (" and ", " or ", " vs "))):
        intent = "complex"
        confidence = 0.7
    state["intent"] = intent
    state["intent_confidence"] = confidence
    next_node = "expand_query" if intent == "complex" else "decompose_query" if intent == "procedural" else "retrieve_documents"
    logger.info("[RAG] classify_intent | intent=%s | confidence=%.2f | next=%s", intent, confidence, next_node)
    return state


def expand_query(state: RAGState) -> RAGState:
    """Expand query for complex intent (e.g. multi-query)."""
    q = state.get("enhanced_query") or state.get("query") or ""
    # Stub: use single enhanced query; could call LLM to generate sub-queries
    state["expanded_queries"] = [q]
    logger.info("[RAG] expand_query | num_queries=%d | expanded_preview=%s", len(state["expanded_queries"]), [str(x)[:60] for x in state["expanded_queries"]])
    return state


def decompose_query(state: RAGState) -> RAGState:
    """Decompose procedural query into steps/sub-queries."""
    q = state.get("enhanced_query") or state.get("query") or ""
    state["expanded_queries"] = [q]
    logger.info("[RAG] decompose_query | num_queries=%d | expanded_preview=%s", len(state["expanded_queries"]), [str(x)[:60] for x in state["expanded_queries"]])
    return state


def retrieve_documents(state: RAGState) -> RAGState:
    """Weaviate hybrid search (vector + BM25), with optional RBAC filter.
    When the query contains a cloudfuze.com URL, retrieval is restricted to that blog/page only.
    """
    from app.weaviate_retriever import (
        retrieve_from_weaviate,
        extract_blog_url_from_query,
        slug_from_cloudfuze_url,
        extract_jira_ticket_key_from_query,
    )
    from app.weaviate_client import get_weaviate_client
    from app.migration_resolver import detect_migration

    queries = state.get("expanded_queries") or [state.get("enhanced_query") or state.get("query") or ""]
    top_k = state.get("top_k") or 50
    user_ctx = state.get("user_context")
    raw_query = state.get("query") or state.get("enhanced_query") or (queries[0] if queries else "")

    # If user asks about a specific blog URL, restrict retrieval to that page only.
    filter_url = extract_blog_url_from_query(raw_query)
    filter_doc_id = slug_from_cloudfuze_url(filter_url) if filter_url else None

    # If user asks about a specific Jira ticket (e.g. "What is ticket PRI-10521 about?"), restrict to that ticket's chunks.
    jira_ticket_key = extract_jira_ticket_key_from_query(raw_query)
    filter_exact_doc_id = jira_ticket_key if jira_ticket_key else None

    # If user mentions a migration direction (e.g. "Slack to Teams"), restrict SharePointDocs to that migration_type.
    migration_info = detect_migration(raw_query)
    filter_migration_type = migration_info.get("migration_type") if migration_info.get("direction_detected") else None

    logger.info("[RAG] retrieve_start | num_queries=%d | top_k=%d | filter_doc_id=%s | filter_url=%s | filter_exact_doc_id=%s | filter_migration_type=%s | queries_preview=%s",
                len(queries), top_k,
                filter_doc_id[:60] + "..." if filter_doc_id and len(filter_doc_id) > 60 else filter_doc_id,
                filter_url[:60] + "..." if filter_url and len(filter_url) > 60 else filter_url,
                filter_exact_doc_id,
                filter_migration_type,
                [str(q)[:60] for q in (queries[:3] if isinstance(queries, list) else [queries])])

    client = get_weaviate_client()
    if client is None:
        logger.warning("[RAG] retrieve_skip | weaviate_unavailable")
        state["retrieved_docs"] = []
        return state

    # Do not pass user_context so RBAC filter is not applied; many chunks may have
    # empty/missing permissions and would be excluded, causing 0 retrieval results.
    all_pairs: List[Tuple[Document, float]] = []
    for q in queries[:3]:  # cap expanded queries
        pairs = retrieve_from_weaviate(
            query=q,
            k=top_k,
            filter_url=filter_url,
            filter_doc_id=filter_doc_id,
            filter_migration_type=filter_migration_type,
            collection_names=["SharePointDocs", "Blogs", "Transcripts", "JiraTickets"],
        )
        all_pairs.extend(pairs)

    # Merge results across queries while preserving layer-aware ordering:
    # 1) Prefer higher-value chunk layers (feature_capability/limitation) over raw_content
    # 2) Within the same layer, prefer lower vector distance
    # 3) Dedupe by chunk_key (keep best ranked)
    all_pairs.sort(key=lambda x: (-_chunk_type_priority(x[0]), x[1]))
    seen = set()
    deduped: List[Tuple[Document, float]] = []
    for d, dist in all_pairs:
        key = _chunk_key(d)
        if key and key not in seen:
            seen.add(key)
            deduped.append((d, dist))
    # Two-hop retrieval: if query is explanatory and results are dominated by one SharePoint doc_id,
    # fetch definition-style chunks from the same doc to avoid matrix flooding.
    enriched = deduped
    raw_query = state.get("query") or state.get("enhanced_query") or ""
    if _should_two_hop(raw_query):
        dom_doc_id = _dominant_sharepoint_doc_id(deduped[: max(20, top_k)])
        if dom_doc_id:
            feats = _extract_feature_names(deduped[: max(20, top_k)])
            # Use a generic "definition/explanation" query; add feature names if present.
            def_query = "definitions descriptions details meaning explanation"
            if feats:
                def_query += " " + " ".join(feats[:10])
            try:
                extra = retrieve_from_weaviate(
                    query=def_query,
                    k=min(40, top_k),
                    collection_names=["SharePointDocs"],
                    filter_exact_doc_id=dom_doc_id,
                )
                if extra:
                    enriched = deduped + extra
                    enriched.sort(key=lambda x: (-_chunk_type_priority(x[0]), x[1]))
                    # Dedup again
                    seen2 = set()
                    ded2 = []
                    for d2, dist2 in enriched:
                        k2 = _chunk_key(d2)
                        if k2 and k2 not in seen2:
                            seen2.add(k2)
                            ded2.append((d2, dist2))
                    enriched = ded2
            except Exception:
                pass

    diversified = _diversify_pairs(enriched, top_k, raw_query)
    state["retrieved_docs"] = diversified
    pairs = diversified
    scores = [s for _, s in pairs]
    if scores:
        logger.info("[RAG] retrieve_done | num_docs=%d | score_min=%.4f | score_avg=%.4f | score_max=%.4f",
                    len(pairs), min(scores), sum(scores) / len(scores), max(scores))
    else:
        logger.info("[RAG] retrieve_done | num_docs=0")
    return state


def rerank_results(state: RAGState) -> RAGState:
    """Rerank with cross-encoder (e.g. ms-marco-MiniLM); optional MMR."""
    docs = state.get("retrieved_docs") or []
    rerank_k = state.get("rerank_top_k") or 15
    logger.info("[RAG] rerank_start | input_count=%d | rerank_top_k=%d", len(docs), rerank_k)
    if len(docs) <= rerank_k:
        state["reranked_docs"] = docs
        out = docs
    else:
        # Stub: take top rerank_k by score (already sorted by distance)
        state["reranked_docs"] = docs[:rerank_k]
        out = state["reranked_docs"]
    top_scores = [round(s, 4) for _, s in out[:5]] if out else []
    logger.info("[RAG] rerank_done | output_count=%d | top_scores=%s", len(out), top_scores)
    return state


# Minimum retrieval sufficiency (RAG-wide): refuse to answer when below these.
MIN_DOCS_FOR_SUFFICIENCY = 2
MIN_CONTEXT_TOKENS_FOR_SUFFICIENCY = 250


def _retrieval_is_sufficient(docs: List[Tuple[Document, float]]) -> bool:
    """Return True if retrieval has enough docs and context tokens to attempt generation (RAG-wide)."""
    if not docs or len(docs) < MIN_DOCS_FOR_SUFFICIENCY:
        return False
    total_tokens = 0
    for d, _ in docs:
        total_tokens += len((d.page_content or "").split())
    return total_tokens >= MIN_CONTEXT_TOKENS_FOR_SUFFICIENCY


def validate_context(state: RAGState) -> RAGState:
    """CRAG validator: relevance, coverage, diversity, quality_score, corrective_action.
    Sets no_sufficient_context for RAG-wide refuse path when retrieval is insufficient."""
    docs = state.get("reranked_docs") or state.get("retrieved_docs") or []
    query = state.get("enhanced_query") or state.get("query") or ""

    issues: List[str] = []
    if not docs:
        quality = 0.0
        coverage = False
        diversity = 0.0
        corrective = "expand_topk"
        issues.append("no_documents")
        state["no_sufficient_context"] = True
    else:
        scores = [s for _, s in docs]
        avg_score = sum(scores) / len(scores) if scores else 0.0
        quality = min(1.0, 1.0 - avg_score) if isinstance(scores[0], (int, float)) else 0.7
        coverage = len(docs) >= 3
        diversity = 0.8 if len(set(d.metadata.get("source_type", "") for d, _ in docs)) > 1 else 0.5
        corrective = "none" if (quality >= 0.5 and coverage) else "expand_topk"
        sufficient = _retrieval_is_sufficient(docs)
        state["no_sufficient_context"] = not sufficient
        if not sufficient:
            issues.append("insufficient_context")

    state["validation_result"] = ValidationResult(
        quality_score=quality,
        relevance_scores=[s for _, s in docs],
        coverage_sufficient=coverage,
        diversity_score=diversity,
        issues=issues,
        corrective_action=corrective,
    )
    state["corrective_action"] = corrective
    logger.info("[RAG] validate | quality_score=%.2f | coverage=%s | diversity=%.2f | corrective=%s | retry_count=%s | no_sufficient_context=%s",
                quality, coverage, diversity, corrective, state.get("retry_count"), state.get("no_sufficient_context"))
    return state


def apply_corrective_action(state: RAGState) -> RAGState:
    """Apply CRAG corrective action and prepare for retry (e.g. expand top_k)."""
    retry = state.get("retry_count") or 0
    state["retry_count"] = retry + 1
    top_k = state.get("top_k") or 50
    state["top_k"] = min(150, top_k + 30)
    logger.info("[RAG] corrective_action | retry_count=%d | new_top_k=%d", state["retry_count"], state["top_k"])
    return state


# Fixed disclaimer when retrieval is insufficient (RAG-wide; no LLM call).
REFUSE_RESPONSE_MESSAGE = (
    "I don't have sufficient information in our internal knowledge base to answer this accurately. "
    "Please rephrase or specify the document/source you're interested in."
)


def refuse_response(state: RAGState) -> RAGState:
    """Set final_response to disclaimer when retrieval is insufficient (RAG-wide). No LLM call."""
    state["final_response"] = REFUSE_RESPONSE_MESSAGE
    logger.info("[RAG] refuse_response | insufficient retrieval, returning disclaimer")
    return state


def compress_context(state: RAGState) -> RAGState:
    """Compress context to token budget."""
    docs = state.get("reranked_docs") or state.get("retrieved_docs") or []
    budget = state.get("context_token_count") or DEFAULT_CONTEXT_TOKEN_BUDGET

    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
    except Exception:
        enc = None

    parts: List[str] = []
    used = 0
    for d, _ in docs:
        if enc:
            n = len(enc.encode(d.page_content))
        else:
            n = len(d.page_content) // 4
        if used + n > budget:
            break
        parts.append(d.page_content)
        used += n

    state["compressed_context"] = "\n\n".join(parts)
    state["context_token_count"] = used
    logger.info("[RAG] compress_context | budget=%d | used_tokens=%d | num_chunks=%d", budget, used, len(parts))
    return state


# Global rule appended to system message (RAG-wide): only cite retrieved sources.
CITE_ONLY_FROM_CONTEXT_RULE = (
    "IMPORTANT: Only cite sources that appear in the provided context. "
    "Do not invent or reference any document names, ticket IDs, URLs, transcript references, "
    "or other sources that were not retrieved."
)


def generate_email_response(state: RAGState) -> RAGState:
    """Generate polished email from user draft. No RAG: no context, no citations."""
    from app.llm_factory import get_llm
    from langchain_core.messages import SystemMessage, HumanMessage

    from config import EMAIL_DRAFT_SYSTEM_PROMPT

    query = state.get("enhanced_query") or state.get("query") or ""
    logger.info("[RAG] generate_email_response | query_len=%d", len(query or ""))
    llm = get_llm(temperature=0.2, max_tokens=1500)
    resp = llm.invoke([SystemMessage(content=EMAIL_DRAFT_SYSTEM_PROMPT), HumanMessage(content=query)])
    state["final_response"] = resp.content if hasattr(resp, "content") else str(resp)
    # Ensure no docs so extract_citations yields empty list
    state.setdefault("retrieved_docs", [])
    state.setdefault("reranked_docs", [])
    logger.info("[RAG] generate_email_response | response_len=%d", len(state["final_response"]))
    return state


def generate_response(state: RAGState) -> RAGState:
    """LLM generation with system prompt + context + query.
    Appends cite-only-from-context rule (RAG-wide) and optional source-specific notes."""
    from app.llm_factory import get_llm
    from langchain_core.messages import SystemMessage, HumanMessage

    ctx = state.get("compressed_context") or ""
    query = state.get("enhanced_query") or state.get("query") or ""
    from config import SYSTEM_PROMPT

    sys = SYSTEM_PROMPT or "Answer based on the context."
    # RAG-wide: always append cite-only-from-context rule
    sys = (sys.rstrip() + "\n\n" + CITE_ONLY_FROM_CONTEXT_RULE).strip()
    # Optional: source-specific notes when a source type is absent (reduces temptation)
    docs = state.get("reranked_docs") or state.get("retrieved_docs") or []
    source_types = {((getattr(d, "metadata", None) or {}).get("source_type") or "") for d, _ in docs}
    if "jira" not in source_types:
        sys = sys + "\n\nNo Jira tickets were retrieved; do not reference any Jira ticket IDs."
    msg = f"Context:\n{ctx}\n\nQuestion: {query}"
    logger.info("[RAG] generate_start | context_len=%d | query_len=%d", len(ctx), len(query))
    llm = get_llm(temperature=0.1, max_tokens=1500)
    resp = llm.invoke([SystemMessage(content=sys), HumanMessage(content=msg)])
    state["final_response"] = resp.content if hasattr(resp, "content") else str(resp)
    logger.info("[RAG] generate_done | response_len=%d", len(state["final_response"]))
    return state


def extract_citations(state: RAGState) -> RAGState:
    """Extract citations from model output and/or chunk_key/source metadata."""
    docs = state.get("reranked_docs") or state.get("retrieved_docs") or []
    response = state.get("final_response") or ""
    citations = []
    chunk_keys = []
    for d, _ in docs[:10]:
        meta = getattr(d, "metadata", {}) or {}
        chunk_key = meta.get("chunk_key") or meta.get("source_ref") or ""
        if chunk_key:
            chunk_keys.append(chunk_key)
        title = meta.get("title") or meta.get("source_ref") or "Source"
        citations.append({"chunk_key": chunk_key, "title": title})
    state["citations"] = citations
    state["chunk_keys_cited"] = chunk_keys
    logger.info("[RAG] extract_citations | citations=%d | chunk_keys=%d", len(citations), len(chunk_keys))
    return state


