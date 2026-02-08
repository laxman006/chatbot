## Retrieval pipeline (Weaviate → RAG)

This doc describes how the backend queries Weaviate today, what filters exist, how results are ordered, and where RBAC and “summary chunks” fit.

### Source of truth

- Retriever: `app/weaviate_retriever.py`
- RAG retrieval node: `app/rag/nodes.py` (`retrieve_documents`)
- RBAC: `app/rbac.py`
- Schema constants: `app/weaviate_schema.py` (collections + chunk roles)

---

## A) Low-level retriever (`app/weaviate_retriever.py`)

### Query embedding

The retriever embeds the user query using OpenAI embeddings:

- `OpenAIEmbeddings(model="text-embedding-3-small")`

This matches ingestion’s embedding model.

### Query primitive: `near_vector`

Retrieval uses Weaviate v4 `near_vector` searches:

- `coll.query.near_vector(near_vector=query_vector, limit=..., return_metadata=MetadataQuery(distance=True), filters=...)`

Returned scoring is **distance** (lower is better).

### Collections queried

- Default: all collections in `COLLECTIONS` (`app/weaviate_schema.py`)
- If the user query includes a `cloudfuze.com` URL (the “answer from this page” pattern):
  - retrieval is restricted to `Blogs` only

### Filters (current implementation)

Filters are combined with AND when multiple apply.

- **Blog URL / doc restriction**
  - If `filter_doc_id` is provided: filter `doc_id == <slug>`
  - Else if `filter_url` is provided: filter `url == <url>` (with a retry adding trailing `/`)
- **SharePoint migration direction restriction**
  - If `filter_migration_type` is provided: filter `migration_type == <canonical>`
- **RBAC filter (optional)**
  - If `user_context` is passed, a filter is added:
    - `permissions ContainsAny user.group_ids`
- **Exclude image chunks (SharePointDocs only)**
  - `chunk_type != "image_context"`

### Summary chunks (two-step query)

If `include_summary_chunks=True`, retriever runs an additional query per collection:

- filter: `chunk_role == <collection summary role>`

Summary roles used:

- SharePointDocs/Blogs → `doc_summary`
- JiraTickets → `ticket_summary`
- Spreadsheets → `sheet_summary`
- EmailThreads → `thread_summary`
- Transcripts → `meeting_summary`

These summary results are appended to the same result list before final sorting/deduping.

### Ordering (layer-aware) + dedupe

After gathering results:

1. **Sort** by:
   - first: `chunk_type` priority (higher is better)
   - then: vector distance (lower is better)

Current priorities (`SharePointDocs` metadata):

- `feature_capability` (100)
- `limitation` (90)
- `migration_capability_summary` (80)
- `table_row` (40)
- `raw_content` (10)

2. **Deduplicate** by `chunk_key` (keep best-ranked instance)

3. Return top `k`

---

## B) RAG retrieval node (`app/rag/nodes.py`)

`app/rag/nodes.py` has its own retrieval orchestration. Key differences vs the low-level retriever:

- It can run retrieval for up to 3 expanded queries and then merges results.
- It currently calls `retrieve_from_weaviate(...)` with:
  - `collection_names=["SharePointDocs"]` (SharePoint-only in this node)
  - migration filtering (via `detect_migration(query)` from `app/migration_resolver.py`)
  - blog URL filtering (if URL exists in the query)
- It intentionally **does not pass `user_context`** to the retriever, so RBAC filtering is not applied in that path (comment in code explains this avoids accidental 0-results when permissions are missing).

It also re-applies the same **layer-aware ordering + dedupe by chunk_key** when merging results across expanded queries.

Note: the `retrieve_documents` node docstring mentions “hybrid (vector + BM25)”, but the current implementation path is **vector-only** (`near_vector`) via `retrieve_from_weaviate(...)`.

---

## C) RBAC behavior (important)

### Ingestion default

If `permissions` is missing during enrichment, it defaults to `["admin"]` (deny-by-default).

### Retrieval filter

If RBAC is enabled (user_context passed), retrieval applies:

- `permissions ContainsAny user.group_ids`

### Common failure mode

If you enable RBAC filtering but most chunks have:

- missing `permissions`
- or `permissions=["admin"]`

Then most users will see **0 results** unless they have `admin` in their groups.

---

## D) Parent-doc neighbor expansion (schema-level contract)

Neighbor expansion relies on:

- `parent_id`
- sequential `chunk_id` in `0..N`

**Do not include summary chunks (`chunk_id=-1`) in neighbor expansion queries.**  
Summary chunks should be fetched separately by `chunk_role`.

