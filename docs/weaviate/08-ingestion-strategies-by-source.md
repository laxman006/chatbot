## Ingestion strategies by source (complete)

This doc explains **how each source is loaded and mapped into Weaviate collections** in this repo, including the key metadata required for the Weaviate schema contract.

### Source of truth

- Ingest CLI: `scripts/ingest_to_weaviate.py`
- Weaviate pipeline: `app/weaviate_ingestion.py`
- Schema mapping: `app/weaviate_schema.py` (`COLLECTION_TO_SOURCE_TYPE`)
- Metadata enrichment: `app/metadata_enricher.py` (`ParentKeyBuilder`, `MetadataEnricher`)

---

## 1) Canonical source → collection mapping

In `scripts/ingest_to_weaviate.py`:

| CLI `--source` | Collection | Derived `source_type` |
|---|---|---|
| `sharepoint` | `SharePointDocs` | `sharepoint` |
| `jira` | `JiraTickets` | `jira` |
| `blog` | `Blogs` | `blog` |
| `transcript` | `Transcripts` | `transcript` |
| `excel` | `Spreadsheets` | `excel` |
| `email` | `EmailThreads` | `email` |

Important: even if a loader sets `metadata["source_type"]`, the Weaviate metadata enricher **re-sets `source_type` from the collection name** to keep it consistent.

---

## 2) Shared ingestion contract (applies to all sources)

No matter the source, by the time chunks are inserted into Weaviate they must have:

- stable `doc_id` (for grouping)
- stable `parent_key` (computed from doc metadata)
- stable `chunk_key` (derived from parent_key + chunk_id)
- `permissions` (defaults to `["admin"]` if missing)
- explicit `vector` (because schema vectorizer is disabled)

Idempotency:

- Weaviate object UUID = `uuid5(NAMESPACE_DNS, chunk_key)`

---

## 3) SharePoint → `SharePointDocs`

### Loader

Entry point: `load_sharepoint_documents()` in `scripts/ingest_to_weaviate.py`

Sources included depending on config flags:

- Main SharePoint site via Graph extractor:
  - `app.sharepoint_graph_extractor.extract_sharepoint_via_graph()`
- Presales SharePoint:
  - `app.helpers.fetch_latest_sharepoint_presales(...)`
- Limitations SharePoint:
  - `app.helpers.fetch_latest_sharepoint_limitations(...)`

### Strategy

SharePoint ingestion is **file-type aware**, and often produces already-structured chunks:

- PDF → layered table/text chunks with `chunk_type` and optional migration fields
- DOCX → block-level chunks (paragraphs + table rows)
- Excel/CSV → row/cell-level chunks (feature + limitation + summary)
- PPTX → slide-level text chunks

### Stable IDs

Graph extractor uses file-level doc identity:

- `doc_id = "sharepoint:<graph_item_id>"`

MetadataEnricher uses:

- `parent_id = uuid5(doc_id)`
- `parent_key = sharepoint/{site}/{folder}/{file}` (from metadata)

### Retrieval-relevant fields

The extractor emits metadata that the schema supports and retrieval uses:

- `chunk_type` (layer-aware ranking in retrieval)
- `feature`, `supported`, `is_limitation`
- `raw_kv` (JSON string)
- `migration_type`, `migration_combination` (when detected)
- `page_number` / `page_start` / `page_end`
- `section_title`
- `vertical_position` (text-only interleaving; images are not ingested)

---

## 4) Jira → `JiraTickets`

### Loader

- `app.jira_processor.JiraProcessor.process_jira_content()`

### Strategy

Field-aware ticket chunking:

- Summary chunk (ticket metadata)
- Description chunk (may be large; pipeline chunker may split)
- Root cause chunk (never split)
- Fix description chunk (never split)
- Optional AI-suggestion chunk
- One chunk per comment

### Stable IDs

Jira processor does not explicitly set `doc_id` today (it uses `ticket_key` in metadata).  
The Weaviate ingestion pipeline groups by `chunk.metadata["doc_id"]`; if it’s missing, it generates a random UUID.

Practical implication:

- For perfect idempotency and clean re-ingestion, Jira chunks should carry:
  - `doc_id = ticket_key`

Even if `doc_id` is missing, the schema is still populated (but re-ingestion stability will be weaker).

---

## 5) Blogs → `Blogs`

### Loader

- `load_blog_documents()` → `app.helpers.fetch_web_content(...)` or `fetch_latest_web_content(...)`

### Strategy

Per post:

- HTML → cleaned text
- chunk with `RecursiveCharacterTextSplitter` (1500/300)
- stable `doc_id = slug`
- sets canonical metadata used downstream:
  - `title`, `url`, `author_name`, `post_date`, etc.

### Incremental ingest strategy

The blog loader supports incremental ingestion using a stored `last_blog_post_date`.

Safety rule:

- Blog ingestion sets `allow_deletions=False` for incremental mode to avoid destructive deletes on partial fetch.

---

## 6) Transcripts → `Transcripts`

### Loader

- `scripts/process_transcripts_from_sharepoint.py::process_transcripts()`
- which calls `app.transcript_processor.TranscriptProcessor.extract_transcripts_from_sharepoint()`

### Strategy

Transcripts are transformed into retrieval-optimized chunks:

- raw transcript chunks (conversation)
- artifact chunks (Q&A, objections, feature capability, decision drivers)
- artifacts are grouped into ~180–350 token chunks to avoid “one artifact = one tiny chunk”

### Stable IDs

Schema contract states:

- `doc_id` should equal `meeting_id` for Transcripts

The transcript processor stores meeting metadata; the Weaviate metadata enricher maps transcript fields into the Transcripts collection properties.

---

## 7) Spreadsheets → `Spreadsheets`

### Loader

- `scripts/ingest_to_weaviate.py` uses local directory:
  - `app.excel_processor.process_excel_directory(EXCEL_SOURCE_DIR)`

### Strategy

The Excel processor builds text plus metadata describing:

- `sheet_name`, `row_start`, `row_end`
- a “row_data” representation (JSON-string requirement is part of the schema for Weaviate insertion)

For SharePoint-hosted Excels, the SharePoint Graph extractor uses the row-level strategy and stores those rows into `SharePointDocs` (not `Spreadsheets`) because they are treated as SharePoint documents.

---

## 8) Email → `EmailThreads`

### Loader

- `app.outlook_processor.process_outlook_content()`

### Strategy

- Fetch messages from folder
- group by conversation/thread
- format one thread → one large document
- chunk large threads with 2000/400 splitter

### Stable IDs

EmailThreads schema expects:

- `thread_id` (Outlook conversation id) in metadata
- `doc_id` ideally should be thread_id to keep grouping stable

---

## 9) Where “strategy knobs” live

- Summaries: `--no-summaries` in CLI (and `SummaryGenerator` thresholds)
- Dedup: `--no-dedup` in CLI (pipeline uses exact dedup by `content_hash`)
- Incremental: `--no-incremental` in CLI (tracker in `data/ingestion_tracking/`)
- Deletions: blog incremental disables deletions (`allow_deletions=False`) to avoid partial-fetch deletes

