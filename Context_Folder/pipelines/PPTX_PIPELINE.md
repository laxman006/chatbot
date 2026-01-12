# PPTX Processing Pipeline Documentation

## Overview

Extracts content from PowerPoint (PPTX) files and processes them separately from the main vectorstore to avoid token waste from low-semantic-density presentation content.

**Location:** `app/pptx_processor.py`

---

## Pipeline Architecture

```
PPTX File
    │
    ├─► Extract with python-pptx (Native)
    │   ├─► Extract slide text
    │   ├─► Extract slide notes
    │   └─► Extract shapes and placeholders
    │
    ├─► OR Extract with Unstructured (Fallback)
    │   └─► Alternative extraction method
    │
    ├─► Process Each Slide
    │   ├─► Combine slide text
    │   ├─► Add notes if available
    │   └─► Create slide dictionary
    │
    ├─► Store Extracted Content
    │   ├─► JSON format
    │   ├─► Text format
    │   └─► Optional: Add to vectorstore
    │
    └─► Return Documents (if vectorstore integration)
```

---

## Class: `PPTXProcessor`

**Location:** `app/pptx_processor.py` (line 32)

**Purpose:** Process PowerPoint files separately from main ingestion

---

## Initialization

### `__init__(output_dir)`
**Location:** Lines 39-50

**Parameters:**
- `output_dir`: Directory to store extracted content (default: `./data/pptx_extracted`)

**What it does:**
- Creates output directory if it doesn't exist
- Checks for available libraries (python-pptx, unstructured)

---

## Key Functions

### `extract_with_pptx_library(pptx_path)`
**Location:** Lines 52-100+

**Purpose:** Extract text from PPTX using python-pptx library

**What it does:**
1. Opens PPTX file with `Presentation()`
2. For each slide:
   - Extracts text from shapes
   - Identifies title placeholders
   - Extracts notes if available
   - Combines content
3. Returns list of slide dictionaries

**Slide Dictionary:**
```python
{
    "slide_number": int,
    "content": str,  # Combined slide text
    "notes": str,     # Slide notes (if available)
    "has_content": bool
}
```

**Returns:** List of slide dictionaries

---

### `extract_with_unstructured(pptx_path)`
**Location:** Lines 100-200+

**Purpose:** Extract using Unstructured library (fallback)

**What it does:**
1. Uses `UnstructuredProcessor` if available
2. Extracts content from PPTX
3. Returns structured content

**Returns:** Extracted content (format depends on Unstructured)

---

### `process_pptx_file(pptx_path)`
**Location:** Lines 200-300+

**Purpose:** Process single PPTX file

**What it does:**
1. Tries `extract_with_pptx_library()` first
2. Falls back to `extract_with_unstructured()` if needed
3. Stores extracted content to output directory
4. Returns Documents (if vectorstore integration enabled)

**Output Files:**
- `{filename}.json` - Structured slide data
- `{filename}.txt` - Plain text extraction

**Returns:** List of LangChain Documents (if integrated)

---

### `process_pptx_directory(pptx_directory)`
**Location:** Lines 300-400+

**Purpose:** Process all PPTX files in directory

**What it does:**
1. Lists all `.pptx` files
2. Processes each file
3. Returns all documents

**Returns:** List of LangChain Documents

---

## Extraction Methods

### Method 1: python-pptx (Native)
**Library:** `python-pptx`

**Advantages:**
- Native PowerPoint support
- Fast extraction
- Preserves structure
- Access to notes

**Usage:**
```python
from pptx import Presentation

prs = Presentation(pptx_path)
for slide in prs.slides:
    for shape in slide.shapes:
        if hasattr(shape, "text"):
            text = shape.text
```

---

### Method 2: Unstructured (Fallback)
**Library:** `unstructured`

**Advantages:**
- Handles various formats
- Advanced extraction
- Better for complex layouts

**Usage:**
```python
from app.unstructured_processor import UnstructuredProcessor

processor = UnstructuredProcessor()
content = processor.extract(pptx_path)
```

---

## Document Structure

### If Integrated with Vectorstore
```python
Document(
    page_content=slide_content,
    metadata={
        "source_type": "pptx",
        "tag": "pptx",
        "file_name": filename,
        "slide_number": slide_num,
        "has_notes": bool,
        "kb_tier": "primary"
    }
)
```

---

## Storage Format

### JSON Format
```json
{
    "filename": "presentation.pptx",
    "slides": [
        {
            "slide_number": 1,
            "content": "Slide text...",
            "notes": "Speaker notes...",
            "has_content": true
        }
    ],
    "extracted_at": "2025-01-09T10:00:00Z"
}
```

### Text Format
```
# Slide 1
Slide text content here...

Notes:
Speaker notes here...

---

# Slide 2
...
```

---

## Configuration

**From `config.py`:**
```python
ENABLE_PPTX_SOURCE = True  # If enabled
PPTX_SOURCE_DIR = "./data/pptx"  # Directory with PPTX files
```

**Output Directory:**
- Default: `./data/pptx_extracted`
- Configurable in `PPTXProcessor.__init__()`

---

## Usage

### Process Single PPTX
```python
from app.pptx_processor import PPTXProcessor

processor = PPTXProcessor()
documents = processor.process_pptx_file("presentation.pptx")
```

### Process Directory
```python
from app.pptx_processor import PPTXProcessor

processor = PPTXProcessor()
documents = processor.process_pptx_directory("./data/pptx")
```

### Extract from SharePoint
```python
# Via script
python scripts/extract_pptx_from_sharepoint.py
```

---

## Integration Points

### Separate Processing
- PPTX files processed separately
- Stored in `data/pptx_extracted/`
- Not added to main vectorstore by default
- Avoids token waste from presentation content

### Optional Vectorstore Integration
- Can be enabled if needed
- Documents created per slide
- Chunked appropriately
- Added to vectorstore

---

## Dependencies

### Required
- **python-pptx** - Native PowerPoint support

### Optional
- **unstructured** - Alternative extraction method

### Installation
```bash
pip install python-pptx
pip install unstructured  # Optional
```

---

## Error Handling

### File Errors
- File not found → Log error, skip
- Corrupted PPTX → Try unstructured, log error
- Permission denied → Skip file, log error

### Extraction Errors
- python-pptx fails → Try unstructured
- Both fail → Log error, return empty

---

## Processing Statistics

```
[*] Processing presentation.pptx
[OK] Extracted 20 slides
[OK] Saved to data/pptx_extracted/presentation.json
[OK] Saved to data/pptx_extracted/presentation.txt
```

---

## Key Files

- **`app/pptx_processor.py`** - Main PPTX processor
- **`app/unstructured_processor.py`** - Unstructured processor (if used)
- **`scripts/extract_pptx_from_sharepoint.py`** - SharePoint extraction script

---

## Best Practices

1. **Separate Processing:** Keep PPTX separate from main vectorstore
2. **Store Extracted Content:** Save JSON and text for reference
3. **Handle Notes:** Include speaker notes for better context
4. **Title Detection:** Identify title placeholders for structure
5. **Error Handling:** Try multiple extraction methods

---

**Last Updated:** 2025-01-09  
**File:** `app/pptx_processor.py`
