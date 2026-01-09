# Scripts Documentation Index

## Complete Scripts Documentation

This index provides navigation to all utility scripts in the CloudFuze Chatbot system.

---

## 📋 All Scripts

### Data Processing Scripts

1. **[Transcript Processing](./DATA_PROCESSING_SCRIPTS.md#transcript-processing)**
   - `process_transcripts_from_sharepoint.py` - Process transcripts from SharePoint
   - `delete_transcript_chunks.py` - Delete transcript chunks from vectorstore
   - `inspect_transcripts.py` - Inspect transcript content

2. **[SharePoint Processing](./DATA_PROCESSING_SCRIPTS.md#sharepoint-processing)**
   - `extract_pptx_from_sharepoint.py` - Extract PPTX files from SharePoint

---

### Maintenance Scripts

1. **[Vectorstore Management](./MAINTENANCE_SCRIPTS.md#vectorstore-management)**
   - `backup_vectorstore.py` - Backup vectorstore data
   - `cleanup_bad_sessions.py` - Clean up bad sessions

2. **[Data Management](./MAINTENANCE_SCRIPTS.md#data-management)**
   - `export_cloudfuze_users.py` - Export user data
   - `count_blogs.py` - Count blog posts in vectorstore

---

### Analytics Scripts

1. **[Analytics & Monitoring](./ANALYTICS_SCRIPTS.md#analytics-monitoring)**
   - `analyze_user_questions.py` - Analyze user questions
   - `check_email_tracing.py` - Check email tracing

2. **[Langfuse Integration](./ANALYTICS_SCRIPTS.md#langfuse-integration)**
   - `auto_correct_low_scores.py` - Auto-correct low-scored responses
   - `process_bad_traces_and_log_to_langfuse.py` - Process bad traces

---

### Question Management Scripts

1. **[Question Management](./MAINTENANCE_SCRIPTS.md#question-management)**
   - `seed_suggested_questions.py` - Seed suggested questions
   - `reset_questions.py` - Reset questions
   - `auto_update_questions.py` - Auto-update questions

---

## 🔧 Script Categories

### By Purpose

| Category | Scripts | Purpose |
|----------|----------|---------|
| **Data Processing** | `process_transcripts_from_sharepoint.py`, `delete_transcript_chunks.py` | Process and manage data sources |
| **Maintenance** | `backup_vectorstore.py`, `cleanup_bad_sessions.py` | System maintenance tasks |
| **Analytics** | `analyze_user_questions.py`, `auto_correct_low_scores.py` | Analytics and monitoring |
| **Question Management** | `seed_suggested_questions.py`, `reset_questions.py` | Manage suggested questions |

---

## 📖 Documentation Files

### 1. [Data Processing Scripts](./DATA_PROCESSING_SCRIPTS.md)
- Transcript processing
- SharePoint extraction
- Data inspection

### 2. [Maintenance Scripts](./MAINTENANCE_SCRIPTS.md)
- Vectorstore backup
- Session cleanup
- Question management
- Data export

### 3. [Analytics Scripts](./ANALYTICS_SCRIPTS.md)
- User question analysis
- Langfuse integration
- Auto-correction
- Email tracing

---

## 🚀 Quick Reference

### Most Common Scripts

**Process Transcripts:**
```bash
python scripts/process_transcripts_from_sharepoint.py
```

**Backup Vectorstore:**
```bash
python scripts/backup_vectorstore.py
```

**Auto-Correct Low Scores:**
```bash
python scripts/auto_correct_low_scores.py --poll
```

**Seed Questions:**
```bash
python scripts/seed_suggested_questions.py
```

---

## 📁 Script Locations

**All scripts located in:** `scripts/`

**Script files:**
- `process_transcripts_from_sharepoint.py`
- `delete_transcript_chunks.py`
- `inspect_transcripts.py`
- `extract_pptx_from_sharepoint.py`
- `backup_vectorstore.py`
- `cleanup_bad_sessions.py`
- `export_cloudfuze_users.py`
- `count_blogs.py`
- `analyze_user_questions.py`
- `check_email_tracing.py`
- `auto_correct_low_scores.py`
- `process_bad_traces_and_log_to_langfuse.py`
- `seed_suggested_questions.py`
- `reset_questions.py`
- `auto_update_questions.py`

---

## 🔍 Script Usage Patterns

### One-Time Execution
```bash
python scripts/script_name.py
```

### With Options
```bash
python scripts/script_name.py --option value
```

### Dry Run
```bash
python scripts/script_name.py --dry-run
```

### Continuous Polling
```bash
python scripts/script_name.py --poll --interval 300
```

---

## ⚙️ Configuration

Most scripts use configuration from:
- `config.py` - Main configuration
- Environment variables (`.env` file)
- Command-line arguments

---

## 🛠️ Dependencies

Scripts require:
- Python 3.11+
- Application dependencies (from `requirements.txt`)
- Access to application modules (`app/`)

---

**Last Updated:** 2025-01-09  
**Location:** `scripts/`
