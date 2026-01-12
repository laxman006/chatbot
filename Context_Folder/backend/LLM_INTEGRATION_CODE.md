# LLM Integration - Code Documentation

## File: `app/llm.py`

This file handles LLM integration, document formatting, and response generation.

---

## Functions

### `format_docs(docs)` 
**Location:** Lines 18-104

**Purpose:** Format retrieved documents with metadata for LLM context

**What it does:**
1. Iterates through retrieved documents
2. Adds source tags: `[SOURCE: {tag}]`
3. For SharePoint docs: Adds file name and folder path
4. For Outlook/Email docs: Adds email thread metadata (subject, participants, date range, email count)
5. For downloadable files: Adds download URL with `[DOWNLOAD LINK: ...]`
6. For videos: Adds video URL with `[VIDEO LINK: ...]`
7. For blog posts: Adds blog post URL with `[BLOG POST LINK: ...]`

**Returns:** List of formatted document strings

**Example Output:**
```
[SOURCE: sharepoint/blog]
File: CloudFuze_Migration_Guide.docx
Folder: Documentation/Migration

Content here...

[DOWNLOAD LINK: CloudFuze_Migration_Guide.docx (is_certificate: False, is_downloadable: True) - https://...]
```

---

### `setup_qa_chain(retriever)`
**Location:** Lines 107-208

**Purpose:** Creates a Q&A chain for semantic retrieval and response generation

**What it does:**
1. Creates prompt template with SYSTEM_PROMPT
2. Gets LLM instance from factory (temperature=0.1, streaming=True, max_tokens=1500)
3. Creates document chain: `prompt_template | llm | StrOutputParser()`
4. Returns `SemanticRetrievalQA` wrapper class

**SemanticRetrievalQA.invoke(inputs)** (Lines 136-205):
- Extracts query from inputs
- Performs primary semantic search: `vectorstore.similarity_search(query, k=25)`
- Rephrases query using LLM (temperature=0.0 for deterministic rephrasing)
- Performs secondary searches with rephrased queries (k=12 each)
- Deduplicates documents by content hash
- Limits to 30 documents
- Formats documents using `format_docs()`
- Invokes document chain with context and question
- Returns `{"result": answer}`

---

### `_generate_simple_keyword_recommendations(user_question)`
**Location:** Lines 211-271

**Purpose:** Generate keyword-based follow-up questions when no docs available (zero cost)

**What it does:**
- Checks question for keywords (cloudfuze, migrate, price, email, sharepoint, security)
- Returns 4 predefined questions based on keywords
- No LLM call - instant, free recommendations

**Returns:** List of 4 question strings

---

### `generate_recommended_questions_from_docs(user_question, retrieved_docs, bot_response=None)`
**Location:** Lines 274-389

**Purpose:** Generate 4-5 follow-up questions from already-retrieved documents (cost-effective)

**What it does:**
1. If no docs: Falls back to `_generate_simple_keyword_recommendations()`
2. Extracts content from top 8 docs (first 300 chars each)
3. Extracts topics/tags from metadata
4. Builds prompt with user question, doc content, and topics
5. Calls LLM (temperature=0.7, max_tokens=200) to generate questions
6. Parses JSON response or falls back to line-by-line parsing
7. Cleans and validates questions (10-200 chars, removes numbering)
8. Returns exactly 4 questions

**Returns:** List of 4 question strings

---

## Class: `AsyncStreamHandler`

**Location:** Lines 10-15

**Purpose:** Handles streaming LLM responses

**Methods:**
- `__init__()`: Creates asyncio.Queue
- `on_llm_new_token(token, **kwargs)`: Puts token in queue for streaming

---

## File: `app/llm_factory.py`

This file provides a factory function to create LLM instances based on provider configuration.

---

## Functions

### `get_llm(model_name=None, temperature=0.7, streaming=False, max_tokens=None)`
**Location:** Lines 10-32

**Purpose:** Factory function to create LLM instance

**What it does:**
- Checks `LLM_PROVIDER` from config (openai or gemini)
- Calls `_get_openai_llm()` or `_get_gemini_llm()` accordingly
- Raises ValueError if provider is invalid

**Returns:** ChatOpenAI or ChatGoogleGenerativeAI instance

---

### `_get_openai_llm(model_name, temperature, streaming, max_tokens)`
**Location:** Lines 35-58

**Purpose:** Create OpenAI ChatGPT LLM instance

**What it does:**
- Validates OPENAI_API_KEY exists
- Defaults to "gpt-4o-mini" if no model specified
- Creates ChatOpenAI with:
  - model_name
  - temperature
  - api_key
  - streaming (if enabled)
  - max_tokens (if specified)

**Returns:** ChatOpenAI instance

---

### `_get_gemini_llm(model_name, temperature, streaming, max_tokens)`
**Location:** Lines 61-87

**Purpose:** Create Google Gemini LLM instance

**What it does:**
- Validates GEMINI_API_KEY exists
- Defaults to "gemini-2.5-flash-lite" if no model specified
- Creates ChatGoogleGenerativeAI with:
  - model (not model_name)
  - temperature
  - api_key
  - streaming (if enabled)
  - max_output_tokens (not max_tokens)

**Returns:** ChatGoogleGenerativeAI instance

---

### `get_llm_provider_info()`
**Location:** Lines 90-97

**Purpose:** Get current LLM provider information for logging/debugging

**Returns:** Dictionary with provider, model, and API key status

---

## Configuration

**From `config.py`:**
- `LLM_PROVIDER`: "openai" or "gemini"
- `OPENAI_API_KEY`: Required if provider is "openai"
- `GEMINI_API_KEY`: Required if provider is "gemini"
- `SYSTEM_PROMPT`: System prompt for LLM

---

## Usage Examples

### Get LLM Instance
```python
from app.llm_factory import get_llm

# Default LLM (based on LLM_PROVIDER config)
llm = get_llm()

# Custom temperature
llm = get_llm(temperature=0.3)

# Streaming enabled
llm = get_llm(streaming=True, max_tokens=1000)
```

### Format Documents
```python
from app.llm import format_docs

formatted = format_docs(retrieved_documents)
context = "\n\n".join(formatted)
```

### Setup Q&A Chain
```python
from app.llm import setup_qa_chain
from app.vectorstore import retriever

qa_chain = setup_qa_chain(retriever)
result = qa_chain.invoke({"query": "What is CloudFuze?"})
answer = result["result"]
```

---

**Last Updated:** 2025-01-09  
**Files:** `app/llm.py`, `app/llm_factory.py`
