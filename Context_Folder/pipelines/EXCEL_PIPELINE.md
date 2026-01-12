# Excel Processing Pipeline Documentation

## Overview

Extracts structured data from Excel files (.xlsx, .xls) and converts them to LangChain Documents for the vectorstore.

**Location:** `app/excel_processor.py`

---

## Pipeline Architecture

```
Excel Directory
    │
    ├─► List Excel Files
    │   └─► Filter .xlsx and .xls files
    │
    ├─► Extract Content (All Sheets)
    │   ├─► Read all sheets
    │   ├─► Extract column headers
    │   ├─► Extract data rows
    │   └─► Calculate statistics (numeric columns)
    │
    ├─► Convert to Text Format
    │   ├─► File metadata
    │   ├─► Sheet headers
    │   ├─► Row data (pipe-separated)
    │   └─► Summary statistics
    │
    ├─► Create Documents
    │   └─► One document per Excel file
    │
    ├─► Chunk Documents
    │   └─► RecursiveCharacterTextSplitter (1500 tokens, 200 overlap)
    │
    └─► Add Metadata
        └─► source_type, tag, file_name, source
```

---

## Functions

### `extract_text_from_excel(excel_path)`
**Location:** Lines 23-80

**Purpose:** Extract text content from Excel file (all sheets)

**What it does:**
1. Opens Excel file with `pd.ExcelFile()`
2. Adds file-level metadata
3. For each sheet:
   - Reads sheet with `pd.read_excel()`
   - Extracts column headers
   - Extracts data rows (pipe-separated)
   - Calculates statistics for numeric columns
   - Formats as text
4. Combines all sheets into single text

**Text Format:**
```
Excel file: filename.xlsx
Contains structured data and information

--- Sheet: Sheet1 ---
Columns: Column1 | Column2 | Column3

Row 1: Value1 | Value2 | Value3
Row 2: Value4 | Value5 | Value6

Summary for numeric columns:
Column2: mean=5.50, min=1.00, max=10.00

--- Sheet: Sheet2 ---
...
```

**Returns:** Formatted text string

---

### `process_excel_directory(excel_directory)`
**Location:** Lines 82-187

**Purpose:** Process all Excel files in directory

**What it does:**
1. Checks if directory exists
2. Lists all `.xlsx` and `.xls` files
3. For each Excel file:
   - Extracts text using `extract_text_from_excel()`
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
    page_content=extracted_text,  # Formatted Excel content
    metadata={
        "source_type": "excel",
        "tag": "excel",
        "file_name": os.path.basename(excel_path),
        "source": excel_path,
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
- Separators: Sheet separator, line, sentence, word

---

## Data Extraction Details

### Column Headers
- Extracted from first row
- Pipe-separated format: `Column1 | Column2 | Column3`

### Data Rows
- Each row formatted as: `Row N: Value1 | Value2 | Value3`
- Empty cells handled gracefully
- Only non-empty rows included

### Statistics (Numeric Columns)
- Mean, min, max calculated
- Only for numeric columns
- Formatted as: `Column: mean=X.XX, min=Y.YY, max=Z.ZZ`

---

## Dependencies

### Required Libraries
- **pandas** - Excel reading and data manipulation
- **openpyxl** - Excel file support (.xlsx)
- **xlrd** - Older Excel format support (.xls)

### Installation
```bash
pip install pandas openpyxl xlrd
```

---

## Error Handling

### File Errors
- File not found → Skip file, log error
- Corrupted Excel → Log error, skip file
- Permission denied → Skip file, log error

### Sheet Errors
- Sheet read fails → Log error, continue with other sheets
- Empty sheet → Skip sheet, continue
- Invalid data → Handle gracefully, log warning

---

## Configuration

**From `config.py`:**
```python
ENABLE_EXCEL_SOURCE = True
EXCEL_SOURCE_DIR = "./data/excel"  # Directory containing Excel files
```

---

## Usage

### Process Excel Directory
```python
from app.excel_processor import process_excel_directory

documents = process_excel_directory("./data/excel")
# Returns List[Document]
```

### Extract Text from Single Excel
```python
from app.excel_processor import extract_text_from_excel

text = extract_text_from_excel("data.xlsx")
```

---

## Processing Statistics

```
Processing 5 Excel files...
Processing: data1.xlsx
Processing: data2.xlsx
...
[OK] Processed 5 Excel files
[OK] Created 15 documents (chunks)
```

---

## Integration

### Vectorstore Integration
```python
from app.excel_processor import process_excel_directory
from app.enhanced_helpers import EnhancedVectorstoreBuilder

excel_docs = process_excel_directory(EXCEL_SOURCE_DIR)
builder = EnhancedVectorstoreBuilder()
chunks = builder.process_documents(excel_docs, "excel")
```

---

## Supported Formats

### File Extensions
- `.xlsx` - Modern Excel format (openpyxl)
- `.xls` - Older Excel format (xlrd)

### Sheet Types
- All sheets in workbook
- Named sheets
- Default sheets (Sheet1, Sheet2, etc.)

---

## Limitations

1. **Large Files:** Memory intensive for very large Excel files
2. **Complex Formulas:** Formula values extracted, not formulas
3. **Charts/Images:** Not extracted (text only)
4. **Formatting:** Formatting information not preserved
5. **Macros:** Macros not executed

---

## Best Practices

1. **Process All Sheets:** Include all sheets for completeness
2. **Include Statistics:** Add numeric column statistics
3. **Handle Empty Cells:** Skip empty rows/cells
4. **Chunk Appropriately:** 1500 tokens per chunk
5. **Add Metadata:** Include file name and source

---

## Key Files

- **`app/excel_processor.py`** - Main Excel processor
- **`app/helpers.py`** - Helper functions (if used)
- **`app/enhanced_helpers.py`** - Enhanced processing

---

**Last Updated:** 2025-01-09  
**File:** `app/excel_processor.py`
