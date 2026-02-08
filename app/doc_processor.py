import os
import pandas as pd
from typing import List, Dict, Optional
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

# Try to import python-docx for Word document support
try:
    DOCX_AVAILABLE = True
    from docx import Document as DocxDocument  # Correct import - use public API
    from docx.table import Table
    from docx.text.paragraph import Paragraph
except ImportError:
    DOCX_AVAILABLE = False
    Table = type(None)
    Paragraph = type(None)
    DocxDocument = None
    print("python-docx not available, Word document processing may be limited")

def iter_block_items(parent):
    """
    Yield each paragraph and table child within *parent*, in document order.
    Each returned value is an instance of either Table or Paragraph.
    """
    if not parent: return
    
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    if hasattr(parent, "element") and hasattr(parent.element, "body"):
        parent_elm = parent.element.body
    elif hasattr(parent, "_element"):
        parent_elm = parent._element
    else:
        return

    for child in parent_elm.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)

# Try to import python-docx2txt as alternative
try:
    import docx2txt
    DOCX2TXT_AVAILABLE = True
except ImportError:
    DOCX2TXT_AVAILABLE = False
    print("docx2txt not available, using alternative methods")

def extract_text_from_docx(docx_path: str) -> str:
    """Extract text content from a Word document (.docx file)."""
    text_content = []
    
    try:
        # Method 1: Try python-docx first (most reliable)
        if DOCX_AVAILABLE:
            try:
                doc = DocxDocument(docx_path)
                
                # Add file-level metadata for better searchability
                text_content.append(f"Word document: {os.path.basename(docx_path)}")
                text_content.append(f"Contains structured text and formatting information")
                
                # Extract text from all paragraphs
                for paragraph in doc.paragraphs:
                    if paragraph.text.strip():
                        text_content.append(paragraph.text)
                
                # Extract text from tables
                for table in doc.tables:
                    for row in table.rows:
                        row_data = []
                        for cell in row.cells:
                            cell_text = cell.text.strip()
                            if cell_text:
                                row_data.append(cell_text)
                        if row_data:
                            text_content.append(" | ".join(row_data))

                # Extract text from textboxes/shapes (w:txbxContent), which are common in templates.
                # python-docx does not expose these as normal paragraphs reliably.
                try:
                    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                    tb_nodes = doc.element.body.xpath(".//w:txbxContent", namespaces=ns)
                    for tb in tb_nodes or []:
                        parts = []
                        for t in tb.xpath(".//w:t", namespaces=ns):
                            if t is not None and getattr(t, "text", None):
                                parts.append(str(t.text))
                        tb_text = " ".join(" ".join(parts).split()).strip()
                        if tb_text:
                            text_content.append(tb_text)
                except Exception:
                    pass
                
                return "\n".join(text_content)
                
            except Exception as e:
                print(f"python-docx failed for {docx_path}: {e}")
        
        # Method 2: Try docx2txt as fallback
        if DOCX2TXT_AVAILABLE:
            try:
                text = docx2txt.process(docx_path)
                if text.strip():
                    return f"Word document: {os.path.basename(docx_path)}\n\n{text}"
            except Exception as e:
                print(f"docx2txt failed for {docx_path}: {e}")
        
        # Method 3: Try to read as plain text (for some .docx files)
        try:
            with open(docx_path, 'r', encoding='utf-8', errors='ignore') as file:
                content = file.read()
                if content.strip():
                    return f"Word document: {os.path.basename(docx_path)}\n\n{content}"
        except Exception as e:
            print(f"Plain text reading failed for {docx_path}: {e}")
        
        return ""
        
    except Exception as e:
        print(f"Error reading Word document {docx_path}: {e}")
        return ""


def extract_docx_blocks_as_chunks(docx_path: str, file_name: Optional[str] = None) -> List[Dict]:
    """
    Extract DOCX as atomic chunks: one table row = one fact chunk; paragraphs = rule/process chunks.
    Maintains document order to track heading context for "Parent-Based Attachment".
    """
    from app.semantic_normalizer import normalize_columns, row_to_raw_kv, is_line_heading
    from app.migration_resolver import migration_type_to_display, normalize_migration_column, get_migration_columns_from_headers

    chunks = []
    file_name = file_name or os.path.basename(docx_path)
    if not DOCX_AVAILABLE:
        # Fallback to docx2txt if available (text only)
        if DOCX2TXT_AVAILABLE:
            try:
                import docx2txt
                text = docx2txt.process(docx_path)
                return [{"content": text, "chunk_type": "process", "source_file": file_name}]
            except:
                pass
        return []

    try:
        doc = DocxDocument(docx_path)
        current_section = None
        # Image extraction from DOCX is disabled; only text and tables are extracted.
        seen_texts = set()

        def _norm_text(s: str) -> str:
            return " ".join((s or "").split()).strip()

        def _should_emit_paragraph(text: str, is_heading: bool) -> bool:
            """
            Decide whether to emit a paragraph chunk.
            Goal: do not drop short-but-important definitions (e.g. 'Group Permissions: ...')
            while still skipping low-signal boilerplate.
            """
            t = _norm_text(text)
            if not t:
                return False
            if is_heading:
                return False  # headings become context only (section_title)
            # Always include lines that look like definitions / steps (often short).
            if ":" in t and len(t) >= 12:
                return True
            # Bullet/numbered items are frequently short but meaningful.
            if t.startswith(("-", "•", "*")) and len(t) >= 10:
                return True
            if len(t) >= 25:
                return True
            return False

        # Iterate through the document elements in order (xml sequence)
        for item in iter_block_items(doc):
            
            # --- Handle Paragraphs (Headings & Context) ---
            if isinstance(item, Paragraph):
                text = item.text.strip()
                if not text and not item.runs: continue # Skip empty
                
                # Check if this is a heading
                is_heading = False
                if item.style and hasattr(item.style, "name"):
                    if "Heading" in item.style.name:
                        is_heading = True
                
                # Fallback to regex if style is not reliable
                if not is_heading and is_line_heading(text):
                    is_heading = True
                
                if is_heading and text:
                    current_section = text
                # Images inside paragraphs are not extracted (image ingestion disabled)

                if _should_emit_paragraph(text, is_heading):
                    chunk_type = "rule" if "not supported" in text.lower() or "limitation" in text.lower() else "process"
                    norm = _norm_text(text)
                    if norm in seen_texts:
                        continue
                    seen_texts.add(norm)
                    chunks.append({
                        "content": norm,
                        "chunk_type": chunk_type,
                        "source_file": file_name,
                        "section_title": current_section,
                        "raw_kv": ""
                    })

            # --- Handle Tables (Atomic Rules) ---
            elif isinstance(item, Table):
                if not item.rows: continue
                
                header_cells = [c.text.strip() or f"Col{i}" for i, c in enumerate(item.rows[0].cells)]
                is_matrix_sheet, is_feature_row_matrix, migration_columns_B = get_migration_columns_from_headers(header_cells)
                
                for row_idx, row in enumerate(item.rows[1:], start=1):
                    cells = [c.text.strip() for c in row.cells]
                    row_dict = dict(zip(header_cells, cells))
                    
                    if is_feature_row_matrix:
                        feature = (cells[0] if cells else "").strip()
                        if not feature: continue
                        # Mixed tables (Feature + Description + Migration columns) are common in DOCX.
                        # Emit a definition chunk from the description column (typically col1) when present.
                        desc_val = (cells[1] if len(cells) > 1 else "").strip()
                        if desc_val:
                            raw_kv_def = row_to_raw_kv({"description": desc_val}, row_index=row_idx)
                            chunks.append({
                                "content": "\n".join([
                                    f"Section: {current_section or 'N/A'}",
                                    f"Feature: {feature}",
                                    f"Description: {desc_val}",
                                    f"Source: {file_name}",
                                ]),
                                "chunk_type": "definition",
                                "feature": feature,
                                "supported": None,
                                "source_file": file_name,
                                "section_title": current_section,
                                "raw_kv": raw_kv_def,
                            })
                        for j, col_header, migration_type in migration_columns_B:
                            value = (cells[j] if j < len(cells) else "").strip()
                            if not value: continue
                            display_migration = migration_type_to_display(migration_type)
                            raw_kv_str = row_to_raw_kv({col_header: value}, row_index=row_idx)
                            
                            content_parts = [
                                f"Feature: {feature}",
                                f"Migration: {display_migration}",
                                f"Supported: {value}",
                                f"Source: {file_name}"
                            ]
                            if current_section:
                                content_parts.insert(0, f"Section: {current_section}")
                                
                            chunks.append({
                                "content": "\n".join(content_parts),
                                "chunk_type": "feature_capability",
                                "feature": feature,
                                "supported": value or None,
                                "source_file": file_name,
                                "section_title": current_section,
                                "raw_kv": raw_kv_str,
                                "migration_type": migration_type,
                                "migration_combination": display_migration,
                            })
                            
                            if value.lower() in ("no", "na", "n/a"):
                                chunks.append({
                                    "content": f"Limitation: {feature} is not supported for {display_migration}. Section: {current_section or 'N/A'}",
                                    "chunk_type": "limitation",
                                    "feature": feature,
                                    "supported": value,
                                    "limitation": f"Not supported for {display_migration}",
                                    "source_file": file_name,
                                    "section_title": current_section,
                                    "raw_kv": raw_kv_str,
                                    "migration_type": migration_type,
                                    "migration_combination": display_migration,
                                })
                    else:
                        normalized, raw = normalize_columns(row_dict)
                        feature = (normalized.get("feature") or "").strip()
                        if not feature and row_dict:
                             first_val = next((v for v in row_dict.values() if v), "")
                             if first_val and len(first_val) > 2:
                                 feature = first_val
                        
                        if feature:
                            supported = (normalized.get("supported") or "").strip()
                            description = (normalized.get("description") or "").strip()
                            raw_kv_str = row_to_raw_kv(raw, row_index=row_idx)

                            # Intent labeling: if supported is missing but description exists, treat as definition.
                            ct = "feature_capability"
                            if (not supported) and description:
                                ct = "definition"
                            content_lines = [
                                f"Section: {current_section or 'N/A'}",
                                f"Feature: {feature}",
                            ]
                            if supported:
                                content_lines.append(f"Supported: {supported}")
                            if description:
                                content_lines.append(f"Description: {description}")
                            content_lines.append(f"Source: {file_name}")

                            chunks.append({
                                "content": "\n".join(content_lines),
                                "chunk_type": ct,
                                "feature": feature,
                                "supported": supported or None,
                                "source_file": file_name,
                                "section_title": current_section,
                                "raw_kv": raw_kv_str,
                            })
                            # Mixed: if both supported and description exist, emit a definition chunk too.
                            if supported and description and ct != "definition":
                                chunks.append({
                                    "content": "\n".join([
                                        f"Section: {current_section or 'N/A'}",
                                        f"Feature: {feature}",
                                        f"Description: {description}",
                                        f"Source: {file_name}",
                                    ]),
                                    "chunk_type": "definition",
                                    "feature": feature,
                                    "supported": None,
                                    "source_file": file_name,
                                    "section_title": current_section,
                                    "raw_kv": raw_kv_str,
                                })

        # Also extract standalone textbox/shapes content that may not appear in iter_block_items().
        try:
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            tb_nodes = doc.element.body.xpath(".//w:txbxContent", namespaces=ns)
            for tb in tb_nodes or []:
                parts = []
                for t in tb.xpath(".//w:t", namespaces=ns):
                    if t is not None and getattr(t, "text", None):
                        parts.append(str(t.text))
                tb_text = _norm_text(" ".join(parts))
                if not tb_text:
                    continue
                if tb_text in seen_texts:
                    continue
                seen_texts.add(tb_text)
                chunks.append({
                    "content": tb_text,
                    "chunk_type": "process",
                    "source_file": file_name,
                    "section_title": current_section,
                    "raw_kv": "",
                })
        except Exception:
            pass

        return chunks
    except Exception as e:
        print(f"Error in extract_docx_blocks_as_chunks({docx_path}): {e}")
        return []

def process_doc_directory(doc_directory: str) -> List[Document]:
    """Process all Word documents in a directory and return as LangChain Documents."""
    documents = []
    
    if not os.path.exists(doc_directory):
        print(f"Word documents directory {doc_directory} does not exist")
        return documents
    
    # Supported Word document file extensions
    doc_extensions = ['.docx', '.doc']
    doc_files = []
    
    for file in os.listdir(doc_directory):
        if any(file.lower().endswith(ext) for ext in doc_extensions):
            doc_files.append(file)
    
    if not doc_files:
        print(f"No Word documents found in {doc_directory}")
        return documents
    
    print(f"Processing {len(doc_files)} Word document(s)...")
    
    for doc_file in doc_files:
        doc_path = os.path.join(doc_directory, doc_file)
        print(f"Processing: {doc_file}")
        
        try:
            # Extract text from Word document
            text = extract_text_from_docx(doc_path)
            source_type = "doc"
            
            if text.strip():
                # Create a document with metadata
                doc = Document(
                    page_content=text,
                    metadata={
                        "source": doc_file,
                        "source_type": source_type,
                        "file_path": doc_path,
                        "file_format": doc_file.split('.')[-1].lower(),
                        "content_type": "word_document",
                        "searchable_terms": " ".join(text.split()[:20])  # Add first 20 words for better searchability
                    }
                )
                documents.append(doc)
                print(f"Successfully processed {doc_file} ({len(text)} characters)")
            else:
                print(f"Warning: No text extracted from {doc_file}")
                
        except Exception as e:
            print(f"Error processing {doc_file}: {e}")
    
    return documents

def chunk_doc_documents(documents: List[Document], chunk_size: int = 1000, chunk_overlap: int = 200) -> List[Document]:
    """Split Word documents into smaller chunks for better retrieval."""
    if not documents:
        return documents
    
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", " | ", " ", ""]  # Better separators for Word documents
    )
    
    chunked_docs = []
    for doc in documents:
        chunks = splitter.split_documents([doc])
        # Add metadata to each chunk for better searchability
        for chunk in chunks:
            chunk.metadata.update(doc.metadata)  # Preserve original metadata first
            chunk.metadata.update({
                "chunk_type": "word_document",
                "searchable_content": " ".join(chunk.page_content.split()[:20]),  # First 20 words for search
                "tag": "doc"  # Tag for chatbot to identify Word document content
            })
        chunked_docs.extend(chunks)
    
    print(f"Split {len(documents)} Word documents into {len(chunked_docs)} chunks")
    return chunked_docs

def get_doc_summary(doc_path: str) -> Dict:
    """Get a summary of a Word document's structure."""
    try:
        if DOCX_AVAILABLE:
            doc = DocxDocument(doc_path)
            summary = {
                "file_name": os.path.basename(doc_path),
                "paragraph_count": len(doc.paragraphs),
                "table_count": len(doc.tables),
                "total_text_length": 0
            }
            
            # Count text length
            for paragraph in doc.paragraphs:
                summary["total_text_length"] += len(paragraph.text)
            
            return summary
        else:
            return {"error": "python-docx not available for detailed analysis"}
    except Exception as e:
        return {"error": str(e)}
