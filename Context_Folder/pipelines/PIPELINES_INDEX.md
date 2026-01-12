# Pipelines Documentation Index

## Complete Pipeline Documentation

This index provides navigation to all data processing pipeline documentation.

---

## 📋 All Pipelines

### 1. [SharePoint Pipeline](./SHAREPOINT_PIPELINE.md)
**Purpose:** Process SharePoint pages, FAQs, tables, and text content

**Key Files:**
- `app/sharepoint_processor.py` - Main processor
- `app/sharepoint_auth.py` - Authentication
- `app/sharepoint_models.py` - Data models
- `app/sharepoint_graph_extractor.py` - Graph API extractor

**Features:**
- Page crawling (BFS)
- FAQ extraction
- Table extraction
- Text content extraction
- Chunking (1500 tokens, 200 overlap)

---

### 2. [PDF Pipeline](./PDF_PIPELINE.md)
**Purpose:** Extract text from PDF files

**Key Files:**
- `app/pdf_processor.py` - Main processor

**Features:**
- Multiple extraction methods (pdfplumber, PyMuPDF, PyPDF2)
- Text extraction
- Chunking (1500 tokens, 200 overlap)
- Error handling with fallbacks

---

### 3. [PPTX Pipeline](./PPTX_PIPELINE.md)
**Purpose:** Extract content from PowerPoint files

**Key Files:**
- `app/pptx_processor.py` - Main processor
- `app/unstructured_processor.py` - Alternative extraction

**Features:**
- Slide extraction
- Notes extraction
- Separate processing (not in main vectorstore)
- JSON and text output

---

### 4. [Excel Pipeline](./EXCEL_PIPELINE.md)
**Purpose:** Extract structured data from Excel files

**Key Files:**
- `app/excel_processor.py` - Main processor

**Features:**
- Multi-sheet support
- Column header extraction
- Row data extraction
- Statistics calculation (numeric columns)
- Chunking (1500 tokens, 200 overlap)

---

### 5. [Outlook Pipeline](./OUTLOOK_PIPELINE.md)
**Purpose:** Process Outlook email threads

**Key Files:**
- `app/outlook_processor.py` - Main processor
- `app/sharepoint_auth.py` - Authentication (shared)

**Features:**
- Email fetching via Graph API
- Thread grouping
- Participant tracking
- Date range filtering
- Thread-based chunking

---

### 6. [Blog Pipeline](./BLOG_PIPELINE.md)
**Purpose:** Fetch and process blog posts from WordPress

**Key Files:**
- `app/helpers.py` - Blog fetching functions

**Features:**
- WordPress API integration
- Pagination support
- HTML cleaning
- Post metadata preservation
- Incremental updates

---

### 7. [Transcript Pipeline](./TRANSCRIPT_PIPELINE.md)
**Purpose:** Process customer demo transcripts

**Key Files:**
- `app/transcript_processor.py` - Main processor
- `app/transcript_normalizer.py` - Text normalization
- `app/transcript_artifact_extractor.py` - Artifact extraction

**Features:**
- Artifact extraction (Q&A, objections, features)
- Retrieval text building
- Artifact grouping (180-300 tokens)
- Customer name extraction
- Industry inference

---

## 🔄 Pipeline Integration

### Enhanced Vectorstore Builder
**Location:** `app/enhanced_helpers.py`

**Function:** `build_enhanced_vectorstore()`

**Processes:**
1. SharePoint documents
2. Outlook documents
3. Blog documents
4. Transcript documents

**All pipelines integrated through:**
- `EnhancedVectorstoreBuilder.process_documents()`
- Source-specific chunking strategies
- Metadata addition
- Vectorstore building

---

## 📊 Pipeline Comparison

| Pipeline | Source | Chunk Size | Overlap | Special Features |
|----------|--------|------------|---------|------------------|
| SharePoint | SharePoint API | 1500 | 200 | FAQ/Table extraction |
| PDF | File system | 1500 | 200 | Multiple extraction methods |
| PPTX | File system/SharePoint | N/A | N/A | Separate processing |
| Excel | File system | 1500 | 200 | Statistics calculation |
| Outlook | Graph API | 1500 | 200 | Thread grouping |
| Blog | WordPress API | 1500 | 300 | Incremental updates |
| Transcript | SharePoint | 180-300 | N/A | Artifact grouping |

---

## 🔧 Configuration

### Enable/Disable Pipelines
```python
ENABLE_SHAREPOINT_SOURCE = True
ENABLE_PDF_SOURCE = True
ENABLE_EXCEL_SOURCE = True
ENABLE_OUTLOOK_SOURCE = True
ENABLE_WEB_SOURCE = True
ENABLE_TRANSCRIPT_PROCESSING = True
```

### Source Paths
```python
SHAREPOINT_SITE_URL = "..."
PDF_SOURCE_DIR = "./data/pdfs"
EXCEL_SOURCE_DIR = "./data/excel"
OUTLOOK_USER_EMAIL = "..."
OUTLOOK_FOLDER_NAME = "..."
WEB_SOURCE_URL = "https://cloudfuze.com"
SHAREPOINT_TRANSCRIPTS_SITE_URL = "..."
SHAREPOINT_TRANSCRIPTS_FOLDER_PATH = "..."
```

---

## 🚀 Usage Examples

### Process All Sources
```python
from app.vectorstore import build_enhanced_vectorstore_full

vectorstore = build_enhanced_vectorstore_full()
```

### Process Single Source
```python
from app.sharepoint_processor import process_sharepoint_content
from app.pdf_processor import process_pdf_directory
from app.outlook_processor import process_outlook_content
from app.helpers import fetch_web_content
from app.transcript_processor import TranscriptProcessor

# SharePoint
sharepoint_docs = process_sharepoint_content()

# PDF
pdf_docs = process_pdf_directory("./data/pdfs")

# Outlook
outlook_docs = process_outlook_content()

# Blog
blog_docs = fetch_web_content("https://cloudfuze.com")

# Transcripts
processor = TranscriptProcessor()
transcript_docs = processor.extract_transcripts_from_sharepoint()
```

---

## 📈 Processing Statistics

### Typical Output
```
[*] Processing SharePoint content...
[OK] Processed 50 SharePoint pages
[OK] Created 200 documents

[*] Processing PDF files...
[OK] Processed 10 PDF files
[OK] Created 50 documents

[*] Processing Outlook emails...
[OK] Fetched 50 emails
[OK] Grouped into 10 threads
[OK] Created 10 documents

[*] Fetching blog posts...
[OK] Fetched 1,400 blog posts
[OK] Created 5,600 chunks

[*] Processing transcripts...
[OK] Processed 5 transcript files
[OK] Created 23 documents
```

---

## 🔍 Key Functions Reference

### SharePoint
- `SharePointProcessor.crawl_pages()` - Crawl pages
- `process_sharepoint_content()` - Process SharePoint

### PDF
- `extract_text_from_pdf()` - Extract text
- `process_pdf_directory()` - Process directory

### PPTX
- `PPTXProcessor.extract_with_pptx_library()` - Extract slides
- `PPTXProcessor.process_pptx_file()` - Process file

### Excel
- `extract_text_from_excel()` - Extract text
- `process_excel_directory()` - Process directory

### Outlook
- `OutlookProcessor.fetch_emails()` - Fetch emails
- `OutlookProcessor.group_emails_into_threads()` - Group threads
- `process_outlook_content()` - Process Outlook

### Blog
- `fetch_posts()` - Fetch posts
- `fetch_web_content()` - Process blogs
- `fetch_latest_web_content()` - Latest blogs

### Transcripts
- `TranscriptProcessor.extract_transcripts_from_sharepoint()` - Extract
- `build_retrieval_text()` - Build retrieval text
- `group_artifacts_for_chunking()` - Group artifacts

---

## 🎯 Best Practices

1. **Incremental Updates:** Use incremental mode when vectorstore exists
2. **Error Handling:** All pipelines handle errors gracefully
3. **Metadata Rich:** Add comprehensive metadata to all documents
4. **Chunk Appropriately:** Use appropriate chunk sizes per source
5. **Separate Processing:** Keep PPTX separate from main vectorstore

---

**Last Updated:** 2025-01-09  
**Location:** `Context_Folder/pipelines/`
