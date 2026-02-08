## Schema reference (Weaviate v4)

### Source of truth

- **Schema module**: `app/weaviate_schema.py`
- **Existing schema doc**: `WEAVIATE_SCHEMA.md` (high-level)

### Collections

| Collection | `source_type` | What it contains |
|---|---|---|
| `SharePointDocs` | `sharepoint` | SharePoint documents (pdf/doc/docx/md/html) chunked into text blocks |
| `Blogs` | `blog` | Blog/wiki posts chunked by sections/headings |
| `JiraTickets` | `jira` | Jira ticket text fields chunked (typically description-heavy) |
| `Transcripts` | `transcript` | Demo/meeting transcripts (secondary KB) |
| `Spreadsheets` | `excel` | Excel sheets/rows represented as text + row JSON metadata |
| `EmailThreads` | `email` | Email threads and messages represented as chunks |

The mapping is enforced by:

- `COLLECTION_TO_SOURCE_TYPE` and `get_source_type_for_collection()` in `app/weaviate_schema.py`
- Metadata enrichment uses that helper (`app/metadata_enricher.py`)

### Vectorization & index

- **Vectorizer**: `Configure.Vectorizer.none()` (external vectors)
- **Vector index**: HNSW
  - distance: cosine
  - `ef_construction`: 128
  - `max_connections`: 32

Reference: `DEFAULT_HNSW` + `create_collection()` in `app/weaviate_schema.py`

### Universal properties (present in all collections)

These fields form the **contract** between ingestion and retrieval.

#### Chunk payload

- `content` (TEXT): chunk text (also duplicated in metadata for easy Document mapping)

#### Source identity

- `source_type` (TEXT): must match collection
- `source_ref` (TEXT): source identifier (ticket key, filename, etc.)
- `file_type` (TEXT): `pdf|docx|xlsx|md|html|txt` (when applicable)

#### Parent document identity (parent-doc expansion)

- `doc_id` (TEXT): stable doc identifier (SharePoint file id, Jira key, blog slug, transcript id, etc.)
- `parent_id` (TEXT): stable UUID-like value for grouping chunks of a doc (derived from doc_id)
- `parent_key` (TEXT): stable path-like id, built per source (see `03-identifiers-and-metadata.md`)

#### Chunk identity

- `chunk_id` (INT): sequential id \(0..N\); **summary chunks use -1**
- `chunk_key` (TEXT): globally unique chunk key (`{parent_key}#chunk_{chunk_id}`)
- `chunk_role` (TEXT): standardized role (see below)

#### Document metadata (UX/citations)

- `title` (TEXT)
- `url` (TEXT)
- `created_at` (DATE, RFC3339 string)
- `updated_at` (DATE, RFC3339 string)

#### RBAC & org boundary

- `permissions` (TEXT_ARRAY): RBAC groups (retrieval uses `ContainsAny`)
- `tenant_id` (TEXT)
- `department` (TEXT)

#### Ingestion/ops

- `version` (INT)
- `last_indexed_at` (DATE)
- `token_count` (INT)

### Chunk roles (standardized)

In `app/weaviate_schema.py`:

- `content`
- `doc_summary`
- `sheet_summary`
- `ticket_summary`
- `thread_summary`
- `message_summary`
- `meeting_summary`
- `decisions_summary`
- `action_items_summary`

**Rule**: summary chunks always use `chunk_id = -1`.  
**Important**: neighbor expansion must **exclude `chunk_id=-1`** (summary chunks are not sequential neighbors).

### Collection-specific properties (summary)

This section is intentionally compact; use `WEAVIATE_SCHEMA.md` for the full property list.

#### `SharePointDocs`

Key fields used by retrieval and grounding:

- `site_name`, `folder_name`
- `page_start`, `page_end`
- `chunk_type` (layering; see retrieval ordering)
- `migration_type`, `migration_combination`
- `is_limitation`
- `raw_kv` (JSON string for audit)

#### `Blogs`

- `author`, `author_name`
- `tags`, `category`
- `heading_path`, `section_title`
- `publish_date`

#### `JiraTickets`

- `ticket_key`, `project_key`
- `issue_type`, `status`, `priority`
- `assignee`, `reporter`
- `labels`, `components`, `sprint`

#### `Transcripts`

Meeting identity + “secondary KB” controls:

- `meeting_id` (**must equal** `doc_id`), `meeting_title`, `meeting_date`, `transcript_source`
- `customer`, `participants`, `topic`
- `kb_tier` (default `secondary`), `reliability` (default `contextual`)
- `not_contractual=True`, `internal_use_only=True`

#### `Spreadsheets`

- `sharepoint_file_id` (**often equals** `doc_id`)
- `sheet_name`, `row_start`, `row_end`
- `row_data` (**JSON string**), `row_keys` (must contain all keys in `row_data`)
- Optional normalized fields: `feature_name`, `limitations`, `supported`

#### `EmailThreads`

- `thread_id`, `subject`, `mailbox_id`, `mail_source`
- Message-level: `message_id`, `from_email`, `to_emails`, `sent_at`

