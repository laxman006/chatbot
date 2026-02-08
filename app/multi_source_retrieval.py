"""
Utilities for merging and deduplicating retrieval results across sources.

Placed under `app/` so type checkers resolve imports consistently.
"""

from __future__ import annotations

import hashlib
from typing import Dict, Iterable, List, Tuple

from langchain_core.documents import Document


Pair = Tuple[Document, float]


def merge_source_results(results_by_source: Dict[str, List[Pair]]) -> List[Pair]:
    """Merge results from multiple sources into a single list."""
    merged: List[Pair] = []
    for _, pairs in (results_by_source or {}).items():
        merged.extend(pairs or [])
    return merged


def _content_fingerprint(doc: Document) -> str:
    """Prefer chunk_key; otherwise hash content."""
    meta = getattr(doc, "metadata", None) or {}
    key = (meta.get("chunk_key") or "").strip()
    if key:
        return key
    content = (getattr(doc, "page_content", "") or "").strip()
    if not content:
        return ""
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def deduplicate_by_content(pairs: Iterable[Pair]) -> List[Pair]:
    """Deduplicate ranked pairs by fingerprint; keep first occurrence."""
    out: List[Pair] = []
    seen = set()
    for doc, score in pairs or []:
        fp = _content_fingerprint(doc)
        if fp and fp in seen:
            continue
        if fp:
            seen.add(fp)
        out.append((doc, score))
    return out

