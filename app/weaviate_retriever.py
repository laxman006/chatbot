"""
Weaviate-only retriever for RAG.

Searches Weaviate collections using vector similarity (external embeddings).
Returns results in the same (Document, score) format used by the chat endpoints.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import List, Tuple, Optional, Any
from urllib.parse import urlparse

from langchain_core.documents import Document
from weaviate.classes.query import Filter, MetadataQuery

from app.weaviate_client import get_weaviate_client
from app.weaviate_schema import COLLECTIONS

logger = logging.getLogger(__name__)

# Match cloudfuze.com blog/article URLs for "answer from this page" detection
_CLOUDFUZE_URL_RE = re.compile(
    r"https?://(?:www\.)?cloudfuze\.com/[^\s)\]\">]+",
    re.IGNORECASE,
)


def extract_blog_url_from_query(query: str) -> Optional[str]:
    """
    If the user's message contains a cloudfuze.com URL, return it (normalized).
    Used to restrict retrieval to that blog/article so the answer is grounded in it only.
    """
    if not query or not isinstance(query, str):
        return None
    m = _CLOUDFUZE_URL_RE.search(query)
    if not m:
        return None
    url = m.group(0).strip().rstrip("/")
    return url if url else None


def slug_from_cloudfuze_url(url: str) -> Optional[str]:
    """
    Extract the path slug from a cloudfuze.com URL. Blogs use doc_id = slug.
    Prefer filtering by doc_id (slug) over url: slugs are stable even if URLs change.
    """
    if not url or not isinstance(url, str):
        return None
    if "cloudfuze.com" not in url.lower():
        return None
    parsed = urlparse(url.strip())
    path = (parsed.path or "").strip("/")
    segments = [s for s in path.split("/") if s]
    return segments[-1] if segments else None


# Jira ticket key: PROJECTKEY-NUMBER (e.g. PRI-10521, PROJ-123, CFITS-456)
_JIRA_TICKET_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,10}-\d+)\b", re.IGNORECASE)


def extract_jira_ticket_key_from_query(query: str) -> Optional[str]:
    """
    If the user's message contains a Jira ticket key (e.g. PRI-10521, PROJ-123),
    return it in canonical form (uppercase). Used to restrict retrieval to that ticket's chunks.
    """
    if not query or not isinstance(query, str):
        return None
    m = _JIRA_TICKET_KEY_RE.search(query)
    if not m:
        return None
    return (m.group(1) or "").strip().upper()

# Layer-aware retrieval: prefer higher semantic chunks (never answer from raw_content first)
CHUNK_TYPE_PRIORITY = {
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
    """Return priority for layer-aware sort (higher = prefer)."""
    if doc is None:
        return _DEFAULT_CHUNK_PRIORITY
    ct = (getattr(doc, "metadata", None) or {}).get("chunk_type") or ""
    return CHUNK_TYPE_PRIORITY.get(ct, _DEFAULT_CHUNK_PRIORITY)


# Lazy singleton for embeddings (same model as ingestion: text-embedding-3-small)
_embedding_model = None


def _get_embedding_model():
    """Lazy init OpenAI embeddings for query vector (text-embedding-3-small)."""
    global _embedding_model
    if _embedding_model is None:
        from langchain_openai import OpenAIEmbeddings
        _embedding_model = OpenAIEmbeddings(model="text-embedding-3-small")
    return _embedding_model


def _weaviate_object_to_document(obj, distance: float) -> Tuple[Document, float]:
    """Map a Weaviate object to LangChain Document and distance (lower = better)."""
    props = obj.properties or {}
    try:
        metadata = dict(props) if hasattr(props, "items") else {}
    except Exception:
        metadata = {}
    content = metadata.get("content", "")
    if not content and hasattr(props, "get"):
        content = props.get("content", "")
    return (Document(page_content=content or "", metadata=metadata), distance)


def _score_to_distance(meta: Any) -> float:
    """
    Normalize Weaviate hybrid/bm25 scoring into the same "distance-like" scale where lower is better.

    - near_vector returns metadata.distance (lower = better)
    - hybrid often returns metadata.score (higher = better) depending on SDK/server versions
    We convert score -> distance using (1 - score) when score is in [0,1], otherwise 1/(1+score).
    """
    if meta is None:
        return 0.0
    # Prefer true vector distance when present
    dist = getattr(meta, "distance", None)
    if isinstance(dist, (int, float)):
        return float(dist)
    score = getattr(meta, "score", None)
    if isinstance(score, (int, float)):
        s = float(score)
        if 0.0 <= s <= 1.0:
            return 1.0 - s
        if s >= 0:
            return 1.0 / (1.0 + s)
    # Fallback: neutral
    return 0.0


def _doc_identity_for_log(collection_name: str, metadata: dict) -> str:
    """
    Build a short document-identity string for retrieval logging.
    Used so backend logs show which SharePoint doc / transcript / blog was retrieved.
    """
    meta = metadata or {}
    doc_id = (meta.get("doc_id") or meta.get("source_ref") or "").strip()
    title = (meta.get("title") or "").strip()[:60]
    if collection_name == "SharePointDocs":
        site = (meta.get("site_name") or "").strip()[:25]
        folder = (meta.get("folder_name") or "").strip()[:25]
        parts = [p for p in (doc_id, title, site, folder) if p]
        return " | ".join(parts) if parts else "(no meta)"
    if collection_name == "Transcripts":
        meeting_id = (meta.get("meeting_id") or doc_id or "").strip()[:30]
        meeting_title = (meta.get("meeting_title") or title or "").strip()[:50]
        source = (meta.get("transcript_source") or "").strip()[:20]
        parts = [p for p in (meeting_id, meeting_title, source) if p]
        return " | ".join(parts) if parts else "(no meta)"
    if collection_name == "Blogs":
        slug = (meta.get("doc_id") or meta.get("post_slug") or "").strip()[:40]
        post_title = (meta.get("title") or meta.get("post_title") or "").strip()[:50]
        parts = [p for p in (slug, post_title) if p]
        return " | ".join(parts) if parts else "(no meta)"
    # JiraTickets, Spreadsheets, EmailThreads, etc.
    if doc_id or title:
        return (doc_id or "")[:40] + (" | " + title if title else "")
    return "(no meta)"


def retrieve_from_weaviate(
    query: str,
    k: int = 50,
    collection_names: Optional[List[str]] = None,
    filter_url: Optional[str] = None,
    filter_doc_id: Optional[str] = None,
    filter_exact_doc_id: Optional[str] = None,
    filter_migration_type: Optional[str] = None,
    user_context: Optional[Any] = None,
    include_summary_chunks: bool = True,
    summary_k: int = 5,
) -> List[Tuple[Document, float]]:
    """
    Retrieve documents from Weaviate using vector search (Weaviate-only path).

    Embeds the query with text-embedding-3-small, runs near_vector on each
    collection, merges and sorts by distance, returns top k.

    Args:
        query: User query string.
        k: Maximum number of (doc, score) pairs to return.
        collection_names: Collections to search. Defaults to all in COLLECTIONS.
        filter_url: If set (and filter_doc_id not set), restrict to chunks with
            metadata url equal to this when querying Blogs. Fallback when slug not available.
        filter_doc_id: If set, restrict to chunks with doc_id equal to this (e.g. blog slug).
            Preferred over filter_url for Blogs—slugs are stable even if URLs change.
        filter_migration_type: If set, restrict SharePointDocs to chunks with this canonical
            migration_type (e.g. slack__TO__teams). Use detect_migration(query)["migration_type"] when direction_detected.
        user_context: Optional app.rbac.UserContext; when set, RBAC filter is applied so only
            chunks whose permissions contain at least one of the user's groups are returned.
        include_summary_chunks: If True, also query chunk_role=doc_summary (and equivalents) so
            high-level summary chunks can surface for faster answers.
        summary_k: Max summary chunks to fetch per collection when include_summary_chunks is True.

    Returns:
        List of (Document, distance) tuples, sorted by distance ascending.
        Empty list if Weaviate is unavailable or no collections exist.
    """
    # #region agent log
    _log_path = r"c:\Users\ChaitanyaMalle\Slack2teams-2-confident-chatbot\.cursor\debug.log"
    _ts = int(time.time() * 1000)
    logger.info("[RETRIEVAL] >>> started | query=%s | k=%s | collection_names_arg=%s", (query or "")[:120], k, collection_names)
    try:
        with open(_log_path, "a", encoding="utf-8") as _f:
            _f.write(json.dumps({"timestamp": _ts, "location": "weaviate_retriever.py:retrieve_from_weaviate:entry", "message": "retrieval started", "data": {"query_preview": (query or "")[:200], "k": k, "collection_names_arg": collection_names}, "sessionId": "debug-session", "hypothesisId": "H1"}) + "\n")
    except Exception:
        pass
    # #endregion

    client = get_weaviate_client()
    if client is None:
        logger.warning("[WEAVIATE_RETRIEVER] Weaviate client unavailable")
        return []

    # When user asks "from this blog" (filter_doc_id or filter_url), search only Blogs.
    # NOTE: filter_exact_doc_id is different: it is a generic doc_id filter (used for SharePoint two-hop retrieval).
    if filter_doc_id or filter_url:
        names = ["Blogs"]
        if filter_doc_id:
            logger.info("[RETRIEVAL] filter_doc_id set → restricting to Blogs doc_id=%s", filter_doc_id[:80] + "..." if len(filter_doc_id) > 80 else filter_doc_id)
        else:
            logger.info("[RETRIEVAL] filter_url set → restricting to Blogs url=%s", (filter_url or "")[:80] + "..." if len(filter_url or "") > 80 else filter_url)
    else:
        names = collection_names or COLLECTIONS
    # #region agent log
    logger.info("[RETRIEVAL] collections to query: %s", names)
    try:
        with open(_log_path, "a", encoding="utf-8") as _f:
            _f.write(json.dumps({"timestamp": int(time.time() * 1000), "location": "weaviate_retriever.py:retrieve_from_weaviate:resolved", "message": "collections to query", "data": {"resolved_collections": names}, "sessionId": "debug-session", "hypothesisId": "H2"}) + "\n")
    except Exception:
        pass
    # #endregion

    model = _get_embedding_model()
    try:
        query_vector = model.embed_query(query)
    except Exception as e:
        logger.error(f"[WEAVIATE_RETRIEVER] Embedding failed: {e}")
        return []

    all_results_with_src: List[Tuple[Document, float, str]] = []
    per_collection = max(10, (k + len(names) - 1) // len(names))

    for col_name in names:
        try:
            if not client.collections.exists(col_name):
                # #region agent log
                logger.info("[RETRIEVAL] collection missing (skipped): %s", col_name)
                try:
                    with open(_log_path, "a", encoding="utf-8") as _f:
                        _f.write(json.dumps({"timestamp": int(time.time() * 1000), "location": "weaviate_retriever.py:retrieve_from_weaviate:collection_skip", "message": "collection missing", "data": {"collection": col_name}, "sessionId": "debug-session", "hypothesisId": "H3"}) + "\n")
                except Exception:
                    pass
                # #endregion
                continue
            coll = client.collections.get(col_name)
            # Restrict to chunks from this blog when user asks about a specific page.
            # Prefer doc_id (slug) over url: slugs are stable even if URLs change.
            doc_filter = None
            if col_name == "Blogs":
                if filter_doc_id:
                    doc_filter = Filter.by_property("doc_id").equal(filter_doc_id)
                elif filter_url:
                    doc_filter = Filter.by_property("url").equal(filter_url)
            elif filter_exact_doc_id:
                # Generic doc_id filter across non-blog collections (e.g. SharePointDocs, JiraTickets, etc.)
                doc_filter = Filter.by_property("doc_id").equal(filter_exact_doc_id)
            elif col_name == "SharePointDocs" and filter_migration_type:
                doc_filter = Filter.by_property("migration_type").equal(filter_migration_type)
                logger.info("[RETRIEVAL] filter_migration_type=%s → restricting SharePointDocs", filter_migration_type)
            # RBAC: restrict to chunks the user is allowed to see
            rbac_filter = None
            if user_context is not None and hasattr(user_context, "group_ids"):
                from app.rbac import PermissionsManager
                rbac_filter = PermissionsManager().filter_for_user(user_context)
            
            # Parent-Based Attachment: Exclude images from normal vector search
            chunk_type_filter = None
            if col_name == "SharePointDocs":
                chunk_type_filter = Filter.by_property("chunk_type").not_equal("image_context")
            
            # Jira: prefer resolution/steps chunks for "how to fix" queries, error chunks for "what error"
            jira_chunk_type_filter = None
            if col_name == "JiraTickets":
                q_lower = (query or "").lower()
                if any(phrase in q_lower for phrase in ("how to fix", "how do i fix", "resolve", "resolution", "steps", "workaround", "fix for", "solution for", "how was this resolved", "how to resolve")):
                    jira_chunk_type_filter = (
                        Filter.by_property("ticket_chunk_type").equal("resolution")
                        | Filter.by_property("ticket_chunk_type").equal("steps")
                    )
                    logger.info("[RETRIEVAL] JiraTickets → restricting to ticket_chunk_type in (resolution, steps)")
                elif any(phrase in q_lower for phrase in ("error", "exception", "what error", "which error")):
                    jira_chunk_type_filter = Filter.by_property("ticket_chunk_type").equal("error")
                    logger.info("[RETRIEVAL] JiraTickets → restricting to ticket_chunk_type=error")
            
            combined_filter = None
            # Combine doc_filter, rbac_filter, chunk_type_filter, and jira_chunk_type_filter
            filters_to_combine = [f for f in (doc_filter, rbac_filter, chunk_type_filter, jira_chunk_type_filter) if f is not None]
            if len(filters_to_combine) == 1:
                combined_filter = filters_to_combine[0]
            elif len(filters_to_combine) > 1:
                combined_filter = filters_to_combine[0]
                for f in filters_to_combine[1:]:
                    combined_filter = combined_filter & f
            kwargs = dict(
                near_vector=query_vector,
                limit=per_collection,
                return_metadata=MetadataQuery(distance=True),
            )
            if combined_filter is not None:
                kwargs["filters"] = combined_filter
            resp = coll.query.near_vector(**kwargs)
            # If filtering by url and 0 results, try with trailing slash (WP often stores that)
            if filter_url and not filter_doc_id and col_name == "Blogs" and len(resp.objects) == 0 and not (filter_url or "").endswith("/"):
                retry_filter = Filter.by_property("url").equal(filter_url + "/")
                if rbac_filter is not None:
                    retry_filter = retry_filter & rbac_filter
                kwargs["filters"] = retry_filter
                resp = coll.query.near_vector(**kwargs)
            n = 0
            collection_doc_identities: List[str] = []
            for o in resp.objects:
                d = _score_to_distance(getattr(o, "metadata", None))
                doc, d = _weaviate_object_to_document(o, d)
                all_results_with_src.append((doc, d, col_name))
                collection_doc_identities.append(_doc_identity_for_log(col_name, doc.metadata))
                n += 1

            # Hybrid retrieval (BM25 + vector) to improve recall for exact terms in tables/definitions.
            # This is not hardcoded for any doc type: it's always attempted and merged with vector results.
            try:
                from config import WEAVIATE_HYBRID_ALPHA
                alpha = float(WEAVIATE_HYBRID_ALPHA)
            except Exception:
                alpha = 0.7
            try:
                hybrid_kwargs = dict(
                    query=query,
                    alpha=alpha,
                    limit=per_collection,
                    return_metadata=MetadataQuery(score=True, distance=True),
                )
                if combined_filter is not None:
                    hybrid_kwargs["filters"] = combined_filter
                # Some weaviate-client versions allow passing vector=...; we try it when accepted.
                try:
                    hresp = coll.query.hybrid(vector=query_vector, **hybrid_kwargs)
                except TypeError:
                    hresp = coll.query.hybrid(**hybrid_kwargs)
                for o in getattr(hresp, "objects", []) or []:
                    d2 = _score_to_distance(getattr(o, "metadata", None))
                    doc2, d2 = _weaviate_object_to_document(o, d2)
                    all_results_with_src.append((doc2, d2, col_name))
            except Exception as e:
                logger.debug("[RETRIEVAL] hybrid query failed for %s: %s", col_name, e)
            # #region agent log
            logger.info("[RETRIEVAL] %s -> %d docs", col_name, n)
            if col_name in ("SharePointDocs", "Transcripts") and collection_doc_identities:
                for idx, ident in enumerate(collection_doc_identities[:5], 1):
                    logger.info("[RETRIEVAL]     %s #%d: %s", col_name, idx, ident)
                if len(collection_doc_identities) > 5:
                    logger.info("[RETRIEVAL]     ... and %d more %s", len(collection_doc_identities) - 5, col_name)
            try:
                with open(_log_path, "a", encoding="utf-8") as _f:
                    _f.write(json.dumps({"timestamp": int(time.time() * 1000), "location": "weaviate_retriever.py:retrieve_from_weaviate:per_collection", "message": "results from collection", "data": {"collection": col_name, "count": n, "doc_identities": collection_doc_identities[:10]}, "sessionId": "debug-session", "hypothesisId": "H4"}) + "\n")
            except Exception:
                pass
            # #endregion
            # Two-step: also fetch summary chunks (doc_summary / ticket_summary / etc.) for high-level answers
            if include_summary_chunks and summary_k > 0:
                try:
                    from app.weaviate_schema import CHUNK_ROLE_DOC_SUMMARY, CHUNK_ROLE_TICKET_SUMMARY, CHUNK_ROLE_SHEET_SUMMARY, CHUNK_ROLE_THREAD_SUMMARY, CHUNK_ROLE_MEETING_SUMMARY
                    summary_roles = {
                        "SharePointDocs": CHUNK_ROLE_DOC_SUMMARY,
                        "Blogs": CHUNK_ROLE_DOC_SUMMARY,
                        "JiraTickets": CHUNK_ROLE_TICKET_SUMMARY,
                        "Spreadsheets": CHUNK_ROLE_SHEET_SUMMARY,
                        "EmailThreads": CHUNK_ROLE_THREAD_SUMMARY,
                        "Transcripts": CHUNK_ROLE_MEETING_SUMMARY,
                    }
                    role = summary_roles.get(col_name, CHUNK_ROLE_DOC_SUMMARY)
                    summary_filter = Filter.by_property("chunk_role").equal(role)
                    if combined_filter is not None:
                        summary_filter = summary_filter & combined_filter
                    sum_resp = coll.query.near_vector(
                        near_vector=query_vector,
                        limit=min(summary_k, per_collection),
                        return_metadata=MetadataQuery(distance=True),
                        filters=summary_filter,
                    )
                    for o in sum_resp.objects:
                        dist = o.metadata.distance if o.metadata and hasattr(o.metadata, "distance") else 0.0
                        doc, d = _weaviate_object_to_document(o, dist)
                        all_results_with_src.append((doc, d, col_name))
                except Exception as e:
                    logger.debug("[RETRIEVAL] summary chunk query failed for %s: %s", col_name, e)
        except Exception as e:
            logger.warning(f"[WEAVIATE_RETRIEVER] Error querying {col_name}: {e}")
            continue

    # Sort by chunk_type priority (higher first), then by distance (lower first)
    all_results_with_src.sort(key=lambda x: (-_chunk_type_priority(x[0]), x[1]))
    # Dedupe by chunk_key (keep first = best distance)
    seen_keys = set()
    deduped = []
    for item in all_results_with_src:
        doc, dist, col = item
        key = doc.metadata.get("chunk_key") or (f"{doc.metadata.get('parent_key', '')}#{doc.metadata.get('chunk_id', '')}")
        if key not in seen_keys:
            seen_keys.add(key)
            deduped.append(item)
    all_results_with_src = deduped
    top_with_src = all_results_with_src[:k]
    out_pairs = [(d, dist) for d, dist, _ in top_with_src]

    # #region agent log
    _content_debug_len = 800  # full chunk for debugging (Feature, Supported, Description, Source | Sheet)
    try:
        previews = []
        for i, (doc, dist, col_name) in enumerate(top_with_src[:10]):
            doc_ident = _doc_identity_for_log(col_name, doc.metadata)
            full_content = (doc.page_content or "")
            previews.append({
                "rank": i + 1,
                "distance": dist,
                "collection": col_name,
                "doc_identity": doc_ident,
                "content_preview": full_content[:250],
                "content_full": full_content[: _content_debug_len] + ("..." if len(full_content) > _content_debug_len else ""),
            })
        logger.info("[RETRIEVAL] <<< finished | total_returned=%d", len(out_pairs))
        for i, (doc, dist, col_name) in enumerate(top_with_src[:10], 1):
            doc_ident = _doc_identity_for_log(col_name, doc.metadata)
            full_content = (doc.page_content or "")[:_content_debug_len]
            if len(doc.page_content or "") > _content_debug_len:
                full_content += "..."
            logger.info("[RETRIEVAL]   #%d [%s] dist=%.4f | %s", i, col_name, dist, doc_ident)
            for line in full_content.splitlines():
                logger.info("[RETRIEVAL]       %s", line.strip() or " ")
        with open(_log_path, "a", encoding="utf-8") as _f:
            _f.write(json.dumps({"timestamp": int(time.time() * 1000), "location": "weaviate_retriever.py:retrieve_from_weaviate:exit", "message": "retrieval finished", "data": {"total_returned": len(out_pairs), "top_docs": previews}, "sessionId": "debug-session", "hypothesisId": "H5"}) + "\n")
    except Exception:
        pass
    # #endregion

    return out_pairs


def retrieve_from_weaviate_collection(
    query: str,
    collection_name: str,
    k: int = 20,
) -> List[Tuple[Document, float]]:
    """
    Retrieve from a single Weaviate collection (for source-specific retrieval).

    Args:
        query: User query string.
        collection_name: Weaviate collection name (e.g. "Transcripts", "SharePointDocs").
        k: Max results to return.

    Returns:
        List of (Document, distance) tuples.
    """
    return retrieve_from_weaviate(query, k=k, collection_names=[collection_name])


# Routing plan source key -> Weaviate collection name
_ROUTING_SOURCE_TO_COLLECTION = {
    "blog": "Blogs",
    "sharepoint": "SharePointDocs",
    "jira": "JiraTickets",
    "transcripts": "Transcripts",
    "pdfs": "SharePointDocs",
    "excel": "Spreadsheets",
}


def weaviate_multi_source_retrieve(
    query: str,
    routing_plan: dict,
    enable_deduplication: bool = True,
    always_include_limitations: bool = True,
) -> List[Tuple[Document, float]]:
    """
    Multi-source retrieval using only Weaviate collections (replacement for
    intelligent_multi_source_retrieve when using Weaviate-only backend).

    Args:
        query: User query.
        routing_plan: Plan with "sources" dict, e.g. {"blog": {"k": 20}, "jira": {"k": 15}, ...}.
        enable_deduplication: If True, deduplicate by content/key.
        always_include_limitations: If True, always add limitations-style docs from SharePointDocs.

    Returns:
        List of (Document, distance) tuples, merged and optionally deduplicated.
    """
    # Optional import - handle gracefully if module doesn't exist
    try:
        from app.multi_source_retrieval import merge_source_results, deduplicate_by_content
    except ImportError:
        logger.warning("[WEAVIATE_RETRIEVER] multi_source_retrieval module not available, using simple merge")
        # Fallback: simple merge without deduplication
        def merge_source_results(results_by_source):
            merged = []
            for docs in results_by_source.values():
                merged.extend(docs)
            return merged
        def deduplicate_by_content(docs):
            # Simple dedup by content hash
            seen = set()
            unique = []
            for doc, dist in docs:
                content = doc.page_content[:100] if doc.page_content else ""
                if content not in seen:
                    seen.add(content)
                    unique.append((doc, dist))
            return unique

    if get_weaviate_client() is None:
        logger.warning("[WEAVIATE_RETRIEVER] Weaviate unavailable for multi-source retrieve")
        return []

    results_by_source: dict = {}
    sources_plan = routing_plan.get("sources", {})

    if always_include_limitations:
        lim = retrieve_from_weaviate(
            "limitations supported features not supported",
            k=4,
            collection_names=["SharePointDocs"],
        )
        if lim:
            results_by_source["limitations"] = lim
            logger.info("[WEAVIATE_RETRIEVER] Pinned %d limitations-style docs", len(lim))

    for source_key, col_name in _ROUTING_SOURCE_TO_COLLECTION.items():
        cfg = sources_plan.get(source_key, {})
        k = cfg.get("k", 0) if isinstance(cfg, dict) else 0
        if k <= 0:
            continue
        try:
            docs = retrieve_from_weaviate_collection(query, col_name, k=k)
            if docs:
                results_by_source[source_key] = docs
                logger.info("[WEAVIATE_RETRIEVER] %s: %d docs", source_key, len(docs))
        except Exception as e:
            logger.warning("[WEAVIATE_RETRIEVER] %s failed: %s", source_key, e)

    merged = merge_source_results(results_by_source)
    if enable_deduplication:
        merged = deduplicate_by_content(merged)
    return merged


def get_transcript_keywords_from_weaviate() -> set:
    """
    Extract participant/customer/meeting keywords from Transcripts collection
    for transcript-query detection.
    """
    try:
        pairs = retrieve_from_weaviate(
            "transcript demo meeting customer participants",
            k=300,
            collection_names=["Transcripts"],
        )
        keywords: set = set()
        for doc, _ in pairs:
            meta = getattr(doc, "metadata", None) or {}
            for key in ("participants", "customer", "meeting_title"):
                val = meta.get(key, "")
                if not val:
                    continue
                for part in str(val).split(","):
                    word = part.strip()
                    if word:
                        keywords.add(word.lower())
                    for w in word.split():
                        if len(w) > 2:
                            keywords.add(w.lower())
            title = meta.get("meeting_title", "")
            if title:
                for w in str(title).split():
                    if len(w) > 3:
                        keywords.add(w.lower())
        return keywords
    except Exception as e:
        logger.warning("[WEAVIATE_RETRIEVER] get_transcript_keywords failed: %s", e)
        return set()


# Image fetch helpers removed: image ingestion is disabled; only document content is ingested.
