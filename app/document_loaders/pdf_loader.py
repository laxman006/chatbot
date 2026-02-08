# -*- coding: utf-8 -*-
"""
PDF document loader using pypdf and pdfplumber.

- pypdf for text extraction and document metadata (title, author, creation date)
- pdfplumber for tables and more reliable text extraction
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Union

from langchain_core.documents import Document

from app.document_loaders.base_loader import BaseDocumentLoader

# Reuse existing PDF extraction logic
from app.pdf_processor import extract_text_from_pdf

try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PdfReader = None
    PYPDF_AVAILABLE = False

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False


class PDFLoader(BaseDocumentLoader):
    """Load PDF files. Uses pdfplumber first for text/tables, pypdf as fallback."""

    source_type = "pdf"

    def load(self, source: Union[str, Path, Dict[str, Any], None]) -> List[Document]:
        if source is None:
            return []
        path = self._to_path(source)
        if path is None or not path.exists():
            return []
        if path.is_file() and path.suffix.lower() == ".pdf":
            return self._load_file(path)
        if path.is_dir():
            return self._load_directory(path)
        return []

    def _to_path(self, source: Union[str, Path, Dict[str, Any]]) -> Union[Path, None]:
        if isinstance(source, Path):
            return source
        if isinstance(source, str):
            return Path(source)
        if isinstance(source, dict) and "path" in source:
            return Path(source["path"])
        return None

    def _load_file(self, path: Path) -> List[Document]:
        documents = []
        try:
            text = extract_text_from_pdf(str(path))
            if not text.strip():
                return documents
            meta = self.extract_metadata(str(path))
            meta["file_path"] = str(path)
            meta["source"] = path.name
            documents.append(self._doc(text, meta))
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("PDF load failed for %s: %s", path, e)
        return documents

    def _load_directory(self, dir_path: Path) -> List[Document]:
        documents = []
        for p in sorted(dir_path.iterdir()):
            if p.suffix.lower() == ".pdf":
                documents.extend(self._load_file(p))
        return documents

    def extract_metadata(self, item: Union[str, Path, Document, Dict[str, Any]]) -> Dict[str, Any]:
        if isinstance(item, Document):
            return dict(item.metadata)
        if isinstance(item, dict):
            return {k: v for k, v in item.items() if v is not None}
        path = Path(item) if isinstance(item, str) else item
        if not isinstance(path, Path):
            path = Path(str(path))
        meta = {"source": path.name if getattr(path, "name", None) else str(path), "page_number": None}
        if path.suffix.lower() != ".pdf" or not path.exists():
            return meta
        try:
            if PYPDF_AVAILABLE and PdfReader:
                with open(path, "rb") as f:
                    r = PdfReader(f)
                    meta["page_count"] = len(r.pages)
                    if r.metadata:
                        if r.metadata.get("/Title"):
                            meta["title"] = r.metadata["/Title"]
                        if r.metadata.get("/Author"):
                            meta["author"] = r.metadata["/Author"]
                        if r.metadata.get("/CreationDate"):
                            meta["created"] = str(r.metadata["/CreationDate"])
        except Exception:
            pass
        return meta
