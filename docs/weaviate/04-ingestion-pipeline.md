## Ingestion pipeline (end-to-end)

### Source of truth

- Orchestrator: `app/weaviate_ingestion.py` (`WeaviateIngestionPipeline`)
- Chunkers: `app/chunking/` and fallback `app/chunking_strategy.py`
- Metadata: `app/metadata_enricher.py`
- Embeddings: `app/embedding_service.py`
- Summaries: `app/summary_generator.py`
- Insert/delete: `app/weaviate_batch_inserter.py`
- Incremental tracking: `app/incremental_ingestion.py`

### What “ingestion” means here

Given a list of LangChain `Document`s (with `page_content` and `metadata`), ingestion produces **Weaviate objects** with:

- normalized + enriched metadata (universal schema contract)
- embeddings vector (external)
- deterministic UUID so the write is idempotent

### Pipeline steps (current code)

In `WeaviateIngestionPipeline.ingest_from_source(...)`:

1. **Chunk documents**
   - Default is **markdown-aware chunking**:
     - `get_chunker(kind="markdown_aware", target_tokens=800, overlap_tokens=200, min_tokens=150)`
   - Fallback is `SemanticChunker` (`app/chunking_strategy.py`)
   - Jira special-casing: if `source_type == "jira"`, it uses `self.chunker.chunk_documents(...)`

2. **Group chunks by `doc_id`**
   - Each chunk must have a stable `doc_id` in `chunk.metadata["doc_id"]`
   - If missing, pipeline generates a random UUID (this makes future re-ingestion non-idempotent for that doc)

3. **Enrich metadata (per document)**
   - Converts chunk `Document`s into `WeaviateChunk` dataclasses
   - Adds / normalizes:
     - `source_type` (derived from collection name)
     - `parent_key` (stable, source-dependent)
     - `parent_id` (uuid5 from `doc_id`)
     - `chunk_id`, `chunk_key`
     - `content_hash` (MD5)
     - `token_count` (tiktoken; fallback estimate)
     - `permissions` default is **deny-by-default**: `["admin"]` if missing
     - dates normalized to RFC3339 for Weaviate DATE fields

4. **Optional summary chunk generation**
   - If enabled (`enable_summaries=True`) and conditions match:
     - generate summary if `len(chunks) > 5` OR total tokens `> 2000`
   - Summary becomes a **separate chunk** with:
     - `chunk_id = -1`
     - `chunk_role` set by collection (doc/ticket/sheet/thread/meeting summary)
   - Non-blocking: failures do **not** fail ingestion

5. **Deduplication (exact)**
   - Current pipeline uses **exact dedup** by `content_hash`
   - Keeps first occurrence of each hash
   - Note: there is a separate `app/deduplication.py` module with embedding-similarity dedup, but the current Weaviate ingestion pipeline uses the content-hash method.

6. **Generate embeddings**
   - Uses `OpenAIEmbeddings(model="text-embedding-3-small")`
   - Token-based dynamic batching:
     - `MAX_TOKENS_PER_BATCH = 250000` (safety margin)
   - Optional in-memory caching:
     - `content_hash -> embedding`

7. **Batch insert into Weaviate**
   - Uses the Weaviate v4 `collections` API
   - Schema uses `vectorizer=none()`, so **vectors must be passed explicitly**
   - Object UUID is deterministic:
     - `uuid5(NAMESPACE_DNS, chunk_key)`
   - Insert uses:
     - `collection.data.insert_many([DataObject(properties=..., vector=..., uuid=...)])`
   - Retries with exponential backoff; if a batch fails, falls back to per-object insertion for error isolation

8. **Incremental tracking update**
   - Only if enabled and `incremental=True`
   - Tracker file:
     - `data/ingestion_tracking/<source_type>_tracking.json`
   - Change detection is based on **doc_hash**, computed from normalized content + a few identity metadata fields
   - Deletion handling:
     - If `allow_deletions=True`, it removes doc hashes from the tracker
     - Deleting the stale chunks in Weaviate is a separate action (supported by batch inserter helpers)

### Deletion APIs (when you need to “reingest cleanly”)

`WeaviateBatchInserter` provides helpers:

- `delete_chunks_by_parent_id(collection_name, parent_id)`
- `delete_chunks_by_doc_id(collection_name, doc_id)`

These are useful for “replace document” workflows (delete old chunks then ingest new).

### Ingestion invariants (things that must stay true)

- **`source_type` must match the collection** (enforced via helper)
- **Every inserted chunk must have a vector** (schema vectorizer is disabled)
- **`chunk_key` must be stable** (or you’ll create new object UUIDs and duplicates)
- **Summary chunks must use `chunk_id=-1`** (and should not be treated as sequential neighbors)

