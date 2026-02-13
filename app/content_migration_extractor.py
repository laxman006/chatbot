"""
Content migration capability extractor.

Reads the content Excel (Common_Features_In_Content_Migrations2) where:
- Row 0 = headers: "Cloud Combination/Features", "Is Golden combination?", then feature columns (OneTime, Delta, ...)
- Rows 1+ = migration combination (col 0) + Yes/No/NA per feature column.

Emits ONE chunk per migration row with:
- Supported features (Yes)
- Not supported features (No)
- Not available features (NA, blank, unknown)

Does not modify app/excel_processor.py or any existing code.
"""

import os
from typing import List
import pandas as pd
from langchain_core.documents import Document


def _cell_status(val) -> str:
    """Normalize cell to supported | not_supported | not_available."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "not_available"
    s = str(val).strip()
    if not s or s.lower() in ("nan", "unknown", "n/a", "na"):
        return "not_available"
    u = s.upper()
    if u in ("YES", "Y"):
        return "supported"
    if u in ("NO", "N"):
        return "not_supported"
    if u.startswith("NO") or (len(s) <= 4 and "no" in s.lower()):
        return "not_supported"
    if "yes" in s.lower() or "unlimited" in s.lower():
        return "supported"
    return "not_available"


def extract_content_migration_documents(
    excel_path: str,
    display_file_name: str = None,
    sheet_name: str = None,
) -> List[Document]:
    """
    Extract one Document per migration row from the content Excel.

    Args:
        excel_path: Path to the Excel file.
        display_file_name: Optional display name (e.g. from SharePoint).
        sheet_name: If provided, only this sheet is read; else first sheet.

    Returns:
        List of LangChain Documents (one per migration row).
    """
    documents = []
    file_name = (display_file_name or os.path.basename(excel_path)).strip() or os.path.basename(excel_path)

    try:
        with pd.ExcelFile(excel_path) as xl:
            sheets = [sheet_name] if sheet_name else xl.sheet_names
            for sn in sheets:
                if sn not in xl.sheet_names:
                    continue
                df = pd.read_excel(xl, sheet_name=sn)
                if df.empty or len(df.columns) < 2:
                    continue

                cols = [str(c).strip() if c is not None else "" for c in df.columns]
                feature_cols = []
                for i, c in enumerate(cols):
                    if i <= 1:
                        continue
                    if c and str(c).lower() not in ("nan", ""):
                        feature_cols.append((i, c))

                for _, row in df.iterrows():
                    migration = row.iloc[0]
                    if migration is None or (isinstance(migration, float) and pd.isna(migration)):
                        continue
                    migration_str = str(migration).strip()
                    if not migration_str or migration_str.lower() in ("nan", "cloud combination/features", "features"):
                        continue

                    supported = []
                    not_supported = []
                    not_available = []
                    for col_idx, feature_name in feature_cols:
                        if col_idx >= len(row):
                            continue
                        val = row.iloc[col_idx]
                        status = _cell_status(val)
                        if status == "supported":
                            supported.append(feature_name)
                        elif status == "not_supported":
                            not_supported.append(feature_name)
                        else:
                            not_available.append(feature_name)

                    lines = [
                        f"Migration: {migration_str}",
                        "",
                        "Supported features: " + (", ".join(supported) if supported else "(none)"),
                        "Not supported: " + (", ".join(not_supported) if not_supported else "(none)"),
                        "Not available: " + (", ".join(not_available) if not_available else "(none)"),
                        "",
                        f"Source: {file_name} | Sheet: {sn}",
                    ]
                    content = "\n".join(lines)

                    doc = Document(
                        page_content=content,
                        metadata={
                            "source": file_name,
                            "source_type": "content_migration",
                            "sheet_name": sn,
                            "migration_display": migration_str,
                            "file_path": excel_path,
                            "content_type": "content_migration_matrix",
                            "tag": "content_migration",
                        },
                    )
                    documents.append(doc)

    except Exception as e:
        print(f"[content_migration_extractor] Error reading {excel_path}: {e}")
        import traceback
        traceback.print_exc()

    return documents
