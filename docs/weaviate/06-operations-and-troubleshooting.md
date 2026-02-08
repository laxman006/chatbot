## Operations & troubleshooting

### Source of truth

- Client connection logic: `app/weaviate_client.py`
- Schema creation: `app/weaviate_schema.py`
- Schema init script: `scripts/init_weaviate_schema.py`
- Ingest scripts: `scripts/ingest_to_weaviate.py`, plus source-specific scripts
- Config/env: `config.py` + `.env`

---

## Configuration (env vars you actually need)

### Weaviate

- `WEAVIATE_URL`
  - default: `http://localhost:8080`
  - local URL triggers `weaviate.connect_to_local(...)`
  - otherwise uses `weaviate.connect_to_custom(url=WEAVIATE_URL, ...)`
- `WEAVIATE_API_KEY`
  - optional; if set, client uses API key auth

### Embeddings + LLM

- `OPENAI_API_KEY` (required when using OpenAI for embeddings and/or LLM)
- `LLM_PROVIDER` (`openai` or `gemini`) affects summary generation LLM and RAG generation LLM

Note: retrieval and ingestion embeddings currently use OpenAI embeddings (`text-embedding-3-small`).

### Chunking knobs (optional tuning)

Defined in `config.py` (used by some chunkers/pipelines):

- `CHUNK_TARGET_TOKENS` (default 800)
- `CHUNK_OVERLAP_TOKENS` (default 200)
- `CHUNK_MIN_TOKENS` (default 150)

---

## Initializing schema

Supported ways (repo-standard):

- Use the schema module:
  - `app.weaviate_schema.create_all_collections(recreate=False)`
- Use the script:
  - `scripts/init_weaviate_schema.py`

Important schema notes:

- Collections use `vectorizer=none()` → **you must provide vectors on insert**
- The schema uses a **single legacy vector** (not named vectors) to avoid “named vector not found” retrieval issues

---

## Health checks

`app/weaviate_client.py` provides:

- `check_weaviate_health()`: checks `is_ready()` and `is_live()`
- `reset_weaviate_client()`: closes and recreates client on next use

---

## Common problems (and how to diagnose)

### 1) “0 results” even though data exists

Likely causes:

- **RBAC filter excludes everything**
  - Chunks default to `permissions=["admin"]` when missing
  - If you pass `user_context` without `admin` group, `ContainsAny` may return nothing
  - Fix: ensure ingestion writes correct `permissions`, or include appropriate groups

- **Collections not created / wrong names**
  - Retriever skips collections that don’t exist
  - Verify: `list_collections()` in `app/weaviate_schema.py`

### 2) Insert failures: “Missing vector … vectorizer=None”

Cause:

- Schema uses `vectorizer=none()`, so vectors are mandatory.

Fix:

- Ensure `EmbeddingService.generate_embeddings(...)` ran successfully and each chunk has `chunk.vector`

### 3) Weaviate DATE field errors

Cause:

- Weaviate requires RFC3339 format and timezone for datetime strings.

Fix:

- Ensure `MetadataEnricher._parse_date(...)` is used (it normalizes to RFC3339)

### 4) Duplicate chunks after reingestion

Cause:

- `chunk_key` changed (usually because `parent_key` changed)
  - e.g., a different `folder_name` normalization, or missing `source_ref` now filled differently

Fix:

- Stabilize `ParentKeyBuilder` inputs for that source (site/folder/file id conventions)
- Consider deleting old chunks by `doc_id` or `parent_id` before reingesting:
  - `delete_chunks_by_doc_id(...)` / `delete_chunks_by_parent_id(...)`

### 5) Blog “answer from this URL” doesn’t filter correctly

Current behavior:

- Extracts `cloudfuze.com/...` URL from the query
- Prefer filtering `doc_id == slug(last path segment)`
- Falls back to `url == <url>` (and retries with trailing `/`)

Fix:

- Ensure blog ingestion writes `doc_id` as the slug consistently.

---

## Operational tips

- **Don’t mix schema styles**: this codebase uses Weaviate v4 `client.collections` APIs consistently.
- **Keep filterable fields short**: `parent_id`, `chunk_id`, `ticket_key`, `thread_id`, `sheet_name` are meant for fast filters.
- **Summary chunks**: always query them separately via `chunk_role`; never include them in neighbor expansion.

