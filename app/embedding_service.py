"""
Embedding service for external embedding generation.

Uses OpenAI text-embedding-3-small with token-based batching and content_hash caching.
"""

import logging
import time
from typing import List, Dict, Optional
import numpy as np
from langchain_openai import OpenAIEmbeddings

from app.weaviate_models import WeaviateChunk

logger = logging.getLogger(__name__)

# Token limit for OpenAI embeddings API (300k tokens per request, use 250k for safety)
MAX_TOKENS_PER_BATCH = 250000


class EmbeddingService:
    """
    Service for generating embeddings externally.
    
    Features:
    - Token-based dynamic batching (not fixed chunk count)
    - Content hash caching to avoid re-embedding duplicates
    - Error handling with retries and exponential backoff
    """
    
    def __init__(
        self,
        model: str = "text-embedding-3-small",
        max_tokens_per_batch: int = MAX_TOKENS_PER_BATCH,
        enable_caching: bool = True
    ):
        """
        Initialize embedding service.
        
        Args:
            model: OpenAI embedding model name
            max_tokens_per_batch: Maximum tokens per batch (default: 250k for safety)
            enable_caching: Enable content_hash caching to avoid re-embedding duplicates
        """
        self.embeddings_model = OpenAIEmbeddings(model=model)
        self.max_tokens_per_batch = max_tokens_per_batch
        self.enable_caching = enable_caching
        
        # Cache: content_hash -> embedding vector
        self._embedding_cache: Dict[str, List[float]] = {}
        
        logger.info(
            f"[EMBEDDING] Initialized with model={model}, "
            f"max_tokens_per_batch={max_tokens_per_batch}, "
            f"caching={'enabled' if enable_caching else 'disabled'}"
        )
    
    def generate_embeddings(
        self,
        chunks: List[WeaviateChunk],
        max_retries: int = 3
    ) -> List[WeaviateChunk]:
        """
        Generate embeddings for chunks using token-based batching.
        
        Args:
            chunks: List of WeaviateChunk objects (must have content_hash and token_count set)
            max_retries: Maximum number of retries for failed batches
        
        Returns:
            List of WeaviateChunk objects with vectors populated
        """
        if not chunks:
            return []
        
        # Separate chunks into cached and uncached
        cached_chunks = []
        uncached_chunks = []
        
        for chunk in chunks:
            if self.enable_caching and chunk.content_hash and chunk.content_hash in self._embedding_cache:
                # Use cached embedding
                chunk.vector = self._embedding_cache[chunk.content_hash]
                cached_chunks.append(chunk)
            else:
                uncached_chunks.append(chunk)
        
        logger.info(
            f"[EMBEDDING] Processing {len(uncached_chunks)} uncached chunks "
            f"(skipping {len(cached_chunks)} cached)"
        )
        
        if not uncached_chunks:
            return chunks
        
        # Batch by tokens
        batches = self._batch_by_tokens(uncached_chunks)
        logger.info(f"[EMBEDDING] Created {len(batches)} token-based batches")
        
        # Process each batch
        all_processed = []
        for batch_idx, batch in enumerate(batches, 1):
            logger.info(
                f"[EMBEDDING] Processing batch {batch_idx}/{len(batches)} "
                f"({len(batch)} chunks, ~{sum(c.token_count for c in batch)} tokens)"
            )
            
            processed_batch = self._process_batch_with_retry(batch, max_retries)
            all_processed.extend(processed_batch)
            
            # Cache embeddings
            if self.enable_caching:
                for chunk in processed_batch:
                    if chunk.content_hash and chunk.vector:
                        self._embedding_cache[chunk.content_hash] = chunk.vector
        
        # Combine cached and processed chunks
        result = cached_chunks + all_processed
        
        logger.info(
            f"[EMBEDDING] ✓ Generated embeddings for {len(result)} chunks "
            f"({len(cached_chunks)} from cache, {len(all_processed)} new)"
        )
        
        return result
    
    def _batch_by_tokens(
        self,
        chunks: List[WeaviateChunk]
    ) -> List[List[WeaviateChunk]]:
        """
        Batch chunks by token count (dynamic batching).
        
        Creates batches that don't exceed max_tokens_per_batch.
        
        Args:
            chunks: List of chunks to batch
        
        Returns:
            List of batches (each batch is a list of chunks)
        """
        batches = []
        current_batch = []
        current_tokens = 0
        
        for chunk in chunks:
            chunk_tokens = chunk.token_count or 0
            
            # If adding this chunk would exceed limit, start new batch
            if current_tokens + chunk_tokens > self.max_tokens_per_batch and current_batch:
                batches.append(current_batch)
                current_batch = [chunk]
                current_tokens = chunk_tokens
            else:
                current_batch.append(chunk)
                current_tokens += chunk_tokens
        
        # Add final batch
        if current_batch:
            batches.append(current_batch)
        
        return batches
    
    def _process_batch_with_retry(
        self,
        batch: List[WeaviateChunk],
        max_retries: int
    ) -> List[WeaviateChunk]:
        """
        Process a batch with retry logic.
        
        Args:
            batch: Batch of chunks to process
            max_retries: Maximum retry attempts
        
        Returns:
            List of processed chunks with vectors
        """
        texts = [chunk.content for chunk in batch]
        
        for attempt in range(max_retries):
            try:
                # Generate embeddings
                embeddings = self.embeddings_model.embed_documents(texts)
                
                # Assign vectors to chunks
                for chunk, embedding in zip(batch, embeddings):
                    chunk.vector = embedding
                
                return batch
                
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(
                        f"[EMBEDDING] Batch failed (attempt {attempt + 1}/{max_retries}): {e}. "
                        f"Retrying in {wait_time}s..."
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        f"[EMBEDDING] Batch failed after {max_retries} attempts: {e}"
                    )
                    # Return chunks without vectors (will be logged as failed)
                    return batch
        
        return batch
    
    def clear_cache(self):
        """Clear the embedding cache."""
        self._embedding_cache.clear()
        logger.info("[EMBEDDING] Cache cleared")
    
    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        return {
            "cached_embeddings": len(self._embedding_cache),
            "cache_size_mb": sum(
                len(v) * 4 for v in self._embedding_cache.values()
            ) / (1024 * 1024)  # Approximate size in MB (float32 = 4 bytes)
        }
