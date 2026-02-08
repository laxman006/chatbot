## Weaviate (v4) KB Implementation Docs

This folder documents the **current Weaviate v4 schema + ingestion + retrieval implementation** in this repo, so a new teammate can understand the data model and the end-to-end flow quickly.

If you only read one file first, read **`02-schema-reference.md`** and **`04-ingestion-pipeline.md`**.

### Quick navigation

- **Architecture overview**: `01-architecture-overview.md`
- **Schema reference (collections + properties + chunk roles)**: `02-schema-reference.md`
- **Identifiers & metadata contract (doc_id/parent_id/parent_key/chunk_key)**: `03-identifiers-and-metadata.md`
- **Ingestion pipeline (chunking → metadata → embeddings → summaries → insert)**: `04-ingestion-pipeline.md`
- **Chunking strategies (generic + per-source “atomic” chunking)**: `07-chunking-strategies.md`
- **Ingestion strategies by source (SharePoint/Jira/Blog/Transcript/Excel/Email)**: `08-ingestion-strategies-by-source.md`
- **Retrieval pipeline (filters, RBAC, summary chunks, ordering, dedupe)**: `05-retrieval-pipeline.md`
- **Operations & troubleshooting**: `06-operations-and-troubleshooting.md`

### Source of truth in code

- **Schema**: `app/weaviate_schema.py`
- **Client**: `app/weaviate_client.py`
- **Ingestion**: `app/weaviate_ingestion.py`
- **Batch insert / delete**: `app/weaviate_batch_inserter.py`
- **Retriever**: `app/weaviate_retriever.py`
- **Metadata enrichment**: `app/metadata_enricher.py`
- **Embeddings**: `app/embedding_service.py`
- **Summary chunks**: `app/summary_generator.py`
- **Incremental tracking**: `app/incremental_ingestion.py`
- **RBAC filter**: `app/rbac.py`
- **Chunkers**: `app/chunking/`
- **RAG graph nodes (retrieval orchestration)**: `app/rag/nodes.py`

### Existing schema doc

There is also a top-level schema document: `WEAVIATE_SCHEMA.md`.  
This `docs/weaviate/` folder goes **deeper** into implementation details (IDs, batching, filters, ordering, failure modes).

