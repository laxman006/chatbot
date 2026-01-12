# SharePoint Processing Pipeline Documentation

## Overview

Processes SharePoint pages, extracts content (tables, FAQs, text), and converts them to LangChain Documents for the vectorstore.

**Location:** `app/sharepoint_processor.py`

---

## Pipeline Architecture

```
SharePoint Site
    │
    ├─► Authenticate (Microsoft Graph API)
    │   └─► sharepoint_auth.get_headers()
    │
    ├─► Crawl Pages (BFS)
    │   ├─► Start from SHAREPOINT_START_PAGE
    │   ├─► Follow links up to MAX_DEPTH
    │   └─► Track crawled URLs (avoid duplicates)
    │
    ├─► Extract Content from Each Page
    │   ├─► FAQs (numbered lists, Q&A format)
    │   ├─► Tables (HTML tables)
    │   └─► General Text Content
    │
    ├─► Convert to Documents
    │   ├─► FAQ → Document
    │   ├─► Table → Document
    │   └─► Text → Document
    │
    ├─► Chunk Documents
    │   └─► RecursiveCharacterTextSplitter (1500 tokens, 200 overlap)
    │
    └─► Add Metadata
        └─► source_type, tag, file_name, folder_path, url
```

---

## Class: `SharePointProcessor`

**Location:** `app/sharepoint_processor.py` (line 27)

**Purpose:** Main processor for SharePoint content

---

## Initialization

### `__init__()`
**Location:** Lines 30-51

**Configuration:**
- `site_url`: SharePoint site URL (default: `SHAREPOINT_SITE_URL`)
- `start_page`: Starting page path (default: `SHAREPOINT_START_PAGE`)
- `max_depth`: Maximum crawl depth (default: 3)
- `exclude_files`: Exclude file downloads (default: true)

**Text Splitter:**
```python
RecursiveCharacterTextSplitter(
    chunk_size=1500,
    chunk_overlap=200,
    separators=["\n\n", "\n", ". ", " ", ""]
)
```

---

## Key Functions

### `get_page_content(page_url)`
**Location:** Lines 53-72

**Purpose:** Get SharePoint page content via REST API

**What it does:**
1. Gets access token via `sharepoint_auth.get_headers()`
2. Makes request to SharePoint REST API
3. Returns page data with title, URL, and content

**Returns:** Dictionary with `title`, `url`, `content`

---

### `extract_content_from_html(html_content, page_url, page_title)`
**Location:** Lines 110-143

**Purpose:** Extract structured content from HTML

**What it does:**
1. Parses HTML with BeautifulSoup
2. Extracts FAQs via `_extract_faqs()`
3. Extracts tables via `_extract_tables()`
4. Extracts general text via `_extract_text_content()`
5. Converts each to Document
6. Returns list of Documents

**Returns:** List of LangChain Documents

---

### `_extract_faqs(soup, page_url, page_title)`
**Location:** Lines 145-200+

**Purpose:** Extract FAQ items from page

**Methods:**
1. **Numbered Lists:** Looks for `Q1:`, `Q2:`, etc.
2. **Q&A Format:** Looks for question/answer pairs
3. **Accordion Format:** Looks for expandable sections

**Returns:** List of `SharePointFAQ` objects

---

### `_extract_tables(soup, page_url, page_title)`
**Location:** Lines 200-300+

**Purpose:** Extract HTML tables from page

**What it does:**
1. Finds all `<table>` elements
2. Extracts headers and rows
3. Converts to structured format
4. Creates `SharePointTable` objects

**Returns:** List of `SharePointTable` objects

---

### `_extract_text_content(soup)`
**Location:** Lines 300-400+

**Purpose:** Extract general text content

**What it does:**
1. Removes script and style tags
2. Extracts text from body
3. Cleans whitespace
4. Returns clean text

**Returns:** String of text content

---

### `_faq_to_document(faq)`
**Location:** Lines 400-500+

**Purpose:** Convert FAQ to LangChain Document

**Document Structure:**
```python
Document(
    page_content=f"Q: {faq.question}\nA: {faq.answer}",
    metadata={
        "source_type": "sharepoint",
        "tag": "sharepoint/faq",
        "file_name": page_title,
        "folder_path": folder_path,
        "url": page_url,
        "faq_id": faq.id
    }
)
```

---

### `_table_to_document(table)`
**Location:** Lines 500-600+

**Purpose:** Convert table to LangChain Document

**Document Structure:**
```python
Document(
    page_content=table.to_text(),  # Formatted table text
    metadata={
        "source_type": "sharepoint",
        "tag": "sharepoint/table",
        "file_name": page_title,
        "folder_path": folder_path,
        "url": page_url,
        "table_id": table.id
    }
)
```

---

### `_text_to_document(text_content, page_url, page_title)`
**Location:** Lines 600-700+

**Purpose:** Convert text content to Document

**Document Structure:**
```python
Document(
    page_content=text_content,
    metadata={
        "source_type": "sharepoint",
        "tag": "sharepoint/page",
        "file_name": page_title,
        "folder_path": folder_path,
        "url": page_url
    }
)
```

---

## Processing Flow

### 1. Page Crawling
```python
def crawl_pages(self, start_url: str) -> List[Document]:
    # BFS crawl from start_url
    # Follow links up to max_depth
    # Extract content from each page
    # Return all documents
```

### 2. Content Extraction
- FAQs extracted and converted to Documents
- Tables extracted and converted to Documents
- Text content extracted and converted to Documents

### 3. Chunking
- Documents chunked with `RecursiveCharacterTextSplitter`
- Chunk size: 1500 tokens
- Overlap: 200 tokens

### 4. Metadata Addition
- Source type: "sharepoint"
- Tag: "sharepoint/faq", "sharepoint/table", "sharepoint/page"
- File name, folder path, URL
- KB tier: "primary"

---

## Configuration

**From `config.py`:**
```python
SHAREPOINT_SITE_URL = "https://cloudfuzecom.sharepoint.com/sites/DOC360"
SHAREPOINT_START_PAGE = "/SitePages/Multi%20User%20Golden%20Image%20Combinations.aspx"
SHAREPOINT_MAX_DEPTH = 3
ENABLE_SHAREPOINT_SOURCE = True
```

---

## SharePoint Models

**Location:** `app/sharepoint_models.py`

**Models:**
- `SharePointPage` - Page data
- `SharePointFAQ` - FAQ item
- `SharePointTable` - Table data
- `SharePointCrawlResult` - Crawl result
- `SharePointMetadata` - Page metadata

---

## Authentication

**Location:** `app/sharepoint_auth.py`

**Method:** Microsoft Graph API authentication

**Functions:**
- `sharepoint_auth.get_headers()` - Get auth headers
- Uses application permissions or delegated permissions

---

## Error Handling

- **Network Errors:** Retry logic, timeout handling
- **Parse Errors:** Graceful degradation, skip invalid content
- **Auth Errors:** Re-authenticate, log errors

---

## Usage

### Process SharePoint Content
```python
from app.sharepoint_processor import SharePointProcessor

processor = SharePointProcessor()
documents = processor.crawl_pages(start_url)
```

### Integration
```python
from app.sharepoint_processor import process_sharepoint_content

documents = process_sharepoint_content()
# Returns List[Document]
```

---

## Output Statistics

```
[*] SharePoint Processor initialized
   Site URL: https://cloudfuzecom.sharepoint.com/sites/DOC360
   Start Page: /SitePages/...
   Max Depth: 3
   Exclude Files: true

[OK] Extracted 5 FAQs, 2 tables, 1 text block from Page Title
[OK] Processed 50 SharePoint pages
[OK] Created 200 documents
```

---

## Key Files

- **`app/sharepoint_processor.py`** - Main processor
- **`app/sharepoint_auth.py`** - Authentication
- **`app/sharepoint_models.py`** - Data models
- **`app/sharepoint_graph_extractor.py`** - Graph API extractor
- **`app/sharepoint_selenium_extractor.py`** - Selenium extractor (if used)

---

**Last Updated:** 2025-01-09  
**File:** `app/sharepoint_processor.py`
