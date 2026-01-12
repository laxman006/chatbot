# Knowledge Base Ingestion Feature

## Overview

Processes documents from multiple sources (SharePoint, PDFs, PPTX, Excel, Outlook, Transcripts, Blogs) and adds them to the vectorstore for retrieval.

---

## Related Files

### Backend Files

#### Document Processors
- **`app/sharepoint_processor.py`**
  - SharePoint page crawling
  - Content extraction
  - Document creation

- **`app/pdf_processor.py`**
  - PDF text extraction
  - PDF chunking

- **`app/pptx_processor.py`**
  - PowerPoint slide extraction
  - Slide content processing

- **`app/excel_processor.py`**
  - Excel table extraction
  - Sheet processing

- **`app/outlook_processor.py`**
  - Email thread extraction
  - Email content processing

- **`app/transcript_processor.py`**
  - Transcript artifact extraction
  - Q&A pair creation
  - Retrieval text building

- **`app/doc_processor.py`**
  - Word document extraction
  - DOCX processing

#### Vectorstore Management
- **`app/vectorstore.py`**
  - `build_enhanced_vectorstore_full()` - Full vectorstore build
  - `build_incremental_vectorstore()` - Incremental build
  - `load_existing_vectorstore()` - Load existing vectorstore
  - `get_changed_sources()` - Detect changed sources
  - `rebuild_vectorstore_if_needed()` - Rebuild if needed

#### Enhanced Processing
- **`app/enhanced_helpers.py`**
  - `EnhancedVectorstoreBuilder` - Document processing builder
  - `process_documents()` - Process documents by type
  - `build_vectorstore()` - Build ChromaDB vectorstore

#### Chunking
- **`app/chunking_strategy.py`**
  - Chunking strategies
  - Text splitting

- **`app/deduplication.py`**
  - Document deduplication

#### Metadata
- **`app/metadata_schema.py`**
  - Metadata schema definitions
  - Metadata validation

#### Ingest Reporter
- **`app/ingest_reporter.py`**
  - Ingestion reporting
  - Statistics tracking

### Scripts

#### Processing Scripts
- **`scripts/process_transcripts_from_sharepoint.py`**
  - Process transcripts from SharePoint

- **`scripts/extract_pptx_from_sharepoint.py`**
  - Extract PowerPoint from SharePoint

- **`scripts/delete_transcript_chunks.py`**
  - Delete transcript chunks

- **`scripts/inspect_transcripts.py`**
  - Inspect transcript documents

#### Maintenance Scripts
- **`scripts/backup_vectorstore.py`**
  - Backup vectorstore

- **`scripts/count_blogs.py`**
  - Count blog documents

### Configuration
- **`config.py`**
  - Source enable/disable flags
  - Source paths and URLs
  - Processing configuration

---

## Feature Workflow

1. **Source Detection** → Check which sources enabled
2. **Change Detection** → Compare with stored metadata
3. **Document Extraction** → Extract from sources
4. **Document Processing** → Process and chunk documents
5. **Metadata Addition** → Add metadata to documents
6. **Vectorstore Update** → Add to ChromaDB
7. **Metadata Save** → Save source metadata for future comparison

---

## Key Functions

### Vectorstore
- `build_enhanced_vectorstore_full()` - Full build
- `build_incremental_vectorstore()` - Incremental build
- `load_existing_vectorstore()` - Load existing
- `get_changed_sources()` - Detect changes

### Processing
- `process_sharepoint_content()` - Process SharePoint
- `process_pdf_directory()` - Process PDFs
- `process_transcript_file()` - Process transcripts
- `process_documents()` - Generic processing

---

## Data Sources

### SharePoint
- **Processor:** `app/sharepoint_processor.py`
- **Config:** `SHAREPOINT_SITE_URL`, `SHAREPOINT_START_PAGE`
- **Content:** Pages, FAQs, tables, downloadable files

### PDFs
- **Processor:** `app/pdf_processor.py`
- **Config:** `PDF_SOURCE_DIR`
- **Content:** PDF documents

### PowerPoint (PPTX)
- **Processor:** `app/pptx_processor.py`
- **Config:** `PPTX_SOURCE_DIR` or SharePoint
- **Content:** Slide presentations

### Excel
- **Processor:** `app/excel_processor.py`
- **Config:** `EXCEL_SOURCE_DIR`
- **Content:** Spreadsheets, tables

### Outlook/Email
- **Processor:** `app/outlook_processor.py`
- **Config:** `OUTLOOK_USER_EMAIL`, `OUTLOOK_FOLDER_NAME`
- **Content:** Email threads

### Transcripts
- **Processor:** `app/transcript_processor.py`
- **Config:** `SHAREPOINT_TRANSCRIPTS_SITE_URL`, `SHAREPOINT_TRANSCRIPTS_FOLDER_PATH`
- **Content:** Customer demo transcripts, Q&A pairs, objections, features

### Blogs
- **Processor:** Web scraping
- **Config:** `WEB_SOURCE_URL`, `BLOG_START_PAGE`
- **Content:** Blog posts

---

## Processing Pipeline

### 1. Extraction
- Extract content from source
- Parse file formats
- Extract metadata

### 2. Normalization
- Clean text
- Remove formatting
- Normalize structure

### 3. Chunking
- Split into chunks
- Optimal chunk size (varies by source)
- Overlap handling

### 4. Metadata Addition
- Source type
- File name
- URL/path
- Tags
- KB tier (primary/secondary)
- Artifact type (for transcripts)

### 5. Embedding
- Generate embeddings
- Store in ChromaDB

---

## Incremental Updates

### Change Detection
- Compare source metadata hashes
- Detect new/changed sources
- Only process changed sources

### Metadata Storage
- Store source metadata in `data/vectorstore_metadata.json`
- Compare on next run
- Rebuild only changed sources

---

## Configuration

### Source Enable/Disable
```python
ENABLE_WEB_SOURCE = True
ENABLE_PDF_SOURCE = True
ENABLE_EXCEL_SOURCE = True
ENABLE_DOC_SOURCE = True
ENABLE_SHAREPOINT_SOURCE = True
ENABLE_OUTLOOK_SOURCE = True
ENABLE_TRANSCRIPT_PROCESSING = True
```

### Source Paths
```python
WEB_SOURCE_URL = "..."
PDF_SOURCE_DIR = "..."
EXCEL_SOURCE_DIR = "..."
SHAREPOINT_SITE_URL = "..."
OUTLOOK_USER_EMAIL = "..."
```

---

## Chunking Strategies

### By Source Type
- **SharePoint:** 1500 tokens, 200 overlap
- **PDFs:** 1500 tokens, 200 overlap
- **Transcripts:** 180-300 tokens (grouped artifacts)
- **Emails:** Thread-based chunks
- **Blogs:** 1500 tokens, 200 overlap

### Special Handling
- **Transcripts:** Pre-grouped artifacts (no re-chunking)
- **Emails:** Thread-based (entire thread = one chunk)
- **SharePoint:** Page-based chunks

---

## Metadata Schema

### Common Metadata
```python
{
    "source": str,
    "source_type": str,  # "sharepoint", "pdf", "email", "transcript", etc.
    "tag": str,
    "file_name": str,
    "url": str,  # For downloadable files
    "kb_tier": "primary" | "secondary",
    "priority": "high" | "medium" | "low"
}
```

### Transcript-Specific
```python
{
    "artifact_type": "Q&A" | "Objection" | "Feature" | "Decision Driver",
    "customer": str,
    "industry": str,
    "raw_content": dict  # Original artifact JSON
}
```

---

**Last Updated:** 2025-01-09
