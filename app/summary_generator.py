"""
Summary generator for creating document summaries as separate chunks.

Conditional generation: only for documents with chunks > 5 OR token_count > 2000.
Non-blocking: doesn't fail ingestion if summary generation fails.
"""

import logging
from typing import List, Dict, Any, Optional
from langchain_core.documents import Document

from app.weaviate_models import WeaviateChunk
from app.weaviate_schema import (
    CHUNK_ROLE_DOC_SUMMARY,
    CHUNK_ROLE_TICKET_SUMMARY,
    CHUNK_ROLE_SHEET_SUMMARY,
    CHUNK_ROLE_THREAD_SUMMARY,
    CHUNK_ROLE_MESSAGE_SUMMARY,
    CHUNK_ROLE_MEETING_SUMMARY,
    VALID_CHUNK_ROLES
)
from app.llm_factory import get_llm

logger = logging.getLogger(__name__)

# Thresholds for conditional summary generation
MIN_CHUNKS_FOR_SUMMARY = 5
MIN_TOKENS_FOR_SUMMARY = 2000

# Chunk role mapping by collection
COLLECTION_TO_SUMMARY_ROLE = {
    "SharePointDocs": CHUNK_ROLE_DOC_SUMMARY,
    "Blogs": CHUNK_ROLE_DOC_SUMMARY,
    "JiraTickets": CHUNK_ROLE_TICKET_SUMMARY,
    "Spreadsheets": CHUNK_ROLE_SHEET_SUMMARY,
    "EmailThreads": CHUNK_ROLE_THREAD_SUMMARY,
    "Transcripts": CHUNK_ROLE_MEETING_SUMMARY,
}


class SummaryGenerator:
    """
    Generates document summaries as separate chunks.
    
    Features:
    - Conditional generation (only if chunks > 5 OR tokens > 2000)
    - Non-blocking error handling (doesn't fail ingestion)
    - Collection-specific chunk_role assignment
    """
    
    def __init__(self, enable_summaries: bool = True):
        """
        Initialize summary generator.
        
        Args:
            enable_summaries: Whether to enable summary generation
        """
        self.enable_summaries = enable_summaries
        self.llm = get_llm() if enable_summaries else None
        logger.info(
            f"[SUMMARY] Initialized with enable_summaries={enable_summaries}"
        )
    
    def should_generate_summary(
        self,
        chunks: List[WeaviateChunk],
        total_tokens: Optional[int] = None
    ) -> bool:
        """
        Determine if summary should be generated.
        
        Conditions:
        - chunks > MIN_CHUNKS_FOR_SUMMARY (5), OR
        - total_tokens > MIN_TOKENS_FOR_SUMMARY (2000)
        
        Args:
            chunks: List of chunks for the document
            total_tokens: Total token count (if None, calculated from chunks)
        
        Returns:
            True if summary should be generated
        """
        if not self.enable_summaries:
            return False
        
        if not chunks:
            return False
        
        # Check chunk count
        if len(chunks) > MIN_CHUNKS_FOR_SUMMARY:
            return True
        
        # Check token count
        if total_tokens is None:
            total_tokens = sum(c.token_count or 0 for c in chunks)
        
        if total_tokens > MIN_TOKENS_FOR_SUMMARY:
            return True
        
        return False
    
    def generate_summary_chunk(
        self,
        chunks: List[WeaviateChunk],
        doc_id: str,
        collection_name: str,
        doc_metadata: Dict[str, Any],
        parent_id: str,
        parent_key: str
    ) -> Optional[WeaviateChunk]:
        """
        Generate a summary chunk for a document.
        
        Args:
            chunks: List of content chunks
            doc_id: Document ID
            collection_name: Collection name
            doc_metadata: Document-level metadata
            parent_id: Parent document UUID
            parent_key: Parent key
        
        Returns:
            WeaviateChunk with summary (chunk_id=-1) or None if generation fails
        """
        if not self.should_generate_summary(chunks):
            logger.debug(
                f"[SUMMARY] Skipping summary for doc_id={doc_id} "
                f"(chunks={len(chunks)}, below threshold)"
            )
            return None
        
        if not self.llm:
            logger.warning("[SUMMARY] LLM not available, skipping summary generation")
            return None
        
        try:
            # Get chunk role for collection
            chunk_role = COLLECTION_TO_SUMMARY_ROLE.get(
                collection_name,
                CHUNK_ROLE_DOC_SUMMARY  # Default fallback
            )
            
            # Combine chunk content for summary
            combined_content = "\n\n".join([c.content for c in chunks])
            
            # Generate summary using LLM
            summary_text = self._generate_summary_text(
                content=combined_content,
                doc_metadata=doc_metadata,
                collection_name=collection_name
            )
            
            if not summary_text:
                logger.warning(f"[SUMMARY] Empty summary generated for doc_id={doc_id}")
                return None
            
            # Create summary chunk (chunk_id=-1)
            from app.metadata_enricher import MetadataEnricher
            
            enricher = MetadataEnricher()
            
            # Create a temporary Document for the summary
            summary_doc = Document(
                page_content=summary_text,
                metadata=doc_metadata.copy()
            )
            
            # Enrich as summary chunk
            summary_chunks = enricher.enrich_chunks(
                chunks=[summary_doc],
                doc_id=doc_id,
                collection_name=collection_name,
                doc_metadata=doc_metadata,
                is_summary=True
            )
            
            if not summary_chunks:
                return None
            
            summary_chunk = summary_chunks[0]
            
            # Override chunk_role to ensure it's correct
            summary_chunk.metadata["chunk_role"] = chunk_role
            
            logger.info(
                f"[SUMMARY] ✓ Generated summary for doc_id={doc_id} "
                f"(chunk_key={summary_chunk.chunk_key}, role={chunk_role})"
            )
            
            return summary_chunk
            
        except Exception as e:
            # Non-blocking: log error but don't fail ingestion
            logger.warning(
                f"[SUMMARY] Failed to generate summary for doc_id={doc_id}: {e}. "
                f"Continuing without summary (non-blocking)."
            )
            return None
    
    def _generate_summary_text(
        self,
        content: str,
        doc_metadata: Dict[str, Any],
        collection_name: str
    ) -> Optional[str]:
        """
        Generate summary text using LLM.
        
        Args:
            content: Combined content from all chunks
            doc_metadata: Document metadata
            collection_name: Collection name
        
        Returns:
            Summary text or None if generation fails
        """
        # Build prompt based on collection type
        title = doc_metadata.get("title", "Document")
        
        if collection_name == "JiraTickets":
            prompt = f"""Summarize the following Jira ticket in 2-3 sentences. Focus on the problem, solution, and key outcomes.

Title: {title}

Content:
{content[:5000]}  # Limit content to avoid token limits

Summary:"""
        
        elif collection_name == "Transcripts":
            prompt = f"""Summarize the following meeting transcript in 2-3 sentences. Focus on key discussion points, decisions, and action items.

Meeting: {title}

Content:
{content[:5000]}

Summary:"""
        
        elif collection_name == "EmailThreads":
            prompt = f"""Summarize the following email thread in 2-3 sentences. Focus on the main topic, key messages, and outcomes.

Subject: {title}

Content:
{content[:5000]}

Summary:"""
        
        else:
            # Default summary for documents
            prompt = f"""Summarize the following document in 2-3 sentences. Focus on the main topic and key information.

Title: {title}

Content:
{content[:5000]}

Summary:"""
        
        try:
            # Invoke LLM
            response = self.llm.invoke(prompt)
            
            # Extract text from response
            if hasattr(response, 'content'):
                summary = response.content
            elif isinstance(response, str):
                summary = response
            else:
                summary = str(response)
            
            # Clean up summary
            summary = summary.strip()
            
            if len(summary) < 50:
                logger.warning(f"[SUMMARY] Summary too short ({len(summary)} chars), may be invalid")
                return None
            
            return summary
            
        except Exception as e:
            logger.error(f"[SUMMARY] LLM invocation failed: {e}")
            return None
