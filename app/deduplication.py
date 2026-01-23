"""
Deduplication module for identifying and merging duplicate chunks.

Uses cosine similarity on embeddings to detect duplicates and merge their metadata.
"""

from typing import List, Dict, Any, Tuple, Optional
import numpy as np
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from sklearn.metrics.pairwise import cosine_similarity
import json


class Deduplicator:
    """
    Deduplicate document chunks based on embedding similarity.
    """
    
    def __init__(
        self,
        threshold: float = 0.85,
        embeddings_model: Optional[OpenAIEmbeddings] = None
    ):
        """
        Initialize deduplicator.
        
        Args:
            threshold: Cosine similarity threshold for duplicate detection (0.85 = 85% similar)
            embeddings_model: Embedding model to use (defaults to OpenAI)
        """
        self.threshold = threshold
        self.embeddings_model = embeddings_model or OpenAIEmbeddings(model="text-embedding-3-small")
        
        # Statistics tracking
        self.stats = {
            "total_checked": 0,
            "duplicates_found": 0,
            "chunks_merged": 0
        }
    
    def compute_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        Compute embeddings for a list of texts with automatic batching.
        Processes in batches to avoid OpenAI token limits (300k tokens/request).
        
        Args:
            texts: List of text strings
        
        Returns:
            NumPy array of embeddings (n_texts, embedding_dim)
        """
        if not texts:
            return np.array([])
        
        # Process in batches to avoid OpenAI token limits (300k tokens/request)
        # Real-world data: 1000 chunks = 624k tokens (measured from actual run)
        # This means ~624 tokens per chunk on average (very large chunks!)
        # Max tokens: 300,000 / 624 = ~480 chunks per batch
        # Use 400 as safe batch size with buffer
        batch_size = 400
        all_embeddings = []
        
        total_batches = (len(texts) + batch_size - 1) // batch_size
        
        if len(texts) > batch_size:
            print(f"   Computing embeddings in {total_batches} batches...")
        
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            batch_num = i // batch_size + 1
            
            if len(texts) > batch_size:
                print(f"   Batch {batch_num}/{total_batches}: Processing {len(batch_texts)} chunks...")
            
            try:
                batch_embeddings = self.embeddings_model.embed_documents(batch_texts)
                all_embeddings.extend(batch_embeddings)
            except Exception as e:
                print(f"   [ERROR] Failed to compute embeddings for batch {batch_num}: {e}")
                raise
        
        return np.array(all_embeddings)
    
    def find_duplicates(
        self,
        new_embeddings: np.ndarray,
        existing_embeddings: np.ndarray
    ) -> List[Tuple[int, int, float]]:
        """
        Find duplicate pairs between new and existing embeddings.
        
        Args:
            new_embeddings: Embeddings of new chunks (n_new, embedding_dim)
            existing_embeddings: Embeddings of existing chunks (n_existing, embedding_dim)
        
        Returns:
            List of (new_idx, existing_idx, similarity_score) for duplicates
        """
        if len(new_embeddings) == 0 or len(existing_embeddings) == 0:
            return []
        
        # Compute cosine similarity matrix
        similarity_matrix = cosine_similarity(new_embeddings, existing_embeddings)
        
        # Find pairs above threshold
        duplicates = []
        for i in range(similarity_matrix.shape[0]):
            for j in range(similarity_matrix.shape[1]):
                similarity = similarity_matrix[i, j]
                if similarity >= self.threshold:
                    duplicates.append((i, j, float(similarity)))
        
        return duplicates
    
    def merge_metadata(
        self,
        existing_doc: Document,
        new_doc: Document,
        similarity: float
    ) -> Document:
        """
        Merge metadata from duplicate document into existing document.
        
        Args:
            existing_doc: Existing document in vectorstore
            new_doc: New duplicate document
            similarity: Similarity score between documents
        
        Returns:
            Document with merged metadata
        """
        merged_metadata = existing_doc.metadata.copy()
        
        # Increment relevance count
        relevance_count = merged_metadata.get("relevance_count", 1) + 1
        merged_metadata["relevance_count"] = relevance_count
        
        # Track original sources
        existing_sources = merged_metadata.get("original_sources", "")
        new_doc_id = new_doc.metadata.get("doc_id", "unknown")
        
        if existing_sources:
            merged_metadata["original_sources"] = f"{existing_sources}, {new_doc_id}"
        else:
            # First merge - add both original and new
            original_doc_id = merged_metadata.get("doc_id", "unknown")
            merged_metadata["original_sources"] = f"{original_doc_id}, {new_doc_id}"
        
        # Track similarity scores
        similarity_scores = merged_metadata.get("duplicate_similarities", "")
        if similarity_scores:
            merged_metadata["duplicate_similarities"] = f"{similarity_scores}, {similarity:.3f}"
        else:
            merged_metadata["duplicate_similarities"] = f"{similarity:.3f}"
        
        # Merge additional metadata from new doc if not present
        for key, value in new_doc.metadata.items():
            if key not in merged_metadata and value is not None:
                # Add as alternative value
                alt_key = f"alt_{key}"
                merged_metadata[alt_key] = value
        
        # Create merged document
        merged_doc = Document(
            page_content=existing_doc.page_content,
            metadata=merged_metadata
        )
        
        return merged_doc
    
    def deduplicate_against_existing(
        self,
        new_docs: List[Document],
        existing_docs: List[Document],
        existing_embeddings: Optional[np.ndarray] = None
    ) -> Tuple[List[Document], List[Document], Dict[str, Any]]:
        """
        Deduplicate new documents against existing collection.
        
        Args:
            new_docs: New documents to check
            existing_docs: Existing documents in vectorstore
            existing_embeddings: Pre-computed embeddings for existing docs (optional)
        
        Returns:
            Tuple of (unique_docs, duplicate_docs, stats_dict)
                - unique_docs: New documents that are not duplicates
                - duplicate_docs: Existing documents with merged metadata
                - stats_dict: Statistics about deduplication
        """
        if not new_docs:
            return [], [], {"total_checked": 0, "duplicates_found": 0, "chunks_merged": 0}
        
        if not existing_docs:
            # No existing docs to compare against
            return new_docs, [], {"total_checked": len(new_docs), "duplicates_found": 0, "chunks_merged": 0}
        
        # Compute embeddings for new documents
        new_texts = [doc.page_content for doc in new_docs]
        new_embeddings = self.compute_embeddings(new_texts)
        
        # Compute embeddings for existing documents if not provided
        if existing_embeddings is None:
            existing_texts = [doc.page_content for doc in existing_docs]
            existing_embeddings = self.compute_embeddings(existing_texts)
        
        # Find duplicates
        duplicate_pairs = self.find_duplicates(new_embeddings, existing_embeddings)
        
        # Track which new docs are duplicates
        duplicate_indices = set()
        merged_docs = {}
        
        for new_idx, existing_idx, similarity in duplicate_pairs:
            duplicate_indices.add(new_idx)
            
            # Merge metadata into existing document
            if existing_idx not in merged_docs:
                merged_docs[existing_idx] = self.merge_metadata(
                    existing_docs[existing_idx],
                    new_docs[new_idx],
                    similarity
                )
            else:
                # Already merged once, merge again
                merged_docs[existing_idx] = self.merge_metadata(
                    merged_docs[existing_idx],
                    new_docs[new_idx],
                    similarity
                )
        
        # Separate unique and duplicate documents
        unique_docs = [doc for i, doc in enumerate(new_docs) if i not in duplicate_indices]
        duplicate_docs_list = list(merged_docs.values())
        
        # Update statistics
        stats = {
            "total_checked": len(new_docs),
            "duplicates_found": len(duplicate_indices),
            "chunks_merged": len(duplicate_docs_list),
            "unique_docs": len(unique_docs)
        }
        
        self.stats["total_checked"] += stats["total_checked"]
        self.stats["duplicates_found"] += stats["duplicates_found"]
        self.stats["chunks_merged"] += stats["chunks_merged"]
        
        return unique_docs, duplicate_docs_list, stats
    
    def deduplicate_within_batch(
        self,
        docs: List[Document]
    ) -> Tuple[List[Document], Dict[str, Any]]:
        """
        Deduplicate documents within a single batch.
        
        Args:
            docs: Documents to deduplicate
        
        Returns:
            Tuple of (unique_docs, stats_dict)
        """
        if not docs or len(docs) <= 1:
            return docs, {"total_checked": len(docs), "duplicates_found": 0}
        
        # Compute embeddings
        texts = [doc.page_content for doc in docs]
        embeddings = self.compute_embeddings(texts)
        
        # Compute similarity matrix
        similarity_matrix = cosine_similarity(embeddings, embeddings)
        
        # Find duplicates (only upper triangle to avoid double counting)
        duplicate_indices = set()
        merged_docs = {}
        
        for i in range(len(docs)):
            if i in duplicate_indices:
                continue
            
            for j in range(i + 1, len(docs)):
                if j in duplicate_indices:
                    continue
                
                similarity = similarity_matrix[i, j]
                if similarity >= self.threshold:
                    # Mark j as duplicate, merge into i
                    duplicate_indices.add(j)
                    
                    if i not in merged_docs:
                        merged_docs[i] = docs[i]
                    
                    merged_docs[i] = self.merge_metadata(
                        merged_docs[i],
                        docs[j],
                        similarity
                    )
        
        # Build result list
        unique_docs = []
        for i, doc in enumerate(docs):
            if i in duplicate_indices:
                continue
            elif i in merged_docs:
                unique_docs.append(merged_docs[i])
            else:
                unique_docs.append(doc)
        
        stats = {
            "total_checked": len(docs),
            "duplicates_found": len(duplicate_indices),
            "unique_docs": len(unique_docs)
        }
        
        self.stats["total_checked"] += stats["total_checked"]
        self.stats["duplicates_found"] += stats["duplicates_found"]
        
        return unique_docs, stats
    
    def get_stats(self) -> Dict[str, Any]:
        """Get deduplication statistics."""
        return self.stats.copy()
    
    def reset_stats(self):
        """Reset statistics counters."""
        self.stats = {
            "total_checked": 0,
            "duplicates_found": 0,
            "chunks_merged": 0
        }


def deduplicate_documents(
    new_docs: List[Document],
    existing_docs: List[Document] = None,
    threshold: float = 0.85
) -> Tuple[List[Document], Dict[str, Any]]:
    """
    Convenience function to deduplicate documents.
    
    Args:
        new_docs: New documents to check
        existing_docs: Existing documents to compare against (optional)
        threshold: Similarity threshold for duplicates
    
    Returns:
        Tuple of (deduplicated_docs, stats)
    """
    deduplicator = Deduplicator(threshold=threshold)
    
    if existing_docs:
        unique_docs, merged_docs, stats = deduplicator.deduplicate_against_existing(
            new_docs, existing_docs
        )
        # Return both unique and merged docs
        return unique_docs + merged_docs, stats
    else:
        # Deduplicate within the batch
        return deduplicator.deduplicate_within_batch(new_docs)

