"""
Main Weaviate ingestion pipeline.

Orchestrates the full ingestion process:
1. Load documents from source
2. Chunk documents
3. Enrich metadata
4. Deduplicate
5. Generate embeddings
6. Generate summaries (conditional)
7. Batch insert into Weaviate
8. Track versions
"""

import logging
import time
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime

from langchain_core.documents import Document
from app.weaviate_models import WeaviateChunk, IngestionResult
from app.embedding_service import EmbeddingService
from app.metadata_enricher import MetadataEnricher, ParentKeyBuilder
from app.weaviate_batch_inserter import WeaviateBatchInserter
from app.summary_generator import SummaryGenerator
from app.incremental_ingestion import IncrementalIngestionTracker
from app.deduplication import Deduplicator
from app.chunking_strategy import SemanticChunker
from app.chunking import get_chunker, MarkdownAwareChunker, RECURSIVE, MARKDOWN_AWARE
from app.ingest_reporter import IngestReporter

logger = logging.getLogger(__name__)


class WeaviateIngestionPipeline:
    """
    Main ingestion pipeline for Weaviate.
    
    Orchestrates the complete ingestion process with all improvements:
    - Token-based embedding batching
    - Content hash caching
    - Conditional summary generation
    - Incremental ingestion with doc_hash
    - Deletion handling
    - Error isolation
    """
    
    def __init__(
        self,
        enable_summaries: bool = True,
        enable_deduplication: bool = True,
        enable_incremental: bool = True,
        allow_deletions: bool = True,
        tracking_dir: str = "data/ingestion_tracking"
    ):
        """
        Initialize ingestion pipeline.
        
        Args:
            enable_summaries: Enable conditional summary generation
            enable_deduplication: Enable MD5 exact dedup
            enable_incremental: Enable incremental ingestion tracking
            allow_deletions: If False, do not remove docs from tracker or delete from Weaviate (safe for append-only sources like blog)
            tracking_dir: Directory for tracking files
        """
        self.enable_summaries = enable_summaries
        self.enable_deduplication = enable_deduplication
        self.enable_incremental = enable_incremental
        self.allow_deletions = allow_deletions
        
        # Initialize components
        self.embedding_service = EmbeddingService()
        self.metadata_enricher = MetadataEnricher()
        self.batch_inserter = WeaviateBatchInserter()
        self.summary_generator = SummaryGenerator(enable_summaries=enable_summaries)
        self.deduplicator = Deduplicator() if enable_deduplication else None
        # Antigravity: prefer markdown-aware chunker; fallback to semantic (legacy)
        try:
            self.chunker = get_chunker(kind=MARKDOWN_AWARE, target_tokens=800, overlap_tokens=200, min_tokens=150)
        except Exception:
            self.chunker = SemanticChunker()
        self.reporter = IngestReporter()
        
        logger.info(
            f"[INGESTION] Pipeline initialized: summaries={enable_summaries}, "
            f"dedup={enable_deduplication}, incremental={enable_incremental}, allow_deletions={allow_deletions}"
        )
    
    def ingest_from_source(
        self,
        source_type: str,
        documents: List[Document],
        collection_name: str,
        incremental: bool = True
    ) -> IngestionResult:
        """
        Ingest documents from a source into Weaviate collection.
        
        Args:
            source_type: Source type (sharepoint, jira, blog, etc.)
            documents: List of LangChain Documents
            collection_name: Weaviate collection name
            incremental: Whether to use incremental ingestion
        
        Returns:
            IngestionResult with statistics
        """
        start_time = time.time()
        self.reporter.start_ingestion()
        
        try:
            logger.info(
                f"[INGESTION] Starting ingestion: source_type={source_type}, "
                f"collection={collection_name}, documents={len(documents)}"
            )
            
            if not documents:
                return IngestionResult(
                    success=True,
                    chunks_processed=0,
                    processing_time_seconds=0.0
                )
            
            # Step 1: Chunk documents
            logger.info("[INGESTION] Step 1: Chunking documents...")
            chunks = self._chunk_documents(documents, source_type)
            logger.info(f"[INGESTION] Created {len(chunks)} chunks")
            
            # Step 2: Group chunks by document
            doc_chunks = self._group_chunks_by_document(chunks)
            logger.info(f"[INGESTION] Grouped into {len(doc_chunks)} documents")
            
            # Step 3: Process each document
            all_weaviate_chunks = []
            all_summary_chunks = []
            
            for doc_id, doc_chunk_list in doc_chunks.items():
                doc_metadata = doc_chunk_list[0].metadata if doc_chunk_list else {}
                
                # Get parent info (will be generated in enrich_chunks)
                # parent_key is generated inside enrich_chunks
                parent_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, doc_id))
                
                # Step 3a: Enrich metadata
                weaviate_chunks = self.metadata_enricher.enrich_chunks(
                    chunks=doc_chunk_list,
                    doc_id=doc_id,
                    collection_name=collection_name,
                    doc_metadata=doc_metadata,
                    is_summary=False
                )
                all_weaviate_chunks.extend(weaviate_chunks)
                
                # Step 3b: Generate summary (conditional)
                if self.enable_summaries and weaviate_chunks:
                    # Get parent_id and parent_key from first chunk
                    parent_id = weaviate_chunks[0].parent_id
                    parent_key = weaviate_chunks[0].parent_key
                    
                    summary_chunk = self.summary_generator.generate_summary_chunk(
                        chunks=weaviate_chunks,
                        doc_id=doc_id,
                        collection_name=collection_name,
                        doc_metadata=doc_metadata,
                        parent_id=parent_id,
                        parent_key=parent_key
                    )
                    if summary_chunk:
                        all_summary_chunks.append(summary_chunk)
            
            # Combine content and summary chunks
            all_chunks = all_weaviate_chunks + all_summary_chunks
            logger.info(
                f"[INGESTION] Enriched {len(all_chunks)} chunks "
                f"({len(all_weaviate_chunks)} content, {len(all_summary_chunks)} summaries)"
            )
            
            # Step 4: Deduplication (if enabled)
            if self.enable_deduplication and self.deduplicator:
                logger.info("[INGESTION] Step 4: Deduplicating chunks...")
                all_chunks = self._deduplicate_chunks(all_chunks)
                logger.info(f"[INGESTION] After dedup: {len(all_chunks)} chunks")
            
            # Step 5: Generate embeddings
            logger.info("[INGESTION] Step 5: Generating embeddings...")
            chunks_with_embeddings = self.embedding_service.generate_embeddings(all_chunks)
            logger.info(f"[INGESTION] Generated embeddings for {len(chunks_with_embeddings)} chunks")
            
            # Step 6: Batch insert into Weaviate
            logger.info(f"[INGESTION] Step 6: Inserting into Weaviate collection '{collection_name}'...")
            result = self.batch_inserter.insert_chunks(chunks_with_embeddings, collection_name)
            
            # Step 7: Update tracking (if incremental)
            if self.enable_incremental and incremental:
                logger.info("[INGESTION] Step 7: Updating tracking...")
                self._update_tracking(source_type, documents, doc_chunks)
            
            # Update result with processing time
            processing_time = time.time() - start_time
            result.processing_time_seconds = processing_time
            
            self.reporter.end_ingestion()
            self.reporter.add_chunks(all_chunks, source_type)
            
            logger.info(
                f"[INGESTION] ✓ Ingestion complete: {result.chunks_inserted} inserted, "
                f"{result.chunks_failed} failed, time={processing_time:.2f}s"
            )
            
            return result
            
        except Exception as e:
            logger.exception(f"[INGESTION] Ingestion failed: {e}")
            processing_time = time.time() - start_time
            return IngestionResult(
                success=False,
                chunks_processed=len(documents),
                errors=[str(e)],
                processing_time_seconds=processing_time
            )
    
    def _chunk_documents(
        self,
        documents: List[Document],
        source_type: str
    ) -> List[Document]:
        """
        Chunk documents using appropriate strategy.
        
        Args:
            documents: List of documents
            source_type: Source type (for source-specific chunking)
        
        Returns:
            List of chunked documents
        """
        if source_type == "jira":
            return documents  # Pass-through: one chunk per section (summary, description, root_cause, fix_description, comment)
        if isinstance(self.chunker, MarkdownAwareChunker):
            return self.chunker.chunk_documents(documents)
        # Legacy SemanticChunker uses chunk_document per-doc
        result = []
        for doc in documents:
            result.extend(self.chunker.chunk_document(doc))
        return result

    def _group_chunks_by_document(
        self,
        chunks: List[Document]
    ) -> Dict[str, List[Document]]:
        """
        Group chunks by document ID.
        
        Args:
            chunks: List of chunked documents
        
        Returns:
            Dictionary mapping doc_id to list of chunks
        """
        doc_chunks = {}
        for chunk in chunks:
            doc_id = chunk.metadata.get("doc_id")
            if not doc_id:
                # Generate doc_id if missing
                doc_id = str(uuid.uuid4())
                chunk.metadata["doc_id"] = doc_id
            
            if doc_id not in doc_chunks:
                doc_chunks[doc_id] = []
            doc_chunks[doc_id].append(chunk)
        
        return doc_chunks
    
    def _deduplicate_chunks(
        self,
        chunks: List[WeaviateChunk]
    ) -> List[WeaviateChunk]:
        """
        Deduplicate chunks using content_hash.
        
        Args:
            chunks: List of WeaviateChunk objects
        
        Returns:
            Deduplicated list of chunks
        """
        if not self.deduplicator:
            return chunks
        
        # Group by content_hash
        seen_hashes = set()
        unique_chunks = []
        
        for chunk in chunks:
            if chunk.content_hash and chunk.content_hash not in seen_hashes:
                seen_hashes.add(chunk.content_hash)
                unique_chunks.append(chunk)
        
        removed = len(chunks) - len(unique_chunks)
        if removed > 0:
            logger.info(f"[INGESTION] Removed {removed} duplicate chunks (by content_hash)")
        
        return unique_chunks
    
    def _update_tracking(
        self,
        source_type: str,
        documents: List[Document],
        doc_chunks: Dict[str, List[Document]]
    ):
        """
        Update incremental ingestion tracking.
        
        Args:
            source_type: Source type
            documents: Original documents
            doc_chunks: Grouped chunks by doc_id
        """
        try:
            tracker = IncrementalIngestionTracker(source_type=source_type)
            
            # Compute doc hashes
            current_docs = {}
            for doc in documents:
                doc_id = doc.metadata.get("doc_id")
                if doc_id:
                    content = doc.page_content
                    doc_hash = tracker.compute_doc_hash(content, doc.metadata)
                    current_docs[doc_id] = (content, doc.metadata)
            
            # Detect changes
            new_ids, modified_ids, deleted_ids = tracker.detect_changes(current_docs)
            
            # Update hashes for new and modified
            for doc_id in new_ids + modified_ids:
                if doc_id in current_docs:
                    content, metadata = current_docs[doc_id]
                    doc_hash = tracker.compute_doc_hash(content, metadata)
                    tracker.update_doc_hash(doc_id, doc_hash)
            
            # Remove deleted (only when allow_deletions=True to avoid destructive deletes on partial fetch)
            if self.allow_deletions:
                for doc_id in deleted_ids:
                    tracker.remove_doc_hash(doc_id)
                    logger.info(f"[INGESTION] Document deleted: {doc_id} (chunks should be deleted)")
            elif deleted_ids:
                logger.info(
                    f"[INGESTION] allow_deletions=False: skipping {len(deleted_ids)} detected deletes (append-only source)"
                )
            
            logger.info(
                f"[INGESTION] Tracking updated: {len(new_ids)} new, "
                f"{len(modified_ids)} modified, {len(deleted_ids)} deleted"
            )
            
        except Exception as e:
            logger.warning(f"[INGESTION] Failed to update tracking: {e}")
    
    def get_report(self) -> str:
        """Get ingestion report."""
        return self.reporter.generate_report()
