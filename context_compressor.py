# context_compressor.py
from typing import List, Tuple, Dict
from langchain_core.documents import Document
from app.llm_factory import get_llm

class ContextCompressor:
    """
    Enhanced context compression with priority-based preservation and metadata retention.
    
    Features:
    - Priority-based compression (preserve top-scoring chunks fully)
    - Metadata preservation (download links, sources, etc.)
    - Iterative compression if needed
    - Critical information retention (steps, numbers, names)
    """
    
    def __init__(self, model_name: str = None):
        # Use factory function to get appropriate LLM based on configuration
        # model_name parameter is ignored when using factory function
        self.llm = get_llm(model_name=model_name, temperature=0)

    def compress(
        self,
        docs: List[Document],
        max_chars: int = 8000,
        doc_scores: List[float] = None
    ) -> str:
        """
        Compress context with priority-based preservation.
        
        Args:
            docs: List of documents to compress
            max_chars: Maximum character limit
            doc_scores: Optional scores for each document (for priority preservation)
        
        Returns:
            Compressed context string with metadata preserved
        """
        if not docs:
            return ""
        
        # If no scores provided, assume all equal priority
        if doc_scores is None:
            doc_scores = [1.0] * len(docs)
        
        # Pair docs with scores and sort by score (highest first)
        doc_score_pairs = list(zip(docs, doc_scores))
        doc_score_pairs.sort(key=lambda x: x[1], reverse=True)
        
        # Separate into high-priority (top 50%) and low-priority
        split_idx = len(doc_score_pairs) // 2
        high_priority = doc_score_pairs[:split_idx]
        low_priority = doc_score_pairs[split_idx:]
        
        # Build full text with metadata
        full_text_parts = []
        metadata_info = []
        
        for doc, score in doc_score_pairs:
            # Extract and preserve metadata
            meta = doc.metadata or {}
            download_url = meta.get("download_url") or meta.get("url")
            filename = meta.get("filename") or meta.get("title") or meta.get("post_title")
            source_type = meta.get("source_type") or meta.get("source", "unknown")
            
            # Build document text with metadata header
            doc_text = doc.page_content
            
            # Add metadata header if important info exists
            if download_url or filename:
                header_parts = []
                if filename:
                    header_parts.append(f"[FILE: {filename}]")
                if download_url:
                    header_parts.append(f"[DOWNLOAD: {download_url}]")
                if source_type:
                    header_parts.append(f"[SOURCE: {source_type}]")
                
                if header_parts:
                    doc_text = " ".join(header_parts) + "\n\n" + doc_text
            
            full_text_parts.append(doc_text)
            
            # Track metadata separately for preservation
            if download_url or filename:
                metadata_info.append({
                    'filename': filename,
                    'download_url': download_url,
                    'source_type': source_type
                })
        
        full = "\n\n".join(full_text_parts)
        
        # If within limit, return as-is
        if len(full) <= max_chars:
            return full
        
        # Try priority-based compression
        compressed = self._priority_compress(
            high_priority,
            low_priority,
            max_chars,
            metadata_info
        )
        
        # If still too long, do iterative compression
        if len(compressed) > max_chars:
            compressed = self._iterative_compress(compressed, max_chars)
        
        return compressed
    
    def _priority_compress(
        self,
        high_priority: List[Tuple[Document, float]],
        low_priority: List[Tuple[Document, float]],
        max_chars: int,
        metadata_info: List[Dict]
    ) -> str:
        """Compress with priority: preserve high-priority fully, compress low-priority."""
        # Preserve high-priority documents fully
        high_priority_text = []
        for doc, score in high_priority:
            meta = doc.metadata or {}
            download_url = meta.get("download_url") or meta.get("url")
            filename = meta.get("filename") or meta.get("title") or meta.get("post_title")
            source_type = meta.get("source_type") or meta.get("source", "unknown")
            
            doc_text = doc.page_content
            if download_url or filename:
                header_parts = []
                if filename:
                    header_parts.append(f"[FILE: {filename}]")
                if download_url:
                    header_parts.append(f"[DOWNLOAD: {download_url}]")
                if source_type:
                    header_parts.append(f"[SOURCE: {source_type}]")
                doc_text = " ".join(header_parts) + "\n\n" + doc_text
            
            high_priority_text.append(doc_text)
        
        high_priority_full = "\n\n".join(high_priority_text)
        remaining_chars = max_chars - len(high_priority_full)
        
        if remaining_chars <= 0:
            # Even high-priority is too long, need full compression
            return self._full_compress(high_priority + low_priority, max_chars, metadata_info)
        
        # Compress low-priority documents
        if low_priority:
            low_priority_text = "\n\n".join([doc.page_content for doc, _ in low_priority])
            
            if len(low_priority_text) > remaining_chars:
                # Need to compress low-priority
                prompt = f"""
You are compressing context for a RAG chatbot.

Summarize the following documentation into a concise but complete set of notes.
CRITICAL: Preserve all:
- Download links and URLs
- File names and document titles
- Step-by-step instructions
- Numbers, dates, and specific values
- Names of people, products, or services

Text to compress:
\"\"\"
{low_priority_text[:remaining_chars * 2]}
\"\"\"

Compressed summary (max {remaining_chars} characters):"""
                
                try:
                    resp = self.llm.invoke(prompt)
                    compressed_low = resp.content.strip()
                except Exception as e:
                    print(f"[WARN] Low-priority compression failed: {e}")
                    # Fallback: truncate
                    compressed_low = low_priority_text[:remaining_chars] + "..."
            else:
                compressed_low = low_priority_text
            
            return high_priority_full + "\n\n" + compressed_low
        else:
            return high_priority_full
    
    def _iterative_compress(self, text: str, max_chars: int) -> str:
        """Iteratively compress text if still too long."""
        if len(text) <= max_chars:
            return text
        
        # First pass compression
        prompt = f"""
You are compressing context for a RAG chatbot.

Summarize the following documentation into a concise but complete set of notes.
CRITICAL: Preserve all:
- Download links and URLs (keep full URLs)
- File names and document titles
- Step-by-step instructions
- Numbers, dates, and specific values
- Names of people, products, or services

Text:
\"\"\"
{text[:max_chars * 3]}
\"\"\"

Compressed summary (max {max_chars} characters):"""
        
        try:
            resp = self.llm.invoke(prompt)
            compressed = resp.content.strip()
            
            # If still too long, truncate (shouldn't happen, but safety)
            if len(compressed) > max_chars:
                compressed = compressed[:max_chars] + "..."
            
            return compressed
        except Exception as e:
            print(f"[WARN] Iterative compression failed: {e}")
            # Fallback: truncate
            return text[:max_chars] + "..."
    
    def _full_compress(
        self,
        all_docs: List[Tuple[Document, float]],
        max_chars: int,
        metadata_info: List[Dict]
    ) -> str:
        """Full compression when even high-priority is too long."""
        # Extract all text
        full_text = "\n\n".join([doc.page_content for doc, _ in all_docs])
        
        # Build metadata summary
        metadata_summary = []
        for meta in metadata_info:
            if meta.get('download_url'):
                metadata_summary.append(f"[DOWNLOAD: {meta['download_url']}]")
            if meta.get('filename'):
                metadata_summary.append(f"[FILE: {meta['filename']}]")
        
        metadata_text = "\n".join(metadata_summary)
        metadata_chars = len(metadata_text)
        remaining_chars = max_chars - metadata_chars - 100  # Reserve space for metadata
        
        # Compress main content
        prompt = f"""
You are compressing context for a RAG chatbot.

Summarize the following documentation into a concise but complete set of notes.
CRITICAL: Preserve all:
- Step-by-step instructions
- Numbers, dates, and specific values
- Names of people, products, or services
- Important technical details

Text:
\"\"\"
{full_text[:remaining_chars * 3]}
\"\"\"

Compressed summary (max {remaining_chars} characters):"""
        
        try:
            resp = self.llm.invoke(prompt)
            compressed = resp.content.strip()
            
            # Combine with metadata
            if metadata_text:
                return metadata_text + "\n\n" + compressed
            else:
                return compressed
        except Exception as e:
            print(f"[WARN] Full compression failed: {e}")
            # Fallback: truncate with metadata
            if metadata_text:
                return metadata_text + "\n\n" + full_text[:remaining_chars] + "..."
            else:
                return full_text[:max_chars] + "..."
