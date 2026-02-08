import os
import re
from typing import List, Dict, Optional

try:
    from pypdf import PdfReader as PyPdfReader
except ImportError:
    PyPdfReader = None
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

# Try to import PyMuPDF, fallback to alternatives if not available
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    print("PyMuPDF not available, using alternative PDF processing methods")

# Try to import pdfplumber as alternative
try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    print("pdfplumber not available, using pypdf only")

# Resolve PDFObjRef (pdfminer lazy refs) before treating as dict/iterable
try:
    from pdfminer.pdftypes import PDFObjRef
except ImportError:
    PDFObjRef = type(None)  # sentinel so isinstance never matches

# OCR/Image imports removed: image extraction from PDFs is disabled.


def resolve_pdf_obj(value):
    """Safely resolve PDFObjRef to underlying object. Return value unchanged if not a ref."""
    if isinstance(value, PDFObjRef):
        try:
            return value.resolve()
        except Exception:
            return None
    return value


def is_line_heading(line_text: str) -> bool:
    """
    Heuristic heading detector for PDF line text.
    Used by extract_pdf_atomic_chunks() to assign section_title.
    """
    if not line_text or not isinstance(line_text, str):
        return False
    s = line_text.strip()
    if len(s) < 3 or len(s) > 90:
        return False
    # Numbered headings like "1. Introduction" / "2) Setup"
    if re.match(r"^\d{1,2}\s*[.)]\s+\S+", s):
        return True
    # All-caps short lines (common in PDFs)
    letters = [ch for ch in s if ch.isalpha()]
    if letters:
        upper_ratio = sum(1 for ch in letters if ch.isupper()) / max(1, len(letters))
        if upper_ratio >= 0.85 and len(letters) >= 5:
            return True
    # Title-cased short lines
    words = [w for w in re.split(r"\s+", s) if w]
    if 2 <= len(words) <= 10:
        titled = sum(1 for w in words if w[:1].isupper())
        if titled / len(words) >= 0.7:
            return True
    return False


# Image extraction from PDFs is disabled; only text and tables are extracted.


def extract_text_from_txt(txt_path: str) -> str:
    """Extract text from a text file."""
    try:
        with open(txt_path, 'r', encoding='utf-8') as file:
            return file.read()
    except Exception as e:
        print(f"Error reading text file {txt_path}: {e}")
        return ""

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from a PDF file using multiple methods for better coverage."""
    text = ""
    
    # Method 1: Try pdfplumber first (most reliable for text extraction)
    if PDFPLUMBER_AVAILABLE:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            if text.strip():
                return text
        except Exception as e:
            print(f"pdfplumber failed for {pdf_path}: {e}")
    
    # Method 2: Try PyMuPDF (fitz) if available - better for complex layouts
    if PYMUPDF_AVAILABLE:
        try:
            doc = fitz.open(pdf_path)
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text += page.get_text()
            doc.close()
            if text.strip():
                return text
        except Exception as e:
            print(f"PyMuPDF failed for {pdf_path}: {e}")
    
    # Method 3: Fallback to pypdf
    if PyPdfReader:
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPdfReader(file)
                for page in pdf_reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
        except Exception as e:
            print(f"pypdf failed for {pdf_path}: {e}")
            return ""
    
    return text


def _extract_text_pages_fitz(doc: "fitz.Document", start_page: int, end_page: int) -> str:
    """Extract text from PyMuPDF doc for pages [start_page, end_page] (0-based inclusive)."""
    parts = []
    for p in range(start_page, min(end_page + 1, len(doc))):
        page = doc.load_page(p)
        parts.append(page.get_text())
    return "\n".join(parts).strip()


def _split_by_heading_pattern(text: str) -> List[tuple]:
    """
    Split full text into (heading, content) by detecting section headers.
    Headers: short numbered lines (1. Title), markdown #, or short ALL-CAPS lines.
    """
    sections = []
    # Pattern: line that looks like a section header (short, often numbered or title case)
    header_pattern = re.compile(
        r"^(?:(?:\d+[.)]\s*)?[A-Z][^\n]{1,80})$|^#{1,3}\s+.+$",
        re.MULTILINE,
    )
    last_end = 0
    last_title = "Document"
    for m in header_pattern.finditer(text):
        start = m.start()
        if start > last_end and (start - last_end) > 20:
            content = text[last_end:start].strip()
            if content:
                sections.append((last_title, content))
        last_title = m.group(0).strip().lstrip("#").strip()
        last_end = m.end()
    if last_end < len(text):
        content = text[last_end:].strip()
        if content:
            sections.append((last_title, content))
    return sections


def extract_pdf_sections_as_documents(
    pdf_path: str,
    file_name: Optional[str] = None,
) -> List[Document]:
    """
    Extract PDF as one Document per section (heading → chunk).
    Uses PyMuPDF TOC when available; otherwise splits full text by heading patterns.
    Returns list of Documents with metadata: section_title, file_name, source_type.
    """
    file_name = file_name or os.path.basename(pdf_path)
    sections: List[tuple] = []  # (title, content)

    if PYMUPDF_AVAILABLE:
        try:
            doc = fitz.open(pdf_path)
            try:
                toc = doc.get_toc()
                if toc:
                    # toc: list of (level, title, page) with page 0-based
                    num_pages = len(doc)
                    for i, (level, title, start_page) in enumerate(toc):
                        start_page = max(0, min(start_page, num_pages - 1))
                        end_page = start_page
                        if i + 1 < len(toc):
                            end_page = max(0, toc[i + 1][2] - 1)
                        else:
                            end_page = num_pages - 1
                        end_page = min(end_page, num_pages - 1)
                        if end_page < start_page:
                            end_page = start_page
                        content = _extract_text_pages_fitz(doc, start_page, end_page)
                        if content or title.strip():
                            sections.append((title.strip() or f"Section {i+1}", content))
                else:
                    # No TOC: get full text and split by heading pattern
                    full = []
                    for p in range(len(doc)):
                        full.append(doc.load_page(p).get_text())
                    text = "\n".join(full)
                    sections = _split_by_heading_pattern(text)
                    if not sections:
                        sections = [("Document", text)] if text.strip() else []
            finally:
                doc.close()
        except Exception as e:
            print(f"PyMuPDF section extraction failed for {pdf_path}: {e}")
            sections = []

    if not sections and (PDFPLUMBER_AVAILABLE or PyPdfReader):
        text = extract_text_from_pdf(pdf_path)
        if text.strip():
            sections = _split_by_heading_pattern(text)
            if not sections:
                sections = [("Document", text)]

    docs = []
    for title, content in sections:
        if not content and not title:
            continue
        doc = Document(
            page_content=content or title,
            metadata={
                "section_title": title,
                "file_name": file_name,
                "source_type": "pdf",
                "source": file_name,
            },
        )
        docs.append(doc)
    return docs


def extract_pdf_tables_as_chunks(
    pdf_path: str,
    file_name: Optional[str] = None,
) -> List[Dict]:
    """
    Extract PDF tables as atomic chunks: one table row = one rule/feature chunk.
    Uses pdfplumber for table detection; uses semantic normalizer for column mapping.
    Returns list of dicts with keys: content, chunk_type, feature, supported, limitation, source_file, raw_kv, page_number.
    """
    file_name = file_name or os.path.basename(pdf_path)
    chunks: List[Dict] = []

    if not PDFPLUMBER_AVAILABLE:
        return chunks

    try:
        from app.semantic_normalizer import normalize_columns, row_to_raw_kv
        from app.migration_resolver import normalize_migration_column, migration_type_to_display
    except ImportError:
        return chunks

    def _looks_like_definition_col(h: str) -> bool:
        """
        Structural (non-feature) heuristic: does a header look like a definition/explanation column?
        We intentionally avoid any product/feature hardcoding here.
        """
        s = (h or "").strip().lower()
        if not s:
            return False
        return any(tok in s for tok in ("description", "details", "notes", "meaning", "explanation", "remarks", "info"))

    def _extract_tables_robust(page) -> List[list]:
        """
        Extract tables from a pdfplumber page using multiple strategies.

        pdfplumber exposes 2 common APIs:
        - page.extract_tables(): returns list-of-rows (best effort)
        - page.find_tables(): returns Table objects that can be extracted (often finds tables extract_tables misses)

        We try extract_tables() first; if empty, fall back to find_tables(). This is critical for PDFs
        where different tables on the same page are detected by different strategies (e.g. matrix vs 2-col definitions).
        """
        try:
            tables = page.extract_tables() or []
            # Some PDFs return [] for extract_tables but do have tables discoverable via find_tables.
            if tables:
                return tables
        except Exception:
            tables = []
        # Fallback: find_tables() -> Table.extract()
        try:
            found = page.find_tables() or []
        except Exception:
            found = []
        out = []
        for t in found:
            try:
                rows = t.extract()
                if rows:
                    out.append(rows)
            except Exception:
                continue
        return out

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                tables = _extract_tables_robust(page)
                if not tables:
                    continue
                for table_idx, table in enumerate(tables):
                    if not table or len(table) < 1:
                        continue
                    # First row as header
                    header_row = table[0]
                    header_cells = [
                        (str(h).strip() if h is not None and str(h).strip() != "nan" else f"Col{i}")
                        for i, h in enumerate(header_row)
                    ]
                    header_text = " ".join(c.lower() for c in header_cells)
                    skip_first = any(
                        h in header_text
                        for h in (
                            "feature", "supported", "description", "status",
                            "limitation", "capability", "scope", "item", "yes",
                        )
                    )
                    start = 1 if skip_first and len(table) > 1 else 0

                    # Layout B: feature-per-row matrix (first col = feature, cols 1+ = migration paths)
                    migration_columns_B = []
                    for j in range(1, len(header_cells)):
                        mt = normalize_migration_column(header_cells[j])
                        if mt:
                            migration_columns_B.append((j, header_cells[j], mt))
                    is_feature_row_matrix = len(migration_columns_B) >= 1
                    migration_summaries: Dict[str, Dict[str, str]] = {}
                    # Layer 2 layout (structure only)
                    table_layout = "B" if is_feature_row_matrix else ("A" if len(header_cells) >= 4 else "C")

                    # ----- Layer 1: Raw truth (one raw_content chunk per table) -----
                    raw_lines = [
                        "Source: SharePoint",
                        f"File: {file_name}",
                        f"Page: {page_num}",
                        f"Table: {table_idx}",
                        "",
                        "Headers:",
                        " | ".join(header_cells),
                        "",
                        "Rows:",
                    ]
                    for r in table[start:]:
                        cells_r = [str(c).strip() if c is not None and str(c) != "nan" else "" for c in r]
                        if any(cells_r):
                            raw_lines.append(" | ".join(cells_r))
                    if len(raw_lines) > 10:
                        chunks.append({
                            "content": "\n".join(raw_lines),
                            "chunk_type": "raw_content",
                            "feature": None,
                            "supported": None,
                            "limitation": None,
                            "source_file": file_name,
                            "raw_kv": "",
                            "page_number": page_num,
                            "layout": None,
                        })

                    for row_idx, row in enumerate(table[start:], start=start):
                        cells = [
                            str(c).strip() if c is not None and str(c) != "nan" else ""
                            for c in row
                        ]
                        if not any(cells):
                            continue
                        row_dict = {}
                        for i, col in enumerate(header_cells):
                            row_dict[col] = cells[i] if i < len(cells) else ""

                        # ----- Layer 2: Structural semantics (one table_row per row) -----
                        table_id = f"page{page_num}_table{table_idx}"
                        raw_kv_row = row_to_raw_kv(row_dict, sheet_name=table_id, row_index=row_idx)
                        row_content_lines = [
                            f"Table row (layout {table_layout}):",
                            "Headers: " + " | ".join(header_cells),
                        ]
                        for k, v in row_dict.items():
                            if v:
                                row_content_lines.append(f"{k}: {v}")
                        row_content_lines.append(f"Source: {file_name} (page {page_num})")
                        chunks.append({
                            "content": "\n".join(row_content_lines),
                            "chunk_type": "table_row",
                            "feature": None,
                            "supported": None,
                            "limitation": None,
                            "source_file": file_name,
                            "raw_kv": raw_kv_row,
                            "page_number": page_num,
                            "layout": table_layout,
                        })

                        # Layout B: feature in col0, migrations in cols 1+ (e.g. "Citrix file share as source")
                        if is_feature_row_matrix:
                            feature = (cells[0] if cells else "").strip()
                            if not feature:
                                continue
                            # If table includes a description-like column (commonly col1), emit a definition chunk too.
                            desc_idx = None
                            if len(header_cells) > 1 and _looks_like_definition_col(header_cells[1]):
                                desc_idx = 1
                            if desc_idx is not None:
                                desc_val = (cells[desc_idx] if desc_idx < len(cells) else "").strip()
                                if desc_val:
                                    chunks.append({
                                        "content": "\n".join([
                                            f"Feature: {feature}",
                                            f"Description: {desc_val}",
                                            f"Source: {file_name} (page {page_num})",
                                        ]),
                                        "chunk_type": "definition",
                                        "feature": feature,
                                        "supported": None,
                                        "limitation": None,
                                        "source_file": file_name,
                                        "raw_kv": raw_kv_row,
                                        "page_number": page_num,
                                    })
                            for j, col_header, migration_type in migration_columns_B:
                                value = (cells[j] if j < len(cells) else "").strip()
                                if not value:
                                    continue
                                display_migration = migration_type_to_display(migration_type)
                                raw_kv_str = row_to_raw_kv(
                                    {col_header: value},
                                    sheet_name=f"page{page_num}_table{table_idx}",
                                    row_index=row_idx,
                                )
                                content_parts = [
                                    f"Feature: {feature}",
                                    f"Migration: {display_migration}",
                                    f"Supported: {value}",
                                    f"Source: {file_name} (page {page_num})",
                                ]
                                chunks.append({
                                    "content": "\n".join(content_parts),
                                    "chunk_type": "feature_capability",
                                    "feature": feature,
                                    "supported": value or None,
                                    "limitation": None,
                                    "source_file": file_name,
                                    "raw_kv": raw_kv_str,
                                    "page_number": page_num,
                                    "migration_type": migration_type,
                                    "migration_combination": display_migration,
                                })
                                if value.upper() in ("YES", "NO", "NA", "N/A") or value.lower() in ("yes", "no"):
                                    migration_summaries.setdefault(migration_type, {})[feature] = value
                                if value.lower() in ("no", "na", "n/a"):
                                    chunks.append({
                                        "content": f"Limitation: {feature} is not supported for {display_migration}. Value: {value}.",
                                        "chunk_type": "limitation",
                                        "feature": feature,
                                        "supported": value,
                                        "limitation": f"Not supported for {display_migration}",
                                        "source_file": file_name,
                                        "raw_kv": raw_kv_str,
                                        "page_number": page_num,
                                        "migration_type": migration_type,
                                        "migration_combination": display_migration,
                                    })
                            continue

                        # Layout A: first column = migration/row identity, rest = capabilities (YES/NO/NA)
                        row_identity = (cells[0] if cells else "").strip()
                        capability_values = ("YES", "NO", "NA", "N/A", "Yes", "No")
                        count_capability = sum(
                            1 for c in cells[1:]
                            if c and (c.upper() in ("YES", "NO", "NA", "N/A") or c.lower() in ("yes", "no"))
                        )
                        is_matrix_row = (
                            len(header_cells) >= 4
                            and len(cells) >= 4
                            and row_identity
                            and count_capability >= 3
                        )

                        if is_matrix_row:
                            # Migration-centric: one feature chunk per (row_identity, column), then one summary per row
                            row_features: Dict[str, str] = {}
                            for j in range(1, min(len(header_cells), len(cells))):
                                col_name = header_cells[j]
                                cell_value = cells[j].strip()
                                if not cell_value:
                                    continue
                                if cell_value.upper() in ("YES", "NO", "NA", "N/A") or cell_value.lower() in ("yes", "no"):
                                    row_features[col_name] = cell_value
                                # Existing: emit feature chunk (Feature × Migration)
                                content_parts = [
                                    f"Feature: {col_name}",
                                    f"Migration: {row_identity}",
                                    f"Supported: {cell_value}" if cell_value else "",
                                    f"Source: {file_name} (page {page_num})",
                                ]
                                content_parts = [p for p in content_parts if p]
                                raw_kv_str = row_to_raw_kv(
                                    {col_name: cell_value},
                                    sheet_name=f"page{page_num}_table{table_idx}",
                                    row_index=row_idx,
                                )
                                chunks.append({
                                    "content": "\n".join(content_parts),
                                    "chunk_type": "feature_capability",
                                    "feature": col_name,
                                    "supported": cell_value or None,
                                    "limitation": None,
                                    "source_file": file_name,
                                    "raw_kv": raw_kv_str,
                                    "page_number": page_num,
                                    "migration_combination": row_identity,
                                })
                                if cell_value.lower() in ("no", "na", "n/a"):
                                    chunks.append({
                                        "content": f"Limitation: {col_name} is not supported for {row_identity}. Value: {cell_value}.",
                                        "chunk_type": "limitation",
                                        "feature": col_name,
                                        "supported": cell_value,
                                        "limitation": f"Not supported for {row_identity}",
                                        "source_file": file_name,
                                        "raw_kv": raw_kv_str,
                                        "page_number": page_num,
                                        "migration_combination": row_identity,
                                    })
                            # ADD: one migration-centric summary chunk per row
                            if len(row_features) >= 3:
                                lines = [
                                    f"Migration: {row_identity}",
                                    "",
                                    "Capabilities:",
                                ]
                                for feat, val in sorted(row_features.items()):
                                    lines.append(f"- {feat.replace('_', ' ').title()}: {val}")
                                lines.append(f"Source: {file_name} (page {page_num})")
                                summary_content = "\n".join(lines)
                                chunks.append({
                                    "content": summary_content,
                                    "chunk_type": "migration_capability_summary",
                                    "feature": None,
                                    "supported": None,
                                    "limitation": None,
                                    "source_file": file_name,
                                    "raw_kv": "",
                                    "page_number": page_num,
                                    "migration_combination": row_identity,
                                    "ingestion_version": "pdf_v2_migration_summary",
                                })
                            continue

                        # Record-per-row: existing logic (one row = one feature record)
                        normalized, raw = normalize_columns(row_dict)
                        feature = (normalized.get("feature") or "").strip()
                        supported = (normalized.get("supported") or "").strip()
                        description = (normalized.get("description") or "").strip()
                        limitation = (normalized.get("limitation") or "").strip()
                        table_id = f"page{page_num}_table{table_idx}"
                        raw_kv_str = row_to_raw_kv(raw, sheet_name=table_id, row_index=row_idx)
                        if not feature and row_dict:
                            first_val = next((v for v in row_dict.values() if v), "")
                            if first_val and len(first_val) > 2:
                                feature = first_val
                        if not feature:
                            continue
                        content_parts = [f"Feature: {feature}"]
                        if description:
                            content_parts.append(f"Description: {description}")
                        if supported:
                            content_parts.append(f"Supported: {supported}")
                        content_parts.append(f"Source: {file_name} (page {page_num})")
                        # Decide intent:
                        # - If supported is missing but description exists, this is a definition chunk.
                        # - If supported exists (Yes/No/NA/etc.), it's a feature_capability chunk.
                        chunk_type = "feature_capability"
                        if (not supported) and description:
                            chunk_type = "definition"
                        chunks.append({
                            "content": "\n".join(content_parts),
                            "chunk_type": chunk_type,
                            "feature": feature,
                            "supported": supported or None,
                            "limitation": None,
                            "source_file": file_name,
                            "raw_kv": raw_kv_str,
                            "page_number": page_num,
                        })
                        # Mixed rows: if both supported and description exist, also emit a definition chunk.
                        if supported and description:
                            chunks.append({
                                "content": "\n".join([
                                    f"Feature: {feature}",
                                    f"Description: {description}",
                                    f"Source: {file_name} (page {page_num})",
                                ]),
                                "chunk_type": "definition",
                                "feature": feature,
                                "supported": None,
                                "limitation": None,
                                "source_file": file_name,
                                "raw_kv": raw_kv_str,
                                "page_number": page_num,
                                "ingestion_version": "pdf_v3_mixed_definition",
                            })
                        supported_upper = str(supported).upper()
                        if supported_upper in ("NO", "N/A", "NA", "OUT OF SCOPE", "NOT SUPPORTED") and description:
                            chunks.append({
                                "content": f"Limitation: {feature} is not supported. Reason: {description}",
                                "chunk_type": "limitation",
                                "feature": feature,
                                "supported": supported,
                                "limitation": description,
                                "source_file": file_name,
                                "raw_kv": raw_kv_str,
                                "page_number": page_num,
                            })
                        if limitation and limitation.strip():
                            chunks.append({
                                "content": f"Limitation for {feature}: {limitation}",
                                "chunk_type": "limitation",
                                "feature": feature,
                                "supported": supported or None,
                                "limitation": limitation,
                                "source_file": file_name,
                                "raw_kv": raw_kv_str,
                                "page_number": page_num,
                            })

                    # Layout B: emit one migration-centric summary per migration (after all rows)
                    if is_feature_row_matrix and migration_summaries:
                        for migration_type, row_features in migration_summaries.items():
                            if len(row_features) < 1:
                                continue
                            display_migration = migration_type_to_display(migration_type)
                            lines = [
                                f"Migration: {display_migration}",
                                "",
                                "Capabilities:",
                            ]
                            for feat, val in sorted(row_features.items()):
                                lines.append(f"- {feat.replace('_', ' ').title()}: {val}")
                            lines.append(f"Source: {file_name} (page {page_num})")
                            summary_content = "\n".join(lines)
                            chunks.append({
                                "content": summary_content,
                                "chunk_type": "migration_capability_summary",
                                "feature": None,
                                "supported": None,
                                "limitation": None,
                                "source_file": file_name,
                                "raw_kv": "",
                                "page_number": page_num,
                                "migration_type": migration_type,
                                "migration_combination": display_migration,
                                "ingestion_version": "pdf_v2_migration_summary",
                            })
    except Exception as e:
        print(f"Error in extract_pdf_tables_as_chunks({pdf_path}): {e}")
    return chunks


def process_pdf_directory(pdf_directory: str) -> List[Document]:
    """Process all PDF files in a directory and return as LangChain Documents."""
    documents = []
    
    if not os.path.exists(pdf_directory):
        print(f"PDF directory {pdf_directory} does not exist")
        return documents
    
    pdf_files = [f for f in os.listdir(pdf_directory) if f.lower().endswith('.pdf')]
    
    if not pdf_files:
        print(f"No PDF files found in {pdf_directory}")
        return documents
    
    print(f"Processing {len(pdf_files)} PDF files...")
    
    for pdf_file in pdf_files:
        pdf_path = os.path.join(pdf_directory, pdf_file)
        print(f"Processing: {pdf_file}")
        
        try:
            # Extract text from PDF
            text = extract_text_from_pdf(pdf_path)
            source_type = "pdf"
            
            if text.strip():
                # Create a document with metadata
                doc = Document(
                    page_content=text,
                    metadata={
                        "source": pdf_file,
                        "source_type": source_type,
                        "file_path": pdf_path
                    }
                )
                documents.append(doc)
                print(f"Successfully processed {pdf_file} ({len(text)} characters)")
            else:
                print(f"Warning: No text extracted from {pdf_file}")
        except Exception as e:
            print(f"Error processing {pdf_file}: {e}")
    
    return documents

def chunk_pdf_documents(documents: List[Document], chunk_size: int = 1000, chunk_overlap: int = 200) -> List[Document]:
    """Split PDF documents into smaller chunks for better retrieval."""
    if not documents:
        return documents
    
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
    )
    
    chunked_docs = []
    for doc in documents:
        chunks = splitter.split_documents([doc])
        # Preserve metadata and add tag
        for chunk in chunks:
            chunk.metadata.update(doc.metadata)
            chunk.metadata["tag"] = "pdf"  # Tag for chatbot to identify PDF content
        chunked_docs.extend(chunks)
    
    return chunked_docs

def extract_pdf_atomic_chunks(pdf_path: str, file_name: Optional[str] = None) -> List[Dict]:
    """
    Extract PDF content as atomic truths:
    1. Tables -> feature/limitation chunks (One Row = One Rule)
    2. Text -> 'explanation' chunks (Context)
    Image extraction is disabled.
    """
    chunks = []
    file_name = file_name or os.path.basename(pdf_path)

    if not PDFPLUMBER_AVAILABLE:
        print("pdfplumber not available, skipping atomic table extraction")
        return []

    try:
        import pdfplumber

        current_section = None
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_num = i + 1
                
                # 0. Find all headings on this page with their top positions
                found_headings = []
                words = page.extract_words()
                if words:
                    # Group words by rounded top coordinate to form logical lines
                    words.sort(key=lambda x: x["top"])
                    from itertools import groupby
                    for top, line_words in groupby(words, key=lambda x: round(float(x["top"]) / 2) * 2):
                        line_text = " ".join([w["text"] for w in line_words]).strip()
                        if is_line_heading(line_text):
                            found_headings.append({"top": top, "text": line_text})

                def get_active_section(obj_top):
                    """Find the heading immediately above the given vertical position."""
                    active = current_section
                    for h in found_headings:
                        if h["top"] < obj_top:
                            active = h["text"]
                        else:
                            break
                    return active

                # 1. Extract Tables (Atomic Rules)
                tables = page.find_tables()
                table_bboxes = [t.bbox for t in tables]
                
                for table in tables:
                    rows = table.extract()
                    if not rows:
                        continue
                    
                    section_title = get_active_section(table.bbox[1]) # [1] is top

                    # Assume first row is header (resolve PDFObjRef in cells)
                    headers = []
                    for j, h in enumerate(rows[0]):
                        h = resolve_pdf_obj(h)
                        headers.append(str(h).strip() if h else f"Col{j}")

                    # Process data rows
                    for row_idx, row in enumerate(rows[1:], start=1):
                        row = [resolve_pdf_obj(c) for c in row]
                        if not any(row):
                            continue

                        # Build row dict
                        row_dict = {}
                        content_parts = []
                        for j, cell in enumerate(row):
                            if j < len(headers):
                                header = headers[j]
                                val = str(cell).strip() if cell else ""
                                row_dict[header] = val
                                if val:
                                    content_parts.append(f"{header}: {val}")
                        
                        if not content_parts: continue

                        # Atomic Chunk
                        chunks.append({
                            "content": "\n".join(content_parts),
                            "chunk_type": "feature_matrix",
                            "doc_id": f"sharepoint:{file_name}", # Placeholder, caller should update
                            "page_number": page_num,
                            "source_file": file_name,
                            "section_title": section_title,
                            "raw_data": row_dict
                        })

                # 2. Extract Text (Excluding Tables) -> Explanations
                # Filter out table areas to avoid duplicate text
                def not_within_tables(obj):
                    x0, top, x1, bottom = obj["x0"], obj["top"], obj["x1"], obj["bottom"]
                    # Check if obj is inside any table bbox
                    for (tx0, ttop, tx1, tbottom) in table_bboxes:
                        if x0 >= tx0 and x1 <= tx1 and top >= ttop and bottom <= tbottom:
                            return False
                    return True

                text = page.filter(not_within_tables).extract_text()
                if text and text.strip():
                    # For plain text, we use the first heading found on the page or previous
                    section_title = get_active_section(0) # Use page top as heuristic for whole-page text
                    # Calculate vertical position: use first word's top position or page top
                    text_position = None
                    text_words = page.filter(not_within_tables).extract_words()
                    if text_words:
                        text_position = min(w.get("top", 0) for w in text_words)
                    
                    chunks.append({
                        "content": text.strip(),
                        "chunk_type": "explanation",
                        "doc_id": f"sharepoint:{file_name}",
                        "page_number": page_num,
                        "source_file": file_name,
                        "section_title": section_title,
                        "vertical_position": text_position,  # Position for interleaving
                    })

                # Images in PDFs are not extracted (image ingestion disabled)

                # Update persistent current_section for next page
                if found_headings:
                    current_section = found_headings[-1]["text"]

    except Exception as e:
        print(f"Error in extract_pdf_atomic_chunks({pdf_path}): {e}")

    # Summary logging (only for atomic chunks - tables are counted separately in SharePoint extractor)
    text_count = sum(1 for c in chunks if c.get("chunk_type") == "explanation")
    total_atomic = len(chunks)
    if total_atomic > 0:
        print(f"   [ATOMIC] {file_name}: {total_atomic} atomic chunks ({text_count} text)")

    return chunks
