# -*- coding: utf-8 -*-
"""
Transcript loader for VTT and SRT subtitle files.

Parses WebVTT (.vtt) and SubRip (.srt) with timestamp preservation.
Optional speaker labels when present in the text (e.g. "Speaker 1:").
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

from langchain_core.documents import Document

from app.document_loaders.base_loader import BaseDocumentLoader

# VTT: 00:00:00.000 --> 00:00:00.000  or with cue settings
# SRT: 00:00:00,000 --> 00:00:00,000
_TIMECODE_RE = re.compile(
    r"(\d{1,2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[.,]\d{3})",
    re.MULTILINE,
)


def _parse_vtt_srt(content: str, preserve_timestamps: bool = True) -> List[Tuple[str, str, str]]:
    """
    Parse VTT or SRT content into (start, end, text) cues.

    Returns list of (start_time, end_time, text). If preserve_timestamps,
    text may include [start --> end] prefix for each cue.
    """
    # Normalize line endings and strip WEBVTT header
    text = content.replace("\r\n", "\n").replace("\r", "\n")
    if text.strip().upper().startswith("WEBVTT"):
        first_blank = text.find("\n\n")
        if first_blank >= 0:
            text = text[first_blank + 2 :]
    # Split into cue blocks (blank-line separated)
    blocks = re.split(r"\n\s*\n", text)
    cues: List[Tuple[str, str, str]] = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        match = _TIMECODE_RE.search(block)
        if not match:
            continue
        start, end = match.group(1), match.group(2)
        # Cue text is everything after the timecode line
        rest = block[match.end() :].strip()
        lines = [ln.strip() for ln in rest.split("\n") if ln.strip()]
        cue_text = " ".join(lines)
        if preserve_timestamps:
            cue_text = f"[{start} --> {end}] {cue_text}"
        cues.append((start, end, cue_text))
    return cues


def _format_transcript_document(cues: List[Tuple[str, str, str]], sep: str = "\n\n") -> str:
    """Turn parsed cues into a single document string."""
    return sep.join(t[2] for t in cues)


class TranscriptLoader(BaseDocumentLoader):
    """Load VTT and SRT transcript files with timestamp preservation."""

    source_type = "transcript"

    def __init__(self, preserve_timestamps: bool = True):
        self.preserve_timestamps = preserve_timestamps

    def load(self, source: Union[str, Path, Dict[str, Any], None]) -> List[Document]:
        if source is None:
            return []
        path = self._to_path(source)
        if path is None or not path.exists():
            return []
        if path.is_file() and path.suffix.lower() in (".vtt", ".srt"):
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
            cues = _parse_vtt_srt(content, preserve_timestamps=self.preserve_timestamps)
            if not cues:
                return documents
            body = _format_transcript_document(cues)
            meta = self.extract_metadata(str(path))
            meta["file_path"] = str(path)
            meta["source"] = path.name
            meta["content_type"] = "transcript"
            meta["format"] = "vtt" if path.suffix.lower() == ".vtt" else "srt"
            meta["cue_count"] = len(cues)
            if cues:
                meta["start_time"] = cues[0][0]
                meta["end_time"] = cues[-1][1]
            documents.append(self._doc(body, meta))
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Transcript load failed for %s: %s", path, e)
        return documents

    def _load_directory(self, dir_path: Path) -> List[Document]:
        documents = []
        exts = {".vtt", ".srt"}
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
        if path.suffix.lower() not in (".vtt", ".srt") or not path.exists():
            return meta
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            cues = _parse_vtt_srt(content, preserve_timestamps=False)
            meta["cue_count"] = len(cues)
            if cues:
                meta["start_time"] = cues[0][0]
                meta["end_time"] = cues[-1][1]
            meta["format"] = "vtt" if path.suffix.lower() == ".vtt" else "srt"
        except Exception:
            pass
        return meta
