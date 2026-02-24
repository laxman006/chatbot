# CloudFuze AI Assistant — End-to-End Project Documentation

This document describes the **entire codebase** from end to end: what is implemented, workflows, functionalities, and technical approaches. It serves as a single reference for the **Slack2teams-2-confident-chatbot** project (product name: **CloudFuze AI Assistant**).

---

## 1. Project Overview

### 1.1 Purpose

- **Internal AI chatbot** for CloudFuze (cloud migration and SaaS management).
- **RAG over internal knowledge**: Jira tickets, SharePoint docs, PDFs, transcripts, blogs, Excel (capabilities/limitations).
- **Conversational chat** with session history, shared chats, and optional **email drafting** (Copilot-style).
- **Admin dashboards**: teams, analytics, Jira sync, blog management, suggested questions, user activity.

### 1.2 Product Context

- **CloudFuze Migrate** (formerly X-Change): enterprise cloud-to-cloud migration (40+ providers).
- **CloudFuze Manage**: SaaS and AI application management (discovery, license optimization, governance).
- The assistant is **exclusively for internal team members** (developers, QA, sales, support); responses prioritize internal docs over marketing content.

---

## 2. Tech Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | Next.js 16, React 19, TypeScript, Tailwind CSS 4, Framer Motion, Radix UI, Axios, Recharts, Marked |
| **Backend** | Python, FastAPI, Uvicorn |
| **Databases** | MongoDB (chat histories, sessions, teams, users, suggested questions), SQLite (graph store), Chroma (main KB + capabilities + Jira) |
| **APIs** | Backend REST (FastAPI); Microsoft Graph (OAuth, user profile); optional Jira; internal ingest (SharePoint, Outlook) |
| **Auth** | Session-based (MongoDB session store) + Microsoft OAuth (login only); Bearer token fallback; admin allowlist **backend-only** (no admin list in frontend) |
| **Deployment** | Docker (multiple compose/Dockerfiles), nginx, shell/batch deploy scripts |

---

## 3. Architecture

### 3.1 High-Level Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Frontend (Next.js)                                                          │
│  /chat/new, /chat/[sessionId], /chats, /login, /admin/*, /api/proxy, shared  │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │ HTTP/SSE
┌───────────────────────────────────▼─────────────────────────────────────────┐
│  Backend (FastAPI) — server.py                                                │
│  Routers: chat_router (endpoints.py), suggested_questions, jira_sync         │
│  Static: /images, optionally /data                                           │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
┌───────────────┐         ┌─────────────────┐         ┌─────────────────┐
│  MongoDB      │         │  Chroma (main +  │         │  SQLite          │
│  sessions,    │         │  capabilities +  │         │  graph_store     │
│  chat_histories│         │  jira)           │         │  (relations)     │
│  teams, users │         │                  │         │                  │
└───────────────┘         └─────────────────┘         └─────────────────┘
```

### 3.2 Root-Level Backend Files

- **server.py** — FastAPI app, lifespan, mounts routers and static.
- **config.py** — Single source for env: LLM provider, Microsoft OAuth, MongoDB, feature flags, retrieval/routing/retry/synthesis, system prompts.
- **intelligent_router.py** — LLM-powered query router (allocates retrieval budget across sources).
- **multi_source_retrieval.py** — Multi-source retrieve, limitations retrieval, dedup, score normalization.
- **query_expander.py** — Query expansion (LLM).
- **reranker.py** — Cross-encoder reranker.
- **context_compressor.py** — Context compression before LLM.
- **bm25_retriever.py** — BM25 sparse retrieval.
- **preflight_check.py**, **start_server.sh**, **restart_services** (sh/bat), **deploy-*** scripts.

### 3.3 Backend Package (`app/`)

| Area | Key Modules |
|------|-------------|
| **Auth** | `auth.py` (session + Microsoft Graph), `session_store.py` (MongoDB sessions) |
| **Chat/API** | `endpoints.py` (streaming chat, sessions, shared chat, feedback, health) |
| **LLM** | `llm.py`, `llm_factory.py` (OpenAI/Gemini), `format_docs` for context |
| **Vectorstores** | `vectorstore.py` (main Chroma, BM25, init/rebuild), `jira_vectorstore.py`, `capabilities_vectorstore.py` |
| **Retrieval** | Used by endpoints: intelligent_router, multi_source_retrieval, query_expander, reranker, context_compressor |
| **Memory** | `mongodb_memory.py` (conversation, sessions, messages, shared chat, user profile, suggested questions, audit) |
| **Ingest** | `blog_poller.py`, `jira_processor.py`, `sharepoint_*`, `outlook_processor.py`, `transcript_processor.py`, `pptx_processor.py`, `pdf_processor.py`, `metadata_schema.py`, `chunking_strategy.py` |
| **Models** | `models/` (teams, jira_config, cloud_contract, etc.) |
| **Routes** | `routes/suggested_questions.py`, `routes/jira_sync.py` |
| **Services** | `services/jira_config_service.py` |
| **Helpers** | `helpers.py`, `enhanced_helpers.py`, `response_formatter.py`, `trace_utils.py`, `email_sender.py`, `langfuse_integration.py` |
| **Integrations** | `teams_repository.py`, `sharepoint_auth.py`, `web_tools.py`, `cloud_classifier.py`, `cloud_api_researcher.py`, `message_limitations_extractor.py`, `doc_link_extractor.py`, `js_scraper.py` |
| **Graph** | `graph_store.py` (SQLite document/chunk/relationship store) |

### 3.4 Frontend Structure (`frontend/src/`)

- **App root**: `app/layout.tsx` — root layout, metadata, GTM, structured data.
- **Pages**:
  - **Home**: `app/page.tsx` → redirects to `/chat/new`.
  - **Chat**: `app/chat/new/page.tsx`, `app/chat/[sessionId]/page.tsx`, `app/chat/others/[sessionId]/page.tsx`, `app/chat/shared/[token]/page.tsx`.
  - **List**: `app/chats/page.tsx`.
  - **Auth**: `app/login/page.tsx`.
  - **Admin**: `app/admin/dashboard/page.tsx`, `analytics`, `teams`, `teams-dashboard`, `users`, `blog`, `jira`, `top-questions`.
- **API routes**: `app/api/proxy/[...path]/route.ts` (dev proxy to backend), `app/api/shared-chat/[token]/route.ts`.
- **Lib**: `lib/chat-initialization.ts` (main chat UI logic, session state, streaming, parallel chats), `lib/api.ts`, `lib/session-utils.ts`, etc.
- **Components**: Chat UI, sidebars, filters, admin components under `components/`.
- **Types**: `types/chat.ts` and related.

---

## 4. Authentication & Authorization

### 4.1 Flow

1. **Login**: User signs in with Microsoft OAuth. Backend exchanges code for tokens, creates a **session** (stored in MongoDB via `session_store`), sets `session_id` cookie.
2. **Per request**: `get_current_user` (in `app/auth.py`) prefers **session cookie**; falls back to **Bearer token**. Session is validated from MongoDB; **no Microsoft Graph call** on every request (avoids random expiration).
3. **Identity**: `user_id` is normalized to user email (lowercase). `conversation_id` for chat memory = `user_id`.

### 4.2 Key Functions

- **get_current_user** — Returns `user_id`, `email`, `name`; 401 if invalid/expired.
- **verify_user_access** — Dependency for protected routes (requires valid user).
- **require_admin** / **require_restricted_admin** — Admin-only routes; allowlist from `ADMIN_EMAILS` (env) **on backend only**; frontend never receives the list; UI uses server-sent `is_admin` flag only.
- **can_access_api_research** — Feature flag for Cloud API research by user.

### 4.3 Session Store

- **app/session_store.py** — MongoDB-backed session storage (session_id, user_id, user_email, user_name, tokens, expiry). Token refresh can run in background when near expiry.

---

## 5. Chat & RAG Workflows

### 5.1 Entry Points

- **POST /chat** — Non-streaming; full answer in one response (used when streaming is not used).
- **POST /chat/stream** — **Primary**: Server-Sent Events (SSE) streaming; used by frontend.
- **POST /chat/retry** — Retry last assistant message (e.g. self-healing RAG with increased retrieval budget).

### 5.2 Request Flow (Streaming)

1. **Auth**: `require_auth` → `user_id`, `email`, `name` from session/token.
2. **Read body**: `question`, `session_id`, optional `ui_mode` (e.g. `"email"`), `refine_action`, `last_email_content`.
3. **Conversation context**: Last 8 messages for session from MongoDB (`get_last_messages`).
4. **Branching**:
   - **Email mode** (`ui_mode == "email"` or email-draft triggers):
     - Refinement (button or implicit): rewrite last email draft.
     - Pending CloudFuze clarification: re-evaluate with conversation; may return clarification or draft.
     - CloudFuze-related but not a draft: set pending and return clarification.
     - Not email-related / incomplete: return clarification message.
     - **Email draft**: Use `EMAIL_DRAFT_SYSTEM_PROMPT`, no RAG; stream response; save with `intent: email_draft`.
   - **Corrected response**: If a stored "corrected" answer matches question → stream it (no RAG).
   - **Cloud API research**: If feature enabled and user toggle ON → `research_cloud_api` + `format_cloud_research_markdown`; stream result.
   - **RAG path**: See §6 (retrieval pipeline); then build context, optionally compress, call LLM with system prompt + context + history, stream tokens.
5. **After reply**: Save user + assistant messages to MongoDB (`save_message`, `add_to_conversation`), log to Langfuse, return `done` with `trace_id`, `recommended_questions`, `intent`.

### 5.3 Identity & Security

- **user_id** is mandatory; 401 if missing.
- **conversation_id** = `user_id` (always email).
- Read-only sessions (`user_chat_*`) cannot receive new messages; frontend uses "Continue in thread" to create an editable copy.

### 5.4 Conversational Memory

- **MongoDB**: `get_last_messages(session_id, limit=8)` for context; `save_message` stores role, content, optional intent/email_content.
- **System prompt** instructs the model to use chat history only when relevant and to answer fresh when the question is unrelated.

---

## 6. Retrieval Pipeline (RAG)

### 6.1 Optional Components (Config)

- **ENABLE_INTELLIGENT_ROUTING** — Use LLM router to allocate retrieval budget per source.
- **ENABLE_QUERY_EXPANSION** — Expand query (e.g. 3 variants) for retrieval.
- **ENABLE_CONTEXT_COMPRESSION** — Compress context before sending to LLM.
- **USE_CONTEXT_SYNTHESIS** — Optional LLM step to synthesize all retrieved docs into one summary (experimental).

### 6.2 Intelligent Routing (when enabled)

- **intelligent_router.py** — `IntelligentQueryRouter.route_query(query)`:
  - LLM analyzes query and assigns **relevance + k** per source (blog, sharepoint, jira, transcripts, pdfs, excel).
  - Returns a **routing plan**: `query_type`, `query_intent`, `sources` (e.g. `blog: { k, relevance, reasoning }`), `confidence`.
  - "Who is &lt;person&gt;" questions can be short-circuited (no KB).
- **multi_source_retrieval.intelligent_multi_source_retrieve**:
  - Takes main vectorstore, Jira vectorstore, query, routing plan.
  - **Pinned**: Always retrieves limitations docs first (`retrieve_limitations_documents`).
  - Per-source retrieval via `retrieve_from_source` (blog, sharepoint, pdf, transcript, excel) and `retrieve_from_jira` (separate Chroma).
  - Optional deduplication (Jira tickets are never deduplicated).
  - Returns combined list of `(Document, score)`.

### 6.3 Fallback (no intelligent routing)

- **retrieve_with_branch_filter** (in endpoints) or similar: intent branches (e.g. general_business, slack_teams_migration) with fixed filters and query expansion; single vectorstore + optional Jira.
- **2-stage for support/limitations**: If question is "support/limitations" and answer contains support claims, merge Stage 1 docs with **limitations** docs (`merge_stage1_with_limitations`).

### 6.4 Hybrid Retrieval (Option E — Perplexity-style)

- **Dense**: Chroma similarity (embedding) — `DENSE_RETRIEVAL_K`.
- **Sparse**: BM25 — `BM25_RETRIEVAL_K`.
- **Weights**: `DENSE_WEIGHT`, `BM25_WEIGHT`; scores normalized and combined.
- **Rerank**: `CrossEncoderReranker.rerank(query, candidates, top_k)`; then `FINAL_RETRIEVAL_K` and optional `MIN_SCORE_THRESHOLD`.
- **Query expansion**: `QueryExpander.expand(query, n=3)`; expanded queries used for retrieval, then merged/deduped.
- **Context compression**: `ContextCompressor.compress(final_docs, max_chars)` before building the context string for the LLM.

### 6.5 Retry Mode (Self-Healing RAG)

- On **low confidence** or empty context, backend can retry with **increased retrieval budget** (config: `RETRY_ATTEMPT_1_*`, `RETRY_ATTEMPT_2_*`, `RETRY_ATTEMPT_3_PLUS_*` for DENSE_K, BM25_K, FINAL_K).
- **RETRY_FORCE_EXPANSION**, **RETRY_SCORE_THRESHOLD_ADJUSTMENT** for more recall on retries.
- **Answer quality check** (optional): LLM evaluates answer quality; can trigger retry or different handling.

### 6.6 Capabilities & Limitations

- **Capabilities vectorstore** (Chroma): Ingest from Excel (content + message/limitations); used for "supported/not supported" and migration capabilities.
- **get_capability_docs**, **get_migrations_mentioned_in_query** (in endpoints) — can augment context for capability questions.
- **retrieve_limitations_documents** — Always run when "always_include_limitations" is True; filter by `source_type` / `doc_type` / tag.

### 6.7 Context to LLM

- **format_docs** (in `app/llm.py`): Formats retrieved docs with tags (e.g. `[SOURCE: jira/...]`), Jira ticket headers (Root Cause, Fix Description, Ticket URL), SharePoint metadata, download URLs, video URLs.
- **System prompt**: `SYSTEM_PROMPT` from config (long rules: internal-only, source priority, Jira handling, no raw context leakage, download/video rules, etc.).
- **Conversational**: Last 8 messages + current question; optional `CONVERSATIONAL_SYSTEM_PROMPT` for relevance.

### 6.8 Chunking Strategies

Chunking is applied during **ingestion** so that retrieval and LLM context use consistent, semantically meaningful units.

**General documents (SharePoint, blog, PDF, etc.) — SemanticChunker** (`app/chunking_strategy.py`):

- **Target size**: Config `CHUNK_TARGET_TOKENS` (default 800), `CHUNK_OVERLAP_TOKENS` (200), `CHUNK_MIN_TOKENS` (150). Token counting uses tiktoken (`cl100k_base`) or a character-based estimate (~5.5 chars/token).
- **Strategy**:
  1. **Split by headings**: Detect Markdown (`#`), HTML (`<h1>`–`<h6>`), or title-with-colon lines; start a new chunk at each heading so sections stay intact.
  2. **Merge small chunks**: Chunks below `min_tokens` are merged with the next chunk if the combined size is under ~1.5× target.
  3. **Split large chunks**: Chunks above ~1.3× target are split with a **RecursiveCharacterTextSplitter** (separators: `\n\n\n`, `\n\n`, `\n`, `. `, `, `, space).
- **Output**: Each chunk gets metadata `chunk_index`, `total_chunks`, `char_range`, `token_count`. Convenience function: `chunk_documents_semantically(documents, target_tokens, overlap_tokens, min_tokens)`.

**Jira tickets — field-aware chunking** (`app/jira_processor.py`):

- **Summary**: One chunk per ticket (no splitting).
- **Description**: Semantically chunked with **Jira-specific** targets: `JIRA_CHUNK_TARGET_TOKENS` (500), `JIRA_CHUNK_OVERLAP_TOKENS` (100), `JIRA_CHUNK_MIN_TOKENS` (120). Only the Description section is split; other fields stay whole.
- **Root Cause / Fix Description**: Single chunk each, never split (critical for solution-oriented answers).
- **Comments**: One chunk per comment (no splitting).
- **AI suggestions**: One chunk per suggestion if present.
- Metadata includes `section` (`summary`, `description`, `root_cause`, `fix_description`, `comments`, etc.), `ticket_key`, `url`, `status`, `combination` (migration type).

**Transcripts** (config):

- `TRANSCRIPT_QA_CHUNK_TOKENS`, `TRANSCRIPT_FEATURE_CHUNK_TOKENS`, `TRANSCRIPT_OBJECTION_CHUNK_TOKENS`, `TRANSCRIPT_RAW_CHUNK_TOKENS` define target sizes for Q&A, feature, objection, and raw transcript chunks. Transcripts are tagged with `kb_tier: secondary` and optional `artifact_type` (Q&A, Objection, Feature, etc.).

**Chunk metadata** (`app/metadata_schema.py`):

- **create_chunk_metadata(base_metadata, chunk_index, total_chunks, char_start, char_end, token_count)**: Builds chunk-level metadata from base document metadata; adds `chunk_id`, `chunk_index`, `total_chunks`, `char_range`, `token_count`. **UnifiedMetadata** and **to_chroma_metadata()** ensure ChromaDB-compatible types (str, int, float, bool).

---

### 6.9 Retrieval Strategies (Detailed)

**Option E (hybrid retrieval) — main RAG path**:

1. **Query expansion** (optional, `ENABLE_QUERY_EXPANSION`): **QueryExpander** uses the LLM to generate `n=3` alternative phrasings (synonyms, related terms, max ~15 words). Original query + expansions are each used for retrieval; results are merged and deduplicated by (content_preview, source_type, page_url).
2. **Dense retrieval**: Chroma `similarity_search_with_score(query, k=k_dense)` per query (original + expansions). Returns `(doc, distance)`; lower distance = more similar. Config: `DENSE_RETRIEVAL_K` (e.g. 40); retry mode uses `RETRY_ATTEMPT_*_K_DENSE` (e.g. 75, 90, 120).
3. **Sparse retrieval (BM25)**: `bm25_retriever.search(query, k=k_bm25)` per query. BM25 scores are **unbounded**; they are **min-max normalized to [0, 1]** before fusion so they are comparable to dense similarity.
4. **Merge by document key**: Key = `(page_content[:120], source_type, page_url)`. For each doc, keep best dense distance and best BM25 score across all queries.
5. **Dense score → similarity**: Dense returns **distance** (lower = better). Normalize to [0, 1] with `(max_dist - dist) / (max_dist - min_dist)` so higher = better.
6. **Hybrid fusion**: `base_score = DENSE_WEIGHT * dense_sim + BM25_WEIGHT * bm25_sim` (config: e.g. 0.5, 0.3). Retry mode uses `RETRY_DENSE_WEIGHT` / `RETRY_BM25_WEIGHT`.
7. **Metadata boosts** (added to base_score before rerank): Primary KB boost (`PRIMARY_KB_PRIORITY_BOOST`), secondary KB / transcript artifact boosts (`SECONDARY_KB_PRIORITY_BOOST`, `TRANSCRIPT_ARTIFACT_BOOST`), SharePoint +0.05, priority high/medium +0.05 / +0.02.
8. **Wide rerank pool**: Candidates are split into primary-KB vs secondary-KB; each list is sorted by base score; then combined (primary first, then secondary) to form the pool for **reranking** (no early top-k slice before rerank).

**Intelligent routing path** (when `ENABLE_INTELLIGENT_ROUTING`):

- **intelligent_multi_source_retrieve**: Uses routing plan from **IntelligentQueryRouter** (LLM allocates k per source). **Pinned**: Always retrieves limitations docs first (`retrieve_limitations_documents`, k=4). Then retrieves per source: blog, sharepoint, jira (separate Jira Chroma), transcripts, pdfs, excel via `retrieve_from_source` / `retrieve_from_jira`. Optional deduplication (Jira tickets are never deduplicated). **normalize_scores**: Converts distance (lower=better) to similarity (higher=better) with min-max over the candidate list: `(max_score - score) / (max_score - min_score)`.

**2-stage support/limitations**:

- If the question is detected as support/limitations (`is_support_question`) and the draft answer contains support claims (`has_support_claim`), Stage 1 docs are merged with **limitations** docs via `merge_stage1_with_limitations` (Stage 1 first, then top N limitations docs, deduped by content fingerprint).

---

### 6.10 Reranking Strategies (Detailed)

**Cross-encoder reranker** (`reranker.py`):

- **Model**: `sentence_transformers` **CrossEncoder** (default `cross-encoder/ms-marco-MiniLM-L-12-v2`). Takes (query, document_content) pairs and returns a relevance score per pair.
- **Input**: List of `(doc, base_score)` or `(doc, base_score, dense_sim, bm25_sim)`. Base score is the hybrid score from retrieval (already in [0, 1] when normalized).
- **Calibration**: Cross-encoder raw scores are passed through **sigmoid** to get `ce_prob` in [0, 1] (stable, no per-batch min-max).
- **Dynamic fusion**: Instead of a fixed weight between CE and base score, the reranker computes a **spread** (e.g. top1 − top5 or top1 − top2) of CE scores. Higher spread = more confident ranking. **Certainty** = 0.7× normalized_spread + 0.3× mean(ce_prob). **CE weight** = 0.6 + 0.35× certainty (range ~0.6–0.95); base weight = 1 − CE weight. Final score = `ce_weight * ce_prob + base_weight * base_prob`. So when the cross-encoder is very decisive, it dominates; when scores are flat, base (hybrid) score matters more.
- **Output**: Reranked list `(doc, final_score)` sorted descending; then **top_k** (e.g. `FINAL_RETRIEVAL_K` = 8) is taken.

**Post-rerank steps** (in endpoints):

- **Score threshold**: Only docs with `final_score >= STRICT_SCORE_THRESHOLD` are kept (e.g. `max(0.55, MIN_SCORE_THRESHOLD)`). If none pass, fallback to top-3 with low confidence.
- **Section-based boosts** (`apply_section_boosts`): After rerank, Jira/SharePoint sections (e.g. root_cause, fix_description, summary) can get authority boosts for final ordering; used for packing context.
- **Direction gating** (migration direction): If query intent has source_platform and target_platform, **filter_by_direction** filters or reorders candidates so that docs matching the asked migration direction are preferred; **pack_context_by_direction** packs matched direction first, then unknown, then limited mismatches.

---

### 6.11 How LLM-Generated Responses Are Built (Streaming RAG)

After retrieval and reranking, the backend has **final_docs** (list of (doc, score)). Response generation proceeds as follows:

1. **Context string**:
   - **format_docs(final_docs)** (in `app/llm.py`) builds the context string: each doc is formatted with `[SOURCE: tag]`, Jira tickets with headers (Ticket URL, Status, Root Cause, Fix Description, etc.), SharePoint/file metadata, download/video URLs. Output is one concatenated text block.
   - If the context length (chars) exceeds a threshold (~90% of model context limit, e.g. 16K tokens), **ContextCompressor** is used: the raw context is sent to the LLM with a “summarize into concise notes” prompt; the LLM returns a compressed text block that replaces the raw context (max_chars ≈ 80% of token limit × chars per token).

2. **System prompt**:
   - Base: **SYSTEM_PROMPT** from config (internal-only, source priority, Jira handling, no raw context leakage, download/video rules, etc.).
   - **Transcript guardrail**: If any final_doc has `kb_tier: secondary` or `source_type: transcript`, an extra instruction is appended: use transcript content for context only, do not present as official guarantees; prefer official docs when they conflict.
   - **Confidence-aware instruction**: If retrieval confidence is classified as low/medium/high (from score spread and threshold), an instruction is appended (e.g. “RETRIEVAL CONFIDENCE: LOW — use ALL context and synthesize” vs “HIGH — focus on top document”).

3. **Message list**:
   - **memory_messages** = [ **SystemMessage**(enhanced_system_prompt) ].
   - Append **conversation_history** (last 8 messages from MongoDB): each `user` → **HumanMessage**(content), each `assistant` → **AIMessage**(content).
   - Append **HumanMessage** with: “Use the following context to answer.\n\n<context>\n{context_text}\n</context>\n\nUser Question:\n{enhanced_query}”. If there is no context (forced_no_context), the human message is just the question.

4. **LLM call**:
   - **get_llm(streaming=True, temperature=0.1, max_tokens=1500)** — low temperature for consistent, factual answers.
   - **llm.astream(messages)** — async stream of chunks. Each chunk’s `content` is yielded to the client as SSE: `data: {"token": "<piece>", "type": "token"}`.
   - Accumulate full response string from streamed tokens.

5. **After stream**:
   - **save_message(session_id, "user", question)** and **save_message(session_id, "assistant", full_response)** (and optional intent/metadata).
   - **add_to_conversation(conversation_id, "user", question)** and **add_to_conversation(conversation_id, "assistant", full_response)**.
   - **langfuse_tracker.create_trace(...)** for observability.
   - SSE **done** event: `{ type: "done", full_response, trace_id, recommended_questions, intent }`.

So: **chunking** defines document units at ingest; **retrieval** (dense + BM25 + optional expansion + routing) selects candidates; **reranking** (cross-encoder + dynamic fusion + threshold + section/direction) selects final_docs; **LLM** receives formatted context + system prompt + history + user question and **streams** the answer token-by-token.

---

## 7. Data Sources & Ingestion

### 7.1 Config Flags (config.py)

- **ENABLE_WEB_SOURCE** — Blog (e.g. WordPress API).
- **ENABLE_PDF_SOURCE**, **ENABLE_EXCEL_SOURCE**, **ENABLE_DOC_SOURCE** — Local dirs.
- **ENABLE_SHAREPOINT_SOURCE** — Main SharePoint (DOC360); **ENABLE_SHAREPOINT_SALES_SOURCE**, **ENABLE_SHAREPOINT_PRESALES_SOURCE**, **ENABLE_SHAREPOINT_LIMITATIONS_SOURCE** — Additional sites/folders.
- **ENABLE_TRANSCRIPT_PROCESSING** — SharePoint transcripts folder.
- **ENABLE_OUTLOOK_SOURCE** — Outlook mailbox.
- **ENABLE_JIRA_SOURCE** — Jira (separate vectorstore when **ENABLE_JIRA_VECTORSTORE**).
- **ENABLE_PPTX_PIPELINE** — Extract PPTX from SharePoint.
- **ENABLE_CAPABILITY_FROM_SHAREPOINT** / capabilities Excel — Capabilities Chroma.

### 7.2 Vectorstore Build (app/vectorstore.py)

- **initialize_vectorstore** / **get_vectorstore** / **check_and_rebuild_if_needed** — Main Chroma at `CHROMA_DB_PATH`.
- **Metadata**: Hashes/URLs per source; **should_rebuild_vectorstore** if metadata changed.
- **build_enhanced_vectorstore_full**, **build_selective_vectorstore**, **build_incremental_vectorstore** — Full or incremental rebuild from enabled sources.
- **add_new_blog_posts** — Incremental blog.
- **manage_vectorstore_backup_and_rebuild** — Backup then rebuild.

### 7.3 Source Processors (in app/)

- **Blog**: `blog_poller.py` — Fetch from WordPress API; chunk and add to main vectorstore.
- **SharePoint**: `sharepoint_*.py`, `sharepoint_auth.py` — Auth, list files/folders, extract text (and optional PPTX); exclude/include folders from config; downloadable folders get `download_url` in metadata.
- **Jira**: `jira_processor.py` — Fetch issues (JQL/project keys); field-aware chunking (Summary, Description, Root Cause, Fix, Comments); store in **Jira Chroma** (`jira_vectorstore.py`).
- **Outlook**: `outlook_processor.py` — Graph API; process mailbox folder to Documents.
- **Transcripts**: Transcript processor + normalization/artifact extraction; stored with `kb_tier: secondary`.
- **PDF/DOC/Excel**: `pdf_processor.py`, unstructured/OCR options; Excel for capabilities/limitations.
- **PPTX**: `pptx_processor.py` — Extract from SharePoint files; optional save to files.
- **Chunking**: `chunking_strategy.py` (e.g. semantic chunker), `metadata_schema.py`, `create_chunk_metadata`.
- **Deduplication**: Config `ENABLE_DEDUPLICATION`, `DEDUP_THRESHOLD`; applied during ingest.

### 7.4 Scripts (scripts/)

- **poll_blogs.py** — Blog polling.
- **sync_jira_incremental.py**, **sync_jira_status.py** — Jira sync.
- **process_transcripts_from_sharepoint.py** — Transcript ingestion.
- **ingest_capability_limitations.py** — Capabilities/limitations Excel → Chroma.
- **backup_vectorstore.py** — Backup Chroma.
- **seed_suggested_questions.py**, **reset_questions.py**, **auto_update_questions.py** — Suggested questions.
- **migrate_teams_to_mongodb.py** — Teams data migration.
- Others: analyze_user_questions, debug_capability_chunks, validate_documentation_decoupling, etc.

### 7.5 Graph Store (app/graph_store.py)

- **SQLite** at `GRAPH_DB_PATH`: documents, chunks, relationships (e.g. doc–chunk, email threads).
- Used for document/chunk relations and future entity relations; not the primary retrieval path.

---

## 8. Key Features

### 8.1 Email Drafting (Copilot-Style)

- **Toggle** in UI (`ui_mode: "email"`); or triggers (e.g. "draft an email", "write an email").
- **Flow**: Classify input (email_related_complete / incomplete / not_email_related / CloudFuze clarification). If complete → `EMAIL_DRAFT_SYSTEM_PROMPT`, no RAG; stream polished email. Refinement (button or implicit) rewrites last draft.
- **Pending topic**: Stored per session for follow-up (e.g. "what should I say?" after "draft email about CloudFuze Migrate").

### 8.2 Shared Chat

- **create_shared_chat** / **get_shared_chat** (MongoDB) — Create shareable token; public page `/chat/shared/[token]` shows read-only thread.
- **Frontend**: `app/chat/shared/[token]/page.tsx`; API `api/shared-chat/[token]` to load thread.

### 8.3 Cloud API Research

- **ENABLE_CLOUD_API_RESEARCH** + user access + user toggle → **research_cloud_api** (app/cloud_api_researcher.py): classify cloud, search/scrape docs, optional cache; then **format_cloud_research_markdown** (response_formatter.py).
- **SCIM** is hard-disabled (no extract/parse/map/mention).

### 8.4 Jira

- **Separate Chroma** for Jira tickets; **jira_vectorstore.py**, **jira_processor.py**.
- **Admin**: `app/routes/jira_sync.py` — Sync status, config; **app/services/jira_config_service.py**, **app/models/jira_config.py**.
- **System prompt**: Jira as primary for troubleshooting; response structure (acknowledge, solution, ticket ID/URL, steps); ticket URL only from context.

### 8.5 Teams & Users (MongoDB)

- **teams_repository.py** — Teams structure; **app/models/teams.py** — TEAMS_STRUCTURE, get_team_by_name.
- **User profile / statistics**: `update_user_profile`, `get_user_profile`, `get_user_statistics`, `set_user_active` in mongodb_memory; **user_data** (e.g. job title).
- **Trace assignment**: `trace_utils.assign_trace_to_team`, `process_trace_batch` for analytics.

### 8.6 Suggested Questions

- **Backend**: `app/routes/suggested_questions.py` — Get, create, update, delete, track analytics.
- **MongoDB**: Stored and optionally seeded/updated by scripts; default list in code if DB empty.

### 8.7 Observability

- **Langfuse**: `app/langfuse_integration.py` — Create trace per request (user, session, question, answer, metadata). Feedback (thumbs up/down, categories) sent to backend and can be sent to Langfuse.
- **Audit**: `insert_audit_log` in mongodb_memory for sensitive actions.

### 8.8 Response Versions (Regenerate)

- **get_response_versions**, **set_current_version**, **get_max_version**, **mark_all_versions_not_current** — Store multiple assistant versions per message (e.g. for "regenerate"); frontend can show version selector.

---

## 9. Admin & Analytics

### 9.1 Admin Routes (Frontend)

- **/admin/dashboard** — Overview.
- **/admin/analytics** — Analytics (Langfuse/traces, time filters, user/team metrics).
- **/admin/teams** — Teams CRUD/config.
- **/admin/teams-dashboard** — Teams dashboard.
- **/admin/users** — User list/activity.
- **/admin/blog** — Blog post management.
- **/admin/jira** — Jira sync status, config.
- **/admin/top-questions** — Suggested questions management.

### 9.2 Backend Support

- **endpoints.py** — Various admin endpoints (sessions, user stats, traces, rankers, feedback, shared chat, Jira stats, etc.).
- **require_admin** / **require_restricted_admin** — Protect admin routes; **EXCLUDED_DEVELOPER_EMAILS** for dashboard stats.
- **Optional global guard**: `app/admin_middleware.AdminPathMiddleware` — in **server.py** add:
  ```python
  from app.admin_middleware import AdminPathMiddleware
  app.add_middleware(AdminPathMiddleware)
  ```
  to reject `/admin/*` and `/api/admin/*` at the edge unless session user is in allowlist (path uses startswith-only; defense-in-depth).
- **After frontend auth changes**: Delete `.next` and rebuild (`rmdir /s /q .next` then `npm run build`) so no old admin list remains in compiled JS.
- **Manual checks**: (1) Register middleware in server.py as above and restart backend. (2) Run `rmdir /s /q .next`, `npm run build`, `npm run start` in frontend. (3) DevTools → Sources → search `cloudfuze.com` — expect only URLs/domain checks, no email array. (4) Penetration tests: change localStorage user to admin email → refresh (admin UI should disappear); fetch `/admin/users/summary` as non-admin or with no cookies → expect 403.

### 9.3 Weekly Report

- **config**: `WEEKLY_REPORT_ENABLED`, `WEEKLY_REPORT_SEND_HOUR`, `WEEKLY_REPORT_SENDER_EMAIL`, `SCHEDULER_TIMEZONE`.
- **app/email_sender.py**: `send_weekly_report_email`, `send_weekly_report_emails` (e.g. team leaderboard).

---

## 10. Frontend Chat Flow (Summary)

- **initializeChatApp** (`lib/chat-initialization.ts`): Session from route or localStorage; per-session generation state (parallel chats); no abort on session switch.
- **UI**: Empty state vs messages; suggested questions in empty state; bottom input appears when there are messages; chat header (read-only vs editable).
- **Send**: POST `/chat/stream` with question, session_id, optional ui_mode; parse SSE (`token`, `thinking_complete`, `done`, `recommended_questions`, `trace_id`); append tokens to message; on `done`, save and update UI.
- **Sessions**: Sidebar history (own + "others"); create new chat; load session by id; "Continue in thread" for read-only copies.
- **Shared**: Load shared chat by token; display read-only.
- **Login**: Redirect to Microsoft OAuth; callback sets session cookie and redirects to app.

---

## 11. Deployment

- **Docker**: `Dockerfile`, `Dockerfile.prod`, `Dockerfile.prod.light`; `docker-compose.yml`, `docker-compose.ai.yml`, `docker-compose.atlas.yml`, `docker-compose.prod.yml`; `frontend/Dockerfile.frontend`.
- **Nginx**: `nginx.conf`, `nginx-ai.conf`.
- **Env**: `env.ai.example` (root); `rag_system/.env.example`; config via `config.py` and env vars.
- **Scripts**: `start_server.sh`, `restart_services.sh`/`.bat`, `deploy-on-server.sh`, `deploy-ubuntu.sh`, `quick-start.sh`/`.bat`, `pre-deployment-check.sh`.

---

## 12. Configuration Reference (Selected)

- **LLM**: `LLM_PROVIDER` (openai | gemini), `OPENAI_API_KEY`, `GEMINI_API_KEY`.
- **Auth**: `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`, `MICROSOFT_TENANT`; `ADMIN_EMAILS`, `EXCLUDED_DEVELOPER_EMAILS` (backend env only; never shipped to frontend).
- **MongoDB**: `MONGODB_URL`, `MONGODB_DATABASE`, `MONGODB_CHAT_COLLECTION`.
- **Chroma**: `CHROMA_DB_PATH`, `JIRA_VECTORSTORE_PATH`, `CHROMA_CAPABILITIES_DB_PATH`; `INITIALIZE_VECTORSTORE`, `INITIALIZE_JIRA_VECTORSTORE`.
- **Retrieval**: `DENSE_RETRIEVAL_K`, `BM25_RETRIEVAL_K`, `FINAL_RETRIEVAL_K`; `DENSE_WEIGHT`, `BM25_WEIGHT`, `RERANKER_WEIGHT`; `MIN_SCORE_THRESHOLD`; retry K and weights; routing `ROUTING_TOTAL_BUDGET`, `ROUTING_FINAL_K`, `ROUTING_MIN_CONFIDENCE`, `MAX_*_K` per source.
- **Features**: `ENABLE_INTELLIGENT_ROUTING`, `ENABLE_QUERY_EXPANSION`, `ENABLE_CONTEXT_COMPRESSION`, `USE_CONTEXT_SYNTHESIS`, `ENABLE_ANSWER_QUALITY_CHECK`, `ENABLE_CLOUD_API_RESEARCH`.
- **Langfuse**: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`.
- **Sources**: All `ENABLE_*_SOURCE`, `*_URL`, `*_DIR`, `*_FOLDER_PATH`, SharePoint exclusions/downloadable folders, Jira `JIRA_*`, Outlook `OUTLOOK_*`, etc.

---

## 13. Key Files Quick Reference

| Purpose | File(s) |
|--------|---------|
| Backend entry | `server.py` |
| Config | `config.py` |
| Chat API & RAG orchestration | `app/endpoints.py` |
| Auth | `app/auth.py`, `app/session_store.py` |
| Memory & sessions | `app/mongodb_memory.py` |
| LLM & formatting | `app/llm.py`, `app/llm_factory.py` |
| Main vectorstore | `app/vectorstore.py` |
| Jira vectorstore | `app/jira_vectorstore.py` |
| Capabilities | `app/capabilities_vectorstore.py` |
| Routing | `intelligent_router.py` |
| Multi-source retrieval | `multi_source_retrieval.py` |
| Query expansion / Reranker / Compressor | `query_expander.py`, `reranker.py`, `context_compressor.py` |
| Graph | `app/graph_store.py` |
| Ingest | `app/vectorstore.py`, `app/*_processor.py`, `app/blog_poller.py`, scripts in `scripts/` |
| Frontend app | `frontend/src/app/layout.tsx`, `page.tsx`, `chat/*`, `admin/*` |
| Chat UI logic | `frontend/src/lib/chat-initialization.ts` |
| API client | `frontend/src/lib/api.ts` |

---

This document reflects the **implemented** behavior, **workflows**, **functionalities**, and **approaches** of the CloudFuze AI Assistant codebase as of the last review. For env-specific values and secrets, use the example env files and deployment docs (e.g. in `.github/` or `Context_Folder/`) where available.
