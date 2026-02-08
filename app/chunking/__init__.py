# -*- coding: utf-8 -*-
"""
Chunking package for antigravity ingestion.

Provides:
- BaseChunker: abstract base
- RecursiveChunker: recursive character splitter with token size/overlap
- MarkdownAwareChunker: heading-aware then recursive for large sections
- get_chunker(kind): factory
"""

from app.chunking.base import BaseChunker
from app.chunking.recursive import RecursiveChunker
from app.chunking.markdown_aware import MarkdownAwareChunker

RECURSIVE = "recursive"
MARKDOWN_AWARE = "markdown_aware"


def get_chunker(
    kind: str = RECURSIVE,
    target_tokens: int = 800,
    overlap_tokens: int = 200,
    min_tokens: int = 150,
) -> BaseChunker:
    """Return a chunker by kind. Default recursive; use markdown_aware for md-heavy content."""
    if kind == MARKDOWN_AWARE:
        return MarkdownAwareChunker(
            target_tokens=target_tokens,
            overlap_tokens=overlap_tokens,
            min_tokens=min_tokens,
        )
    return RecursiveChunker(
        target_tokens=target_tokens,
        overlap_tokens=overlap_tokens,
    )


__all__ = [
    "BaseChunker",
    "RecursiveChunker",
    "MarkdownAwareChunker",
    "get_chunker",
    "RECURSIVE",
    "MARKDOWN_AWARE",
]
