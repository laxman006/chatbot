# SharePoint Ingestion Documentation

Complete guide to SharePoint document ingestion into Weaviate vector database.

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Authentication](#authentication)
4. [SharePoint Sources](#sharepoint-sources)
5. [File Type Processing](#file-type-processing)
6. [Ingestion Pipeline](#ingestion-pipeline)
7. [Configuration](#configuration)
8. [Usage](#usage)
9. [Troubleshooting](#troubleshooting)

---

## Overview

The SharePoint ingestion system extracts documents from multiple SharePoint sites and processes them into structured chunks for vector search. It supports:

- **Main SharePoint Site** (DOC360) - Primary documentation site
- **Presales SharePoint** - Pre-sales training materials
- **Limitations SharePoint** - Features and limitations documentation
- **Multiple file types**: PDF, DOCX, Excel (XLS/XLSX), PPTX, CSV, Images (PNG/JPG), and text files

The system uses Microsoft Graph API for reliable file extraction and processes documents into semantic chunks with rich metadata for enterprise knowledge retrieval.

---

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                    SharePoint Ingestion                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │   Main Site  │  │   Presales   │  │ Limitations   │    │
│  │   (DOC360)   │  │   Training   │  │   & Features  │    │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘    │
│         │                  │                  │             │
│         └──────────────────┼──────────────────┘             │
│                            │                                 │
│                   ┌────────▼────────┐                        │
│                   │ Graph API       │                        │
│                   │ Extractor       │                        │
│                   └────────┬────────┘                        │
│                            │                                 │
│         ┌──────────────────┼──────────────────┐             │
│         │                  │                  │             │
│  ┌──────▼──────┐  ┌───────▼──────┐  ┌───────▼──────┐       │
│  │   PDF       │  │   DOCX       │  │   Excel      │       │
│  │ Processor   │  │  Processor   │  │  Processor   │       │
│  └─────────────┘  └──────────────┘  └─────────────┘       │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   PPTX       │  │   Images     │  │   Text       │     │
│  │  Processor   │  │  Processor   │  │  Processor   │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                            │                                 │
│                   ┌────────▼────────┐                        │
│                   │  Ingestion      │                        │
│                   │  Pipeline        │                        │
│                   └────────┬────────┘                        │
│                            │                                 │
│                   ┌────────▼────────┐                        │
│                   │    Weaviate     │                        │
│                   │   SharePointDocs│                        │
│                   └─────────────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

### Key Files

- **`app/sharepoint_graph_extractor.py`** - Main Graph API extractor
- **`app/sharepoint_auth.py`** - Authentication handler
- **`app/helpers.py`** - Presales and Limitations extractors
- **`app/pdf_processor.py`** - PDF processing with tables, images, OCR
- **`app/doc_processor.py`** - DOCX processing with blocks
- **`app/excel_processor.py`** - Excel row-level extraction
- **`app/pptx_processor.py`** - PPTX slide and image extraction
- **`app/weaviate_ingestion.py`** - Main ingestion pipeline
- **`scripts/ingest_to_weaviate.py`** - CLI entry point

---

## Authentication

### Microsoft Graph API Authentication

The system uses **client credentials flow** (application permissions) for SharePoint access.

**Required Environment Variables:**
```bash
MICROSOFT_CLIENT_ID=your_client_id
MICROSOFT_CLIENT_SECRET=your_client_secret
MICROSOFT_TENANT=cloudfuze.com  # or your tenant
```

**Required Azure AD Permissions:**
- `Sites.Read.All` - Read all site collections
- `Files.Read.All` - Read all files

**Authentication Flow:**
1. Request access token from `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token`
2. Use `client_credentials` grant type
3. Scope: `https://graph.microsoft.com/.default`
4. Token cached and refreshed automatically (expires in ~1 hour)

**Implementation:**
```python
from app.sharepoint_auth import sharepoint_auth

# Get headers with Bearer token
headers = sharepoint_auth.get_headers()
# Returns: {"Authorization": "Bearer {token}", "Accept": "application/json", ...}
```

---

## SharePoint Sources

### 1. Main SharePoint Site (DOC360)

**Configuration:**
- **Site URL**: `SHAREPOINT_SITE_URL` (default: `https://cloudfuzecom.sharepoint.com/sites/DOC360`)
- **Enable Flag**: `ENABLE_SHAREPOINT_SOURCE=true`
- **Collection**: `SharePointDocs`

**Extraction Process:**
1. Get site ID from Graph API: `GET /sites/{hostname}:/sites/{sitename}`
2. Get drive ID (Documents library): `GET /sites/{site_id}/drive`
3. Recursively extract from root folder: `GET /drives/{drive_id}/root/children`
4. Process each file based on type (PDF, DOCX, Excel, etc.)
5. Skip excluded folders (configured in `SHAREPOINT_EXCLUDE_FOLDERS`)

**Code:**
```python
from app.sharepoint_graph_extractor import extract_sharepoint_via_graph

documents = extract_sharepoint_via_graph()
# Returns List[Document] with metadata
```

### 2. Presales SharePoint

**Configuration:**
- **Site URL**: `SHAREPOINT_PRESALES_SITE_URL`
- **Folder Path**: `SHAREPOINT_PRESALES_FOLDER_PATH` (e.g., "Release 1")
- **Enable Flag**: `ENABLE_SHAREPOINT_PRESALES_SOURCE=true`
- **Max Depth**: `SHAREPOINT_PRESALES_MAX_DEPTH=999`

**Extraction Process:**
1. Extract site URL and get site/drive IDs
2. Find folder by path (if `SHAREPOINT_PRESALES_FOLDER_PATH` specified)
3. Extract recursively from folder (or root if no folder specified)
4. Tag documents with `sharepoint_presales/{folder_path}`

**Code:**
```python
from app.helpers import fetch_latest_sharepoint_presales

documents = fetch_latest_sharepoint_presales(max_items=9999)
```

### 3. Limitations SharePoint

**Configuration:**
- **Site URL**: `SHAREPOINT_LIMITATIONS_SITE_URL`
- **Folder Path**: `SHAREPOINT_LIMITATIONS_FOLDER_PATH` (e.g., "Neutara Labs/Limitations and features")
- **Enable Flag**: `ENABLE_SHAREPOINT_LIMITATIONS_SOURCE=true`
- **Max Depth**: `SHAREPOINT_LIMITATIONS_MAX_DEPTH=999`

**Extraction Process:**
Same as Presales, but extracts from Limitations folder.

**Code:**
```python
from app.helpers import fetch_latest_sharepoint_limitations

documents = fetch_latest_sharepoint_limitations(max_items=9999)
```

---

## File Type Processing

### PDF Files

**Processing Strategy:**
- **Tables** → Extracted as `feature_capability`, `limitation`, or `table_row` chunks
- **Text** → Extracted as `explanation` chunks
- **Images** → Extracted as `image_context` chunks with OCR text

**Chunk Types:**
- `feature_capability` - Feature descriptions from tables
- `limitation` - Limitations from tables
- `table_row` - Raw table rows
- `explanation` - Body text paragraphs
- `image_context` - Images with OCR text

**Metadata:**
```python
{
    "doc_id": "sharepoint:{item_id}",
    "source_type": "sharepoint",
    "content_type": "pdf_feature_capability",
    "chunk_type": "feature_capability",
    "page_number": 5,
    "section_title": "Migration Features",
    "feature": "Email Migration",
    "supported": "Yes",
    "is_limitation": False,
    "image_data": "base64...",  # For image chunks
    "has_ocr": True,  # If OCR text available
    "ocr_text": "extracted text..."
}
```

**Implementation:**
```python
from app.pdf_processor import extract_pdf_tables_as_chunks, extract_pdf_atomic_chunks

# Extract tables
table_chunks = extract_pdf_tables_as_chunks(pdf_path, file_name="doc.pdf")

# Extract text and images
atomic_chunks = extract_pdf_atomic_chunks(pdf_path, file_name="doc.pdf")
```

### DOCX Files

**Processing Strategy:**
- **Tables** → One row = one chunk (`feature`, `limitation`, `process`)
- **Paragraphs** → Block-level chunks (`explanation`, `process`, `rule`)
- **Images** → `image_context` chunks with OCR

**Chunk Types:**
- `feature` - Feature descriptions
- `limitation` - Limitations
- `process` - Process descriptions
- `rule` - Rules and guidelines
- `explanation` - Explanatory text
- `image_context` - Images with OCR

**Metadata:**
```python
{
    "doc_id": "sharepoint:{item_id}",
    "content_type": "sharepoint_file",
    "chunk_type": "feature",
    "block_index": 0,
    "section_title": "Introduction",
    "feature": "Email Migration",
    "supported": "Yes"
}
```

**Implementation:**
```python
from app.doc_processor import extract_docx_blocks_as_chunks

chunks = extract_docx_blocks_as_chunks(docx_path)
```

### Excel Files (XLS/XLSX)

**Processing Strategy:**
- **One row = one chunk** - Each row becomes a separate document
- **Sheet-based** - Each sheet represents a migration path/combination
- **Structured extraction** - Feature, description, status, migration type

**Chunk Types:**
- `feature` - Feature rows
- `limitation` - Limitation rows
- `capability` - Capability rows

**Metadata:**
```python
{
    "doc_id": "sharepoint:{item_id}",  # Same for all rows in file
    "content_type": "excel_fact",
    "chunk_type": "feature",
    "row_index": 0,
    "sheet_name": "Gmail to Exchange",
    "feature": "Email Migration",
    "supported": "Yes",
    "migration_type": "Gmail to Exchange",
    "migration_combination": "Gmail to Exchange",
    "raw_kv": "Feature: Email Migration | Status: Yes"
}
```

**Implementation:**
```python
from app.excel_processor import extract_excel_rows_as_chunks

row_chunks = extract_excel_rows_as_chunks(excel_path, display_file_name="features.xlsx")
```

### CSV Files

**Processing Strategy:**
- Same as Excel - one row = one chunk
- Treated as single-sheet Excel file

**Implementation:**
```python
from app.excel_processor import extract_csv_rows_as_chunks

row_chunks = extract_csv_rows_as_chunks(csv_path, display_file_name="data.csv")
```

### PPTX Files

**Processing Strategy:**
- **Slides** → One slide = one document (`pptx_slide`)
- **Images** → Separate documents (`pptx_image`) with OCR
- **Slide content** → Text from shapes and placeholders

**Chunk Types:**
- `pptx_slide` - Slide text content
- `pptx_image` - Images from slides with OCR

**Metadata:**
```python
{
    "doc_id": "sharepoint:{item_id}",
    "content_type": "pptx_slide",
    "chunk_type": "explanation",
    "page_number": 1,
    "section_title": "Introduction",
    "image_data": "base64...",  # For image chunks
    "has_ocr": True,
    "ocr_text": "extracted text..."
}
```

**Implementation:**
```python
from app.pptx_processor import PPTXProcessor

processor = PPTXProcessor(output_dir="./data/pptx_extracted")
result = processor.process_pptx_from_bytes(pptx_bytes, file_name="presentation.pptx", metadata={})
```

### Images (PNG/JPG/JPEG)

**Processing Strategy:**
- **Base64 encoding** - Image stored as base64 in metadata
- **OCR** - Text extracted using Tesseract (if available)
- **Standalone documents** - Each image = one document
- **All image types included** - Screenshots, photos, diagrams, charts, etc. are all processed the same way
- **No filtering** - All PNG, JPG, and JPEG files are ingested (no distinction between screenshot vs other images)

**Supported Formats:**
- PNG (`.png`)
- JPEG (`.jpg`, `.jpeg`)

**What Gets Stored:**
- Screenshots (PNG/JPG format)
- Photos
- Diagrams
- Charts and graphs
- Any other PNG/JPG/JPEG image files

**What Gets Skipped:**
- Video files (MP4, AVI, MOV, WMV, MKV)
- Call recordings (files with "call" and "recording" in filename)
- Files in excluded folders (configured in `SHAREPOINT_EXCLUDE_FOLDERS`)

**Metadata:**
```python
{
    "doc_id": "sharepoint:{item_id}",
    "content_type": "image_png",  # or "image_jpg", "image_jpeg"
    "chunk_type": "image_context",
    "image_data": "base64...",  # Full image encoded as base64
    "has_ocr": True,  # If OCR text was extracted
    "ocr_text": "extracted text...",  # OCR text if available
    "file_name": "screenshot.png",
    "file_url": "https://...",
    "folder_path": "Documents > Screenshots"
}
```

**OCR Processing:**
- OCR is attempted on ALL images (including screenshots)
- Uses Tesseract OCR engine (if available)
- Extracted text is stored in `ocr_text` metadata field
- OCR text is also included in document `page_content` for searchability

### Text Files (TXT, CSV, JSON, XML, HTML, MD)

**Processing Strategy:**
- Direct text extraction
- Simple document creation

---

## Ingestion Pipeline

### Pipeline Steps

1. **Document Loading**
   - Load documents from SharePoint sources
   - Combine main site, presales, and limitations documents

2. **Chunking**
   - Use markdown-aware chunker (preferred) or semantic chunker
   - Target: 800 tokens per chunk, 200 token overlap
   - Minimum: 150 tokens

3. **Metadata Enrichment**
   - Add `parent_key` (UUID5 from doc_id + site_name + folder_name + source_ref)
   - Add `parent_id` (UUID5 from doc_id)
   - Add `chunk_key` (UUID5 from parent_key + chunk_index)
   - Add `content_hash` (MD5 of content)

4. **Summary Generation** (optional)
   - Generate document-level summaries for chunks > 3
   - Uses LLM to create concise summaries

5. **Deduplication** (optional)
   - Remove duplicate chunks by `content_hash`
   - Prevents duplicate embeddings

6. **Embedding Generation**
   - Generate embeddings using OpenAI `text-embedding-3-small`
   - Batch processing for efficiency

7. **Weaviate Insertion**
   - Batch insert chunks into `SharePointDocs` collection
   - Use deterministic UUIDs for stable updates

8. **Tracking** (incremental)
   - Track document hashes for incremental updates
   - Detect new, modified, and deleted documents

### Pipeline Code

```python
from app.weaviate_ingestion import WeaviateIngestionPipeline

pipeline = WeaviateIngestionPipeline(
    enable_summaries=True,
    enable_deduplication=True,
    enable_incremental=True,
    allow_deletions=True
)

result = pipeline.ingest_from_source(
    source_type="sharepoint",
    documents=documents,
    collection_name="SharePointDocs",
    incremental=True
)
```

### Result Object

```python
class IngestionResult:
    success: bool
    chunks_processed: int
    chunks_inserted: int
    chunks_failed: int
    failed_chunk_keys: List[str]
    errors: List[str]
    processing_time_seconds: float
```

---

## Configuration

### Environment Variables

**Authentication:**
```bash
MICROSOFT_CLIENT_ID=your_client_id
MICROSOFT_CLIENT_SECRET=your_client_secret
MICROSOFT_TENANT=cloudfuze.com
```

**Main SharePoint:**
```bash
ENABLE_SHAREPOINT_SOURCE=true
SHAREPOINT_SITE_URL=https://cloudfuzecom.sharepoint.com/sites/DOC360
SHAREPOINT_START_PAGE=  # Empty for Documents library
SHAREPOINT_MAX_DEPTH=999
SHAREPOINT_EXCLUDE_FILES=true
```

**Presales SharePoint:**
```bash
ENABLE_SHAREPOINT_PRESALES_SOURCE=true
SHAREPOINT_PRESALES_SITE_URL=https://cloudfuzecom.sharepoint.com/sites/Pre-SalesTrining
SHAREPOINT_PRESALES_FOLDER_PATH=Release 1
SHAREPOINT_PRESALES_MAX_DEPTH=999
```

**Limitations SharePoint:**
```bash
ENABLE_SHAREPOINT_LIMITATIONS_SOURCE=true
SHAREPOINT_LIMITATIONS_SITE_URL=https://cloudfuzecom.sharepoint.com/sites/Repository25
SHAREPOINT_LIMITATIONS_FOLDER_PATH=Neutara Labs/Limitations and features
SHAREPOINT_LIMITATIONS_MAX_DEPTH=999
```

**PPTX Processing:**
```bash
ENABLE_PPTX_PIPELINE=true
ENABLE_PPTX_SAVE_FILES=false  # Set to true to save extracted PPTX to files
PPTX_OUTPUT_DIR=./data/pptx_extracted
```

**Excluded Folders:**
```python
# In config.py
SHAREPOINT_EXCLUDE_FOLDERS = [
    "Archive",
    "Old Documents",
    "Backup"
]
```

**Downloadable Folders:**
```python
# In config.py
SHAREPOINT_DOWNLOADABLE_FOLDERS = [
    "certificates",
    "policy documents",
    "guides"
]
```

---

## Usage

### CLI Usage

**Ingest all SharePoint sources:**
```bash
python scripts/ingest_to_weaviate.py --source sharepoint
```

**Options:**
```bash
--source sharepoint          # Required: source type
--collection SharePointDocs  # Optional: collection name (default: inferred)
--incremental                # Enable incremental ingestion (default: True)
--no-incremental             # Disable incremental ingestion
--no-summaries               # Disable summary generation
--no-dedup                   # Disable deduplication
--dry-run                    # Dry run (don't insert)
```

### Programmatic Usage

**Load SharePoint documents:**
```python
from scripts.ingest_to_weaviate import load_sharepoint_documents

documents = load_sharepoint_documents()
# Returns combined documents from all enabled SharePoint sources
```

**Extract from specific source:**
```python
# Main site
from app.sharepoint_graph_extractor import extract_sharepoint_via_graph
docs = extract_sharepoint_via_graph()

# Presales
from app.helpers import fetch_latest_sharepoint_presales
docs = fetch_latest_sharepoint_presales(max_items=9999)

# Limitations
from app.helpers import fetch_latest_sharepoint_limitations
docs = fetch_latest_sharepoint_limitations(max_items=9999)
```

**Re-ingest single PDF:**
```bash
python scripts/reingest_sharepoint_pdf.py \
    --doc-id "sharepoint:01XV..." \
    --pdf-path "C:\path\to\file.pdf"
```

### Debugging

**Check ingested documents:**
```bash
python scripts/debug_sharepoint_ingested.py --doc-id "sharepoint:01XV..."
```

**Check image ingestion:**
```bash
python scripts/check_image_ingestion.py
```

---

## Troubleshooting

### Authentication Issues

**Error: "Failed to get SharePoint access token"**
- Check `MICROSOFT_CLIENT_ID` and `MICROSOFT_CLIENT_SECRET`
- Verify Azure AD app has `Sites.Read.All` and `Files.Read.All` permissions
- Check tenant ID is correct

**Error: "Failed to get site ID"**
- Verify `SHAREPOINT_SITE_URL` format: `https://{hostname}/sites/{sitename}`
- Check site exists and app has access

### Extraction Issues

**Error: "Failed to get drive ID"**
- Site ID must be valid
- Check Documents library exists
- Verify app permissions

**No documents extracted:**
- Check `ENABLE_SHAREPOINT_SOURCE=true` in config
- Verify excluded folders aren't blocking all content
- Check folder paths are correct (case-sensitive)

**Missing file types:**
- Verify file processors are installed:
  - PDF: `pypdf`, `pdfplumber`, `PyMuPDF`
  - DOCX: `python-docx`
  - Excel: `openpyxl`, `pandas`
  - PPTX: `python-pptx`
  - OCR: `pytesseract`, `PIL`

### Ingestion Issues

**Chunks not inserted:**
- Check Weaviate is running: `docker-compose ps weaviate`
- Check collection exists: `scripts/init_weaviate_schema.py`
- Check embedding service is configured (OpenAI API key)

**Duplicate chunks:**
- Enable deduplication: `--no-dedup` flag should NOT be used
- Check `content_hash` is being generated correctly

**Incremental updates not working:**
- Check tracking files in `data/ingestion_tracking/`
- Verify `enable_incremental=True` in pipeline
- Check document hashes are stable

### Performance Issues

**Slow extraction:**
- Reduce `SHAREPOINT_MAX_DEPTH` if too many folders
- Exclude unnecessary folders in `SHAREPOINT_EXCLUDE_FOLDERS`
- Process specific folder paths instead of entire site

**Slow ingestion:**
- Disable summaries: `--no-summaries`
- Increase batch size in `WeaviateBatchInserter`
- Check network latency to Weaviate

### File Processing Issues

**PDF tables not extracted:**
- Install `pdfplumber` for better table extraction
- Check PDF has actual tables (not images)
- Verify `extract_pdf_tables_as_chunks` is being called

**Images missing OCR:**
- Install `pytesseract` and Tesseract OCR engine
- Check `OCR_AVAILABLE` flag in code
- Verify image format is supported (PNG, JPG)

**Excel rows not extracted:**
- Verify `extract_excel_rows_as_chunks` is being called (not `extract_text_from_excel`)
- Check Excel file has data rows (not just headers)
- Verify sheet names are correct

---

## Best Practices

1. **Incremental Ingestion**: Always use `--incremental` for regular updates to avoid re-processing unchanged documents

2. **Folder Exclusion**: Configure `SHAREPOINT_EXCLUDE_FOLDERS` to skip unnecessary content (archives, backups, etc.)

3. **Chunking Strategy**: Use markdown-aware chunker for better semantic boundaries

4. **Metadata Enrichment**: Ensure all documents have `doc_id`, `source_type`, and `folder_path` for proper grouping

5. **Error Handling**: Monitor ingestion logs for failed chunks and retry if needed

6. **Testing**: Use `--dry-run` to test extraction without inserting into Weaviate

7. **Re-ingestion**: Use `reingest_sharepoint_pdf.py` for fixing specific documents without full re-ingestion

---

## Related Documentation

- `WEAVIATE_SCHEMA.md` - Weaviate collection schemas
- `WORKFLOW.md` - Overall system workflow
- `app/weaviate_ingestion.py` - Ingestion pipeline implementation
- `app/weaviate_schema.py` - Collection definitions

---

## Version History

- **2026-02-04**: Initial comprehensive documentation
- Supports PDF, DOCX, Excel, PPTX, Images, and text files
- Multiple SharePoint sources (Main, Presales, Limitations)
- Incremental ingestion with tracking
- Atomic truth extraction (tables → features/limitations, images → OCR)
