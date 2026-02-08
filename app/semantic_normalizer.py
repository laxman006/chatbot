# -*- coding: utf-8 -*-
"""
Semantic normalizer for enterprise knowledge ingestion.

Do NOT hard-code business meaning to column names.
DO normalize + preserve raw structure.

Two layers:
1. Normalized semantic layer → used by the bot (feature, supported, limitation, description)
2. Raw evidence layer → stored in raw_kv for grounding & audit
"""

import json
import re
from typing import Dict, Any, Tuple, List

# Heading detection for Parent-Based Attachment (Shared across processors)
HEADING_PATTERNS = [
    r'^#{1,6}\s+.+$',  # Markdown: # Heading
    r'^[A-Z][A-Za-z\s]{2,50}:$',  # Title case with colon (Step 1:, Conclusion:)
    r'^\d+\.\d*\s+[A-Z].+$', # 1.1 Heading
    r'^Step\s+\d+[:\.]\s+.+$', # Step 1: ...
    r'^Chapter\s+\d+[:\.]\s+.+$', # Chapter 1: ...
]

def is_line_heading(line: str) -> bool:
    """Check if a line is likely a heading/section title."""
    line = line.strip()
    if not line or len(line) > 120: return False
    for p in HEADING_PATTERNS:
        if re.match(p, line, re.IGNORECASE):
            return True
    return False

# Column name aliases: semantic_key -> list of possible column names (lowercase, partial match)
SUPPORTED_ALIASES = {
    "supported": [
        "supported", "status", "availability", "enabled", "support", "yes/no",
        "yes/no/partial", "scope", "in scope", "out of scope",
    ],
    "feature": [
        "feature", "capability", "functionality", "item", "feature name",
        "features", "capabilities", "migration item",
    ],
    "limitation": [
        "limitation", "limitations", "out of scope", "restriction", "not supported",
        "notes", "note", "remarks", "constraints", "exclusions",
    ],
    "description": [
        # Common variants / misspellings seen in source Excels
        "description", "desxription",
        "details", "notes", "remarks", "summary", "info",
    ],
}


def normalize_columns(row: Dict[str, Any]) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """
    Normalize a row (dict of column_name -> value) into semantic keys + raw copy.

    Args:
        row: Dictionary of column name -> value (e.g. {"Feature": "Reactions", "Status": "No"})

    Returns:
        (normalized, raw):
        - normalized: dict with keys feature, supported, limitation, description (only keys that matched)
        - raw: dict suitable for raw_kv (original column names -> string value), plus keys we use for audit
    """
    normalized = {}
    raw = {}

    for col, value in row.items():
        if col is None or (isinstance(col, float) and str(col) == "nan"):
            continue
        col_str = str(col).strip()
        # NOTE: Do NOT skip "Unnamed" here blindly; we need to inspect content first.
        # Filtering is now handled by header-inference in the processor.
        
        val_str = str(value).strip() if value is not None and (not isinstance(value, float) or str(value) != "nan") else ""
        raw[col_str] = val_str

        col_lower = col_str.lower()
        for semantic_key, aliases in SUPPORTED_ALIASES.items():
            if any(alias in col_lower for alias in aliases):
                normalized[semantic_key] = val_str
                break

    return normalized, raw


def map_column_indices(cols: List[str]) -> Dict[str, int]:
    """
    Identify which index corresponds to which semantic key (feature, supported, etc.)
    based on a list of column names.
    """
    mapping = {}
    for i, col in enumerate(cols):
        col_lower = str(col).lower().strip()
        for semantic_key, aliases in SUPPORTED_ALIASES.items():
            if semantic_key in mapping:
                continue
            if any(alias in col_lower for alias in aliases):
                mapping[semantic_key] = i
                break
    return mapping


def row_to_raw_kv(raw: Dict[str, Any], sheet_name: str = None, row_index: int = None) -> str:
    """
    Build JSON string for raw_kv property (audit trail).

    Args:
        raw: Original column name -> value
        sheet_name: Optional sheet name (Excel) or table identifier
        row_index: Optional row index

    Returns:
        JSON string to store in Weaviate raw_kv
    """
    out = {"original_columns": raw}
    if sheet_name is not None:
        out["sheet_name"] = sheet_name
    if row_index is not None:
        out["row_index"] = int(row_index)
    return json.dumps(out, ensure_ascii=False)
