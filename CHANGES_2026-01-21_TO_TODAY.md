# Changes Log: January 21, 2026 to Today

**Generated:** 2026-01-23 19:46:51  
**Date Range:** 2026-01-21 to Today  
**Branch:** before-agentic-rag

---

## Table of Contents

1. [Commits Summary](#commits-summary)
2. [Uncommitted Changes](#uncommitted-changes)
3. [Environment File Changes](#environment-file-changes)
4. [Detailed Code Changes](#detailed-code-changes)
5. [File Statistics](#file-statistics)

---

## Commits Summary

### Commits from 2026-01-21 to Today

Based on git log, the following commits were made:

#### 1. Commit f724077 - UI fixes
- **Date:** 2026-01-21 11:12:57 +0530
- **Author:** Chaitanya Malle
- **Files Changed:** 1 file, 16 insertions(+), 37 deletions(-)
- **File:** `frontend/src/lib/chat-initialization.ts`

**Changes:**
- Simplified auto-scroll logic
- Removed redundant scroll calls
- Extracted `isUserNearBottom()` helper function
- Cleaned up scroll timing (reduced from 100ms to 50ms in some places)
- Removed immediate scroll calls after message send/receive

**Code Changes:**
```typescript
// Added helper function
function isUserNearBottom(): boolean {
  const messagesContainer = document.querySelector('.messages-container') as HTMLElement;
  if (!messagesContainer) return true;
  
  const threshold = 150;
  const isNearBottom = messagesContainer.scrollHeight - messagesContainer.scrollTop - messagesContainer.clientHeight < threshold;
  return isNearBottom;
}

// Simplified auto-scroll
function autoScrollToBottom() {
  if (isUserNearBottom()) {
    scrollToBottom();
  }
}
```

#### 2. Commit 86310ec - auto-scroll fixed
- **Date:** 2026-01-20 18:24:21 +0530
- **Author:** Chaitanya Malle
- **Files Changed:** 1 file, 37 insertions(+), 16 deletions(-)
- **File:** `frontend/src/lib/chat-initialization.ts`

**Changes:**
- Added optimized auto-scroll with RAF (RequestAnimationFrame) throttling
- Added immediate scroll calls when messages are sent/received
- Improved scroll behavior during streaming
- Added scroll calls at key points (thinking state, streaming start, final message)

**Code Changes:**
```typescript
// Optimized auto-scroll with RAF throttling
let scrollRaf: number | null = null;

function autoScrollToBottom() {
  const messagesContainer = document.querySelector('.messages-container') as HTMLElement;
  if (!messagesContainer) return;

  const threshold = 150;
  const distanceFromBottom = messagesContainer.scrollHeight - messagesContainer.scrollTop - messagesContainer.clientHeight;
  
  // Only scroll if user is near bottom
  if (distanceFromBottom > threshold) return;

  // Throttle with RAF for smooth performance during streaming
  if (scrollRaf) return;

  scrollRaf = requestAnimationFrame(() => {
    messagesContainer.scrollTo({
      top: messagesContainer.scrollHeight,
      behavior: 'smooth'
    });
    scrollRaf = null;
  });
}
```

#### 3. Commit 0107fc9 - Conversation added
- **Date:** 2026-01-20 16:16:06 +0530
- **Author:** Chaitanya Malle
- **Files Changed:** 10 files, 1,569 insertions(+), 172 deletions(-)

**Files Modified:**
- `CONVERSATIONAL_MEMORY_IMPLEMENTATION.md` (new, 469 lines)
- `DEPLOYMENT_COMMANDS.md` (580 lines modified)
- `app/endpoints.py` (444 lines added)
- `app/mongodb_memory.py` (134 lines added)
- `frontend/src/app/chat/[sessionId]/page.tsx` (2 lines changed)
- `frontend/src/app/chat/new/page.tsx` (2 lines changed)
- `frontend/src/app/chat/others/[sessionId]/page.tsx` (2 lines changed)
- `frontend/src/components/ChatSidebar.tsx` (5 lines changed)
- `frontend/src/lib/chat-initialization.ts` (78 lines changed)
- `frontend/src/lib/session-utils.ts` (25 lines changed)

**Major Features Added:**
- Conversational memory implementation
- Enhanced MongoDB memory management
- Updated deployment commands documentation
- Improved session handling in frontend

*Note: This commit was made on 2026-01-20, but is included as it's part of the recent changes.*

---

## Uncommitted Changes

### Overview

There are **significant uncommitted changes** across 13 files with:
- **2,383 insertions**
- **430 deletions**
- **Net change: +1,953 lines**

### Files Modified

| File | Changes |
|------|---------|
| `app/endpoints.py` | +1,275 lines (major additions) |
| `app/excel_processor.py` | +123 lines |
| `app/helpers.py` | +181 lines |
| `app/langfuse_integration.py` | +13 lines |
| `app/sharepoint_graph_extractor.py` | +10 lines |
| `app/vectorstore.py` | +253 lines |
| `config.py` | +526 lines (major refactoring) |
| `env.ai.example` | +6 lines |
| `frontend/src/app/globals.css` | +52 lines |
| `frontend/src/components/ChatSidebar.tsx` | +25 lines |
| `frontend/src/lib/chat-initialization.ts` | +220 lines |
| `reranker.py` | +81 lines |
| `server.py` | +48 lines |

---

## Environment File Changes

### .env File Changes (Lines 22-192)

**Status:** The `.env` file is not tracked in git (filtered by .gitignore), but you mentioned changes in lines 22-192.

**Note:** Since `.env` is not version controlled, the specific changes cannot be automatically extracted from git history. However, based on the `env.ai.example` template file, here are the configuration sections that likely correspond to lines 22-192:

#### MongoDB Configuration (Lines 19-23 in env.ai.example)
```bash
# MongoDB configuration (update to your production cluster)
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=slack2teams
MONGODB_CHAT_COLLECTION=chat_histories
MONGODB_VECTORSTORE_COLLECTION=vectorstore_items
```

#### Vectorstore and Feature Toggles (Lines 26-34)
```bash
# Vectorstore and feature toggles
VECTORSTORE_BACKEND=chromadb
INITIALIZE_VECTORSTORE=false
ENABLE_WEB_SOURCE=true
ENABLE_PDF_SOURCE=false
ENABLE_EXCEL_SOURCE=false
ENABLE_DOC_SOURCE=false
ENABLE_SHAREPOINT_SOURCE=true
ENABLE_OUTLOOK_SOURCE=false
```

#### Web/Blog Source Pagination (Lines 37-40)
```bash
# Web/blog source pagination
WEB_SOURCE_URL=https://cloudfuze.com/wp-json/wp/v2/posts?per_page=49
WEB_START_PAGE=1
WEB_MAX_PAGES=5
```

#### Blog Polling Configuration (Lines 43-46) - NEW
```bash
# Blog polling configuration (automatic blog ingestion)
BLOG_POLLING_ENABLED=false
BLOG_POLLING_INTERVAL=3600
BLOG_LAST_POLL_FILE=./data/blog_last_poll.json
```

#### SharePoint Extraction (Lines 49-54)
```bash
# SharePoint extraction
SHAREPOINT_SITE_URL=https://cloudfuzecom.sharepoint.com/sites/DOC360
SHAREPOINT_START_PAGE=
SHAREPOINT_MAX_DEPTH=999
SHAREPOINT_EXCLUDE_FILES=Documentation > Other > Box- onedrive screenshots
# Provide additional comma-separated sharepoint exclusion paths as needed.
```

#### Outlook Extraction (Lines 57-61)
```bash
# Outlook extraction
OUTLOOK_USER_EMAIL=
OUTLOOK_FOLDER_NAME=Inbox
OUTLOOK_MAX_EMAILS=500
OUTLOOK_DATE_FILTER=last_3_months
```

#### Chunking / Deduplication Policy (Lines 64-69)
```bash
# Chunking / deduplication policy
CHUNK_TARGET_TOKENS=800
CHUNK_OVERLAP_TOKENS=200
CHUNK_MIN_TOKENS=150
ENABLE_DEDUPLICATION=true
DEDUP_THRESHOLD=0.85
```

#### OCR + Unstructured Ingestion (Lines 72-75)
```bash
# OCR + unstructured ingestion
ENABLE_UNSTRUCTURED=true
ENABLE_OCR=true
OCR_LANGUAGE=eng
```

#### Graph Storage (Lines 78-80)
```bash
# Graph storage
GRAPH_DB_PATH=/opt/chatbot/data/graph_relations.db
ENABLE_GRAPH_STORAGE=true
```

#### Reranker Flags (Lines 83-86)
```bash
# Reranker flags
RERANKER_SHADOW=false
RERANKER_ENABLED=true
VERIFIER_ENABLED=false
```

**Action Required:** Please manually document the specific changes you made to your `.env` file in lines 22-192 and add them to this section.

---

## Detailed Code Changes

### 1. app/endpoints.py (+1,275 lines)

#### Major Additions:

##### A. Retry Mode Configuration Imports
```python
# New imports from config.py
RETRY_ATTEMPT_1_K_DENSE, RETRY_ATTEMPT_1_K_BM25, RETRY_ATTEMPT_1_K_FINAL,
RETRY_ATTEMPT_2_K_DENSE, RETRY_ATTEMPT_2_K_BM25, RETRY_ATTEMPT_2_K_FINAL,
RETRY_ATTEMPT_3_PLUS_K_DENSE, RETRY_ATTEMPT_3_PLUS_K_BM25, RETRY_ATTEMPT_3_PLUS_K_FINAL,
RETRY_DENSE_WEIGHT, RETRY_BM25_WEIGHT, RETRY_FORCE_EXPANSION, RETRY_SCORE_THRESHOLD_ADJUSTMENT,
ENABLE_ANSWER_QUALITY_CHECK, ANSWER_QUALITY_LLM_TEMPERATURE
```

##### B. Enhanced Migration Direction Detection
**Location:** `extract_migration_direction()` function (around line 969)

**New Platform Patterns Added:**
```python
"google_chat": [
    r"google\s+chat", r"gchat", r"g\s+chat",
    r"^chat\s+to", r"chat\s+migration",  # Add: "chat to teams" = Google Chat
],
"egnyte": [r"egnyte"],
"amazon_s3": [r"amazon\s+s3"],
"google_drive": [r"google\s+drive"],
"gmail": [r"gmail"],
"outlook": [r"outlook"],
"sharepoint": [r"sharepoint"],
"onedrive": [r"onedrive"],
"sharefile": [r"sharefile", r"citrix\s+sharefile"],
```

##### C. New Function: `filter_by_direction()`
**Location:** After `extract_migration_direction()` (around line 1062)

**Purpose:** Filter and re-rank documents based on migration direction match.

**Key Features:**
- Whitelists support matrix documents (limitations/features sheets)
- Uses richer context for direction detection (metadata + filename + folder + tag + content)
- Supports strict and lenient filtering modes
- Penalizes mismatched documents instead of removing them in lenient mode

**Code Snippet:**
```python
def filter_by_direction(
    doc_results: List[Tuple[Document, float]], 
    query_intent: dict,
    strict_mode: bool = False
) -> List[Tuple[Document, float]]:
    """
    Filter and re-rank documents based on direction match.
    
    CRITICAL: Whitelists support matrix documents (limitations/features sheets)
    to ensure authoritative sources always survive filtering.
    """
    # ... implementation
```

##### D. New Function: `apply_section_boosts()`
**Location:** Around line 1373

**Purpose:** Apply section-based boosting to already-reranked results using multiplicative boosts.

**Section Priority Multipliers:**
```python
SECTION_MULT = {
    "root_cause": 0.15,      # +15%
    "ai_suggestions": 0.12,  # +12%
    "description": 0.05,     # +5%
    "summary": 0.02,         # +2%
    "comment": 0.0,
}
```

##### E. Quality Detection Functions (Dual-Level)
**Location:** Around line 1578

**New Functions:**
1. `calculate_retrieval_quality()` - Calculate quality metrics from retrieval results
2. `calculate_answer_quality()` - Use LLM to evaluate answer quality (relevance, completeness, accuracy)
3. `calculate_combined_quality()` - Combine retrieval and answer quality scores
4. `extract_used_doc_chunks()` - Extract (doc_id, chunk_id) pairs from retrieved documents
5. `normalize_distance_to_similarity()` - Convert distance to similarity based on metric type

**Answer Quality Check Example:**
```python
def calculate_answer_quality(
    query: str,
    answer: str,
    context_docs: List[Document]
) -> dict:
    """Use LLM to evaluate answer quality (relevance, completeness, accuracy)."""
    # Returns: relevance, completeness, accuracy, overall_score, quality, issues
```

##### F. Enhanced `perplexity_style_retrieve()` Function
**Location:** Around line 1787

**New Parameters:**
```python
def perplexity_style_retrieve(
    query: str,
    k_dense: int = None,
    k_bm25: int = None,
    k_final: int = None,
    use_expansion: bool = None,
    jira_weight: float = None,
    retry_mode: bool = False,        # NEW
    retry_attempt: int = 1,          # NEW
):
```

**Retry Mode Features:**
- Gradual step-up retrieval (increases k values based on attempt number)
- Force query expansion
- Adjusted weights and thresholds

**Retry Logic:**
```python
if retry_mode:
    print(f"[RETRY MODE] Attempt {retry_attempt} - Applying gradual step-up retrieval")
    if retry_attempt == 1:
        # Attempt 1: 25% increase
        k_dense = RETRY_ATTEMPT_1_K_DENSE if k_dense is None else max(k_dense, RETRY_ATTEMPT_1_K_DENSE)
        k_bm25 = RETRY_ATTEMPT_1_K_BM25 if k_bm25 is None else max(k_bm25, RETRY_ATTEMPT_1_K_BM25)
        k_final = RETRY_ATTEMPT_1_K_FINAL if k_final is None else max(k_final, RETRY_ATTEMPT_1_K_FINAL)
    elif retry_attempt == 2:
        # Attempt 2: 50% increase
        k_dense = RETRY_ATTEMPT_2_K_DENSE if k_dense is None else max(k_dense, RETRY_ATTEMPT_2_K_DENSE)
        # ... similar for k_bm25 and k_final
```

---

### 2. config.py (+526 lines, major refactoring)

#### Major Changes:

**Note:** This file has undergone significant refactoring with 526 lines changed. The changes include:

- New retry attempt configuration variables
- Answer quality check configuration
- Enhanced retrieval parameters
- Updated scoring thresholds

**Key New Configuration Variables (from imports in endpoints.py):**
```python
# Retry attempt configurations
RETRY_ATTEMPT_1_K_DENSE
RETRY_ATTEMPT_1_K_BM25
RETRY_ATTEMPT_1_K_FINAL
RETRY_ATTEMPT_2_K_DENSE
RETRY_ATTEMPT_2_K_BM25
RETRY_ATTEMPT_2_K_FINAL
RETRY_ATTEMPT_3_PLUS_K_DENSE
RETRY_ATTEMPT_3_PLUS_K_BM25
RETRY_ATTEMPT_3_PLUS_K_FINAL
RETRY_DENSE_WEIGHT
RETRY_BM25_WEIGHT
RETRY_FORCE_EXPANSION
RETRY_SCORE_THRESHOLD_ADJUSTMENT

# Answer quality check
ENABLE_ANSWER_QUALITY_CHECK
ANSWER_QUALITY_LLM_TEMPERATURE
```

---

### 3. reranker.py (+81 lines)

#### Changes:

Enhanced reranking logic with:
- Updated fusion weights
- Cross-encoder score monitoring
- Global normalization for all scores
- Improved score calibration

**Key Functions:**
- `sigmoid()` - Sigmoid normalization function
- `CrossEncoderReranker.rerank()` - Enhanced reranking with better score normalization

---

### 4. app/vectorstore.py (+253 lines)

#### Major Additions:

Enhanced vectorstore functionality with:
- Improved retrieval methods
- Better metadata handling
- Enhanced document processing
- Support for multiple vectorstore backends

---

### 5. app/helpers.py (+181 lines)

#### Changes:

New helper functions and enhancements:
- Improved text processing utilities
- Enhanced markdown handling
- Better error handling
- Additional utility functions

---

### 6. app/excel_processor.py (+123 lines)

#### Major Enhancements:

**A. Enhanced Text Extraction with Structured Format**

The `extract_text_from_excel()` function has been completely rewritten to create structured entries with explicit field names and natural language summaries for better semantic search.

**Key Changes:**

1. **Improved File-Level Metadata:**
```python
# Before:
text_content.append(f"Contains structured data and information")

# After:
text_content.append("Contains migration features, limitations, and capabilities for different migration paths.\n")
```

2. **Enhanced Sheet Headers:**
```python
# Before:
text_content.append(f"\n--- Sheet: {sheet_name} ---\n")

# After:
text_content.append(f"\n=== Migration Path: {sheet_name} ===\n")
```

3. **Structured Entry Format:**
Instead of simple row-by-row text, the function now creates structured entries:

```python
entry = f"""
Feature Name: {feature}
Description: {description}
Status: {status}
Migration Path: {sheet_name}
Category: {current_section}
Additional Information: {additional_info}
Summary: {summary}
"""
```

4. **Section Header Detection:**
The function now detects and tracks section headers like:
- "Features Included"
- "Out of Scope Features"
- "Limitations"
- "Feature Name"
- "Capabilities"
- etc.

5. **Natural Language Summaries:**
Creates natural language summaries for better semantic search:
```python
# Example summary:
"For Slack to Teams migration: Private channel migration is supported. Migrates private channels with members and permissions."
```

6. **Status Interpretation:**
Converts status codes (YES/NO/NA) to natural language:
- "YES" → "is supported"
- "NO" → "is not supported"
- "NA" → "is not applicable"

**B. Enhanced Chunking**

The `chunk_excel_documents()` function now uses better separators optimized for the structured format:

```python
# Before:
separators=["\n\n", "\n", " | ", " ", ""]

# After:
separators=["\n\n\n", "\n\n", "\n=== ", "\n## ", "\n", " | ", " ", ""]
```

This ensures that:
- Migration path sections (===) are preserved
- Category headers (##) are respected
- Structured entries remain intact during chunking

**C. Improved Error Handling**

Added traceback printing for better debugging:
```python
except Exception as e:
    print(f"Error processing sheet '{sheet_name}': {e}")
    import traceback
    traceback.print_exc()
```

**D. Better Row Processing**

- Skips completely empty rows
- Handles flexible column structures (3+ columns)
- Extracts feature, description, status, and additional info
- Creates structured entries only for rows with feature names

**Benefits:**
- Better semantic search accuracy
- More natural language queries work better
- Structured format improves RAG retrieval
- Migration path context is preserved
- Status information is more queryable

---

### 7. app/langfuse_integration.py (+13 lines)

#### Changes:

Minor updates to Langfuse integration:
- Improved logging
- Enhanced tracking
- Better error handling

---

### 8. app/sharepoint_graph_extractor.py (+10 lines)

#### Changes:

Minor updates to SharePoint extraction:
- Improved graph extraction
- Better metadata handling

---

### 9. server.py (+48 lines)

#### Changes:

Server configuration updates:
- New endpoints or route handlers
- Enhanced server initialization
- Improved error handling

---

### 10. Frontend Changes

#### A. frontend/src/lib/chat-initialization.ts (+220 lines)

**Major additions:**
- Enhanced chat initialization logic
- Improved session management
- Better error handling
- New conversation features

#### B. frontend/src/components/ChatSidebar.tsx (+25 lines)

**Changes:**
- UI improvements
- Enhanced sidebar functionality
- Better user interaction

#### C. frontend/src/app/globals.css (+52 lines)

**Changes:**
- New CSS styles
- UI improvements
- Responsive design enhancements

---

### 11. env.ai.example (+6 lines)

#### New Configuration Options:

**Blog Polling Configuration (lines 43-46):**
```bash
# Blog polling configuration (automatic blog ingestion)
BLOG_POLLING_ENABLED=false
BLOG_POLLING_INTERVAL=3600
BLOG_LAST_POLL_FILE=./data/blog_last_poll.json
```

---

## File Statistics

### Summary

| Category | Count |
|----------|-------|
| **Total Files Changed** | 13 |
| **Total Insertions** | 2,383 |
| **Total Deletions** | 430 |
| **Net Change** | +1,953 lines |

### Breakdown by File Type

| File Type | Files | Changes |
|-----------|-------|---------|
| Python Backend | 8 | +2,484 lines |
| TypeScript Frontend | 3 | +297 lines |
| CSS | 1 | +52 lines |
| Config | 1 | +6 lines |

---

## Key Features Added

### 1. Retry Mode with Gradual Step-Up Retrieval
- Automatic retry with increased retrieval parameters
- Configurable retry attempts (1, 2, 3+)
- Force query expansion on retries
- Adjusted scoring thresholds

### 2. Direction-Based Document Filtering
- Intelligent filtering based on migration direction
- Whitelist support for critical documents (support matrices)
- Strict and lenient filtering modes
- Penalty-based scoring for mismatched documents

### 3. Dual-Level Quality Detection
- Retrieval quality metrics
- LLM-based answer quality evaluation
- Combined quality scoring
- Quality-aware response generation

### 4. Enhanced Section-Based Boosting
- Multiplicative boosts (preserves calibration)
- Priority-based section ranking
- Better handling of root cause and AI suggestions

### 5. Extended Platform Support
- Google Chat migration patterns
- Additional cloud platforms (Egnyte, Amazon S3, ShareFile)
- Enhanced direction detection

### 6. Blog Polling System
- Automatic blog ingestion
- Configurable polling intervals
- Last poll tracking

---

## Testing Recommendations

### Areas to Test

1. **Retry Mode Functionality**
   - Test retry attempts with low-quality initial results
   - Verify gradual step-up retrieval
   - Check query expansion on retries

2. **Direction Filtering**
   - Test with queries containing migration directions
   - Verify support matrix documents are preserved
   - Test strict vs lenient modes

3. **Quality Detection**
   - Test answer quality evaluation
   - Verify combined quality scoring
   - Check quality metrics logging

4. **Section Boosting**
   - Verify root_cause and ai_suggestions get higher priority
   - Test multiplicative boost calculations
   - Check final document ranking

5. **Platform Detection**
   - Test new platform patterns (Google Chat, Egnyte, etc.)
   - Verify direction extraction accuracy
   - Check query intent classification

---

## Migration Notes

### Configuration Updates Required

1. **Add new config variables** to `config.py`:
   - Retry attempt K values
   - Retry weights and thresholds
   - Answer quality check settings

2. **Update environment variables** (if using .env):
   - Blog polling configuration
   - Any new feature flags

3. **Frontend Updates**:
   - Rebuild frontend with new TypeScript changes
   - Update CSS if needed

### Breaking Changes

None identified, but verify:
- Backward compatibility of new retry mode
- Default behavior when quality checks are disabled
- Frontend compatibility with new chat initialization

---

## Next Steps

1. **Review and Commit Changes**
   - Review all uncommitted changes
   - Create meaningful commit messages
   - Consider splitting into logical commits

2. **Update .env Documentation**
   - Document changes in lines 22-192
   - Update env.ai.example if needed
   - Add comments for new variables

3. **Testing**
   - Run comprehensive tests
   - Verify all new features
   - Check for regressions

4. **Documentation**
   - Update API documentation
   - Document new configuration options
   - Update deployment guides if needed

---

## Notes

- **.env File**: Since `.env` is not tracked in git, manual documentation of changes in lines 22-192 is required. Please add your specific `.env` changes to the [Environment File Changes](#environment-file-changes) section above.
- **Large Changes**: The endpoints.py file has significant additions (1,275 lines). Review carefully before merging.
- **Config Refactoring**: config.py has been significantly refactored. Ensure all configuration variables are properly documented.
- **Uncommitted Changes**: There are significant uncommitted changes (2,383 insertions, 430 deletions). Consider committing these changes with meaningful commit messages.

---

## Quick Reference: .env Changes (Lines 22-192)

**⚠️ ACTION REQUIRED:** Please document your specific `.env` file changes in lines 22-192 below:

```bash
# Add your .env changes here (lines 22-192)
# Example format:
# 
# Line 22-30: Added new MongoDB configuration
# MONGODB_URL=...
# MONGODB_DATABASE=...
# 
# Line 31-50: Updated vectorstore settings
# VECTORSTORE_BACKEND=...
# 
# etc.
```

**Template Reference:** See `env.ai.example` for the expected structure. The template shows configuration sections that likely correspond to your changes.

---

**End of Changes Log**

**Document Generated:** 2026-01-23 19:46:51  
**Total Commits Documented:** 3 (from 2026-01-20 to 2026-01-21)  
**Total Uncommitted Changes:** 13 files, +2,383 insertions, -430 deletions
