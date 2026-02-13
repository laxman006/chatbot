"""
Message/chat migration limitations and features extractor.

Reads the Limitations and features.xlsx (message migrations) with:
- Matrix sheets: Features, Description, then migration columns (Slack to Teams, Teams to Chat, etc.)
- Sectioned sheets: "In Scope Features", "Out of scope features", "Limitations" as section rows

Emits chunks with sheet_name in metadata so retrieval can scope by migration/sheet.
Does not modify app/excel_processor.py or any existing code.
"""

import os
from typing import List
import pandas as pd
from langchain_core.documents import Document


def _cell_str(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("nan", "") else s


def _is_section_header(cell: str) -> str:
    """Return section key or '' if not a section header."""
    t = (cell or "").strip().lower()
    if not t:
        return ""
    if "in scope" in t and "feature" in t:
        return "in_scope_features"
    if "out of scope" in t:
        return "out_of_scope"
    if "limitation" in t:
        return "limitations"
    if t in ("features included", "features"):
        return "in_scope_features"
    return ""


def _is_migration_column(col: str) -> bool:
    """Heuristic: column name looks like a migration path (Slack to Teams, etc.)."""
    if not col or len(col) < 4:
        return False
    lower = col.lower()
    # Skip generic headers
    if lower in ("feature", "features", "description", "desxription", "status", "supported", "yes/no"):
        return False
    # Migration-like: contains "to", " - ", or known platforms
    if " to " in lower or " - " in lower:
        return True
    platforms = ("slack", "teams", "chat", "meta", "google", "gchat", "webex", "ms-teams")
    return any(p in lower for p in platforms)


def _normalize_status(val) -> str:
    """Yes -> supported, No -> not supported, NA/blank/unknown -> not available."""
    s = _cell_str(val)
    if not s:
        return "not available"
    u = s.upper()
    if u in ("YES", "Y"):
        return "supported"
    if u in ("NO", "N") or u.startswith("NO"):
        return "not supported"
    if u in ("NA", "N/A"):
        return "not available"
    if "unknown" in s.lower():
        return "not available"
    return s  # keep as-is for notes like "No - S2 - 16th Oct"


def extract_message_limitations_documents(
    excel_path: str,
    display_file_name: str = None,
) -> List[Document]:
    """
    Extract Documents from the message/limitations Excel (one per feature per migration or per limitation row).

    Args:
        excel_path: Path to the Excel file.
        display_file_name: Optional display name (e.g. from SharePoint).

    Returns:
        List of LangChain Documents with sheet_name, migration_display, source_type, tag in metadata.
    """
    documents = []
    file_name = (display_file_name or os.path.basename(excel_path)).strip() or os.path.basename(excel_path)

    try:
        with pd.ExcelFile(excel_path) as xl:
            for sheet_name in xl.sheet_names:
                try:
                    df = pd.read_excel(xl, sheet_name=sheet_name, header=0)
                except Exception as e:
                    print(f"[message_limitations_extractor] Skip sheet '{sheet_name}': {e}")
                    continue
                if df.empty or len(df.columns) < 2:
                    continue

                cols = [str(c).strip() if c is not None else "" for c in df.columns]
                # Detect migration columns (index 2+)
                migration_cols = []
                for i in range(2, len(cols)):
                    if _is_migration_column(cols[i]):
                        migration_cols.append((i, cols[i]))

                current_section = ""
                for _, row in df.iterrows():
                    if row.isna().all():
                        continue
                    c0 = _cell_str(row.iloc[0]) if len(row) > 0 else ""
                    c1 = _cell_str(row.iloc[1]) if len(row) > 1 else ""
                    first = c0 or c1

                    # Section header row
                    sec = _is_section_header(first)
                    if sec:
                        current_section = sec
                        continue

                    feature = c0 or c1
                    description = c1 if (c0 and c1 and c0 != c1) else ""
                    if feature == description:
                        description = ""
                    if not feature:
                        continue

                    # Skip header-like rows
                    if feature.lower() in ("feature", "features", "description", "status", "limitations"):
                        continue

                    if migration_cols:
                        # Matrix: one chunk per (feature, migration, status)
                        for col_idx, mig_name in migration_cols:
                            if col_idx >= len(row):
                                continue
                            val = row.iloc[col_idx]
                            status_str = _normalize_status(val)
                            if not _cell_str(val) and status_str == "not available":
                                # empty cell -> still emit for completeness
                                pass
                            content_parts = [
                                f"Migration: {mig_name}",
                                f"Sheet: {sheet_name}",
                                f"Feature: {feature}",
                                f"Status: {status_str}",
                            ]
                            if description:
                                content_parts.append(f"Description: {description}")
                            if current_section:
                                content_parts.append(f"Category: {current_section}")
                            content_parts.append(f"Source: {file_name}")
                            content = "\n".join(content_parts)
                            doc = Document(
                                page_content=content,
                                metadata={
                                    "source": file_name,
                                    "source_type": "message_limitations",
                                    "sheet_name": sheet_name,
                                    "migration_display": mig_name,
                                    "feature": feature,
                                    "content_type": "message_limitations_matrix",
                                    "tag": "message_limitations",
                                },
                            )
                            documents.append(doc)
                    else:
                        # Single status column (col 2)
                        status_str = _normalize_status(row.iloc[2]) if len(row) > 2 else "not available"
                        content_parts = [
                            f"Sheet: {sheet_name}",
                            f"Feature: {feature}",
                            f"Status: {status_str}",
                        ]
                        if description:
                            content_parts.append(f"Description: {description}")
                        if current_section:
                            content_parts.append(f"Category: {current_section}")
                        content_parts.append(f"Source: {file_name}")
                        content = "\n".join(content_parts)
                        doc = Document(
                            page_content=content,
                            metadata={
                                "source": file_name,
                                "source_type": "message_limitations",
                                "sheet_name": sheet_name,
                                "feature": feature,
                                "content_type": "message_limitations",
                                "tag": "message_limitations",
                            },
                        )
                        documents.append(doc)

    except Exception as e:
        print(f"[message_limitations_extractor] Error reading {excel_path}: {e}")
        import traceback
        traceback.print_exc()

    return documents
