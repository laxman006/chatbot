## Architecture overview (Weaviate KB)

### What we store in Weaviate

We store a **single knowledge base** split into **source-based collections** (not file-type collections). Each collection stores:

- **Content chunks** (normal chunks) with \(chunk\_role="content"\) and \(chunk\_id=0..N\)
- **Optional summary chunks** with \(chunk\_id=-1\) and a collection-specific summary role (e.g. `doc_summary`, `ticket_summary`, etc.)

Vectors are **generated externally** (OpenAI embeddings) and **explicitly inserted** into Weaviate (schema uses `vectorizer_config=none()`).

### Collections (source-based)

The schema defines these collections:

- `SharePointDocs`
- `Blogs`
- `JiraTickets`
- `Transcripts`
- `Spreadsheets`
- `EmailThreads`

Reference: `app/weaviate_schema.py`

### High-level flow (ingest + retrieve)

```mermaid
flowchart LR
  subgraph Sources
    SP[SharePoint files]
    JIRA[Jira issues]
    BLOG[Blog posts]
    XLS[Excel / spreadsheets]
    MAIL[Email threads]
    TR[Transcripts]
  end

  subgraph Ingestion
    L[Load documents\n(LangChain Document)]
    C[Chunking\nMarkdownAwareChunker\n(fallback SemanticChunker)]
    M[Metadata enrichment\n(parent_key,parent_id,chunk_key,\ncontent_hash, token_count,\nRBAC permissions)]
    D[Exact dedup\n(by content_hash)]
    E[Embeddings\nOpenAI text-embedding-3-small\n(token-batched + cached)]
    S[Optional summary chunk\n(if chunks>5 OR tokens>2000)]
    B[Batch insert\nDeterministic UUID(uuid5) from chunk_key]
  end

  subgraph Weaviate
    W[(Weaviate v4\ncollections API\nvectorizer=None)]
  end

  subgraph Retrieval
    Q[User query]
    QE[Embed query\ntext-embedding-3-small]
    NV[near_vector per collection\n+ optional filters]
    SUM[Optional summary-chunk query\n(chunk_role=...)]
    O[Ordering\nchunk_type priority\nthen distance]
    DD[Dedup by chunk_key]
  end

  Sources --> L --> C --> M --> D --> E --> S --> B --> W
  Q --> QE --> NV --> O --> DD
  NV --> SUM --> O
  W --> NV
```

### Core design principles (why this looks like this)

- **Source-based collections**: retrieval can target sources independently (SharePoint vs Jira vs Blogs).
- **Parent-document retrieval ready**: universal `parent_id` + sequential `chunk_id` allow “neighbor expansion” patterns.
- **RBAC-ready**: universal `permissions` array is filterable at query time.
- **External vectors**: stable embedding model and explicit vectors reduce schema coupling to Weaviate modules.
- **Idempotent writes**: deterministic UUID derived from `chunk_key` ensures “same chunk → same object id”.

