## Identifiers & metadata contract

This doc explains the **stable IDs** used to make ingestion **idempotent** and retrieval **filterable**, and how they are computed in code.

### Source of truth

- `app/metadata_enricher.py` (`MetadataEnricher`, `ParentKeyBuilder`)
- `app/weaviate_batch_inserter.py` (deterministic UUID for Weaviate object id)
- `app/weaviate_schema.py` (universal properties)

### ID glossary

- **`doc_id`**: stable document identity (string)
  - Examples: SharePoint file id, Jira ticket key, blog slug, transcript meeting id
- **`parent_key`**: stable “path-like” identity used to build chunk keys
- **`parent_id`**: stable UUID-like grouping id for *all chunks of the same doc*
- **`chunk_id`**: sequential integer index inside the parent
  - Content chunks: `0..N`
  - Summary chunks: `-1`
- **`chunk_key`**: globally unique chunk key
- **Weaviate object UUID**: deterministic UUID used as the object id for insert/update

### How we compute `parent_key`

`ParentKeyBuilder.build_parent_key(source_type, doc_metadata)` builds it with a per-source convention.

Conventions (current code):

- **SharePoint**: `sharepoint/{site}/{folder}/{file}`
  - `site` comes from `site_name` or parsed from URL (`/sites/<name>/...`)
  - `folder` uses `folder_name` or `folder_path` (with separators normalized)
  - `file` uses `source_ref` / `file_name` / `filename`
- **Jira**: `jira/{project_key}/{ticket_key}`
- **Blog**: `blog/{post_slug}`
- **Transcript**: `transcript/{customer}/{meeting_date}/{meeting_id}`
- **Email**: `email/{mailbox_id}/{thread_id}`
- **Excel**: `excel/{sharepoint_file_id}/{sheet_name}`
- **Fallback**: `{source_type}/{doc_id}`

### How we compute `parent_id`

In metadata enrichment we compute:

- `parent_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, doc_id))`

This makes `parent_id`:

- stable across re-ingestion
- deterministic per `doc_id`
- usable as a filter to fetch all chunks of a document

### How we compute `chunk_key` and `chunk_id`

In enrichment:

- `chunk_id = idx` (for content chunks)
- `chunk_id = -1` for summary chunks (`is_summary=True`)
- `chunk_key = f"{parent_key}#chunk_{chunk_id}"`

### Weaviate object UUID (idempotent inserts)

We do **not rely on `chunk_key` uniqueness constraints in Weaviate**.  
Instead we insert with a deterministic UUID computed from `chunk_key`:

- `object_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk.chunk_key))`

Why this matters:

- inserting the “same chunk” overwrites the same object id (idempotent)
- re-ingesting does not create duplicates if `chunk_key` is stable

Reference: `WeaviateBatchInserter` in `app/weaviate_batch_inserter.py`

### Summary chunks: `chunk_id = -1` is special

Summary chunks are stored *as normal objects* in the same collection, but with:

- `chunk_id = -1`
- `chunk_role` set to a collection-specific summary role:
  - SharePointDocs/Blogs → `doc_summary`
  - JiraTickets → `ticket_summary`
  - Spreadsheets → `sheet_summary`
  - EmailThreads → `thread_summary`
  - Transcripts → `meeting_summary`

**Critical rule for neighbor expansion**:

- When fetching sequential neighbors you must **exclude `chunk_id=-1`**.
- Summary chunks are fetched via a **separate** query by `chunk_role` (see `05-retrieval-pipeline.md`).

### Date fields must be RFC3339

Weaviate DATE properties require RFC3339 date-time strings (timezone required for datetimes).  
`MetadataEnricher` normalizes:

- `YYYY-MM-DD` → `YYYY-MM-DDT00:00:00Z`
- `YYYY-MM-DDTHH:MM:SS` → `YYYY-MM-DDTHH:MM:SSZ`

### RBAC permissions are deny-by-default

In `MetadataEnricher`:

- If chunk/doc metadata has no `permissions`, it uses `DEFAULT_PERMISSIONS = ["admin"]`

At retrieval time, RBAC filtering uses:

- `Filter.by_property("permissions").contains_any(user.group_ids)`

Reference: `app/rbac.py` + RBAC code path in `app/weaviate_retriever.py`

