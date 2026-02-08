# Current Codebase Workflow

This document describes the end-to-end workflow of the RAG chatbot: **LangGraph + Weaviate + Langfuse**.

---

## 1. Application Entry

- **`server.py`** – FastAPI app, mounts routers, CORS, static files.
- **Routers:** `app.endpoints` (chat, sessions, feedback, analytics, admin), `app.routes.suggested_questions`.
- **Startup:** MongoDB init, optional suggested-questions seed, Jira sync scheduler (daily), weekly reports scheduler. Blog ingestion is done only via the Weaviate CLI (see §3).

---

## 2. Chat Flow (User Question → Answer)

### 2.1 API Layer

| Endpoint | Handler | Behavior |
|----------|---------|----------|
| `POST /chat` | `handle_chat` | Non-streaming: one request → full answer + `trace_id`. |
| `POST /chat/stream` | `handle_chat_stream` | Streaming: SSE tokens + final payload with `trace_id`. |
| `POST /chat/retry/stream` | `handle_chat_retry_stream` | Same as stream, with `previous_trace_id` and `retry_attempt` in Langfuse. |

All three live in **`app/chat_handlers.py`** and follow the same logic:

1. **Auth** – Done in `app/endpoints.py` via `require_auth`; `user_id`, `session_id`, `conversation_id`, etc. are passed into the handler.
2. **Langfuse** – Create a RAG pipeline trace (or fallback trace on failure).
3. **Run RAG** – `_run_rag_graph(question, user_id, session_id)` runs the LangGraph pipeline in a thread (sync `invoke`).
4. **Result** – `final_response` from graph state (or placeholder if the graph failed).
5. **Langfuse** – `_log_rag_trace(...)` logs intent, retrieval, rerank, validate, compress, citations, then completes the trace.
6. **Persistence** – For stream/retry, `save_message` and `add_to_conversation` (MongoDB) are called after the full response is known.

So the “brain” of chat is the **LangGraph RAG graph** invoked from `_run_rag_graph`.

### 2.2 RAG Graph (LangGraph)

Defined in **`app/rag/graph.py`** and **`app/rag/nodes.py`**, state in **`app/rag/state.py`**.

**State (`RAGState`)** carries: `query`, `user_id`, `session_id`, `user_context` (RBAC), then intent, `enhanced_query`, `expanded_queries`, `retrieved_docs`, `reranked_docs`, `validation_result`, `corrective_action`, `retry_count`, `compressed_context`, `context_token_count`, `final_response`, `citations`, `chunk_keys_cited`, and optional `trace` / `messages`.

**Graph shape:**

```
                    ┌──────────────────┐
                    │  classify_intent │
                    └────────┬─────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
  expand_query      decompose_query    retrieve_documents
         │                   │                   ▲
         └───────────────────┴───────────────────┤
                                                 │
                    ┌────────────────────────────┴─────────────┐
                    │              rerank_results              │
                    └────────────────────────────┬─────────────┘
                                                 │
                    ┌────────────────────────────▼─────────────┐
                    │            validate_context              │
                    └────────────────────────────┬─────────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
    quality OK / retry≥2          quality low & retry<2
              │                             │
              ▼                             ▼
     compress_context            apply_corrective_action
              │                             │
              │                             └──────────────────┐
              ▼                                                │
     generate_response  ◀──────────────────────────────────────┘
              │
              ▼
     extract_citations
              │
              ▼
             END
```

- **classify_intent** – Heuristics: “how to”/“steps” → procedural; multiple “?” or “ and ”/“ or ”/“ vs ” → complex; else factual. Sets `intent`, `intent_confidence`, `enhanced_query`.
- **expand_query** / **decompose_query** – Currently pass-through: `expanded_queries = [enhanced_query]` (or `[query]`). Can be extended with LLM-based expansion/decomposition.
- **retrieve_documents** – Uses **`app.weaviate_retriever.retrieve_from_weaviate`**: embeds the query with `text-embedding-3-small`, runs vector search over configured Weaviate collections, merges and sorts by distance, returns `(Document, distance)` up to `top_k` (default 50). Optional future: filter by `user_context` (RBAC).
- **rerank_results** – Keeps top `rerank_top_k` (default 15) by distance (stub; no cross-encoder yet).
- **validate_context** – CRAG-style: no docs → quality 0, “expand_topk”; else quality from avg distance, coverage (≥3 docs), diversity (source_type count). Sets `corrective_action` (“none” or “expand_topk”).
- **apply_corrective_action** – Increments `retry_count`, increases `top_k` (cap 150), then the graph returns to **retrieve_documents**.
- **compress_context** – Trims to ~6k tokens (tiktoken `cl100k_base`), fills `compressed_context` and `context_token_count`.
- **generate_response** – `config.SYSTEM_PROMPT` + “Answer from context…” → `get_llm()` → one LLM call with `HumanMessage( Context:\n{compressed_context}\n\nQuestion: {query} )` → `final_response`.
- **extract_citations** – Builds `citations` and `chunk_keys_cited` from top docs’ `chunk_key` / `source_ref` / `title` in metadata.

The graph is built by **`get_rag_graph()`** in `app/rag/graph.py` (lazy singleton, no checkpointer by default).

### 2.3 Retrieval Backend (Weaviate)

- **`app/weaviate_client.py`** – Singleton Weaviate client, health check; used by retriever and ingestion.
- **`app/weaviate_retriever.py`** – `retrieve_from_weaviate(query, k, collection_names)`:
  - Embeds `query` with OpenAI `text-embedding-3-small`.
  - Queries each collection in `app.weaviate_schema.COLLECTIONS` (or the given list) via vector search.
  - Merges and sorts by distance, returns top `k` as `List[(Document, float)]`.
- **`app/weaviate_schema.py`** – Collection names, source-type mapping, and schema (e.g. SharePointDocs, Blogs, JiraTickets, Transcripts, Spreadsheets, EmailThreads).

### 2.4 Langfuse

- **`app/langfuse_integration.py`** – `langfuse_tracker.create_rag_pipeline_trace(...)`, `create_trace(...)` for fallback.
- RAG trace records: intent span, retrieval (query, doc count, source breakdown), rerank span, validate-context span, compress-context span, citations span; then `complete(final_response, metadata)`.
- `trace_id` is returned to the client and used for feedback/analytics.

---

## 3. Document Ingestion (Weaviate)

Ingestion is **offline/CLI**: no in-process poller. Use the Weaviate pipeline + CLI.

### 3.1 CLI Entry

- **`scripts/ingest_to_weaviate.py`** – `--source {sharepoint|jira|blog|transcript|excel|email}` (required), optional `--collection`, `--no-incremental`, `--no-summaries`, `--no-dedup`, `--dry-run`.
- **`scripts/init_weaviate_schema.py`** – Creates/ensures all Weaviate collections from the schema.

### 3.2 Source Loaders (in `ingest_to_weaviate.py`)

- **sharepoint** → `app.sharepoint_graph_extractor.extract_sharepoint_via_graph()`
- **jira** → `app.jira_processor.JiraProcessor().process_jira_content()`
- **blog** → `app.helpers.fetch_latest_web_content()`
- **transcript** → `scripts.process_transcripts_from_sharepoint.process_transcripts()` (returns documents only)
- **excel** → `app.excel_processor.process_excel_directory(EXCEL_SOURCE_DIR)`
- **email** → `app.outlook_processor.process_outlook_content()`

Each loader returns a list of LangChain `Document` objects. The script maps source → collection name (e.g. blog → Blogs, jira → JiraTickets) and calls the pipeline.

### 3.3 Weaviate Ingestion Pipeline

**`app/weaviate_ingestion.py`** – `WeaviateIngestionPipeline`:

1. **Chunking** – `get_chunker(kind=MARKDOWN_AWARE, ...)` from `app.chunking` (fallback: `SemanticChunker` from `app.chunking_strategy`).
2. **Metadata** – `MetadataEnricher` (`app/metadata_enricher.py`): parent keys, chunk_key, source_type, etc.
3. **Dedup** – Optional `Deduplicator` (e.g. content-hash); stats go to `IngestReporter`.
4. **Embeddings** – `EmbeddingService` (`app/embedding_service.py`), same model as retrieval (`text-embedding-3-small`).
5. **Summaries** – Optional `SummaryGenerator` for summary chunks.
6. **Incremental** – `IncrementalIngestionTracker` (doc hashes, skip unchanged).
7. **Insert** – `WeaviateBatchInserter` into the target collection.

Result: **`IngestionResult`** (success, chunks_processed, chunks_inserted, failed_chunk_keys, errors, timing). Reporter can produce a text report.

---

## 4. Other API Surface (Unchanged by RAG Refactor)

- **`POST /feedback`** – Stores feedback (e.g. thumbs up/down, categories); can key by `trace_id`.
- **`GET /health`** – Health check.
- **`GET /analytics/langfuse/*`** – Langfuse-backed analytics (teams summary/details, dashboard, users, top-questions). Use same Langfuse client and trace data.
- **Chat history / sessions** – MongoDB via `app.mongodb_memory` (sessions, messages, shared chats, etc.).
- **Admin** – Blog status/stats (file-based metadata + Weaviate readiness); blog “poll” returns 501 and points to `ingest_to_weaviate.py --source blog`.

---

## 5. File Roles (Implementation-Centric)

| Role | Files / Modules |
|------|------------------|
| **Chat entry** | `app/endpoints.py` (routes), `app/chat_handlers.py` |
| **RAG graph** | `app/rag/state.py`, `app/rag/nodes.py`, `app/rag/graph.py`, `app/rag/__init__.py` |
| **Retrieval** | `app/weaviate_retriever.py`, `app/weaviate_client.py`, `app/weaviate_schema.py` |
| **LLM** | `app/llm_factory.py`, `config.SYSTEM_PROMPT` |
| **Observability** | `app/langfuse_integration.py` |
| **Ingestion** | `app/weaviate_ingestion.py`, `app/weaviate_batch_inserter.py`, `app/embedding_service.py`, `app/metadata_enricher.py`, `app/chunking/`, `app/chunking_strategy.py`, `app/deduplication.py`, `app/incremental_ingestion.py`, `app/summary_generator.py`, `app/ingest_reporter.py`, `scripts/ingest_to_weaviate.py`, `scripts/init_weaviate_schema.py` |
| **RBAC** | `app/rbac.py` (UserContext, filter_for_user – retrieves can use for scoping) |
| **Config** | `config.py` |

---

## 6. Data Flow Summary

```
User Question
    → POST /chat or /chat/stream or /chat/retry/stream
    → chat_handlers.handle_* (Langfuse trace, then _run_rag_graph)
    → get_rag_graph().invoke(state)
          classify_intent → [expand/decompose] → retrieve_documents (Weaviate)
          → rerank_results → validate_context → [compress | apply_corrective_action → retrieve again]
          → compress_context → generate_response (LLM) → extract_citations
    → answer + trace_id to client; messages saved to MongoDB (stream/retry)
```

```
Documents (SharePoint / Jira / Blog / Transcript / Excel / Email)
    → scripts/ingest_to_weaviate.py --source <name>
    → source loader → WeaviateIngestionPipeline.ingest_from_source(...)
    → chunk → enrich metadata → dedup (optional) → embed → batch insert into Weaviate
```

This is the current workflow of your codebase end to end.
