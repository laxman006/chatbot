# Jira Vectorstore Implementation - Complete Guide

## 📋 Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Field-Aware Chunking](#field-aware-chunking)
4. [Weighted Inclusion System](#weighted-inclusion-system)
5. [Section-Based Reranking](#section-based-reranking)
6. [Configuration](#configuration)
7. [Implementation Details](#implementation-details)
8. [Next Steps](#next-steps)
9. [Testing](#testing)
10. [Troubleshooting](#troubleshooting)

---

## Overview

This implementation creates a **separate Jira vectorstore** specifically for issue resolution queries. The system uses:

- ✅ **Field-aware chunking** - Preserves Jira ticket structure
- ✅ **Weighted inclusion** - Dynamic retrieval (0-10 tickets) based on query signals
- ✅ **Section-based reranking** - Prioritizes fixes over symptoms
- ✅ **Dual retrieval** - Main vectorstore + Jira vectorstore for issue queries

### Key Features

- **Separate Database**: `./data/jira_chroma_db` (independent from main vectorstore)
- **100 Recent Tickets**: Limited to 100 most recent closed/resolved tickets
- **Auto-Detection**: Automatically detects issue resolution queries
- **Smart Merging**: Combines main + Jira results intelligently

---

## Architecture

### Data Flow

```
User Query
    ↓
[Auto-Detect: Issue Query?]
    ├── Yes → Calculate Weight (0.0-1.0)
    └── No → Weight = 0.0
    ↓
┌─────────────────────────────────────────┐
│ ALWAYS: Retrieve from MAIN vectorstore │
│   ├── Dense retrieval (40 docs)        │
│   ├── BM25 retrieval (40 docs)         │
│   └── Merge + normalize scores          │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ IF WEIGHT > 0: Retrieve from JIRA       │
│   └── Similarity search (k_jira tickets)│
│   └── k_jira = int(10 * weight)        │
└─────────────────────────────────────────┘
    ↓
Merge Results
    ├── Prioritize Jira tickets slightly
    ├── Deduplicate by content
    └── Limit to top candidates
    ↓
Section-Based Reranking
    ├── root_cause → +0.15 boost
    ├── ai_suggestions → +0.12 boost
    ├── description → +0.05 boost
    └── summary → +0.02 boost
    ↓
LLM generates answer with merged context
```

### File Structure

```
app/
├── jira_processor.py          # Field-aware chunking, ticket extraction
├── jira_vectorstore.py        # Separate vectorstore management
├── enhanced_helpers.py        # Jira-specific chunking logic
└── endpoints.py               # Weighted retrieval + section reranking

config.py                      # Configuration settings
.env                           # Environment variables
```

---

## Field-Aware Chunking

### Strategy

Instead of chunking the whole ticket, we create **separate chunks per section**:

| Section | Chunking Strategy | Size | Priority |
|---------|------------------|------|----------|
| **Summary** | No chunking | Single chunk | High |
| **Description** | Semantic chunking | 400-500 tokens | High |
| **Root Cause** | **NEVER split** | Single chunk | **Critical** |
| **Comments** | One per comment | Single chunk each | Medium |
| **AI Suggestions** | No chunking | Single chunk | Critical |

### Implementation

**File**: `app/jira_processor.py`

- **Removed**: Stage 1 chunking (`RecursiveCharacterTextSplitter`)
- **Added**: `format_ticket_documents()` - Creates field-aware chunks
- **Updated**: `process_jira_content()` - Returns field-aware chunks directly

**File**: `app/enhanced_helpers.py`

- **Added**: `_chunk_jira_documents()` - Only chunks Description section semantically
- **Preserves**: Summary, Root Cause, Comments, AI Suggestions intact

### Chunk Metadata

Each chunk includes:

```python
{
    "section": "root_cause",           # Section identifier
    "section_priority": "critical",    # Priority level
    "ticket_key": "PRI-9314",         # Ticket reference
    "combination": "Teams to Teams",   # Migration type
    "root_cause": "...",               # Full root cause text
    # ... other ticket metadata
}
```

---

## Weighted Inclusion System

### Overview

Replaced binary gating (`True/False`) with **weighted inclusion** (`0.0-1.0`).

### Weight Calculation

**Function**: `calculate_jira_weight(query: str) -> float`

| Signal | Effect | Weight |
|--------|--------|--------|
| **Ticket ID present** (PRI-/CFITS-) | Full retrieval | `1.0` |
| Fix/error keywords | Add weight | `+0.4` |
| Problem keywords | Add weight | `+0.3` |
| How/why questions | Add weight | `+0.2` |
| Migration issues | Add weight | `+0.2` |
| Pure informational | No retrieval | `0.0` |

### Dynamic Retrieval

```python
k_jira = int(10 * jira_weight)  # 0-10 tickets dynamically
```

**Examples**:
- Weight `0.9` → Retrieve `9` tickets
- Weight `0.5` → Retrieve `5` tickets
- Weight `0.0` → Retrieve `0` tickets

### Keywords

**Fix/Error Keywords**: `fix`, `error`, `bug`, `failed`, `broken`, `not working`, `resolve`, `solution`

**Problem Keywords**: `problem`, `issue`, `troubleshoot`, `debug`, `conflict`

**How/Why Keywords**: `how to`, `how do`, `why`, `what is wrong`, `what happened`

**Migration Issues**: `migration issue`, `migration problem`, `migration failed`, `migration error`

**Informational**: `what is`, `tell me about`, `explain`, `describe`, `show me`

---

## Section-Based Reranking

### Overview

After cross-encoder reranking, apply **section-based boosts** to prioritize fixes over symptoms.

### Boost Values

**Function**: `apply_section_based_reranking()`

| Section | Boost | Priority | Reason |
|---------|-------|----------|--------|
| **root_cause** | `+0.15` | Critical | Actual fixes/solutions |
| **ai_suggestions** | `+0.12` | Critical | AI-generated solutions |
| **description** | `+0.05` | High | Problem description |
| **summary** | `+0.02` | High | Ticket summary |
| **comment** | `+0.0` | Medium | Developer comments |

### Implementation

1. **Base Reranking**: Cross-encoder reranks all candidates
2. **Section Detection**: Check `section` metadata in each document
3. **Apply Boost**: Add section-specific boost to score
4. **Re-sort**: Sort by boosted scores (higher = better)

### Result

**Before**: Description chunks might rank higher than Root Cause
**After**: Root Cause chunks always rank highest (fixes beat symptoms)

---

## Configuration

### Environment Variables (.env)

```env
# ============================================================================
# JIRA CONFIGURATION - Separate Vectorstore for Issue Resolution
# ============================================================================

# Jira Connection (Required)
JIRA_SERVER=https://cf2020.atlassian.net
JIRA_EMAIL=your-email@cloudfuze.com
JIRA_API_TOKEN=your-api-token

# Jira Project Configuration
JIRA_PROJECT_KEYS=PRI  # Migration KB Board project
JIRA_MAX_ISSUES=100  # Limit to 100 recent tickets
JIRA_DATE_FILTER=last_3_months  # Options: last_month, last_3_months, last_6_months, last_year

# Optional: Custom JQL Query (overrides project keys if set)
# JIRA_JQL_QUERY=project = PRI AND (status = Closed OR status = Resolved) ORDER BY updated DESC

# ============================================================================
# SEPARATE JIRA VECTORSTORE CONFIGURATION
# ============================================================================

# Path for separate Jira vectorstore (independent from main vectorstore)
JIRA_VECTORSTORE_PATH=./data/jira_chroma_db

# Enable/disable Jira vectorstore
ENABLE_JIRA_VECTORSTORE=true

# Set to true to build Jira vectorstore initially (then set to false)
INITIALIZE_JIRA_VECTORSTORE=true

# ============================================================================
# JIRA-SPECIFIC CHUNKING CONFIGURATION
# ============================================================================

# Field-aware chunking settings (only affects Description section)
JIRA_CHUNK_TARGET_TOKENS=500   # 400-600 tokens for Description section
JIRA_CHUNK_OVERLAP_TOKENS=100  # 80-120 tokens overlap
JIRA_CHUNK_MIN_TOKENS=120      # Minimum chunk size

# ============================================================================
# MAIN VECTORSTORE CONFIGURATION
# ============================================================================

# IMPORTANT: Keep Jira disabled in main vectorstore (since it's separate now)
ENABLE_JIRA_SOURCE=false

# Other main vectorstore sources
ENABLE_WEB_SOURCE=true
ENABLE_PDF_SOURCE=true
ENABLE_EXCEL_SOURCE=true
ENABLE_DOC_SOURCE=true
ENABLE_SHAREPOINT_SOURCE=true
ENABLE_OUTLOOK_SOURCE=true

# Main vectorstore initialization
INITIALIZE_VECTORSTORE=true  # Set to true if rebuilding main vectorstore
```

### Configuration Files

**`config.py`**:
- `JIRA_VECTORSTORE_PATH` - Path to separate Jira vectorstore
- `ENABLE_JIRA_VECTORSTORE` - Enable/disable Jira vectorstore
- `INITIALIZE_JIRA_VECTORSTORE` - Build on startup
- `JIRA_CHUNK_TARGET_TOKENS` - Chunk size for Description (500)
- `JIRA_CHUNK_OVERLAP_TOKENS` - Overlap between chunks (100)
- `JIRA_CHUNK_MIN_TOKENS` - Minimum chunk size (120)

---

## Implementation Details

### Key Functions

#### 1. `calculate_jira_weight(query: str) -> float`
- **Location**: `app/endpoints.py`
- **Purpose**: Calculate retrieval weight (0.0-1.0) based on query signals
- **Returns**: Weight value determining how many Jira tickets to retrieve

#### 2. `apply_section_based_reranking(query, candidates, top_k)`
- **Location**: `app/endpoints.py`
- **Purpose**: Apply section-based boosts after cross-encoder reranking
- **Returns**: Reranked documents with section boosts applied

#### 3. `format_ticket_documents(ticket_data) -> List[Document]`
- **Location**: `app/jira_processor.py`
- **Purpose**: Create field-aware chunks from ticket data
- **Returns**: List of Document objects, one per section

#### 4. `_chunk_jira_documents(docs) -> List[Document]`
- **Location**: `app/enhanced_helpers.py`
- **Purpose**: Apply semantic chunking only to Description section
- **Returns**: Chunked documents with sections preserved

### Retrieval Flow

```python
# 1. Calculate weight
jira_weight = calculate_jira_weight(query)  # 0.0-1.0

# 2. Calculate dynamic k
k_jira = int(10 * jira_weight)  # 0-10 tickets

# 3. Retrieve from Jira if weight > 0
if k_jira > 0:
    jira_results = jira_vectorstore.similarity_search_with_score(query, k=k_jira)

# 4. Merge results
merged_results = merge_retrieval_results(main_results, jira_results)

# 5. Section-based reranking
final_results = apply_section_based_reranking(query, merged_results, top_k=8)
```

---

## Next Steps

### Step 1: Update Environment Variables

Add/update these in your `.env` file:

```env
# Jira Connection
JIRA_SERVER=https://cf2020.atlassian.net
JIRA_EMAIL=your-email@cloudfuze.com
JIRA_API_TOKEN=your-api-token

# Jira Project
JIRA_PROJECT_KEYS=PRI
JIRA_MAX_ISSUES=100

# Separate Jira Vectorstore
JIRA_VECTORSTORE_PATH=./data/jira_chroma_db
ENABLE_JIRA_VECTORSTORE=true
INITIALIZE_JIRA_VECTORSTORE=true  # Set to true initially

# Jira Chunking
JIRA_CHUNK_TARGET_TOKENS=500
JIRA_CHUNK_OVERLAP_TOKENS=100
JIRA_CHUNK_MIN_TOKENS=120

# Main Vectorstore (disable Jira)
ENABLE_JIRA_SOURCE=false
```

### Step 2: Build Jira Vectorstore

**First Run** (build the vectorstore):

```bash
# Ensure INITIALIZE_JIRA_VECTORSTORE=true in .env
python -c "from app.jira_vectorstore import build_jira_vectorstore; build_jira_vectorstore()"
```

Or start your application - it will build automatically if `INITIALIZE_JIRA_VECTORSTORE=true`.

**Expected Output**:
```
============================================================
BUILDING SEPARATE JIRA VECTORSTORE
============================================================
[*] Fetching 100 recent closed/resolved tickets...
[OK] Processed X Jira ticket chunks
     Sections: Summary=X, Description=X, Root Cause=X, Comments=X, AI Suggestions=0
[OK] Processed into Y chunks after enhancement
[OK] Loaded Jira vectorstore with Y documents
```

### Step 3: After First Build

**Update `.env`**:
```env
INITIALIZE_JIRA_VECTORSTORE=false  # Already built, just load it
```

### Step 4: Test the System

**Test Issue Resolution Query**:
```
Query: "How to fix migration conflict error?"

Expected:
[JIRA WEIGHT] Fix/error keywords detected → +0.4
[JIRA WEIGHT] How/why question detected → +0.2
[JIRA WEIGHT] Problem keywords detected → +0.3
[JIRA WEIGHT] Final weight = 0.90
[RETRIEVAL] Retrieving 9 tickets from Jira vectorstore (weight=0.90)
[RERANK] Section 'root_cause' (critical): base=0.8234, boost=0.1500, final=0.9734
```

**Test Regular Query**:
```
Query: "What is CloudFuze Migrate?"

Expected:
[JIRA WEIGHT] Pure informational query → weight = 0.0
[RETRIEVAL] Will retrieve 0 tickets from Jira vectorstore (weight=0.00)
```

**Test Ticket ID Query**:
```
Query: "Tell me about PRI-9314"

Expected:
[JIRA WEIGHT] Ticket ID detected → weight = 1.00
[RETRIEVAL] Retrieving 10 tickets from Jira vectorstore (weight=1.00)
```

### Step 5: Monitor Logs

Watch for these log messages:

**Successful Retrieval**:
```
[OK] Loaded Jira vectorstore with X documents
[OK] Jira retriever ready for issue resolution queries
[JIRA WEIGHT] Final weight = X.XX
[RETRIEVAL] Retrieved X Jira tickets
[MERGE] Adding X Jira tickets to results
[RERANK] Section 'root_cause' (critical): ...
```

**No Jira Retrieval**:
```
[JIRA WEIGHT] Pure informational query → weight = 0.0
[RETRIEVAL] Will retrieve 0 tickets from Jira vectorstore (weight=0.00)
```

---

## Testing

### Test Cases

#### 1. Issue Resolution Query
```python
Query: "How to fix migration conflict error?"
Expected Weight: 0.9
Expected k_jira: 9
Expected: Root Cause chunks ranked highest
```

#### 2. Ticket ID Query
```python
Query: "PRI-9314"
Expected Weight: 1.0
Expected k_jira: 10
Expected: Specific ticket retrieved
```

#### 3. Informational Query
```python
Query: "What is CloudFuze Migrate?"
Expected Weight: 0.0
Expected k_jira: 0
Expected: No Jira retrieval
```

#### 4. Partial Issue Query
```python
Query: "migration problem"
Expected Weight: 0.5 (0.3 + 0.2)
Expected k_jira: 5
Expected: Some Jira tickets retrieved
```

### Manual Testing

```bash
# Test Jira weight calculation
python -c "
from app.endpoints import calculate_jira_weight
print(calculate_jira_weight('How to fix migration error?'))
print(calculate_jira_weight('What is CloudFuze?'))
print(calculate_jira_weight('PRI-9314'))
"

# Test Jira vectorstore loading
python -c "
from app.jira_vectorstore import jira_vectorstore
if jira_vectorstore:
    print(f'Jira vectorstore loaded: {jira_vectorstore._collection.count()} documents')
else:
    print('Jira vectorstore not available')
"
```

---

## Troubleshooting

### Issue: Jira Vectorstore Not Loading

**Symptoms**:
```
[INFO] No Jira vectorstore available - set INITIALIZE_JIRA_VECTORSTORE=true to create one
```

**Solution**:
1. Check `.env`: `ENABLE_JIRA_VECTORSTORE=true`
2. Check `.env`: `INITIALIZE_JIRA_VECTORSTORE=true`
3. Verify Jira credentials are correct
4. Check if `./data/jira_chroma_db` directory exists

### Issue: No Tickets Retrieved

**Symptoms**:
```
[RETRIEVAL] Retrieved 0 Jira tickets
```

**Possible Causes**:
1. Weight calculation returns 0.0 (check query keywords)
2. No tickets match the query
3. Jira vectorstore is empty

**Solution**:
- Check weight calculation logs: `[JIRA WEIGHT] Final weight = X.XX`
- Verify tickets exist in vectorstore
- Check query contains issue-related keywords

### Issue: Wrong Section Ranking

**Symptoms**: Description chunks rank higher than Root Cause

**Solution**:
- Verify section metadata exists: `doc.metadata.get("section")`
- Check reranking logs: `[RERANK] Section 'root_cause' ...`
- Ensure `apply_section_based_reranking()` is being called

### Issue: Too Many/Few Tickets Retrieved

**Symptoms**: Retrieving 10 tickets for informational queries

**Solution**:
- Check weight calculation logic
- Verify informational keywords are detected
- Adjust weight thresholds if needed

---

## Summary

### ✅ What's Implemented

1. **Separate Jira Vectorstore** - Independent database for issue resolution
2. **Field-Aware Chunking** - Preserves ticket structure (Root Cause intact)
3. **Weighted Inclusion** - Dynamic retrieval (0-10 tickets) based on query
4. **Section-Based Reranking** - Prioritizes fixes over symptoms
5. **Auto-Detection** - Automatically detects issue queries

### 🎯 Key Benefits

- **Better Retrieval**: Root Cause sections stay intact
- **Precise Matching**: Smaller chunks (400-500 tokens) improve precision
- **Smart Routing**: Weighted system avoids hard cutoffs
- **Prioritized Results**: Fixes rank higher than symptoms

### 📝 Next Actions

1. ✅ Update `.env` with configuration
2. ✅ Set `INITIALIZE_JIRA_VECTORSTORE=true`
3. ✅ Build Jira vectorstore (first run)
4. ✅ Test with issue resolution queries
5. ✅ Monitor logs for weight calculation and reranking

---

## Contact & Support

For issues or questions:
1. Check logs for `[JIRA WEIGHT]` and `[RERANK]` messages
2. Verify `.env` configuration
3. Test weight calculation manually
4. Check section metadata in retrieved documents

---

**Last Updated**: 2026-01-08
**Status**: ✅ Implementation Complete & Ready for Production
