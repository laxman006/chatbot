import os
import pandas as pd
from typing import List, Dict
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

# Try to import openpyxl for Excel support
try:
    import openpyxl
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False
    print("openpyxl not available, Excel processing may be limited")

# Try to import xlrd for older Excel formats
try:
    import xlrd
    XLRD_AVAILABLE = True
except ImportError:
    XLRD_AVAILABLE = False
    print("xlrd not available, older Excel formats (.xls) may not be supported")

def extract_text_from_excel(excel_path: str) -> str:
    """Extract text from all sheets in an Excel file."""
    text_content = []
    
    try:
        # Read all sheets from the Excel file using a context manager to ensure closure
        with pd.ExcelFile(excel_path) as excel_file:
            # Add file-level metadata for better searchability
            text_content.append(f"Excel file: {os.path.basename(excel_path)}")
            text_content.append("Contains migration features, limitations, and capabilities for different migration paths.\n")
            
            for sheet_name in excel_file.sheet_names:
                try:
                    # Read the sheet using the already open excel_file
                    df = pd.read_excel(excel_file, sheet_name=sheet_name)
                    
                    # Add sheet header with migration path context
                    text_content.append(f"\n=== Migration Path: {sheet_name} ===\n")
                except Exception as e:
                    print(f"Error processing sheet '{sheet_name}' in {excel_path}: {e}")
                    import traceback
                    traceback.print_exc()
                    text_content.append(f"\nError reading sheet '{sheet_name}': {str(e)}\n")
                    continue
                
                if not df.empty:
                    cols = list(df.columns)
                    
                    # Track section headers (Features Included, Out of Scope, Limitations, etc.)
                    current_section = None
                    
                    # Process each row
                    for index, row in df.iterrows():
                        # Skip completely empty rows
                        if df.iloc[index].isna().all():
                            continue
                        
                        # Extract values (handle different column structures)
                        feature = str(row[cols[0]]) if len(cols) > 0 and pd.notna(row[cols[0]]) else ""
                        description = str(row[cols[1]]) if len(cols) > 1 and pd.notna(row[cols[1]]) else ""
                        status = str(row[cols[2]]) if len(cols) > 2 and pd.notna(row[cols[2]]) else ""
                        
                        # Additional columns if present (for flexibility)
                        additional_info = ""
                        if len(cols) > 3:
                            additional_values = []
                            for i in range(3, len(cols)):
                                if pd.notna(row[cols[i]]):
                                    additional_values.append(f"{cols[i]}: {row[cols[i]]}")
                            if additional_values:
                                additional_info = " | ".join(additional_values)
                        
                        # Check if this is a section header row
                        feature_lower = feature.lower().strip() if feature else ""
                        section_headers = [
                            'features included', 'out of scope features', 'limitations',
                            'feature name', 'feature', 'features', 'capabilities',
                            'supported features', 'unsupported features'
                        ]
                        
                        if feature_lower in section_headers:
                            current_section = feature
                            text_content.append(f"\n## {feature}\n")
                            continue
                        
                        # Skip if no feature name
                        if not feature or feature.strip() == "":
                            continue
                        
                        # Create structured entry with explicit field names
                        entry = f"Feature Name: {feature}\n"
                        
                        if description and description.strip():
                            entry += f"Description: {description}\n"
                        
                        if status and status.strip():
                            entry += f"Status: {status}\n"
                        
                        entry += f"Migration Path: {sheet_name}\n"
                        
                        if current_section:
                            entry += f"Category: {current_section}\n"
                        
                        if additional_info:
                            entry += f"Additional Information: {additional_info}\n"
                        
                        # Create natural language summary for better semantic search
                        status_upper = status.upper().strip() if status else ""
                        
                        if status_upper in ['YES', 'NO', 'NA', 'N/A']:
                            if status_upper == "YES":
                                status_text = "is supported"
                            elif status_upper == "NO":
                                status_text = "is not supported"
                            else:
                                status_text = "is not applicable"
                            
                            summary = f"For {sheet_name} migration: {feature} {status_text}."
                            if description and description.strip():
                                summary += f" {description}"
                        else:
                            # If status is not Yes/No/NA, include it as additional details
                            summary = f"For {sheet_name} migration: {feature}."
                            if description and description.strip():
                                summary += f" {description}"
                            if status and status.strip():
                                summary += f" Status or details: {status}"
                        
                        entry += f"Summary: {summary}\n"
                        text_content.append(entry)
                    
                    # Add summary statistics for numeric columns (if any)
                    numeric_cols = df.select_dtypes(include=['number']).columns
                    if len(numeric_cols) > 0:
                        text_content.append(f"\nSummary statistics for numeric columns:\n")
                        for col in numeric_cols:
                            if not df[col].isna().all():
                                stats = df[col].describe()
                                text_content.append(f"{col}: mean={stats.get('mean', 'N/A'):.2f}, "
                                                  f"min={stats.get('min', 'N/A'):.2f}, "
                                                  f"max={stats.get('max', 'N/A'):.2f}\n")
                
            # The original code had an extra try/except block here, which was incorrect.
            # The inner try/except for sheet processing is sufficient.
            # The outer try/except handles file-level errors.
        
        return "\n".join(text_content)
        
    except Exception as e:
        print(f"Error reading Excel file {excel_path}: {e}")
        import traceback
        traceback.print_exc()
        return ""

def process_excel_directory(excel_directory: str) -> List[Document]:
    """Process all Excel files in a directory and return as LangChain Documents."""
    documents = []
    
    if not os.path.exists(excel_directory):
        print(f"Excel directory {excel_directory} does not exist")
        return documents
    
    # Supported Excel file extensions
    excel_extensions = ['.xlsx', '.xls']
    excel_files = []
    
    for file in os.listdir(excel_directory):
        if any(file.lower().endswith(ext) for ext in excel_extensions):
            excel_files.append(file)
    
    if not excel_files:
        print(f"No Excel files found in {excel_directory}")
        return documents
    
    print(f"Processing {len(excel_files)} Excel file(s)...")
    
    for excel_file in excel_files:
        excel_path = os.path.join(excel_directory, excel_file)
        print(f"Processing: {excel_file}")
        
        try:
            # Extract text from Excel file
            text = extract_text_from_excel(excel_path)
            source_type = "excel"
            
            if text.strip():
                # Create a document with metadata
                doc = Document(
                    page_content=text,
                    metadata={
                        "source": excel_file,
                        "source_type": source_type,
                        "file_path": excel_path,
                        "file_format": excel_file.split('.')[-1].lower(),
                        "content_type": "excel_data",
                        "searchable_terms": " ".join(text.split()[:20])  # Add first 20 words for better searchability
                    }
                )
                documents.append(doc)
                print(f"Successfully processed {excel_file} ({len(text)} characters)")
            else:
                print(f"Warning: No text extracted from {excel_file}")
                
        except Exception as e:
            print(f"Error processing {excel_file}: {e}")
    
    return documents

def chunk_excel_documents(documents: List[Document], chunk_size: int = 800, chunk_overlap: int = 150) -> List[Document]:
    """
    Split Excel documents into smaller chunks for better retrieval.
    Uses separators optimized for the enhanced structured format.
    """
    if not documents:
        return documents
    
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n\n", "\n\n", "\n=== ", "\n## ", "\n", " | ", " ", ""]  # Better separators for structured Excel data
    )
    
    chunked_docs = []
    for doc in documents:
        chunks = splitter.split_documents([doc])
        # Add metadata to each chunk for better searchability
        for chunk in chunks:
            chunk.metadata.update(doc.metadata)  # Preserve original metadata first
            chunk.metadata.update({
                "chunk_type": "excel_data",
                "searchable_content": " ".join(chunk.page_content.split()[:20]),  # First 20 words for search
                "tag": "excel"  # Tag for chatbot to identify Excel content
            })
        chunked_docs.extend(chunks)
    
    print(f"Split {len(documents)} Excel documents into {len(chunked_docs)} chunks")
    return chunked_docs

# --- Sectioned feature matrix: format detection and markers ---
# Only apply section-aware ingestion when the sheet actually contains these section headers.
SECTION_MARKERS = frozenset({
    "features included",
    "out of scope",
    "out of scope features",
    "limitations",
})

# Normalized section values for chunks (used in metadata and retrieval).
SECTION_FEATURES_INCLUDED = "features_included"
SECTION_OUT_OF_SCOPE = "out_of_scope"
SECTION_LIMITATIONS = "limitations"

# Display labels for section_title (Weaviate / UI).
SECTION_DISPLAY = {
    SECTION_FEATURES_INCLUDED: "Features Included",
    SECTION_OUT_OF_SCOPE: "Out of scope",
    SECTION_LIMITATIONS: "Limitations",
}


def _cell_str(v) -> str:
    """Normalize a cell value to a non-empty string or empty."""
    if v is None:
        return ""
    if isinstance(v, float) and str(v) == "nan":
        return ""
    s = str(v).strip()
    return "" if s.lower() == "nan" else s


def _detect_sheet_format(df: pd.DataFrame) -> str:
    """
    Detect if the sheet follows the sectioned feature matrix format.
    Scans all cells and column names for section markers (features included, out of scope, limitations).
    If at least 2 distinct markers are found → "sectioned_feature_matrix", else "generic_table".
    """
    if df.empty or len(df.columns) == 0:
        return "generic_table"
    found = set()

    def _mark(lower: str) -> None:
        if "features included" in lower or lower.strip() == "features included":
            found.add("features_included")
        if "out of scope" in lower:
            found.add("out_of_scope")
        if "limitations" in lower or lower.strip() == "limitations":
            found.add("limitations")

    for col in df.columns:
        _mark(str(col).lower())
    for _, row in df.iterrows():
        for c in row:
            val = _cell_str(c)
            if val:
                _mark(val.lower())
            if len(found) >= 2:
                return "sectioned_feature_matrix"
    return "generic_table"


def _normalize_section_header(cell_text: str) -> str:
    """
    Map a section header row text to a normalized section key.
    Returns one of: features_included, out_of_scope, limitations, or "" if not a section header.
    Only full section phrases are matched; column headers like "Feature" or "Feature Name" are not.
    """
    if not cell_text:
        return ""
    t = cell_text.lower().strip()
    if "out of scope" in t:
        return SECTION_OUT_OF_SCOPE
    if "limitation" in t:
        return SECTION_LIMITATIONS
    if "features included" in t:
        return SECTION_FEATURES_INCLUDED
    return ""


def _chunks_for_sectioned_sheet(df: pd.DataFrame, sheet_name: str, file_name: str) -> List[Dict]:
    """
    Process a sheet that has been detected as sectioned feature matrix format.
    Rule: A section header applies to all subsequent rows until the next section header.
    - current_section is persisted; never reset per row.
    - Every chunk has sheet_name (product boundary).
    - feature_capability: section in (features_included, out_of_scope); one chunk per feature (or per feature x migration if matrix).
    - limitation: section = limitations; one chunk per limitation row (never matrix-expanded).
    """
    from app.migration_resolver import normalize_migration_column, migration_type_to_display

    chunks = []
    if df.empty or len(df.columns) == 0:
        return chunks

    sheet_migration_type = normalize_migration_column(sheet_name)
    display_migration_sheet = migration_type_to_display(sheet_migration_type) if sheet_migration_type else sheet_name

    # Column names for migration detection (cols 0,1 = feature, description; cols 2+ may be status or migration columns)
    cols = [str(c).strip() if c is not None else "" for c in df.columns]
    ncols = len(cols)
    # Detect migration columns (cols from index 2 that normalize to a migration type) for matrix-level chunking
    migration_columns = []
    for idx in range(2, ncols):
        col_name = cols[idx] if idx < len(cols) else ""
        if not col_name:
            continue
        mt = normalize_migration_column(col_name)
        if mt:
            migration_columns.append((idx, col_name, mt))

    current_section = None  # normalized: features_included | out_of_scope | limitations

    for index, row in df.iterrows():
        if row.isna().all():
            continue
        c0 = _cell_str(row.iloc[0]) if ncols > 0 else ""
        c1 = _cell_str(row.iloc[1]) if ncols > 1 else ""
        c2 = _cell_str(row.iloc[2]) if ncols > 2 else ""
        first_cell = c0 or c1

        # 1) Check if this row is a section header
        section_key = _normalize_section_header(first_cell)
        if section_key:
            current_section = section_key
            continue

        # 2) If we have no section yet, skip (or could treat as generic; we skip to avoid noise)
        if not current_section:
            continue

        # 3) Limitations section: each row is one limitation (text); include Yes/No from status column (c2) in content
        if current_section == SECTION_LIMITATIONS:
            text = c0 or c1  # body from col0/col1; c2 is status (Yes/No) only
            if not text:
                continue
            # Read status column (c2) so LLM sees Supported: No/Yes in context
            status_cell = (c2 or "").strip().upper()
            if status_cell in ("YES", "Y"):
                status_line = "Supported: Yes\n"
                supported_meta = True
            elif status_cell in ("NO", "N"):
                status_line = "Supported: No\n"
                supported_meta = False
            elif status_cell in ("NA", "N/A"):
                status_line = "Supported: NOT AVAILABLE\n"
                supported_meta = None
            else:
                status_line = "Supported: No\n"  # limitations default to not supported
                supported_meta = False
            content_str = f"Limitation for {display_migration_sheet}: {text}\n{status_line}Source: {file_name} | Sheet: {sheet_name}"
            chunks.append({
                "content": content_str,
                "chunk_type": "limitation",
                "sheet_name": sheet_name,
                "section": SECTION_LIMITATIONS,
                "section_title": SECTION_DISPLAY.get(SECTION_LIMITATIONS, "Limitations"),
                "text": text,
                "feature": None,
                "supported": supported_meta,
                "limitation": text,
                "source_file": file_name,
                "migration_type": sheet_migration_type,
                "display_migration": display_migration_sheet,
                "ingestion_version": "excel_sectioned_limitation",
            })
            continue

        # 4) Features Included or Out of Scope: feature row — matrix (one chunk per migration column) or single status (c2)
        if current_section in (SECTION_FEATURES_INCLUDED, SECTION_OUT_OF_SCOPE):
            feature = c0 or c1
            if not feature:
                continue
            description = c1 if c0 and c1 else (c0 if not c0 else "")
            if description == feature:
                description = ""

            if migration_columns:
                # Matrix mode: one chunk per (feature, migration_type); section and sheet_name preserved
                for col_idx, col_name, migration_type in migration_columns:
                    cell_val = _cell_str(row.iloc[col_idx]) if col_idx < len(row) else ""
                    if not (cell_val or "").strip():
                        continue
                    supported_val = (cell_val or "").strip().upper()
                    if supported_val in ("YES", "Y"):
                        supported = True
                    elif supported_val in ("NO", "N"):
                        supported = False
                    elif supported_val in ("NA", "N/A"):
                        supported = None  # Not Applicable
                    else:
                        supported = current_section == SECTION_FEATURES_INCLUDED
                    display_migration = migration_type_to_display(migration_type)
                    status_str = "Yes" if supported is True else ("No" if supported is False else "Not Applicable")
                    content_parts = [
                        f"Migration: {display_migration}",
                        f"Feature: {feature}",
                        f"Supported: {status_str}",
                    ]
                    if description:
                        content_parts.append(f"Description: {description}")
                    content_parts.append(f"Source: {file_name} | Sheet: {sheet_name}")
                    chunks.append({
                        "content": "\n".join(content_parts),
                        "chunk_type": "feature_capability",
                        "sheet_name": sheet_name,
                        "section": current_section,
                        "section_title": SECTION_DISPLAY.get(current_section, ""),
                        "feature": feature,
                        "description": description or None,
                        "supported": supported,
                        "source_file": file_name,
                        "migration_type": migration_type,
                        "display_migration": display_migration,
                        "limitation": None,
                        "raw_kv": "",
                        "ingestion_version": "excel_sectioned_matrix",
                    })
            else:
                # Single-status mode: one chunk per row using c2 (current behavior)
                supported_val = (c2 or "").strip().upper()
                if supported_val in ("YES", "Y"):
                    supported = True
                elif supported_val in ("NO", "N"):
                    supported = False
                else:
                    supported = current_section == SECTION_FEATURES_INCLUDED
                content_parts = [
                    f"Feature: {feature}",
                    f"Supported: {'Yes' if supported else 'No'}",
                ]
                if description:
                    content_parts.append(f"Description: {description}")
                content_parts.append(f"Source: {file_name} | Sheet: {sheet_name}")
                chunks.append({
                    "content": "\n".join(content_parts),
                    "chunk_type": "feature_capability",
                    "sheet_name": sheet_name,
                    "section": current_section,
                    "section_title": SECTION_DISPLAY.get(current_section, ""),
                    "feature": feature,
                    "description": description or None,
                    "supported": supported,
                    "source_file": file_name,
                    "migration_type": sheet_migration_type,
                    "display_migration": display_migration_sheet,
                    "limitation": None,
                    "raw_kv": "",
                    "ingestion_version": "excel_sectioned_feature",
                })

    return chunks


def _chunks_for_one_sheet(df: pd.DataFrame, sheet_name: str, file_name: str) -> List[Dict]:
    """
    Build atomic knowledge chunks for a single sheet (DataFrame).
    Used for generic Excel sheets that do NOT match the sectioned feature matrix format.
    Shared by extract_excel_rows_as_chunks and extract_csv_rows_as_chunks when format is generic_table.
    """
    from app.semantic_normalizer import map_column_indices, row_to_raw_kv
    from app.migration_resolver import normalize_migration_column, migration_type_to_display

    chunks = []
    if df.empty or len(df.columns) == 0:
        return chunks

    # Calculate migration type early so it's available for all chunks (including limitations)
    sheet_migration_type = normalize_migration_column(sheet_name)
    display_migration_sheet = migration_type_to_display(sheet_migration_type) if sheet_migration_type else sheet_name

    # --- Heuristic: Infer headers if missing ---
    # Many sheets lack "Feature" / "Description" headers and just have raw data (Title Row -> Data).
    # Pandas reads Title Row as headers, leaving other cols as "Unnamed: 1", "Unnamed: 2".
    # We rename them based on content pattern matching.
    
    # Check if we already have good headers
    existing_headers = [str(c).lower().strip() for c in df.columns]
    has_feature = any(x in existing_headers for x in ["feature", "capability", "item"])
    has_status = any(x in existing_headers for x in ["supported", "status", "availability", "yes/no"])
    
    if not (has_feature and has_status):
        # Infer based on content sampling (first 10 rows)
        sample = df.head(10)
        rename_map = {}
        
        for col in df.columns:
            col_str = str(col).lower()
            # Don't rename if it already looks meaningful
            if any(k in col_str for k in ["feature", "status", "supported", "description", "details", "limitations"]):
                continue
            # Never rename columns that are migration paths (Slack to Teams, Meta to Google Chat, etc.)
            if normalize_migration_column(str(col).strip()):
                continue
                
            # Analyze column content
            col_vals = sample[col].astype(str).tolist()
            valid_vals = [v.lower().strip() for v in col_vals if v.lower().strip() not in ("nan", "", "none")]
            if not valid_vals:
                continue
                
            # Check for Status (Yes/No/NA) — but only if column name is not a migration path (already skipped above)
            # Do NOT rename to "Supported" when the column header looks like a feature/capability name
            # (e.g. transposed matrix: "Suppressing Email Notification", "Inner file permissions", "OneTime").
            # Otherwise we lose which feature each column is and all chunks show "Feature: Supported".
            col_lower = col_str.strip()
            is_likely_feature_name = (
                " " in col_lower or "-" in col_lower
                or any(k in col_lower for k in [
                    "permission", "notification", "version", "filter", "timestamp", "comment",
                    "folder", "file", "share", "link", "drive", "path", "character", "embed",
                    "suppress", "combination", "onetime", "delta", "root", "sub", "inner",
                    "external", "preserve", "selective", "long", "special", "box", "note",
                    "papers", "golden", "egnyte", "citrix", "mydrive", "shared", "availability",
                ])
            )
            yes_no_count = sum(1 for v in valid_vals if v in ("yes", "no", "pro", "na", "n/a", "partial"))
            if yes_no_count / len(valid_vals) > 0.6 and not is_likely_feature_name:
                rename_map[col] = "Supported"
                continue
                
            # Check for Description (Long text)
            avg_len = sum(len(v) for v in valid_vals) / len(valid_vals)
            if avg_len > 40: # Arbitrary threshold for description text
                rename_map[col] = "Description"
                continue
                
        # If we found mappings, apply them
        if rename_map:
            df.rename(columns=rename_map, inplace=True)
            # Log for debugging (in a real scenario)
            # print(f"Renamed columns in {sheet_name}: {rename_map}")
            
        # Fallback: If Column 0 is still unknown/unnamed and looked like a feature list?
        # Usually Col 0 is the Feature. If it wasn't renamed to Supported/Desc, map it to Feature
        col0 = df.columns[0]
        col0_str = str(col0).lower()
        if "unnamed" in col0_str or col0_str in ("feature", "features included"): # "Features Included" is a common title-as-header
             # Check if it was already mapped
             if col0 not in rename_map.values():
                 df.rename(columns={col0: "Feature"}, inplace=True)

    # --- End Heuristic ---

    def _cell_str(v) -> str:
        if v is None:
            return ""
        if isinstance(v, float) and str(v) == "nan":
            return ""
        s = str(v).strip()
        return "" if s.lower() == "nan" else s

    cols = [_cell_str(c) for c in df.columns]
    is_limitations_sheet = "limitation" in sheet_name.lower() or "out of scope" in sheet_name.lower()

    def _section_category(text: str) -> str:
        """Normalize section headers found inside a sheet (not just in sheet name)."""
        t = (text or "").strip().lower()
        if not t:
            return ""
        if "out of scope" in t:
            return "out_of_scope"
        if "limitation" in t:
            return "limitations"
        if "feature" in t or "capabilit" in t:
            return "features"
        return ""

    migration_columns = []
    if len(cols) >= 3:
        for col in cols[2:]:
            mt = normalize_migration_column(col)
            if mt:
                migration_columns.append((col, mt))

    is_matrix_sheet = len(migration_columns) >= 1
    migration_summaries = {}

    # ----- Layer 1: Raw truth (one raw_content chunk per sheet) -----
    raw_lines = [
        "Source: SharePoint",
        f"File: {file_name}",
        f"Sheet: {sheet_name}",
        "",
        "Headers:",
        " | ".join(str(c) for c in cols),
        "",
        "Rows:",
    ]
    for _, r in df.iterrows():
        if r.isna().all():
            continue
        row_vals = []
        for i in range(len(cols)):
            v = r.iloc[i] if i < len(r) else None
            val = str(v).strip() if pd.notna(v) and str(v) != "nan" else ""
            row_vals.append(val)
        raw_lines.append(" | ".join(row_vals))

    if len(raw_lines) > 8:
        chunks.append({
            "content": "\n".join(raw_lines),
            "chunk_type": "raw_content",
            "feature": None,
            "supported": None,
            "limitation": None,
            "sheet_name": sheet_name,
            "source_file": file_name,
            "raw_kv": "",
            "ingestion_version": "excel_v2_raw",
        })

    # ----- Layer 2: Atomic Facts (one chunk per feature/row) -----
    col_map = map_column_indices(cols)
    current_section_header = ""
    current_section_category = ""
    
    f_idx = col_map.get("feature")
    d_idx = col_map.get("description")
    s_idx = col_map.get("supported")
    l_idx = col_map.get("limitation")

    for index, row in df.iterrows():
        if row.isna().all():
            continue

        # Extract values early to help with section header vs feature discrimination
        feature = str(row.iloc[f_idx]).strip() if f_idx is not None and f_idx < len(row) and pd.notna(row.iloc[f_idx]) else ""
        description = str(row.iloc[d_idx]).strip() if d_idx is not None and d_idx < len(row) and pd.notna(row.iloc[d_idx]) else ""
        supported = row.iloc[s_idx] if s_idx is not None and s_idx < len(row) else None
        supported_str = str(supported).strip() if supported is not None and str(supported).lower() != "nan" else ""

        # Section headers can appear as rows inside a sheet (common in "Limitations and features.xlsx").
        first_two = ""
        try:
            c0 = _cell_str(row.iloc[0]) if len(row) > 0 else ""
            c1 = _cell_str(row.iloc[1]) if len(row) > 1 else ""
            first_two = c0 or c1
        except Exception:
            first_two = ""
            
        if first_two:
            cat = _section_category(first_two)
            # Treat short "label-like" rows as section headers IF they don't have supported/description data
            # This prevents "Test Feature 1" (which has status) from being eaten as a header.
            if cat and len(first_two) <= 60 and not supported_str and not description:
                current_section_header = first_two
                current_section_category = cat
                continue
        
        # Capture limitation/notes from the row if available
        limitation_text = str(row.iloc[l_idx]).strip() if l_idx is not None and l_idx < len(row) and pd.notna(row.iloc[l_idx]) else ""
        if limitation_text.lower() == "nan":
            limitation_text = ""

        if not feature:
            # If feature is empty but we have description/limitation text, 
            # and we are in a limitations context, treat it as a general limitation.
            has_content = (description and description.strip()) or (limitation_text and limitation_text.strip())
            is_limitations_context = is_limitations_sheet or current_section_category in ("limitations", "out_of_scope")
            
            if is_limitations_context and has_content:
                # Use section header as feature name context, or generic
                feature = current_section_header or "General Limitation"
            elif feature.lower().strip() in ["feature name", "feature", "capabilities", "description", "status", "supported", "notes", "remarks"]:
                # specific skip for header-like rows that are not headers
                continue
            elif not feature.strip():
                # IN LIMITATIONS CONTEXT: If feature is empty, but we have long text in Col 0 (which might be mapped to feature but deemed empty?), 
                # check if there's untracked content in the row.
                # Actually, 'feature' var comes from f_idx. If f_idx is 0, 'feature' IS the content of Col 0.
                # If 'feature' is empty, it means Col 0 is empty.
                # But maybe 'description' has the text?
                if is_limitations_context and (description or limitation_text):
                     feature = current_section_header or "General Limitation"
                else:
                    continue

        raw_dict = {}
        for i, col in enumerate(cols):
            if i < len(row):
                v = row.iloc[i]
                # Keep raw keys intact initially; filtering should ideally happen at display time 
                # or we should rename them if they contain real data.
                key = str(col).strip() if col else f"Col{i}"
                if key.lower().startswith("unnamed:"):
                    # Only skip if value is empty/nan, otherwise keep it as it might be 'Description'
                    if not pd.notna(v) or str(v).strip() == "":
                        continue
                raw_dict[key] = str(v).strip() if pd.notna(v) else ""

        raw_kv_str = row_to_raw_kv(raw_dict, sheet_name=sheet_name, row_index=index)

        is_limitations_context = is_limitations_sheet or current_section_category in ("limitations", "out_of_scope")
        if is_limitations_context:
            text = f"{feature}: {description}" if description else feature
            if limitation_text:
                text += f" | Note: {limitation_text}"
            
            section_label = current_section_header or ("Limitations" if is_limitations_sheet else "")
            category_line = f"Category: {section_label}\n" if section_label else ""
            # Include Yes/No status in content so the LLM sees it (metadata alone is not in context)
            if supported is not None and str(supported).strip():
                s = str(supported).strip().upper()
                if s in ("NA", "N/A"):
                    status_line = "Supported: NOT AVAILABLE\n"
                elif s in ("NO", "N"):
                    status_line = "Supported: No\n"
                elif s in ("YES", "Y"):
                    status_line = "Supported: Yes\n"
                else:
                    status_line = f"Supported: {supported}\n"
            else:
                status_line = "Supported: No\n"
            content_str = f"Limitation for {display_migration_sheet}: {text}\n{status_line}{category_line}Source: {file_name} | Sheet: {sheet_name}"
            supported_meta = str(supported).strip() if supported is not None and str(supported).strip() else "No"
            chunks.append({
                "content": content_str,
                "chunk_type": "limitation",
                "feature": None,
                "supported": supported_meta,
                "limitation": text,
                "sheet_name": sheet_name,
                "source_file": file_name,
                "raw_kv": raw_kv_str,
                "migration_type": sheet_migration_type,  # Apply calculated migration type
                "display_migration": display_migration_sheet,
                "section_title": section_label or None,
            })
            continue

        # Standard feature chunk
        content_parts = [f"Feature: {feature}"]
        if supported is not None and str(supported).strip():
            s = str(supported).strip()
            if s.upper() in ("NA", "N/A"):
                content_parts.append("Supported: NOT AVAILABLE")
            elif s.lower() == "no":
                content_parts.append("Supported: NOT SUPPORTED")
            else:
                content_parts.append(f"Supported: {supported}")
        if description:
            content_parts.append(f"Description: {description}")
        
        # Include limitation note if present
        if limitation_text:
            content_parts.append(f"Limitation: {limitation_text}")
            
        if current_section_header:
            content_parts.append(f"Category: {current_section_header}")
        content_parts.append(f"Source: {file_name} | Sheet: {sheet_name}")

        # Intent labeling (structural, non-hardcoded)
        row_supported_str = str(supported).strip() if supported is not None else ""
        base_chunk_type = "feature_capability"
        if description and not row_supported_str:
            base_chunk_type = "definition"

        chunks.append({
            "content": "\n".join(content_parts),
            "chunk_type": base_chunk_type,
            "feature": feature,
            "supported": str(supported) if supported is not None else None,
            "limitation": limitation_text if limitation_text else None,
            "sheet_name": sheet_name,
            "source_file": file_name,
            "raw_kv": raw_kv_str,
            "migration_type": sheet_migration_type,
            "display_migration": display_migration_sheet,
            "section_title": current_section_header or None,
        })

        # Mixed rows: if both Supported and Description exist, also emit a definition chunk.
        if description and row_supported_str:
            def_parts = [
                f"Feature: {feature}",
                f"Description: {description}"
            ]
            if limitation_text:
                def_parts.append(f"Limitation: {limitation_text}")
            
            if current_section_header:
                def_parts.append(f"Category: {current_section_header}")
            
            def_parts.append(f"Source: {file_name} | Sheet: {sheet_name}")
            
            chunks.append({
                "content": "\n".join(def_parts).strip(),
                "chunk_type": "definition",
                "feature": feature,
                "supported": None,
                "limitation": limitation_text if limitation_text else None,
                "sheet_name": sheet_name,
                "source_file": file_name,
                "raw_kv": raw_kv_str,
                "migration_type": sheet_migration_type,
                "display_migration": display_migration_sheet,
                "section_title": current_section_header or None,
                "ingestion_version": "excel_v3_mixed_definition",
            })

        if is_matrix_sheet:
            for col_name, migration_type in migration_columns:
                try:
                    col_idx = cols.index(col_name)
                    val = str(row.iloc[col_idx]).strip() if col_idx < len(row) and pd.notna(row.iloc[col_idx]) else ""
                except (ValueError, IndexError):
                    continue

                # Ingest all non-empty cells including No/NA so the bot can answer correctly
                if not val:
                    continue

                # Normalize for display and retrieval
                val_upper = val.upper()
                if val_upper == "NO":
                    status = "No"
                elif val_upper in ("NA", "N/A"):
                    status = "Not Applicable"
                else:
                    status = val

                if migration_type not in migration_summaries:
                    migration_summaries[migration_type] = {}
                migration_summaries[migration_type][feature] = status

                display_migration = migration_type_to_display(migration_type)
                m_content = [
                    f"Migration: {display_migration}",
                    f"Feature: {feature}",
                    f"Value/Status: {status}",
                ]
                if description:
                    m_content.append(f"Description: {description}")
                if limitation_text:
                    m_content.append(f"Limitation: {limitation_text}")
                if current_section_header:
                    m_content.append(f"Category: {current_section_header}")
                m_content.append(f"Source: {file_name} | Sheet: {sheet_name}")
                
                chunks.append({
                    "content": "\n".join(m_content),
                    "chunk_type": "feature_capability",
                    "feature": feature,
                    "supported": status,
                    "limitation": limitation_text if limitation_text else None,
                    "sheet_name": sheet_name,
                    "source_file": file_name,
                    "raw_kv": raw_kv_str,
                    "migration_type": migration_type,
                    "display_migration": display_migration,
                    "ingestion_version": "excel_v2_matrix_cell",
                    "section_title": current_section_header or None,
                })
        
        # ----- Transposed Matrix Support (Row = Migration Path, Cols = Features) -----
        # If the "Feature" column actually contains a Migration Path (e.g. "Box - OneDrive"),
        # and we haven't detected standard migration columns, then this is a transposed row.
        if not is_matrix_sheet and feature:
            row_migration_type = normalize_migration_column(feature)
            if row_migration_type:
                # Iterate all columns to find features (skip the migration name col itself)
                row_display_migration = migration_type_to_display(row_migration_type)
                
                for j, col_name in enumerate(cols):
                    # Skip the identity column (where the migration name is found)
                    if f_idx is not None and j == f_idx:
                        continue
                    
                    # Skip special columns if mapped
                    if (d_idx is not None and j == d_idx) or \
                       (l_idx is not None and j == l_idx) or \
                       (s_idx is not None and j == s_idx):
                        continue
                        
                    # Skip empty headers or values
                    if not col_name or not col_name.strip():
                        continue
                        
                    val = str(row.iloc[j]).strip() if j < len(row) and pd.notna(row.iloc[j]) else ""
                    if not val or val.lower() == "nan":
                        continue

                    # Feature is the column header
                    t_feature = col_name.strip()
                    
                    # Normalize Status
                    val_upper = val.upper()
                    if val_upper == "NO":
                        status = "No"
                    elif val_upper in ("NA", "N/A"):
                        status = "Not Applicable"
                    elif val_upper == "YES":
                        status = "Yes"
                    else:
                        status = val

                    # Build Content
                    t_content = [
                        f"Migration: {row_display_migration}",
                        f"Feature: {t_feature}",
                        f"Value/Status: {status}",
                    ]
                    if description: # If there's a description col, it applies to the migration broadly? Or maybe not valid here.
                        t_content.append(f"Description: {description}")
                    if limitation_text:
                        t_content.append(f"Limitation: {limitation_text}")
                    
                    t_content.append(f"Source: {file_name} | Sheet: {sheet_name}")

                    chunks.append({
                        "content": "\n".join(t_content),
                        "chunk_type": "feature_capability",
                        "feature": t_feature,
                        "supported": status,
                        "limitation": limitation_text if limitation_text else None,
                        "sheet_name": sheet_name,
                        "source_file": file_name,
                        "raw_kv": raw_kv_str,
                        "migration_type": row_migration_type,
                        "display_migration": row_display_migration,
                        "ingestion_version": "excel_v2_transposed_cell",
                        "section_title": current_section_header or None,
                    })

    # ----- Layer 3: Capability Summaries (one per migration path) -----
    if is_matrix_sheet and migration_summaries:
        for migration_type, row_features in migration_summaries.items():
            if len(row_features) < 3:
                continue
            display_migration = migration_type_to_display(migration_type)
            content_lines = [
                f"Migration combination: {display_migration}",
                "",
                "Capabilities:",
            ]
            for feat, val in sorted(row_features.items()):
                content_lines.append(f"- {feat.replace('_', ' ').title()}: {val}")
            content_lines.append(f"Source: {file_name} | Sheet: {sheet_name}")
            summary_content = "\n".join(content_lines)
            chunks.append({
                "content": summary_content,
                "chunk_type": "migration_capability_summary",
                "feature": None,
                "supported": None,
                "limitation": None,
                "sheet_name": sheet_name,
                "source_file": file_name,
                "raw_kv": "",
                "migration_type": migration_type,
                "migration_combination": display_migration,
                "ingestion_version": "excel_v2_migration_summary",
            })

    return chunks


def extract_excel_rows_as_chunks(excel_path: str, display_file_name: str = None) -> List[Dict]:
    """
    Extract Excel as atomic knowledge chunks: one row = one or more chunks (feature + optional limitation).
    Uses semantic normalizer for column mapping; uses migration_resolver for canonical migration_type.
    Matrix sheets: cols[0]=feature, cols[1]=description, cols[2:]=migration columns (one chunk per cell).
    Non-matrix sheets: one chunk per row; migration_type from sheet name if it normalizes.

    Args:
        excel_path: Path to the Excel file (may be a temp file).
        display_file_name: Optional display name for the file (e.g. original SharePoint item name).
    """
    chunks = []
    try:
        with pd.ExcelFile(excel_path) as excel_file:
            file_name = (display_file_name or os.path.basename(excel_path)).strip() or os.path.basename(excel_path)

            for sheet_name in excel_file.sheet_names:
                try:
                    # Some workbooks (esp. capability matrices) use multi-row headers / merged cells.
                    # Try several header offsets and pick the one that best matches our semantic contract.
                    from app.semantic_normalizer import map_column_indices
                    from app.migration_resolver import normalize_migration_column

                    best_df = None
                    best_score = -1
                    for header_row in (0, 1, 2, 3):
                        try:
                            cand = pd.read_excel(excel_file, sheet_name=sheet_name, header=header_row)
                        except Exception:
                            continue
                        if cand is None or cand.empty or len(cand.columns) == 0:
                            continue
                        cols = [
                            str(c).strip()
                            if c is not None and (not isinstance(c, float) or str(c) != "nan")
                            else ""
                            for c in cand.columns
                        ]
                        col_map = map_column_indices(cols)
                        score = 0
                        # Prefer sheets where we can find Feature/Description/Supported columns
                        if "feature" in col_map:
                            score += 3
                        if "description" in col_map:
                            score += 2
                        if "supported" in col_map:
                            score += 1
                        # Prefer headers that expose migration columns (matrix layout)
                        mig = 0
                        if len(cols) >= 3:
                            for col in cols[2:]:
                                if normalize_migration_column(col):
                                    mig += 1
                        score += min(6, mig)  # cap to avoid over-weighting
                        # Penalize "Unnamed:" heavy headers (common when header row is wrong)
                        unnamed = sum(1 for c in cols if str(c).lower().startswith("unnamed"))
                        score -= min(4, unnamed)

                        if score > best_score:
                            best_score = score
                            best_df = cand

                    df = best_df if best_df is not None else pd.read_excel(excel_file, sheet_name=sheet_name)
                    sheet_format = _detect_sheet_format(df)
                    if sheet_format == "sectioned_feature_matrix":
                        chunks.extend(_chunks_for_sectioned_sheet(df, sheet_name, file_name))
                    else:
                        chunks.extend(_chunks_for_one_sheet(df, sheet_name, file_name))
                except Exception as e:
                    print(f"Error processing sheet '{sheet_name}' in {excel_path}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue

        return chunks
    except Exception as e:
        print(f"Error in extract_excel_rows_as_chunks({excel_path}): {e}")
        import traceback
        traceback.print_exc()
        return []


def extract_csv_rows_as_chunks(csv_path: str, display_file_name: str = None) -> List[Dict]:
    """
    Extract CSV as atomic knowledge chunks using the same logic as Excel (one logical "sheet").
    Treats the CSV file as a single sheet; sheet_name = file base name (e.g. "Common_Features_In_Content_Migrations2").

    Args:
        csv_path: Path to the CSV file (may be a temp file).
        display_file_name: Optional display name for the file (e.g. original SharePoint item name).
    """
    chunks = []
    try:
        file_name = (display_file_name or os.path.basename(csv_path)).strip() or os.path.basename(csv_path)
        # Use file base name as sheet name (CSV has no multiple sheets)
        sheet_name = os.path.splitext(os.path.basename(csv_path))[0].strip() or "Sheet1"

        # Try multiple encodings to handle different CSV file formats
        encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1', 'utf-16']
        df = None
        encoding_used = None
        
        for encoding in encodings:
            try:
                df = pd.read_csv(csv_path, encoding=encoding)
                encoding_used = encoding
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
            except Exception:
                # Other errors (file not found, etc.) - try next encoding
                continue
        
        if df is None:
            print(f"   [WARNING] Failed to read CSV with any encoding: {file_name}")
            return []
        
        if encoding_used != 'utf-8':
            print(f"   [INFO] CSV read with {encoding_used} encoding: {file_name}")
        
        sheet_format = _detect_sheet_format(df)
        if sheet_format == "sectioned_feature_matrix":
            chunks = _chunks_for_sectioned_sheet(df, sheet_name, file_name)
        else:
            chunks = _chunks_for_one_sheet(df, sheet_name, file_name)
        return chunks
    except Exception as e:
        print(f"   [WARNING] Error in extract_csv_rows_as_chunks({csv_path}): {e}")
        import traceback
        traceback.print_exc()
        return []

def get_excel_summary(excel_path: str) -> Dict:
    """Get a summary of an Excel file's structure."""
    try:
        excel_file = pd.ExcelFile(excel_path)
        summary = {
            "file_name": os.path.basename(excel_path),
            "sheet_count": len(excel_file.sheet_names),
            "sheet_names": excel_file.sheet_names,
            "total_rows": 0,
            "total_columns": 0
        }
        
        for sheet_name in excel_file.sheet_names:
            try:
                df = pd.read_excel(excel_path, sheet_name=sheet_name)
                summary["total_rows"] += len(df)
                summary["total_columns"] = max(summary["total_columns"], len(df.columns))
            except:
                continue
                
        return summary
    except Exception as e:
        return {"error": str(e)}
