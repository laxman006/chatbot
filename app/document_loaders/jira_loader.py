# -*- coding: utf-8 -*-
"""
Jira document loader (API integration).

Loads tickets via Jira REST API: summary, description, comments.
Ticket fields and link/attachment metadata are preserved in document metadata.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Union

from langchain_core.documents import Document

from app.document_loaders.base_loader import BaseDocumentLoader

logger = logging.getLogger(__name__)


class JiraLoader(BaseDocumentLoader):
    """Load Jira tickets via API. Uses config (JIRA_SERVER, JIRA_PROJECT_KEYS, etc.)."""

    source_type = "jira"

    def load(self, source: Union[str, Path, Dict[str, Any], None]) -> List[Document]:
        # source is ignored; Jira uses app config (JIRA_SERVER, JIRA_PROJECT_KEYS, JIRA_JQL_QUERY, etc.)
        try:
            from app.jira_processor import process_jira_content
            documents = process_jira_content()
            # Ensure every doc has source_type for downstream
            for d in documents:
                if isinstance(d, Document) and "source_type" not in d.metadata:
                    d.metadata["source_type"] = self.source_type
            return documents
        except ImportError as e:
            logger.warning("Jira loader skipped: %s", e)
            return []
        except Exception as e:
            logger.exception("Jira load failed: %s", e)
            return []

    def extract_metadata(self, item: Union[str, Path, Document, Dict[str, Any]]) -> Dict[str, Any]:
        if isinstance(item, Document):
            return dict(item.metadata)
        if isinstance(item, dict):
            return {k: v for k, v in item.items() if v is not None}
        return super().extract_metadata(item)
