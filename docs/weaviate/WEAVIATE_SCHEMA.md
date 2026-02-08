# Weaviate Schema Documentation

**Production-grade Weaviate v4 schema for Branching RAG Knowledge Base**

## Overview

This schema implements a source-based collection architecture (NOT file-type collections) with:
- ✅ Universal Parent-Document Retrieval fields everywhere
- ✅ RBAC-ready metadata (permissions filters)
- ✅ Incremental ingestion support (doc_id, version, last_indexed_at)
- ✅ Summary chunk support (chunk_role)
- ✅ Weaviate v4 client.collections API only
- ✅ External vectorization (embeddings provided externally)

### More detailed implementation docs

For deeper “how it works in this repo” documentation (IDs, ingestion pipeline, retrieval filters/ordering, ops/troubleshooting), see:

- `docs/weaviate/README.md`

---

## Collections

The schema defines **6 source-based collections**:

| Collection | Description |
|------------|-------------|
| `SharePointDocs` | PDF/DOC/DOCX/MD/HTML files from SharePoint |
| `Blogs` | Internal blogs/wiki posts |
| `JiraTickets` | Jira issues/tickets |
| `Transcripts` | VTT/SRT/demo call transcripts |
| `Spreadsheets` | Excel files/sheets/rows (stored in SharePoint) |
| `EmailThreads` | Email threads/conversations |

---

## Universal Properties

All collections share these universal properties:

### Chunk Payload
- **`content`** (TEXT) - Chunk content text (embedded externally)

### Source and Typing
- **`source_type`** (TEXT) - Source type: `sharepoint|blog|jira|transcript|excel|email`
  - ⚠️ **IMPORTANT**: Must match collection name for consistency:
    - `SharePointDocs` → `"sharepoint"`
    - `Blogs` → `"blog"`
    - `JiraTickets` → `"jira"`
    - `Transcripts` → `"transcript"`
    - `Spreadsheets` → `"excel"`
    - `EmailThreads` → `"email"`
  - Use `get_source_type_for_collection()` helper function to ensure consistency
- **`source_ref`** (TEXT) - Source reference identifier (ticket key, filename, etc.) e.g., `'PROJ-123'`, `'policy.pdf'`
- **`file_type`** (TEXT) - File type: `pdf|docx|xlsx|md|html|txt` (if applicable)

### Parent Document Identity (Parent-Doc Retrieval)
- **`doc_id`** (TEXT) - Stable document ID (SharePoint file id, Jira key, blog slug, transcript id)
- **`parent_id`** (TEXT) - Stable UUID/string for parent document (same across all chunks of a doc)
- **`parent_key`** (TEXT) - Path-like identifier (e.g., `'sharepoint/limitations/policy.pdf'`)

### Chunk Identity
- **`chunk_id`** (INT) - Order within parent scope (0..N). Use `-1` for summary chunks.
  - ⚠️ **IMPORTANT**: When fetching neighbor chunks for parent-doc expansion, **ALWAYS exclude `chunk_id = -1`** from neighbor queries. Summary chunks should be fetched separately if needed, not as part of sequential neighbor expansion.
- **`chunk_key`** (TEXT) - Globally unique chunk key, e.g., `parent_key + '#chunk_' + chunk_id`
- **`chunk_role`** (TEXT) - Chunk role (see [Chunk Roles](#chunk-roles) section below)
  - ⚠️ **IMPORTANT**: Must be validated against `VALID_CHUNK_ROLES` during ingestion
  - Use `validate_chunk_role()` helper function to enforce validation

### Document Metadata (UX + Citations)
- **`title`** (TEXT) - Document title
- **`url`** (TEXT) - Document URL / SharePoint link / Jira link
- **`created_at`** (DATE) - Creation date (ISO-8601)
- **`updated_at`** (DATE) - Last update date (ISO-8601)

### RBAC / Permission Filtering
- **`permissions`** (TEXT_ARRAY) - RBAC permission groups e.g. `['eng','admin','sales']`

### Multi-Tenant / Organizational Structure
- **`tenant_id`** (TEXT) - Org tenant/team identifier for multi-tenant deployments
- **`department`** (TEXT) - Department name for organizational filtering and security boundaries

### Ingestion + Operations
- **`version`** (INT) - Document version number (increment on change)
- **`last_indexed_at`** (DATE) - When this chunk was last indexed
- **`token_count`** (INT) - Token count for this chunk

---

## Collection-Specific Properties

### Blogs
- **`author`** (TEXT) - Blog author
- **`tags`** (TEXT_ARRAY) - Blog tags
- **`category`** (TEXT) - Blog category
- **`heading_path`** (TEXT) - Heading hierarchy e.g. `'Intro > Setup > Install'`
- **`section_title`** (TEXT) - Section title
- **`publish_date`** (DATE) - Publish date

### JiraTickets
- **`ticket_key`** (TEXT) - Jira ticket key e.g. `PROJ-123`
- **`project_key`** (TEXT) - Jira project key
- **`issue_type`** (TEXT) - `Bug|Story|Task|Epic`
- **`status`** (TEXT) - Ticket status
- **`priority`** (TEXT) - Ticket priority
- **`assignee`** (TEXT) - Ticket assignee
- **`reporter`** (TEXT) - Ticket reporter
- **`labels`** (TEXT_ARRAY) - Ticket labels
- **`components`** (TEXT_ARRAY) - Ticket components
- **`sprint`** (TEXT) - Sprint name or id

### Transcripts

**Meeting Identity:**
- **`meeting_id`** (TEXT) - Unique meeting/session ID (used as `doc_id` and for `parent_id` grouping)
  - ⚠️ **IMPORTANT**: Always set `doc_id = meeting_id` for Transcripts (no mismatch)
- **`meeting_title`** (TEXT) - Meeting/demo title (e.g., `'CloudFuze Manage Demo - Customer Name'`)
- **`meeting_date`** (DATE) - Meeting date (ISO-8601)
- **`meeting_time`** (TEXT) - Meeting time (HH:MM:SS format, if available)
- **`transcript_source`** (TEXT) - Transcript source: `sharepoint_transcripts|zoom|teams|gmeet`

**Context Metadata:**
- **`customer`** (TEXT) - Customer name/organization from the demo
- **`industry`** (TEXT) - Customer industry sector (e.g., `Education`, `Healthcare`, `Finance`)
- **`participants`** (TEXT_ARRAY) - List of participant names in the meeting
- **`speaker_roles`** (TEXT_ARRAY) - Speaker roles mapped to names (e.g., `['John (Sales)', 'Jane (Customer)']`)
- **`topic`** (TEXT_ARRAY) - Topics discussed in the transcript (multi-topic tagging)

**Reliability Controls:**
- **`kb_tier`** (TEXT) - Knowledge base tier: always `'secondary'` for transcripts
- **`reliability`** (TEXT) - Reliability level: `'contextual'` for transcripts (not contractual)
- **`not_contractual`** (BOOL) - `True` - transcript content is not contractual/guaranteed
- **`internal_use_only`** (BOOL) - `True` - transcript is for internal use only

**Extraction Metadata:**
- **`artifact_type`** (TEXT) - Type of extracted artifact: `qa|objection|feature|decision|action_item|raw`
- **`contains_pricing`** (BOOL) - `True` if transcript contains pricing discussions

**Legacy/Additional Fields:**
- **`speaker`** (TEXT) - Speaker name (for individual chunk context, if applicable)
- **`t_start`** (NUMBER) - Start timestamp in seconds (for time-based chunking, if applicable)
- **`t_end`** (NUMBER) - End timestamp in seconds (for time-based chunking, if applicable)

### Spreadsheets

> **Note**: Excel files are stored in SharePoint. The `source_type` is `"excel"` (matching collection name), but SharePoint metadata is tracked separately.

**Sheet Structure:**
- **`sheet_name`** (TEXT) - Excel sheet name
- **`sheet_index`** (INT) - Sheet index (ordering)
- **`row_start`** (INT) - Start row number
- **`row_end`** (INT) - End row number

**SharePoint Source (Excel files are stored in SharePoint):**
- **`sharepoint_site_name`** (TEXT) - SharePoint site name where Excel file is stored
- **`sharepoint_folder_name`** (TEXT) - SharePoint folder name/path where Excel file is stored
- **`sharepoint_file_id`** (TEXT) - SharePoint file ID for the Excel file (used as `doc_id`)

**Generic Row Storage (works for all Excels):**
- **`row_data`** (TEXT) - JSON string of row key-value pairs (universal format for any Excel row)
  - ⚠️ **IMPORTANT**: Must be stored as JSON string (not object). All keys in `row_data` must be present in `row_keys`
- **`row_keys`** (TEXT_ARRAY) - Column names present in row (for filtering and querying)
  - ⚠️ **IMPORTANT**: Must always include all keys that exist in `row_data` JSON

**Optional Standardized Fields (only if present, e.g., limitations Excel):**
- **`feature_name`** (TEXT) - Feature name (optional - only for standardized formats like limitations Excel)
- **`limitations`** (TEXT) - Limitations/notes (optional - only for standardized formats like limitations Excel)
- **`supported`** (TEXT) - `yes|no|na` (optional - only for standardized formats like limitations Excel)

> **Note**: This schema supports both generic Excel files (using `row_data` and `row_keys`) and standardized formats like limitations Excel (using `feature_name`, `limitations`, `supported`). During ingestion, fill `row_data` and `row_keys` for all Excels, and additionally fill the optional fields if the Excel matches a standardized format.

### SharePointDocs
- **`folder_name`** (TEXT) - SharePoint folder name
- **`site_name`** (TEXT) - SharePoint site name
- **`page_start`** (INT) - Start page number (if PDF)
- **`page_end`** (INT) - End page number (if PDF)
- **`section_title`** (TEXT) - Section title / heading

### EmailThreads
**Thread-level metadata:**
- **`thread_id`** (TEXT) - Gmail thread id / Outlook conversation id
- **`subject`** (TEXT) - Email thread subject
- **`mailbox_id`** (TEXT) - Mailbox identifier (e.g., `support@company.com`, `engineering@company.com`)
- **`mail_source`** (TEXT) - Email source: `gmail|outlook|exchange`
- **`participant_emails`** (TEXT_ARRAY) - List of participant email addresses
- **`participant_names`** (TEXT_ARRAY) - List of participant names (optional)
- **`message_count`** (INT) - Number of messages in the thread
- **`is_external_thread`** (BOOL) - Whether thread contains external participants
- **`external_domains`** (TEXT_ARRAY) - List of external email domains in thread

**Message-level metadata:**
- **`message_id`** (TEXT) - Unique email message ID
- **`from_email`** (TEXT) - Sender email address
- **`to_emails`** (TEXT_ARRAY) - Recipient email addresses
- **`cc_emails`** (TEXT_ARRAY) - CC email addresses
- **`sent_at`** (DATE) - Message sent timestamp (ISO-8601)
- **`in_reply_to`** (TEXT) - Message ID this email is replying to
- **`references`** (TEXT_ARRAY) - Email references header (thread chain)

**User email tracking:**
- **`user_email_ids`** (TEXT_ARRAY) - Organization member email IDs involved in thread
- **`external_email_ids`** (TEXT_ARRAY) - External participant email IDs (optional)

> **Note**: `thread_summary` and `message_summary` are **NOT** stored as properties. They are stored as chunks with `chunk_role="thread_summary"` or `chunk_role="message_summary"`.

---

## Chunk Roles

Standardized `chunk_role` values for consistent retrieval:

| Role | Description | Collection(s) |
|------|-------------|---------------|
| `content` | Regular content chunk | All |
| `doc_summary` | Document summary | SharePointDocs, Blogs |
| `sheet_summary` | Excel sheet summary | Spreadsheets |
| `ticket_summary` | Jira ticket summary | JiraTickets |
| `thread_summary` | Email thread summary | EmailThreads |
| `message_summary` | Individual email message summary | EmailThreads |
| `meeting_summary` | Meeting transcript summary | Transcripts |
| `decisions_summary` | Decisions extracted from transcript | Transcripts |
| `action_items_summary` | Action items extracted from transcript | Transcripts |

**Summary chunks use `chunk_id = -1`** to distinguish them from sequential content chunks.

---

## Vector Index Configuration

Default HNSW configuration for all collections:

```python
{
    "distance": "cosine",
    "ef": 64,              # Higher = better recall, slower
    "ef_construction": 128, # Build quality
    "max_connections": 32,  # Graph connectivity
}
```

These are safe defaults for mid-scale corpora. Tune later based on recall vs latency needs.

---

## Filterable Fields

These fields are kept short/structured for efficient filtering in Parent-Doc retrieval:

- **`parent_id`** (TEXT, stable UUID)
- **`chunk_id`** (INT, 0..N or -1 for summaries)
- **`permissions`** (TEXT_ARRAY, RBAC groups)
- **Collection-specific**: `ticket_key`, `thread_id`, `sheet_name` (all TEXT, short identifiers)

---

## ⚠️ CRITICAL: Parent-Doc Expansion Logic

### chunk_id = -1 Exclusion

When fetching neighbor chunks for parent-doc expansion:

**Example**: Expanding around `chunk_id=3` with `expand_k=1`

- ✅ **CORRECT**: Fetch `chunk_id IN [2, 3, 4]` (exclude -1)
- ❌ **WRONG**: Fetch `chunk_id IN [2, 3, 4, -1]`

**Why**: Summary chunks (`chunk_id = -1`) are not sequential neighbors. They should be fetched separately if needed, not as part of sequential neighbor expansion queries.

### Correct Weaviate Filter Patterns

#### Neighbor Expansion (exclude -1)
```json
{
  "operator": "And",
  "operands": [
    {"path": ["parent_id"], "operator": "Equal", "valueText": parent_id},
    {"path": ["chunk_id"], "operator": "GreaterThanEqual", "valueInt": 0},
    {"path": ["chunk_id"], "operator": "ContainsAny", "valueInt": [2, 3, 4]}
  ]
}
```

#### Summary Chunk Fetch (separate query)
```json
{
  "operator": "And",
  "operands": [
    {"path": ["parent_id"], "operator": "Equal", "valueText": parent_id},
    {"path": ["chunk_id"], "operator": "Equal", "valueInt": -1},
    {"path": ["chunk_role"], "operator": "Equal", "valueText": "doc_summary"}
  ]
}
```

### Implementation Example

```python
# ✅ CORRECT: Neighbor expansion (exclude -1)
neighbor_ids = range(
    max(0, chunk_id - expand_k),
    chunk_id + expand_k + 1
)
# Filter: chunk_id >= 0 AND chunk_id IN neighbor_ids

# ✅ CORRECT: Summary fetch (separate query)
# Filter: chunk_id = -1 AND chunk_role = "doc_summary"
```

---

## Collection Creation

### Using the Schema Module

```python
from app.weaviate_schema import create_collection, create_all_collections

# Create a single collection
create_collection("EmailThreads")

# Create all collections
create_all_collections()

# Recreate (delete + create)
create_all_collections(recreate=True)
```

### Collection Structure

Each collection:
- Uses **external vectorization** (vectorizer disabled)
- Shares **universal properties** + **collection-specific properties**
- Uses **HNSW vector index** with cosine distance
- Enforces **chunk_key uniqueness** via deterministic UUID at ingestion time

---

## Validation Helpers & Best Practices

### source_type Consistency

Always use the helper function to ensure `source_type` matches collection name:

```python
from app.weaviate_schema import get_source_type_for_collection

# ✅ CORRECT: Ensures consistency
source_type = get_source_type_for_collection("SharePointDocs")  # Returns "sharepoint"
source_type = get_source_type_for_collection("Blogs")  # Returns "blog"
source_type = get_source_type_for_collection("JiraTickets")  # Returns "jira"
source_type = get_source_type_for_collection("Transcripts")  # Returns "transcript"
source_type = get_source_type_for_collection("Spreadsheets")  # Returns "excel"
source_type = get_source_type_for_collection("EmailThreads")  # Returns "email"
```

### chunk_role Validation

Always validate `chunk_role` during ingestion:

```python
from app.weaviate_schema import validate_chunk_role, VALID_CHUNK_ROLES

# ✅ CORRECT: Validate before inserting
chunk_role = "doc_summary"
validate_chunk_role(chunk_role)  # Raises ValueError if invalid

# Or check manually:
if chunk_role not in VALID_CHUNK_ROLES:
    raise ValueError(f"Invalid chunk_role: {chunk_role}")
```

### Transcript doc_id = meeting_id

For Transcripts collection, always ensure `doc_id = meeting_id`:

```python
# ✅ CORRECT: No mismatch
meeting_id = "demo_20251202_110233"
doc_id = meeting_id  # Always set equal
parent_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, meeting_id))
```

### Spreadsheet doc_id = sharepoint_file_id

For Spreadsheets collection, always ensure `doc_id = sharepoint_file_id` (since Excel files are stored in SharePoint):

```python
# ✅ CORRECT: No mismatch
sharepoint_file_id = "01ABC123XYZ..."  # SharePoint file ID
doc_id = sharepoint_file_id  # Always set equal
parent_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, sharepoint_file_id))
```

### Excel row_data Format

For Spreadsheets collection, ensure proper JSON string format:

```python
import json

# ✅ CORRECT: Store as JSON string
row_dict = {"Feature": "SSO", "Supported": "Yes", "Limitations": "None"}
row_data = json.dumps(row_dict)  # JSON string
row_keys = list(row_dict.keys())  # All keys from row_data

# ❌ WRONG: Don't store as object
# row_data = row_dict  # This will fail
```

---

## Key Design Principles

1. **Source-based collections** - Organized by data source, not file type
2. **Parent-document retrieval** - All collections support neighbor expansion via `parent_id` + `chunk_id`
3. **RBAC-ready** - `permissions` field enables access control filtering
4. **Incremental ingestion** - `version` and `last_indexed_at` support update tracking
5. **Summary chunks** - Stored as chunks with `chunk_id = -1`, not as separate properties
6. **Multi-tenant support** - `tenant_id` and `department` for organizational boundaries
7. **Idempotent updates** - Deterministic UUID from `chunk_key` ensures updates overwrite existing chunks

---

## Data Types Reference

| Weaviate DataType | Python Type | Description |
|-------------------|-------------|-------------|
| `TEXT` | `str` | Text string |
| `TEXT_ARRAY` | `List[str]` | Array of text strings |
| `INT` | `int` | Integer |
| `NUMBER` | `float` | Floating point number |
| `DATE` | `datetime` | ISO-8601 date/datetime |
| `BOOL` | `bool` | Boolean |

---

## Notes

- **External Embeddings**: All collections use `vectorizer_config=None`. Embeddings must be provided externally during ingestion.
- **Chunk Key Uniqueness**: Enforced via deterministic UUID based on `chunk_key` as the Weaviate object ID.
- **Email Summaries**: Thread and message summaries are stored as chunks, not properties (see EmailThreads section).
- **Filter Performance**: Keep filterable fields (`parent_id`, `chunk_id`, `ticket_key`, etc.) short and structured for optimal query performance.

---

## Schema Version

- **Weaviate Version**: v4
- **API**: `client.collections` API only
- **Last Updated**: 2026-01-26

---

## Related Files

- Schema Implementation: `app/weaviate_schema.py`
- Client Wrapper: `app/weaviate_client.py`
- Configuration: `config.py` (WEAVIATE_URL, WEAVIATE_API_KEY)
