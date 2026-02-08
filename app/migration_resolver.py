# -*- coding: utf-8 -*-
"""
Canonical migration path resolution: single source of truth for platform names
and migration direction. Used in Excel ingestion, query parsing, and retrieval filtering.

Canonical form: <source_platform>__TO__<target_platform>
Examples: slack__TO__teams, teams__TO__teams, meta__TO__google_chat
"""

import re
from typing import Dict, List, Any, Optional, Tuple

# Single source of truth: platform key -> regex patterns (lowercase, match in column/query text)
PLATFORMS: Dict[str, List[str]] = {
    # Chat / collab
    "slack": [r"slack"],
    "teams": [r"microsoft\s*teams", r"ms[-\s]*teams", r"\bteams\b"],
    "google_chat": [r"google\s*chat", r"\bgchat\b", r"g\s*chat", r"\bchat\b"],
    "meta": [r"meta", r"workplace"],
    "webex": [r"webex"],
    # Cloud / file storage
    "box": [r"\bbox\b", r"box\s*for\s*business"],
    "one_drive": [
        r"one\s*drive",
        r"\bonedrive\b",
        r"one\s*drive\s*for\s*business",
        r"onedrive\s*for\s*business",
    ],
    "sharepoint_online": [
        r"share\s*point\s*online",
        r"sharepoint\s*online",
        r"\bsharepoint\b",
        r"share\s*point",
        r"sharepint\s*online",
    ],
    "google_suite": [r"google\s*suite", r"\bgsuite\b", r"g\s*suite", r"google\s*drive"],
    "google_shared_drive": [
        r"google\s*shared\s*drive",
        r"shared\s*drive",
        r"gshared\s*drive",
        r"g\s*shared\s*drive",
    ],
    "google_mydrive": [r"\bmydrive\b", r"my\s*drive", r"google\s*mydrive", r"google\s*my\s*drive"],
    "dropbox": [r"\bdropbox\b", r"drop\s*box", r"dropbox\s*for\s*business"],
    "egnyte": [r"\begnyte\b"],
    "citrix": [r"\bcitrix\b", r"\bsharefile\b", r"share\s*file"],
    "azure": [r"\bazure\b"],
    "amazon_s3": [r"amazon\s*s3", r"amazon\s*s\s*3", r"\bs3\b"],
    "nfs": [r"\bnfs\b", r"nfs\s*t[-\s]*mydrive", r"nfs\s*t[-\s]*shared\s*drive"],
    "amazon_workdocs": [
        r"amazon\s*workdocs",
        r"\bworkdocs\b",
        r"amazon\s*wordocs",
        r"\bwordocs\b",
    ],
}

# Order for source/target when multiple platforms match (first occurrence wins for order)
PLATFORM_ORDER = [
    "slack", "teams", "google_chat", "meta", "webex",
    "box", "one_drive", "sharepoint_online", "google_suite", "google_shared_drive", "google_mydrive",
    "dropbox", "egnyte", "citrix", "azure", "amazon_s3", "nfs", "amazon_workdocs",
]


# Regex to split on "X to Y" / "X -> Y" / "X → Y" (phrase-based source/target)
_MIGRATION_TO_PATTERN = re.compile(
    r"\s+(?:to|->|→)\s+",
    re.IGNORECASE,
)


def _first_platform_in_text(text: str) -> Optional[str]:
    """Return the first (by position) platform key found in text, or None."""
    if not (text or "").strip():
        return None
    text_lower = text.lower().strip()
    best_pos, best_platform = None, None
    for platform, patterns in PLATFORMS.items():
        for pat in patterns:
            m = re.search(pat, text_lower, re.IGNORECASE)
            if m and (best_pos is None or m.start() < best_pos):
                best_pos = m.start()
                best_platform = platform
    return best_platform


def _detect_platforms_in_text(text: str) -> List[str]:
    """Return list of platform keys found in text, in order of first occurrence (deduped)."""
    text_lower = text.lower().strip()
    found: List[str] = []
    positions: List[tuple] = []
    for platform, patterns in PLATFORMS.items():
        for pat in patterns:
            m = re.search(pat, text_lower, re.IGNORECASE)
            if m:
                positions.append((m.start(), platform))
                break
    positions.sort(key=lambda x: x[0])
    seen = set()
    for _, platform in positions:
        if platform not in seen:
            seen.add(platform)
            found.append(platform)
    return found


def detect_migration(text: str) -> Dict[str, Any]:
    """
    Detect migration direction from user query or any text.
    Handles "X to Y" phrase so that same platform twice (e.g. "teams to teams") is valid.
    Normalizes "X - Y" (space-dash-space) to "X to Y" so Excel-style headers match.

    Returns:
        If direction detected: direction_detected=True, source_platform, target_platform, migration_type.
        Else: direction_detected=False, mentioned_platforms list.
    """
    text = (text or "").strip()
    if not text:
        return {"direction_detected": False, "mentioned_platforms": []}
    # Normalize only space-dash-space to " to " (do NOT replace all hyphens: breaks "OneDrive-to-Azure", etc.)
    text = re.sub(r"\s+-\s+", " to ", text)

    # 1) Phrase-based: "X to Y" / "X -> Y" → source from left part, target from right (same platform allowed)
    parts = _MIGRATION_TO_PATTERN.split(text, 1)
    if len(parts) == 2:
        left, right = parts[0].strip(), parts[1].strip()
        source = _first_platform_in_text(left)
        target = _first_platform_in_text(right)
        if source is not None and target is not None:
            return {
                "source_platform": source,
                "target_platform": target,
                "migration_type": f"{source}__TO__{target}",
                "direction_detected": True,
                "mentioned_platforms": [source, target],
            }

    # 2) Fallback: 2+ distinct platforms in order of appearance
    found = _detect_platforms_in_text(text)
    if len(found) >= 2:
        return {
            "source_platform": found[0],
            "target_platform": found[1],
            "migration_type": f"{found[0]}__TO__{found[1]}",
            "direction_detected": True,
            "mentioned_platforms": found,
        }
    return {
        "direction_detected": False,
        "mentioned_platforms": found,
    }


def normalize_migration_column(col: str) -> Optional[str]:
    """
    Normalize an Excel column header (or sheet name) to canonical migration_type.
    Column can be e.g. "Box - One Drive for Business", "Slack to Teams", "Teams to Teams".
    Normalizes " - " (space-dash-space) to " to " so headers like "Box - One Drive" match.

    Returns:
        Canonical migration_type (e.g. "box__TO__one_drive") or None if not a migration column.
    """
    col = (col or "").strip()
    if not col:
        return None
    # Normalize only space-dash-space to " to " (do NOT replace all hyphens)
    col = re.sub(r"\s+-\s+", " to ", col)
    # Same phrase-based logic as detect_migration: "X to Y" → source from left, target from right
    parts = _MIGRATION_TO_PATTERN.split(col, 1)
    if len(parts) == 2:
        source = _first_platform_in_text(parts[0])
        target = _first_platform_in_text(parts[1])
        if source is not None and target is not None:
            return f"{source}__TO__{target}"
    found = _detect_platforms_in_text(col)
    if len(found) >= 2:
        return f"{found[0]}__TO__{found[1]}"
    return None


def migration_type_to_display(migration_type: str) -> str:
    """Convert canonical form to human-readable: teams__TO__webex -> 'teams to webex'."""
    if not migration_type or "__TO__" not in migration_type:
        return migration_type or ""
    return migration_type.replace("__TO__", " to ")


def get_migration_columns_from_headers(header_cells: List[str]) -> Tuple[bool, bool, List[Tuple[int, str, str]]]:
    """
    Analyze table headers to detect migration columns and determine table layout.
    
    Args:
        header_cells: List of header cell text values (from first row of table)
    
    Returns:
        Tuple of:
        - is_matrix_sheet: True if table has migration columns (Layout A or B)
        - is_feature_row_matrix: True if Layout B (feature per row, migrations as columns)
        - migration_columns_B: List of (column_index, column_header, migration_type) tuples
                              Only populated if is_feature_row_matrix is True
    """
    if not header_cells or len(header_cells) < 3:
        return False, False, []
    
    # Check if columns 2+ are migration columns (Layout B: feature per row)
    migration_columns_B = []
    for j, col_header in enumerate(header_cells[2:], start=2):  # Skip first 2 columns (feature, description)
        migration_type = normalize_migration_column(col_header)
        if migration_type:
            migration_columns_B.append((j, col_header, migration_type))
    
    is_matrix_sheet = len(migration_columns_B) >= 1
    is_feature_row_matrix = is_matrix_sheet  # Layout B: feature per row, migrations as columns
    
    return is_matrix_sheet, is_feature_row_matrix, migration_columns_B
