# -*- coding: utf-8 -*-
"""
Base chunker interface for the antigravity ingestion pipeline.
"""

from abc import ABC, abstractmethod
from typing import List

from langchain_core.documents import Document


class BaseChunker(ABC):
    """Abstract base for all chunkers. Supports token counting and overlap."""

    @abstractmethod
    def chunk_documents(self, documents: List[Document]) -> List[Document]:
        """Split documents into chunks. Returns new Documents with chunk content and metadata."""
        pass

    def count_tokens(self, text: str) -> int:
        """Return token count for text. Override for accurate counting."""
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception:
            return max(1, int(len(text) / 5))
