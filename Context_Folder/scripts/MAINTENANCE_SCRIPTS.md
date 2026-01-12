# Maintenance Scripts Documentation

## Overview

Scripts for system maintenance, vectorstore management, data export, and question management.

---

## Vectorstore Management

### `backup_vectorstore.py`
**Location:** `scripts/backup_vectorstore.py`

**Purpose:** Backup vectorstore data (ChromaDB)

**What it does:**
1. Connects to ChromaDB vectorstore
2. Exports all documents and metadata
3. Saves backup to file (JSON or other format)
4. Optionally compresses backup

**Usage:**
```bash
python scripts/backup_vectorstore.py
```

**Options:**
- `--output PATH` - Output file path
- `--compress` - Compress backup file

**Use case:** Before major changes or deletions

---

### `cleanup_bad_sessions.py`
**Location:** `scripts/cleanup_bad_sessions.py`

**Purpose:** Clean up bad or corrupted chat sessions

**What it does:**
1. Connects to MongoDB
2. Finds sessions matching criteria (empty, corrupted, old)
3. Deletes or fixes bad sessions
4. Reports cleanup statistics

**Usage:**
```bash
python scripts/cleanup_bad_sessions.py
```

**Options:**
- `--dry-run` - Preview what would be deleted
- `--older-than DAYS` - Delete sessions older than N days
- `--empty` - Delete empty sessions

**Use case:** Periodic cleanup of old or corrupted sessions

---

## Data Management

### `export_cloudfuze_users.py`
**Location:** `scripts/export_cloudfuze_users.py`

**Purpose:** Export user data to CSV/JSON/Excel

**What it does:**
1. Connects to MongoDB
2. Fetches user data
3. Exports to specified format (CSV, JSON, Excel)
4. Includes user statistics

**Usage:**
```bash
python scripts/export_cloudfuze_users.py
```

**Options:**
- `--format FORMAT` - Output format (csv, json, excel)
- `--output PATH` - Output file path

**Output files:**
- `cloudfuze_users.csv`
- `cloudfuze_users.json`
- `cloudfuze_users.xlsx`

---

### `count_blogs.py`
**Location:** `scripts/count_blogs.py`

**Purpose:** Count blog posts in vectorstore

**What it does:**
1. Connects to ChromaDB vectorstore
2. Queries documents with `tag: "blog"` or `is_blog_post: True`
3. Counts and reports statistics
4. Shows blog distribution

**Usage:**
```bash
python scripts/count_blogs.py
```

**Output:**
- Total blog posts
- Total blog chunks
- Blog post titles
- Metadata statistics

---

## Question Management

### `seed_suggested_questions.py`
**Location:** `scripts/seed_suggested_questions.py`

**Purpose:** Seed suggested questions into database

**What it does:**
1. Reads question list (from file or hardcoded)
2. Connects to MongoDB
3. Inserts questions into `suggested_questions` collection
4. Sets question metadata (category, priority, etc.)

**Usage:**
```bash
python scripts/seed_suggested_questions.py
```

**Options:**
- `--file PATH` - Read questions from file
- `--category CATEGORY` - Set question category
- `--overwrite` - Overwrite existing questions

**Use case:** Initial setup or updating question list

---

### `reset_questions.py`
**Location:** `scripts/reset_questions.py`

**Purpose:** Reset suggested questions to default set

**What it does:**
1. Deletes all existing suggested questions
2. Seeds default question set
3. Resets question statistics

**Usage:**
```bash
python scripts/reset_questions.py
```

**Warning:** This deletes all existing questions. Use with caution.

---

### `auto_update_questions.py`
**Location:** `scripts/auto_update_questions.py`

**Purpose:** Automatically update suggested questions based on analytics

**What it does:**
1. Analyzes user question patterns
2. Identifies popular questions
3. Updates suggested questions list
4. Removes outdated questions

**Usage:**
```bash
# Run once
python scripts/auto_update_questions.py

# Continuous mode
python scripts/auto_update_questions.py --poll --interval 3600
```

**Options:**
- `--poll` - Enable continuous polling
- `--interval SECONDS` - Polling interval
- `--min-frequency N` - Minimum question frequency

**Use case:** Keep suggested questions relevant

---

## Script Details

### Common Patterns

**MongoDB Connection:**
```python
from app.mongodb_memory import MongoDBMemoryManager

memory_manager = MongoDBMemoryManager()
memory_manager.connect()
```

**ChromaDB Connection:**
```python
from app.vectorstore import load_existing_vectorstore

vectorstore = load_existing_vectorstore()
```

**Error Handling:**
- Try-except blocks for database operations
- Graceful error messages
- Rollback on failure

---

## Integration Points

### Vectorstore
- **`app/vectorstore.py`** - Vectorstore management
- **`app/enhanced_helpers.py`** - Enhanced processing

### MongoDB
- **`app/mongodb_memory.py`** - MongoDB connection
- **`app/endpoints.py`** - API endpoints

### Configuration
- **`config.py`** - Configuration values
- Environment variables for secrets

---

## Error Handling

### Common Errors

**Database Connection:**
- Connection refused → Check MongoDB/ChromaDB running
- Authentication failed → Check credentials

**File Errors:**
- File not found → Check file paths
- Permission denied → Check file permissions

**Data Errors:**
- Invalid format → Validate data before processing
- Missing fields → Check data structure

---

## Best Practices

1. **Backup First:** Always backup before destructive operations
2. **Dry Run:** Use `--dry-run` to preview changes
3. **Incremental Updates:** Update data incrementally when possible
4. **Error Handling:** Check logs for errors
5. **Validation:** Validate data before processing

---

## Output Examples

### Backup Vectorstore
```
[*] Backing up vectorstore...
[*] Connecting to ChromaDB...
[OK] Found 10,000 documents
[*] Exporting documents...
[OK] Exported 10,000 documents
[OK] Saved backup to data/backup_2025-01-09.json
[OK] Backup size: 50 MB
```

### Cleanup Sessions
```
[*] Cleaning up bad sessions...
[*] Found 100 sessions
[*] Checking for bad sessions...
[OK] Found 5 empty sessions
[OK] Found 2 corrupted sessions
[*] Deleting bad sessions...
[OK] Deleted 7 sessions
[OK] Cleanup complete
```

### Export Users
```
[*] Exporting user data...
[*] Connecting to MongoDB...
[OK] Found 50 users
[*] Exporting to CSV...
[OK] Exported 50 users to cloudfuze_users.csv
[OK] Export complete
```

---

## Key Files

- **`scripts/backup_vectorstore.py`** - Vectorstore backup
- **`scripts/cleanup_bad_sessions.py`** - Session cleanup
- **`scripts/export_cloudfuze_users.py`** - User export
- **`scripts/count_blogs.py`** - Blog counting
- **`scripts/seed_suggested_questions.py`** - Question seeding
- **`scripts/reset_questions.py`** - Question reset
- **`scripts/auto_update_questions.py`** - Question auto-update

---

**Last Updated:** 2025-01-09  
**Location:** `scripts/`
