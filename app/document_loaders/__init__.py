# -*- coding: utf-8 -*-
"""
Document loaders: unified interface for PDF, DOCX, Excel, Markdown, Transcript (VTT/SRT), Jira.

Usage:
    from app.document_loaders import get_loader, PDFLoader, load_documents

    loader = get_loader("pdf")
    docs = loader.load("/path/to/file.pdf")

    # Or by file extension
    docs = load_documents("/path/to/doc.docx")
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from langchain_core.documents import Document

from app.document_loaders.base_loader import BaseDocumentLoader
from app.document_loaders.docx_loader import DOCXLoader
from app.document_loaders.excel_loader import ExcelLoader
from app.document_loaders.jira_loader import JiraLoader
from app.document_loaders.markdown_loader import MarkdownLoader
from app.document_loaders.pdf_loader import PDFLoader
from app.document_loaders.transcript_loader import TranscriptLoader

# Registry: source_type -> loader class
LOADER_REGISTRY: Dict[str, type] = {
    "pdf": PDFLoader,
    "docx": DOCXLoader,
    "excel": ExcelLoader,
    "markdown": MarkdownLoader,
    "md": MarkdownLoader,
    "transcript": TranscriptLoader,
    "vtt": TranscriptLoader,
    "srt": TranscriptLoader,
    "jira": JiraLoader,
}

# File extension -> source_type for load_documents()
EXTENSION_TO_SOURCE: Dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".doc": "docx",
    ".xlsx": "excel",
    ".xls": "excel",
    ".md": "markdown",
    ".markdown": "markdown",
    ".vtt": "transcript",
    ".srt": "transcript",
}

# Lazy singleton instances
_loaders: Dict[str, BaseDocumentLoader] = {}


def get_loader(source_type: str) -> BaseDocumentLoader:
    """Return a loader instance for the given source type (e.g. 'pdf', 'docx', 'jira')."""
    key = source_type.lower()
    if key not in _loaders:
        clz = LOADER_REGISTRY.get(key)
        if clz is None:
            raise ValueError(f"Unknown source_type: {source_type}. Known: {list(LOADER_REGISTRY.keys())}")
        if source_type == "transcript" or key in ("vtt", "srt"):
            _loaders[key] = TranscriptLoader(preserve_timestamps=True)
        else:
            _loaders[key] = clz()
    return _loaders[key]


def load_documents(
    source: Union[str, Path, Dict[str, Any], None],
    source_type: Optional[str] = None,
) -> List[Document]:
    """
    Load documents from a path or config using the appropriate loader.

    If source_type is None and source is a path, it is inferred from the file extension.
    For directories, only the first level of files is considered when inferring type;
    pass source_type explicitly (e.g. "pdf", "excel") when loading a directory.

    Args:
        source: File path, directory path, or loader-specific config (e.g. None for Jira).
        source_type: One of pdf, docx, excel, markdown, transcript, jira. Optional if source is a file path.

    Returns:
        List of LangChain Document objects.
    """
    path = Path(source) if isinstance(source, (str, Path)) else None
    if path is not None and path.exists() and path.is_file() and source_type is None:
        ext = path.suffix.lower()
        source_type = EXTENSION_TO_SOURCE.get(ext)
    if source_type is None:
        source_type = "pdf"  # safe default when wrong/missing
    loader = get_loader(source_type)
    return loader.load(source)


__all__ = [
    "BaseDocumentLoader",
    "PDFLoader",
    "DOCXLoader",
    "ExcelLoader",
    "MarkdownLoader",
    "TranscriptLoader",
    "JiraLoader",
    "get_loader",
    "load_documents",
    "LOADER_REGISTRY",
    "EXTENSION_TO_SOURCE",
]
