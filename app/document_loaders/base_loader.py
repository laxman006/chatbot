# -*- coding: utf-8 -*-
"""
Base document loader interface.

Abstract base class for all document loaders. Provides a common interface
(load, extract_metadata) and standard error handling and logging.
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Union

from langchain_core.documents import Document

logger = logging.getLogger(__name__)


class BaseDocumentLoader(ABC):
    """
    Abstract base class for all document loaders.

    Subclasses must implement load() and may override extract_metadata().
    """

    source_type: str = "generic"

    @abstractmethod
    def load(self, source: Union[str, Path, Dict[str, Any], None]) -> List[Document]:
        """
        Load documents from the given source.

        Args:
            source: File path, directory path, or loader-specific config
                    (e.g. API params for Jira). None means "use default config".

        Returns:
            List of LangChain Document objects with page_content and metadata.
        """
        pass

    def extract_metadata(self, item: Union[str, Path, Document, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract metadata from a path, document, or raw item.

        Override in subclasses for format-specific metadata (e.g. page numbers,
        title, author for PDF; sheet_name for Excel).

        Args:
            item: File path, existing Document, or raw structure (e.g. API response).

        Returns:
            Dictionary of metadata keys and values.
        """
        if isinstance(item, Document):
            return dict(item.metadata)
        if isinstance(item, (str, Path)):
            return {"source": str(Path(item).name), "file_path": str(item)}
        if isinstance(item, dict):
            return {k: v for k, v in item.items() if v is not None}
        return {}

    def _doc(self, content: str, metadata: Dict[str, Any]) -> Document:
        """Build a Document with source_type in metadata."""
        meta = {"source_type": self.source_type, **metadata}
        return Document(page_content=content, metadata=meta)
