# PDF Processing Pipeline Documentation

## Overview

Extracts text from PDF files and converts them to LangChain Documents for the vectorstore.

**Location:** `app/pdf_processor.py`

---

## Pipeline Architecture

```
PDF Directory
    │
    ├─► List PDF Files
    │   └─► Filter .pdf files
    │
    ├─► Extract Text (Multiple Methods)
    │   ├─► Method 1: pdfplumber (preferred)
    │   ├─► Method 2: PyMuPDF (fitz) - fallback
    │   └─► Method 3: PyPDF2 - last resort
    │
    ├─► Create Documents
    │   └─► One document per PDF
    │
    ├─► Chunk Documents
    │   └─► RecursiveCharacterTextSplitter (1500 tokens, 200 overlap)
    │
    └─► Add Metadata
        └─► source_type, tag, file_name, source
```

---

## Functions

### `extract_text_from_pdf(pdf_path)`
**Location:** Lines 32-74

**Purpose:** Extract text from PDF using multiple methods

**Methods (in order):**

1. **pdfplumber (Preferred)**
   ```python
   with pdfplumber.open(pdf_path) as pdf:
       for page in pdf.pages:
           text += page.extract_text() + "\n"
   ```
   - Most reliable for text extraction
   - Handles complex layouts well

2. **PyMuPDF (fitz) (Fallback)**
   ```python
   doc = fitz.open(pdf_path)
   for page_num in range(len(doc)):
       page = doc.load_page(page_num)
       text += page.get_text()
   ```
   - Better for complex layouts
   - Handles images and graphics

3. **PyPDF2 (Last Resort)**
   ```python
   pdf_reader = PyPDF2.PdfReader(file)
   for page in pdf_reader.pages:
       text += page.extract_text() + "\n"
   ```
   - Basic text extraction
   - Works for simple PDFs

**Returns:** Extracted text string

---

### `process_pdf_directory(pdf_directory)`
**Location:** Lines 76-141

**Purpose:** Process all PDF files in a directory

**What it does:**
1. Checks if directory exists
2. Lists all `.pdf` files
3. For each PDF:
   - Extracts text using `extract_text_from_pdf()`
   - Creates LangChain Document
   - Adds metadata
4. Chunks documents with `RecursiveCharacterTextSplitter`
5. Returns list of chunked documents

**Returns:** List of LangChain Documents

---

## Document Creation

### Document Structure
```python
Document(
    page_content=extracted_text,
    metadata={
        "source_type": "pdf",
        "tag": "pdf",
        "file_name": os.path.basename(pdf_path),
        "source": pdf_path,
        "kb_tier": "primary"
    }
)
```

---

## Chunking

### Text Splitter
```python
RecursiveCharacterTextSplitter(
    chunk_size=1500,
    chunk_overlap=200,
    separators=["\n\n", "\n", ". ", " ", ""]
)
```

**Parameters:**
- Chunk size: 1500 tokens
- Overlap: 200 tokens
- Separators: Paragraph, line, sentence, word

---

## Dependencies

### Required Libraries
- **pdfplumber** (preferred)
- **PyMuPDF (fitz)** (fallback)
- **PyPDF2** (last resort)

### Installation
```bash
pip install pdfplumber PyMuPDF PyPDF2
```

---

## Error Handling

### File Errors
- File not found → Skip file, log error
- Corrupted PDF → Try next method, log error
- Permission denied → Skip file, log error

### Extraction Errors
- Method 1 fails → Try Method 2
- Method 2 fails → Try Method 3
- All methods fail → Return empty string, log error

---

## Configuration

**From `config.py`:**
```python
ENABLE_PDF_SOURCE = True
PDF_SOURCE_DIR = "./data/pdfs"  # Directory containing PDF files
```

---

## Usage

### Process PDF Directory
```python
from app.pdf_processor import process_pdf_directory

documents = process_pdf_directory("./data/pdfs")
# Returns List[Document]
```

### Extract Text from Single PDF
```python
from app.pdf_processor import extract_text_from_pdf

text = extract_text_from_pdf("document.pdf")
```

---

## Processing Statistics

```
Processing 10 PDF files...
Processing: document1.pdf
Processing: document2.pdf
...
[OK] Processed 10 PDF files
[OK] Created 50 documents (chunks)
```

---

## Integration

### Vectorstore Integration
```python
from app.pdf_processor import process_pdf_directory
from app.enhanced_helpers import EnhancedVectorstoreBuilder

pdf_docs = process_pdf_directory(PDF_SOURCE_DIR)
builder = EnhancedVectorstoreBuilder()
chunks = builder.process_documents(pdf_docs, "pdf")
```

---

## Limitations

1. **Scanned PDFs:** Requires OCR (not implemented)
2. **Image-Only PDFs:** Text extraction may fail
3. **Complex Layouts:** May not preserve formatting
4. **Large PDFs:** Memory intensive for very large files

---

## Best Practices

1. **Use pdfplumber First:** Most reliable method
2. **Handle Errors Gracefully:** Try multiple methods
3. **Chunk Appropriately:** 1500 tokens per chunk
4. **Add Metadata:** Include file name and source
5. **Validate Text:** Check if text extraction succeeded

---

## Key Files

- **`app/pdf_processor.py`** - Main PDF processor
- **`app/helpers.py`** - Helper functions (if used)
- **`app/enhanced_helpers.py`** - Enhanced processing

---

**Last Updated:** 2025-01-09  
**File:** `app/pdf_processor.py`
