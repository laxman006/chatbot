# -*- coding: utf-8 -*-
"""
Recursive character text splitter with token-based size and overlap.
"""

from typing import List

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.chunking.base import BaseChunker

# ~5.5 chars per token for English
CHARS_PER_TOKEN = 5.5


class RecursiveChunker(BaseChunker):
    """
    Recursive chunker using LangChain's RecursiveCharacterTextSplitter
    with token-based chunk_size and chunk_overlap.
    """

    def __init__(
        self,
        target_tokens: int = 800,
        overlap_tokens: int = 200,
        length_function=None,
        separators: List[str] | None = None,
    ):
        self.target_tokens = target_tokens
        self.overlap_tokens = overlap_tokens
        chunk_size = int(target_tokens * CHARS_PER_TOKEN)
        chunk_overlap = int(overlap_tokens * CHARS_PER_TOKEN)
        if length_function is None:
            length_function = len
        if separators is None:
            separators = ["\n\n\n", "\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ", ""]
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=length_function,
            separators=separators,
        )

    def count_tokens(self, text: str) -> int:
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception:
            return max(1, int(len(text) / CHARS_PER_TOKEN))

    def chunk_documents(self, documents: List[Document]) -> List[Document]:
        return self._splitter.split_documents(documents)
