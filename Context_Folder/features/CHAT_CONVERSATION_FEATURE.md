# Chat & Conversation Feature

## Overview

The core chat feature allows users to ask questions and receive AI-powered responses using RAG (Retrieval-Augmented Generation) with streaming support.

---

## Related Files

### Backend Files

#### Core Chat Logic
- **`app/endpoints.py`**
  - `chat()` - Non-streaming chat endpoint (line 1365)
  - `chat_stream()` - Streaming chat endpoint with SSE (line 1624)
  - `perplexity_style_retrieve()` - Hybrid retrieval function (line 1077)
  - `classify_intent()` - Intent classification (line 143)
  - `expand_query_with_intent()` - Query expansion (line 320)
  - `is_conversational_query()` - Check if query is conversational (line 822)
  - `is_transcript_specific_query()` - Detect transcript queries (line 945)

#### LLM Integration
- **`app/llm.py`**
  - `format_docs()` - Format documents for LLM context (line 18)
  - `setup_qa_chain()` - Setup Q&A chain (line 107)
  - `generate_recommended_questions_from_docs()` - Generate follow-up questions (line 274)
  - `AsyncStreamHandler` - Streaming handler class (line 10)

- **`app/llm_factory.py`**
  - `get_llm()` - Factory function for LLM instances (line 10)
  - `_get_openai_llm()` - Create OpenAI LLM (line 35)
  - `_get_gemini_llm()` - Create Gemini LLM (line 61)

#### Retrieval Components
- **`bm25_retriever.py`**
  - BM25 keyword-based retrieval

- **`reranker.py`**
  - `CrossEncoderReranker` - Cross-encoder reranking model

- **`query_expander.py`**
  - `QueryExpander` - Query expansion for better retrieval

- **`context_compressor.py`**
  - `ContextCompressor` - Compress context when too long

#### Vectorstore
- **`app/vectorstore.py`**
  - `vectorstore` - ChromaDB vectorstore instance
  - `retriever` - LangChain retriever
  - `bm25_retriever` - BM25 retriever instance

#### Memory & Session
- **`app/mongodb_memory.py`**
  - `add_to_conversation()` - Save messages to history
  - `get_conversation_context()` - Get conversation context
  - `get_user_chat_history()` - Get user's chat history

#### Configuration
- **`config.py`**
  - `SYSTEM_PROMPT` - System prompt for LLM
  - `LLM_PROVIDER` - OpenAI or Gemini
  - `ENABLE_QUERY_EXPANSION` - Query expansion toggle
  - `ENABLE_CONTEXT_COMPRESSION` - Context compression toggle
  - `DENSE_RETRIEVAL_K`, `BM25_RETRIEVAL_K`, `FINAL_RETRIEVAL_K` - Retrieval parameters

### Frontend Files

#### Chat Pages
- **`frontend/src/app/chat/new/page.tsx`**
  - New chat page

- **`frontend/src/app/chat/[sessionId]/page.tsx`**
  - Chat page with session ID

- **`frontend/src/app/chat/others/[sessionId]/page.tsx`**
  - View other users' chats (read-only)

#### Chat Components
- **`frontend/src/components/ChatInterface.tsx`**
  - Main chat interface component
  - Handles message display, input, streaming

- **`frontend/src/components/ChatHeader.tsx`**
  - Chat header with title, actions

- **`frontend/src/components/ChatSidebar.tsx`**
  - Sidebar with session list

- **`frontend/src/components/TokenMonitor.tsx`**
  - Monitor token usage during streaming

#### API Integration
- **`frontend/src/lib/api.ts`**
  - `chatStream()` - Call streaming chat endpoint
  - `chat()` - Call non-streaming chat endpoint

#### Utilities
- **`frontend/src/lib/chat-initialization.ts`**
  - Chat initialization logic

- **`frontend/src/lib/session-utils.ts`**
  - Session utility functions

---

## Feature Workflow

1. **User sends question** → Frontend calls `/chat/stream`
2. **Authentication** → Verify user token
3. **Query Processing** → Classify intent, expand query
4. **Document Retrieval** → Dense + Sparse + Reranking
5. **Context Formatting** → Format documents for LLM
6. **LLM Generation** → Stream response tokens
7. **Session Save** → Save to MongoDB
8. **Analytics** → Track in Langfuse

---

## Key Functions

### Backend
- `chat()` - Main chat endpoint
- `chat_stream()` - Streaming chat endpoint
- `perplexity_style_retrieve()` - Hybrid retrieval
- `format_docs()` - Document formatting
- `setup_qa_chain()` - LLM chain setup

### Frontend
- `ChatInterface` - Main chat component
- `chatStream()` - API call for streaming
- `TokenMonitor` - Token usage tracking

---

## Configuration

**Retrieval:**
- `DENSE_RETRIEVAL_K = 60`
- `BM25_RETRIEVAL_K = 60`
- `FINAL_RETRIEVAL_K = 10`

**LLM:**
- `LLM_PROVIDER = "openai"` or `"gemini"`
- `SYSTEM_PROMPT` - System instructions

**Features:**
- `ENABLE_QUERY_EXPANSION = True`
- `ENABLE_CONTEXT_COMPRESSION = True`

---

**Last Updated:** 2025-01-09
