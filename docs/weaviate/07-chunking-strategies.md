## Chunking strategies (complete)

This doc captures **all chunking strategies currently used** in the repo for Weaviate ingestion.

Chunking happens in two places:

1. **Source processors** (SharePoint/PDF/DOCX/Excel/Email/Blog/Transcript) often produce *already structured chunks*.
2. The **Weaviate ingestion pipeline** may apply an additional chunking pass using the generic chunker.

### Source of truth

- Generic chunkers: `app/chunking/`
  - `app/chunking/recursive.py` (`RecursiveChunker`)
  - `app/chunking/markdown_aware.py` (`MarkdownAwareChunker`)
  - `app/chunking/__init__.py` (`get_chunker`)
- Legacy chunker: `app/chunking_strategy.py` (`SemanticChunker`)
- Ingestion selection logic: `app/weaviate_ingestion.py` (`_chunk_documents`)
- SharePoint “atomic chunking”: `app/sharepoint_graph_extractor.py`
- PDF table/text chunking: `app/pdf_processor.py`
- DOCX block chunking: `app/doc_processor.py`
- Excel row chunking: `app/excel_processor.py`
- Email thread chunking: `app/outlook_processor.py`
- Blog chunking: `app/helpers.py` (`fetch_latest_web_content`)
- Transcript artifact chunking: `app/transcript_processor.py`

---

## 1) Generic chunkers (used by WeaviateIngestionPipeline)

### 1.1 `MarkdownAwareChunker` (preferred default)

Used by default in `WeaviateIngestionPipeline.__init__()`:

- `get_chunker(kind="markdown_aware", target_tokens=800, overlap_tokens=200, min_tokens=150)`

Behavior:

- Split on Markdown/HTML headings first:
  - Markdown: `#{1,6} ...`
  - HTML: `<h1>...</h1>` ... `<h6>...</h6>`
- Merge small sections if below `min_tokens` and merge stays within ~1.5× target.
- For oversized sections, apply a recursive character splitter fallback with token-to-char approximation:
  - \(chars \approx tokens \times 5.5\)

Where it’s good:

- Markdown docs, HTML-ish content, long prose.

Where it can be redundant:

- When upstream processors already emit “atomic” chunks (table rows, ticket sections, etc.). In that case, most chunks are already small and will not split further.

### 1.2 `RecursiveChunker`

Factory: `get_chunker(kind="recursive", target_tokens=..., overlap_tokens=...)`

Behavior:

- Uses `RecursiveCharacterTextSplitter` with separators:
  - `\n\n\n`, `\n\n`, `\n`, `. `, `! `, `? `, `; `, `, `, ` `, `""`
- Token sizing is approximated via chars-per-token \(5.5\).

### 1.3 `SemanticChunker` (legacy fallback)

If initializing `MarkdownAwareChunker` fails, pipeline falls back to:

- `app/chunking_strategy.py::SemanticChunker`

Behavior:

- Heading-aware splitting (Markdown + HTML + “Title:” style lines)
- Merge small chunks
- Split large ones with recursive splitter
- Adds metadata like `char_range`, `token_count` to chunk documents

---

## 2) Source-specific chunking (produced before Weaviate pipeline)

These chunkers create “semantic units” that map cleanly to your schema fields like `chunk_type`, `feature`, `supported`, `raw_kv`, `migration_type`, etc.

### 2.1 SharePointDocs (Graph extractor)

File: `app/sharepoint_graph_extractor.py`

The extractor branches by file type and produces **LangChain Documents**:

#### Excel (`.xls/.xlsx`) and CSV (`.csv`)

- Uses `app.excel_processor.extract_excel_rows_as_chunks()` or `extract_csv_rows_as_chunks()`
- **One row (or one matrix cell)** becomes one or more atomic chunks:
  - `chunk_type`: `feature_capability`, `limitation`, `table_row`, `migration_capability_summary`, `raw_content`
  - Includes `raw_kv` JSON string for audit/grounding
  - Includes `migration_type` / `migration_combination` when detected
- SharePoint-level grouping:
  - sets file-level `doc_id = "sharepoint:<item_id>"` so *all rows group under the same document*

#### DOCX (`.docx`)

- Uses `app.doc_processor.extract_docx_blocks_as_chunks()`
- Produces “block-level” chunks:
  - paragraphs → `process` / `rule`
  - table rows → `feature_capability` (+ an extra `limitation` chunk when support is `No/NA`)
  - carries `section_title` (heading context)
  - includes `raw_kv` for table rows
- SharePoint-level grouping:
  - sets file-level `doc_id = "sharepoint:<item_id>"`

#### PDF (`.pdf`)

- Uses two extraction paths:
  - `extract_pdf_tables_as_chunks()` (layered + matrix aware)
  - `extract_pdf_atomic_chunks()` (adds non-table “explanation” text chunks)
- Chunk types include:
  - `raw_content` (table dump)
  - `table_row` (structured)
  - `feature_capability`
  - `limitation`
  - `migration_capability_summary`
  - `explanation` (non-table text)
- Adds `page_number`, `section_title`, and for text chunks may include `vertical_position` for interleaving.

#### PPTX (`.ppt/.pptx`)

- Extracts slide text and emits one document per slide (images are skipped in this repo’s ingestion).
- Sets `chunk_type="explanation"` for slide text.

#### Emails / videos / images

- Images (`png/jpg`) are skipped.
- Videos are skipped.

### 2.2 JiraTickets (field-aware chunking)

File: `app/jira_processor.py`

Jira is chunked by **ticket sections**, not by generic splitter:

- One “summary” document
- One “description” document (may be split later if large)
- One “root_cause” document (never split)
- One “fix_description” document (never split)
- One “AI suggestions” document (optional)
- One document per comment

Each chunk includes metadata like `ticket_key`, `project_key`, `status`, etc.

### 2.3 Blogs (WordPress)

File: `app/helpers.py` (`fetch_latest_web_content`)

Per blog post:

- Cleans HTML → plain text
- Prepends `# <title>` for context
- Splits with `RecursiveCharacterTextSplitter`:
  - `chunk_size=1500`, `chunk_overlap=300`
- Sets stable `doc_id` to the post slug (or link/id fallback), plus canonical metadata:
  - `title`, `url`, `post_slug`, `post_date`, `author_name`, etc.

### 2.4 EmailThreads (Outlook)

File: `app/outlook_processor.py`

Strategy:

- Fetch messages, group by `conversationId` (thread)
- Build one “thread document” containing ordered emails
- If thread is large, chunk it with `RecursiveCharacterTextSplitter`:
  - `chunk_size=2000`, `chunk_overlap=400`
  - separators include `\n--- Email `

### 2.5 Transcripts (SharePoint transcript folder)

File: `app/transcript_processor.py`

Strategy (high-level):

- Extract transcript DOCX → text
- Optional normalization and artifact extraction (Q&A, objections, features, decision drivers)
- Group artifacts into **token-sized groups**:
  - target ~250 tokens, max 350, min 180
- Builds natural-language “retrieval text” so artifacts are searchable

---

## 3) “Double chunking” (important to understand)

Because many sources already emit atomic chunks, and then the Weaviate ingestion pipeline applies a generic chunker, you effectively have:

- **Upstream structured chunking** (table rows, ticket sections, artifact groups)
- **Downstream safety chunking** (MarkdownAware / Semantic) to keep any *still-large* text from being too big

This is intentional for robustness, but if you ever see overly fragmented chunks, this is the first place to look.

