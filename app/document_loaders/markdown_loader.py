# -*- coding: utf-8 -*-
"""
Markdown document loader.

Parses markdown with optional YAML frontmatter. Preserves structure
(headers, code blocks). Puts frontmatter keys into metadata.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Union

from langchain_core.documents import Document

from app.document_loaders.base_loader import BaseDocumentLoader


def _parse_frontmatter(text: str) -> tuple[Dict[str, Any], str]:
    """Split optional frontmatter from body. Returns (metadata_dict, body)."""
    meta = {}
    body = text
    if text.startswith("---"):
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
        if match:
            fm, body = match.group(1), match.group(2)
            for line in fm.split("\n"):
                m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*):\s*(.*)$", line.strip())
                if m:
                    key, val = m.group(1), m.group(2).strip()
                    if val.startswith('"') and val.endswith('"'):
                        val = val[1:-1].replace('\\"', '"')
                    elif val.startswith("'") and val.endswith("'"):
                        val = val[1:-1].replace("\\'", "'")
                    meta[key] = val
    return meta, body.strip()


class MarkdownLoader(BaseDocumentLoader):
    """Load Markdown files with optional frontmatter. Preserves headers and code blocks."""

    source_type = "markdown"

    def load(self, source: Union[str, Path, Dict[str, Any], None]) -> List[Document]:
        if source is None:
            return []
        path = self._to_path(source)
        if path is None or not path.exists():
            return []
        if path.is_file() and path.suffix.lower() in (".md", ".markdown"):
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
            content = path.read_text(encoding="utf-8", errors="replace")
            fm_meta, body = _parse_frontmatter(content)
            if not body and not fm_meta:
                return documents
            meta = self.extract_metadata(str(path))
            meta["file_path"] = str(path)
            meta["source"] = path.name
            meta["content_type"] = "markdown"
            meta.update(fm_meta)
            documents.append(self._doc(body or "(no body)", meta))
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Markdown load failed for %s: %s", path, e)
        return documents

    def _load_directory(self, dir_path: Path) -> List[Document]:
        documents = []
        exts = {".md", ".markdown"}
        for p in sorted(dir_path.rglob("*")):
            if p.is_file() and p.suffix.lower() in exts:
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
        meta = {"source": path.name if getattr(path, "name", None) else str(path)}
        if path.suffix.lower() not in (".md", ".markdown") or not path.exists():
            return meta
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            fm, _ = _parse_frontmatter(content)
            meta.update(fm)
        except Exception:
            pass
        return meta
