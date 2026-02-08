"""
Batch inserter for Weaviate with error isolation and retry logic.

Handles efficient batch insertion with deterministic UUIDs, idempotent updates,
and error isolation (retry only failed chunks).
"""

import uuid
import logging
import time
from typing import List, Dict, Any, Optional
from weaviate.classes.query import Filter
from weaviate.classes.data import DataObject

from app.weaviate_models import WeaviateChunk, IngestionResult
from app.weaviate_client import get_weaviate_client

logger = logging.getLogger(__name__)

# Batch size for Weaviate insertion (100-200 objects per batch is safe)
DEFAULT_BATCH_SIZE = 100
MAX_RETRIES = 3


class WeaviateBatchInserter:
    """
    Batch inserter for Weaviate with error isolation.
    
    Features:
    - Deterministic UUIDs from chunk_key (idempotent updates)
    - Batch insertion with configurable batch size
    - Error isolation: retry only failed chunks
    - Comprehensive error logging
    """
    
    def __init__(
        self,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_retries: int = MAX_RETRIES
    ):
        """
        Initialize batch inserter.
        
        Args:
            batch_size: Number of objects per batch
            max_retries: Maximum retry attempts for failed batches
        """
        self.batch_size = batch_size
        self.max_retries = max_retries
        logger.info(
            f"[BATCH_INSERT] Initialized with batch_size={batch_size}, "
            f"max_retries={max_retries}"
        )
    
    def insert_chunks(
        self,
        chunks: List[WeaviateChunk],
        collection_name: str
    ) -> IngestionResult:
        """
        Insert chunks into Weaviate collection.
        
        Args:
            chunks: List of WeaviateChunk objects (must have vectors)
            collection_name: Weaviate collection name
        
        Returns:
            IngestionResult with statistics
        """
        if not chunks:
            return IngestionResult(success=True, chunks_processed=0)
        
        client = get_weaviate_client()
        if client is None:
            return IngestionResult(
                success=False,
                chunks_processed=len(chunks),
                errors=["Weaviate client unavailable"]
            )
        
        # Get collection
        try:
            collection = client.collections.get(collection_name)
        except Exception as e:
            return IngestionResult(
                success=False,
                chunks_processed=len(chunks),
                errors=[f"Failed to get collection '{collection_name}': {e}"]
            )
        
        # Filter chunks with vectors
        chunks_with_vectors = [c for c in chunks if c.vector]
        chunks_without_vectors = [c for c in chunks if not c.vector]
        
        if chunks_without_vectors:
            logger.warning(
                f"[BATCH_INSERT] {len(chunks_without_vectors)} chunks without vectors "
                f"(will be skipped)"
            )
        
        if not chunks_with_vectors:
            return IngestionResult(
                success=False,
                chunks_processed=len(chunks),
                errors=["No chunks with vectors to insert"]
            )
        
        # Batch chunks
        batches = [
            chunks_with_vectors[i:i + self.batch_size]
            for i in range(0, len(chunks_with_vectors), self.batch_size)
        ]
        
        logger.info(
            f"[BATCH_INSERT] Inserting {len(chunks_with_vectors)} chunks "
            f"in {len(batches)} batches into '{collection_name}'"
        )
        
        # Process batches
        all_inserted = 0
        all_failed = 0
        failed_chunk_keys = []
        errors = []
        
        for batch_idx, batch in enumerate(batches, 1):
            logger.info(
                f"[BATCH_INSERT] Processing batch {batch_idx}/{len(batches)} "
                f"({len(batch)} chunks)"
            )
            
            batch_result = self._insert_batch_with_retry(
                collection=collection,
                batch=batch,
                batch_idx=batch_idx
            )
            
            all_inserted += batch_result["inserted"]
            all_failed += batch_result["failed"]
            failed_chunk_keys.extend(batch_result["failed_chunk_keys"])
            if batch_result["errors"]:
                errors.extend(batch_result["errors"])
        
        success = all_failed == 0
        
        result = IngestionResult(
            success=success,
            chunks_processed=len(chunks),
            chunks_inserted=all_inserted,
            chunks_failed=all_failed,
            failed_chunk_keys=failed_chunk_keys,
            errors=errors
        )
        
        logger.info(
            f"[BATCH_INSERT] ✓ Insertion complete: {all_inserted} inserted, "
            f"{all_failed} failed"
        )
        
        return result
    
    def _insert_batch_with_retry(
        self,
        collection: Any,  # weaviate.collections.Collection
        batch: List[WeaviateChunk],
        batch_idx: int
    ) -> Dict[str, Any]:
        """
        Insert a batch with retry logic and error isolation.
        
        Args:
            collection: Weaviate collection object
            batch: Batch of chunks to insert
            batch_idx: Batch index (for logging)
        
        Returns:
            Dictionary with insertion results
        """
        # Prepare objects for insertion
        # CRITICAL: When vectorizer=None, vector MUST be explicitly included
        # Weaviate v4 requires DataObject for custom vectors
        objects_to_insert = []
        chunk_key_to_chunk = {}
        
        for chunk in batch:
            # Validate vector exists (mandatory when vectorizer=None)
            if chunk.vector is None or len(chunk.vector) == 0:
                raise ValueError(
                    f"Missing vector for chunk_key={chunk.chunk_key}. "
                    f"Since vectorizer=None, vectors must be provided manually."
                )
            
            # Generate deterministic UUID from chunk_key
            chunk_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk.chunk_key))
            chunk_key_to_chunk[chunk.chunk_key] = chunk
            
            # Prepare DataObject with explicit properties and vector
            # Weaviate v4 requires DataObject for insert_many() with custom vectors
            obj = DataObject(
                properties=chunk.metadata.copy(),
                vector=chunk.vector,  # ✅ Explicitly include vector
                uuid=chunk_uuid
            )
            
            objects_to_insert.append(obj)
        
        # Try insertion with retries
        for attempt in range(self.max_retries):
            try:
                # Insert batch
                collection.data.insert_many(objects_to_insert)
                
                return {
                    "inserted": len(batch),
                    "failed": 0,
                    "failed_chunk_keys": [],
                    "errors": []
                }
                
            except Exception as e:
                error_msg = f"Batch {batch_idx} failed (attempt {attempt + 1}/{self.max_retries}): {e}"
                logger.warning(f"[BATCH_INSERT] {error_msg}")
                
                if attempt < self.max_retries - 1:
                    # Retry with exponential backoff
                    wait_time = 2 ** attempt
                    time.sleep(wait_time)
                    
                    # Try individual insertions for error isolation
                    if attempt == self.max_retries - 2:
                        # Last retry: try individual insertions
                        return self._insert_individually_with_isolation(
                            collection=collection,
                            batch=batch,
                            chunk_key_to_chunk=chunk_key_to_chunk
                        )
                else:
                    # Final attempt failed: try individual insertions
                    return self._insert_individually_with_isolation(
                        collection=collection,
                        batch=batch,
                        chunk_key_to_chunk=chunk_key_to_chunk
                    )
        
        # All retries failed
        return {
            "inserted": 0,
            "failed": len(batch),
            "failed_chunk_keys": [c.chunk_key for c in batch],
            "errors": [f"Batch {batch_idx} failed after {self.max_retries} attempts"]
        }
    
    def _insert_individually_with_isolation(
        self,
        collection: Any,
        batch: List[WeaviateChunk],
        chunk_key_to_chunk: Dict[str, WeaviateChunk]
    ) -> Dict[str, Any]:
        """
        Insert chunks individually for error isolation.
        
        Retries only failed chunks, not the entire batch.
        
        Args:
            collection: Weaviate collection object
            batch: Batch of chunks
            chunk_key_to_chunk: Mapping of chunk_key to chunk
        
        Returns:
            Dictionary with insertion results
        """
        logger.info(
            f"[BATCH_INSERT] Attempting individual insertions for {len(batch)} chunks "
            f"(error isolation)"
        )
        
        inserted = 0
        failed = 0
        failed_chunk_keys = []
        errors = []
        
        for chunk in batch:
            try:
                # Validate vector exists (mandatory when vectorizer=None)
                if chunk.vector is None or len(chunk.vector) == 0:
                    raise ValueError(
                        f"Missing vector for chunk_key={chunk.chunk_key}. "
                        f"Since vectorizer=None, vectors must be provided manually."
                    )
                
                # Generate deterministic UUID
                chunk_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk.chunk_key))
                
                # CRITICAL: When vectorizer=None, vector MUST be passed explicitly
                # Use explicit keyword arguments: properties=..., vector=..., uuid=...
                collection.data.insert(
                    properties=chunk.metadata.copy(),
                    vector=chunk.vector,  # ✅ Explicitly pass vector
                    uuid=chunk_uuid
                )
                inserted += 1
                
            except Exception as e:
                failed += 1
                failed_chunk_keys.append(chunk.chunk_key)
                error_msg = f"Failed to insert chunk {chunk.chunk_key}: {e}"
                errors.append(error_msg)
                logger.error(f"[BATCH_INSERT] {error_msg}")
        
        return {
            "inserted": inserted,
            "failed": failed,
            "failed_chunk_keys": failed_chunk_keys,
            "errors": errors
        }
    
    def delete_chunks_by_parent_id(
        self,
        collection_name: str,
        parent_id: str
    ) -> bool:
        """
        Delete all chunks for a parent document.
        
        Used for incremental ingestion: delete old chunks before re-ingesting.
        
        Args:
            collection_name: Weaviate collection name
            parent_id: Parent document ID
        
        Returns:
            True if successful, False otherwise
        """
        client = get_weaviate_client()
        if client is None:
            logger.error("[BATCH_INSERT] Weaviate client unavailable")
            return False
        
        try:
            collection = client.collections.get(collection_name)
            
            # Delete by parent_id filter
            collection.data.delete_many(
                where=Filter.by_property("parent_id").equal(parent_id)
            )
            
            logger.info(
                f"[BATCH_INSERT] ✓ Deleted chunks for parent_id={parent_id} "
                f"in collection '{collection_name}'"
            )
            return True
            
        except Exception as e:
            logger.error(
                f"[BATCH_INSERT] Failed to delete chunks for parent_id={parent_id}: {e}"
            )
            return False

    def delete_chunks_by_doc_id(
        self,
        collection_name: str,
        doc_id: str
    ) -> bool:
        """
        Delete all chunks for a document by doc_id.

        Args:
            collection_name: Weaviate collection name (e.g. SharePointDocs)
            doc_id: Document ID (e.g. sharepoint:01PK5PNWOEADXOEDR5TREICKCXHGFQDFO5)

        Returns:
            True if successful, False otherwise
        """
        client = get_weaviate_client()
        if client is None:
            logger.error("[BATCH_INSERT] Weaviate client unavailable")
            return False

        try:
            collection = client.collections.get(collection_name)
            collection.data.delete_many(
                where=Filter.by_property("doc_id").equal(doc_id)
            )
            logger.info(
                f"[BATCH_INSERT] ✓ Deleted chunks for doc_id={doc_id!r} "
                f"in collection '{collection_name}'"
            )
            return True
        except Exception as e:
            logger.error(
                f"[BATCH_INSERT] Failed to delete chunks for doc_id={doc_id!r}: {e}"
            )
            return False

    def delete_chunks_by_parent_key_contains(
        self,
        collection_name: str,
        substring: str
    ) -> bool:
        """
        Delete all chunks whose parent_key contains the given substring.
        Uses Weaviate Like operator (*substring*).

        Use this to delete only one SharePoint scope (e.g. Presales) by
        passing the scope identifier that appears in parent_key
        (e.g. "Pre-SalesTrining" for Presales).

        Args:
            collection_name: Weaviate collection name (e.g. SharePointDocs)
            substring: Substring to match in parent_key (e.g. "Pre-SalesTrining")

        Returns:
            True if successful, False otherwise
        """
        client = get_weaviate_client()
        if client is None:
            logger.error("[BATCH_INSERT] Weaviate client unavailable")
            return False

        try:
            collection = client.collections.get(collection_name)
            # Like uses * for wildcard: *substring* matches any parent_key containing substring
            pattern = f"*{substring}*"
            collection.data.delete_many(
                where=Filter.by_property("parent_key").like(pattern)
            )
            logger.info(
                f"[BATCH_INSERT] ✓ Deleted chunks where parent_key like {pattern!r} "
                f"in collection '{collection_name}'"
            )
            return True
        except Exception as e:
            logger.error(
                f"[BATCH_INSERT] Failed to delete chunks by parent_key contains {substring!r}: {e}"
            )
            return False
