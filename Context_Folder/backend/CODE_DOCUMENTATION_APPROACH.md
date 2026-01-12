# Code Documentation Approach

## What This Documentation Does

This documentation directly maps to your **actual code files** and explains:
1. **What each file does** - Purpose and responsibility
2. **What functions exist** - Function names, locations, parameters
3. **How they work** - Step-by-step what the code does
4. **Actual workflows** - How code flows through your system
5. **Real code references** - Line numbers, file paths, actual function signatures

---

## Documentation Created So Far

### ✅ Code-Focused Documentation

1. **`backend/LLM_INTEGRATION_CODE.md`**
   - Documents `app/llm.py` file
   - Explains `format_docs()`, `setup_qa_chain()`, `generate_recommended_questions_from_docs()`
   - Shows actual function locations (line numbers)
   - Explains what each function does step-by-step

2. **`backend/AUTHENTICATION_CODE.md`**
   - Documents `app/auth.py` file
   - Explains `get_current_user()`, `require_admin()`, `verify_user_access()`
   - Shows authentication flow (session → token fallback)
   - Documents actual security features

3. **`backend/MONGODB_MEMORY_CODE.md`**
   - Documents `app/mongodb_memory.py` file
   - Explains `MongoDBMemoryManager` class
   - Documents all methods: `add_to_conversation()`, `save_session()`, `get_user_statistics()`
   - Shows actual database collections and indexes

4. **`backend/RETRIEVAL_SYSTEM.md`**
   - Documents `perplexity_style_retrieve()` function in `app/endpoints.py`
   - Explains actual retrieval stages (dense, sparse, reranking)
   - Shows real configuration values from `config.py`

5. **`pipelines/TRANSCRIPT_PIPELINE.md`**
   - Documents `app/transcript_processor.py` file
   - Explains actual functions: `build_retrieval_text()`, `group_artifacts_for_chunking()`
   - Shows real processing stages from SharePoint to vectorstore

---

## Documentation Structure

Each code documentation file follows this structure:

### 1. File Header
```
## File: `app/filename.py`
This file handles [purpose]
```

### 2. Functions/Classes Section
For each function/class:
- **Location:** Line numbers
- **Purpose:** What it does
- **What it does:** Step-by-step explanation
- **Parameters:** Actual parameters
- **Returns:** What it returns
- **Raises:** Exceptions it raises

### 3. Code Examples
Real usage examples from your codebase

### 4. Configuration
Actual config values from `config.py`

---

## What's Different from Before

### ❌ Before (High-Level Overview)
- General system architecture
- Conceptual workflows
- No specific code references

### ✅ Now (Code-Focused)
- **Specific file documentation** (`app/llm.py`, `app/auth.py`, etc.)
- **Actual function documentation** with line numbers
- **Real workflows** as they exist in code
- **Code examples** from your actual codebase

---

## Next Files to Document

### Backend Core
- [ ] `app/endpoints.py` - All endpoint functions
- [ ] `app/vectorstore.py` - Vectorstore operations
- [ ] `app/enhanced_helpers.py` - Document processing
- [ ] `app/session_store.py` - Session storage

### Pipelines
- [ ] `app/sharepoint_processor.py` - SharePoint processing
- [ ] `app/pdf_processor.py` - PDF processing
- [ ] `app/pptx_processor.py` - PowerPoint processing
- [ ] `app/excel_processor.py` - Excel processing
- [ ] `app/outlook_processor.py` - Email processing

### Frontend
- [ ] `frontend/src/app/chat/page.tsx` - Chat interface
- [ ] `frontend/src/app/admin/dashboard/page.tsx` - Admin dashboard
- [ ] `frontend/src/components/ChatInterface.tsx` - Chat component
- [ ] `frontend/src/lib/api.ts` - API integration

---

## How to Use This Documentation

1. **Find the file you're working on** in the documentation
2. **See what functions exist** and what they do
3. **Understand the workflow** step-by-step
4. **Reference line numbers** to find code quickly
5. **See configuration** values used

---

## Example: Using LLM Integration Documentation

**Question:** "How does document formatting work?"

**Answer from documentation:**
- File: `app/llm.py`
- Function: `format_docs(docs)` at lines 18-104
- What it does:
  1. Iterates through documents
  2. Adds source tags
  3. For SharePoint: adds file name and folder
  4. For emails: adds thread metadata
  5. For downloads: adds download URL
- Returns: List of formatted strings

**Then you can:**
- Go to `app/llm.py` line 18
- See the actual code
- Understand exactly how it works

---

**This is code-focused documentation that maps directly to your actual codebase.**
