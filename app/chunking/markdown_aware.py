# -*- coding: utf-8 -*-
"""
Markdown-aware chunker: splits on headers first, then recursive on large blocks.
"""

import re
from typing import List, Tuple

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.chunking.base import BaseChunker

CHARS_PER_TOKEN = 5.5


class MarkdownAwareChunker(BaseChunker):
    """
    Chunk by markdown/HTML headings first, then apply recursive splitting
    for oversized sections. Preserves structure and token-based sizing.
    """

    def __init__(
        self,
        target_tokens: int = 800,
        overlap_tokens: int = 200,
        min_tokens: int = 150,
    ):
        self.target_tokens = target_tokens
        self.overlap_tokens = overlap_tokens
        self.min_tokens = min_tokens
        self._chunk_size = int(target_tokens * CHARS_PER_TOKEN)
        self._chunk_overlap = int(overlap_tokens * CHARS_PER_TOKEN)
        self._heading_re = re.compile(r"^(#{1,6})\s+.+$|^<h[1-6]>.*?</h[1-6]>$", re.MULTILINE)
        self._fallback = RecursiveCharacterTextSplitter(
            chunk_size=self._chunk_size,
            chunk_overlap=self._chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def count_tokens(self, text: str) -> int:
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception:
            return max(1, int(len(text) / CHARS_PER_TOKEN))

    def _split_by_headings(self, text: str) -> List[Tuple[str, int, int]]:
        """Return list of (chunk_text, start, end)."""
        if not text or not text.strip():
            return []
        lines = text.split("\n")
        chunks: List[Tuple[str, int, int]] = []
        current: List[str] = []
        start = 0
        pos = 0
        for i, line in enumerate(lines):
            line_with_nl = line + "\n" if i < len(lines) - 1 else line
            is_heading = bool(self._heading_re.match(line.strip())) if line.strip() else False
            if is_heading and current:
                block = "".join(current).strip()
                if block:
                    chunks.append((block, start, pos))
                current = [line_with_nl]
                start = pos
            else:
                current.append(line_with_nl)
            pos += len(line_with_nl)
        if current:
            block = "".join(current).strip()
            if block:
                chunks.append((block, start, pos))
        return chunks

    def _merge_small(self, chunks: List[Tuple[str, int, int]]) -> List[Tuple[str, int, int]]:
        merged: List[Tuple[str, int, int]] = []
        i = 0
        while i < len(chunks):
            t, a, b = chunks[i]
            n = self.count_tokens(t)
            if n < self.min_tokens and i + 1 < len(chunks):
                t2, _, b2 = chunks[i + 1]
                combined = t + "\n\n" + t2
                if self.count_tokens(combined) <= int(self.target_tokens * 1.5):
                    merged.append((combined, a, b2))
                    i += 2
                    continue
            merged.append((t, a, b))
            i += 1
        return merged

    def _split_large(self, chunks: List[Tuple[str, int, int]]) -> List[str]:
        out: List[str] = []
        for t, _, _ in chunks:
            if self.count_tokens(t) <= int(self.target_tokens * 1.3):
                out.append(t)
            else:
                for d in self._fallback.split_text(t):
                    out.append(d)
        return out

    def chunk_documents(self, documents: List[Document]) -> List[Document]:
        result: List[Document] = []
        for doc in documents:
            text = doc.page_content
            meta = dict(doc.metadata)
            by_head = self._split_by_headings(text)
            merged = self._merge_small(by_head)
            texts = self._split_large(merged)
            for i, chunk_text in enumerate(texts):
                result.append(
                    Document(
                        page_content=chunk_text,
                        metadata={**meta, "chunk_index": i},
                    )
                )
        return result
