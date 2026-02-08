"""
Weaviate data models for ingestion pipeline.

Defines WeaviateChunk dataclass and related models for clean data structures
throughout the ingestion pipeline (instead of using LangChain Documents).
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime


@dataclass
class WeaviateChunk:
    """
    Internal dataclass for Weaviate chunks.
    
    Cleaner than transforming LangChain Documents throughout the pipeline.
    Contains all data needed for Weaviate insertion.
    """
    # Core content
    content: str
    metadata: Dict[str, Any]
    vector: Optional[List[float]] = None
    
    # Deduplication and caching
    content_hash: str = field(default="")
    token_count: int = field(default=0)
    
    # Weaviate-specific identifiers
    chunk_key: str = field(default="")
    parent_id: str = field(default="")
    parent_key: str = field(default="")
    chunk_id: int = field(default=0)
    
    def __post_init__(self):
        """Validate required fields after initialization."""
        if not self.content:
            raise ValueError("content cannot be empty")
        if not self.metadata:
            raise ValueError("metadata cannot be empty")
        if not self.chunk_key:
            raise ValueError("chunk_key must be set")
        if not self.parent_id:
            raise ValueError("parent_id must be set")
        if not self.parent_key:
            raise ValueError("parent_key must be set")
    
    def to_weaviate_object(self) -> Dict[str, Any]:
        """
        Convert to Weaviate object format for insertion.
        
        Returns:
            Dictionary with properties and optional vector for Weaviate API
        """
        obj = {
            "properties": self.metadata.copy()
        }
        
        # Add vector if available
        if self.vector:
            obj["vector"] = self.vector
        
        return obj
    
    @classmethod
    def from_langchain_document(
        cls,
        doc: Any,  # langchain_core.documents.Document
        metadata_overrides: Optional[Dict[str, Any]] = None
    ) -> "WeaviateChunk":
        """
        Create WeaviateChunk from LangChain Document.
        
        Args:
            doc: LangChain Document
            metadata_overrides: Optional metadata to override/extend
        
        Returns:
            WeaviateChunk instance
        """
        metadata = doc.metadata.copy() if hasattr(doc, 'metadata') else {}
        if metadata_overrides:
            metadata.update(metadata_overrides)
        
        return cls(
            content=doc.page_content if hasattr(doc, 'page_content') else str(doc),
            metadata=metadata,
            vector=None,  # Will be populated by EmbeddingService
            content_hash="",  # Will be populated by MetadataEnricher
            token_count=0,  # Will be populated by MetadataEnricher
            chunk_key=metadata.get("chunk_key", ""),
            parent_id=metadata.get("parent_id", ""),
            parent_key=metadata.get("parent_key", ""),
            chunk_id=metadata.get("chunk_id", 0)
        )


@dataclass
class IngestionResult:
    """Result of an ingestion operation."""
    success: bool
    chunks_processed: int = 0
    chunks_inserted: int = 0
    chunks_failed: int = 0
    failed_chunk_keys: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    processing_time_seconds: float = 0.0
    
    def __str__(self) -> str:
        """String representation of ingestion result."""
        status = "SUCCESS" if self.success else "FAILED"
        return (
            f"IngestionResult({status}): "
            f"processed={self.chunks_processed}, "
            f"inserted={self.chunks_inserted}, "
            f"failed={self.chunks_failed}, "
            f"time={self.processing_time_seconds:.2f}s"
        )
