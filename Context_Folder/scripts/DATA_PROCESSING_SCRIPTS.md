# Data Processing Scripts Documentation

## Overview

Scripts for processing data sources (transcripts, SharePoint files) and managing vectorstore content.

---

## Transcript Processing

### `process_transcripts_from_sharepoint.py`
**Location:** `scripts/process_transcripts_from_sharepoint.py`

**Purpose:** Process transcript Word documents from SharePoint and add to vectorstore

**What it does:**
1. Extracts transcript documents from SharePoint folder
2. Processes transcripts into raw conversation and Q/A pairs
3. Builds retrieval text for artifacts
4. Groups artifacts for chunking
5. Adds processed documents to vectorstore

**Usage:**
```bash
# Process transcripts
python scripts/process_transcripts_from_sharepoint.py

# Dry run (preview only)
python scripts/process_transcripts_from_sharepoint.py --dry-run

# Custom folder path
python scripts/process_transcripts_from_sharepoint.py --folder-path "Neutara Labs/Transcripts"

# Custom site URL
python scripts/process_transcripts_from_sharepoint.py --site-url "https://..."
```

**Options:**
- `--dry-run` - Preview what will be processed without adding to vectorstore
- `--folder-path PATH` - Override transcript folder path
- `--site-url URL` - Override SharePoint site URL

**Functions:**
- `process_transcripts()` - Main processing function
- Uses `TranscriptProcessor` from `app/transcript_processor.py`
- Uses `EnhancedVectorstoreBuilder` for adding to vectorstore

**Output:**
- Documents added to ChromaDB vectorstore
- Statistics printed to console

---

### `delete_transcript_chunks.py`
**Location:** `scripts/delete_transcript_chunks.py`

**Purpose:** Delete transcript chunks from vectorstore

**What it does:**
1. Connects to ChromaDB vectorstore
2. Finds all documents with `source: "sharepoint_transcripts"`
3. Deletes matching documents
4. Reports deletion statistics

**Usage:**
```bash
python scripts/delete_transcript_chunks.py
```

**Note:** Use before reprocessing transcripts to avoid duplicates

**Warning:** This permanently deletes transcript chunks. Use with caution.

---

### `inspect_transcripts.py`
**Location:** `scripts/inspect_transcripts.py`

**Purpose:** Inspect transcript content without processing

**What it does:**
1. Fetches transcripts from SharePoint
2. Displays transcript metadata
3. Shows extracted artifacts
4. Preview of what would be processed

**Usage:**
```bash
python scripts/inspect_transcripts.py
```

**Use case:** Debug transcript extraction issues

---

## SharePoint Processing

### `extract_pptx_from_sharepoint.py`
**Location:** `scripts/extract_pptx_from_sharepoint.py`

**Purpose:** Extract PPTX files from SharePoint and process them

**What it does:**
1. Connects to SharePoint
2. Lists PPTX files in specified folder
3. Downloads PPTX files
4. Processes with `PPTXProcessor`
5. Stores extracted content

**Usage:**
```bash
python scripts/extract_pptx_from_sharepoint.py
```

**Configuration:**
- SharePoint site URL from config
- Folder path from config
- Output directory configurable

**Output:**
- Extracted PPTX content in JSON/text format
- Stored in `data/pptx_extracted/`

---

## Script Details

### Common Patterns

**Import Structure:**
```python
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.module import Class
from config import CONFIG_VALUE
```

**Error Handling:**
- Try-except blocks for API calls
- Graceful degradation
- Error logging

**Configuration:**
- Uses `config.py` for settings
- Environment variables for secrets
- Command-line arguments for overrides

---

## Integration Points

### Transcript Processing
- **`app/transcript_processor.py`** - TranscriptProcessor class
- **`app/enhanced_helpers.py`** - EnhancedVectorstoreBuilder
- **`app/vectorstore.py`** - Vectorstore management

### SharePoint Processing
- **`app/sharepoint_auth.py`** - Authentication
- **`app/pptx_processor.py`** - PPTXProcessor class
- **`app/sharepoint_graph_extractor.py`** - Graph API extractor

---

## Error Handling

### Common Errors

**SharePoint Authentication:**
- Invalid credentials → Check environment variables
- Token expired → Re-authenticate

**Vectorstore Errors:**
- Database corruption → Backup and rebuild
- Connection issues → Check ChromaDB path

**File Errors:**
- Missing files → Check SharePoint folder
- Permission denied → Check authentication

---

## Best Practices

1. **Dry Run First:** Always use `--dry-run` to preview changes
2. **Backup Before Deletion:** Backup vectorstore before deleting chunks
3. **Incremental Processing:** Process new transcripts incrementally
4. **Error Handling:** Check logs for errors
5. **Configuration:** Use environment variables for secrets

---

## Output Examples

### Transcript Processing
```
[*] Processing transcripts from SharePoint...
[*] Found 5 transcript files
[*] Processing: transcript1.docx
[OK] Extracted 10 Q&A pairs, 3 objections, 2 features
[OK] Created 5 documents
[*] Processing: transcript2.docx
...
[OK] Processed 5 transcripts
[OK] Created 23 documents
[OK] Added to vectorstore
```

### PPTX Extraction
```
[*] Extracting PPTX files from SharePoint...
[*] Found 10 PPTX files
[*] Downloading: presentation1.pptx
[OK] Extracted 20 slides
[OK] Saved to data/pptx_extracted/presentation1.json
...
[OK] Processed 10 PPTX files
```

---

## Key Files

- **`scripts/process_transcripts_from_sharepoint.py`** - Main transcript processor
- **`scripts/delete_transcript_chunks.py`** - Transcript deletion
- **`scripts/inspect_transcripts.py`** - Transcript inspection
- **`scripts/extract_pptx_from_sharepoint.py`** - PPTX extraction

---

**Last Updated:** 2025-01-09  
**Location:** `scripts/`
