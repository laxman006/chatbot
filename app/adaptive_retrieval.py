"""
Adaptive Retrieval System - Dynamic k values based on query type and complexity.

Provides adaptive retrieval strategies for different query types:
- Simple factual: Lower k values (3-5 documents)
- Complex multi-part: Higher k values (10-15 documents)
- Specific document: Metadata-first search with moderate k (5-8)
- Conversational: Standard k values (6-8)
"""

from typing import Dict, List, Tuple, Optional
from langchain_core.documents import Document
# Removed query_classifier import to avoid circular dependency - not needed here
from config import (
    ENABLE_ADAPTIVE_RETRIEVAL,
    SIMPLE_QUERY_K_DENSE, SIMPLE_QUERY_K_BM25, SIMPLE_QUERY_K_FINAL,
    COMPLEX_QUERY_K_DENSE, COMPLEX_QUERY_K_BM25, COMPLEX_QUERY_K_FINAL,
    DOCUMENT_QUERY_K_DENSE, DOCUMENT_QUERY_K_BM25, DOCUMENT_QUERY_K_FINAL,
    CONVERSATIONAL_QUERY_K_DENSE, CONVERSATIONAL_QUERY_K_BM25, CONVERSATIONAL_QUERY_K_FINAL,
    DENSE_RETRIEVAL_K, BM25_RETRIEVAL_K, FINAL_RETRIEVAL_K
)


def get_adaptive_k_values(query_type: str, complexity: str = "medium") -> Dict[str, int]:
    """
    Get adaptive k values based on query type and complexity.
    
    Args:
        query_type: One of 'simple_factual', 'complex_multi_part', 'specific_document', 'conversational'
        complexity: 'low', 'medium', or 'high'
        
    Returns:
        Dictionary with k_dense, k_bm25, k_final values
    """
    if not ENABLE_ADAPTIVE_RETRIEVAL:
        # Fallback to default values
        return {
            'k_dense': DENSE_RETRIEVAL_K,
            'k_bm25': BM25_RETRIEVAL_K,
            'k_final': FINAL_RETRIEVAL_K
        }
    
    # Adjust k_final based on complexity
    complexity_multiplier = {
        'low': 0.8,
        'medium': 1.0,
        'high': 1.2
    }
    mult = complexity_multiplier.get(complexity, 1.0)
    
    if query_type == 'simple_factual':
        k_final = max(3, int(SIMPLE_QUERY_K_FINAL * mult))
        return {
            'k_dense': SIMPLE_QUERY_K_DENSE,
            'k_bm25': SIMPLE_QUERY_K_BM25,
            'k_final': k_final
        }
    elif query_type == 'complex_multi_part':
        k_final = max(10, int(COMPLEX_QUERY_K_FINAL * mult))
        return {
            'k_dense': COMPLEX_QUERY_K_DENSE,
            'k_bm25': COMPLEX_QUERY_K_BM25,
            'k_final': k_final
        }
    elif query_type == 'specific_document':
        k_final = max(5, int(DOCUMENT_QUERY_K_FINAL * mult))
        return {
            'k_dense': DOCUMENT_QUERY_K_DENSE,
            'k_bm25': DOCUMENT_QUERY_K_BM25,
            'k_final': k_final
        }
    else:  # conversational
        k_final = max(6, int(CONVERSATIONAL_QUERY_K_FINAL * mult))
        return {
            'k_dense': CONVERSATIONAL_QUERY_K_DENSE,
            'k_bm25': CONVERSATIONAL_QUERY_K_BM25,
            'k_final': k_final
        }


def apply_metadata_boost(
    candidates: List[Tuple[Document, float]],
    query: str,
    query_type: str
) -> List[Tuple[Document, float]]:
    """
    Apply metadata-based boosting for specific document queries.
    
    For specific_document queries, prioritize exact filename/title matches.
    
    Args:
        candidates: List of (doc, score) tuples
        query: Original query string
        query_type: Query type from classifier
        
    Returns:
        List of (doc, score) tuples with metadata boosts applied
    """
    if query_type != 'specific_document':
        return candidates
    
    query_lower = query.lower()
    boosted = []
    
    for doc, score in candidates:
        meta = doc.metadata or {}
        
        # Check for exact matches in metadata
        filename = (meta.get("filename") or "").lower()
        title = (meta.get("title") or meta.get("post_title") or "").lower()
        
        # Strong boost for exact filename match
        if query_lower in filename or filename in query_lower:
            score += 0.3
        # Medium boost for title match
        elif query_lower in title or title in query_lower:
            score += 0.2
        # Small boost for partial matches
        elif any(word in filename or word in title for word in query_lower.split() if len(word) > 3):
            score += 0.1
        
        boosted.append((doc, score))
    
    # Re-sort by score
    boosted.sort(key=lambda x: x[1], reverse=True)
    return boosted


def metadata_first_search(
    query: str,
    vectorstore,
    bm25_retriever,
    k_dense: int,
    k_bm25: int,
    k_final: int
) -> List[Tuple[Document, float]]:
    """
    Perform metadata-first search for specific document queries.
    
    Prioritizes exact filename/title matches before content search.
    
    Args:
        query: User query
        vectorstore: ChromaDB vectorstore
        bm25_retriever: BM25 retriever instance
        k_dense: Number of dense retrieval results
        k_bm25: Number of BM25 results
        k_final: Final number of results
        
    Returns:
        List of (doc, score) tuples
    """
    # Lazy import to avoid circular dependency
    from app.endpoints import perplexity_style_retrieve
    
    # First, try metadata search via BM25 (which indexes metadata)
    metadata_results = []
    if bm25_retriever:
        try:
            metadata_results = bm25_retriever.search(query, k=k_bm25 * 2)
            # Filter for strong metadata matches
            query_lower = query.lower()
            strong_matches = []
            for doc, score in metadata_results:
                meta = doc.metadata or {}
                filename = (meta.get("filename") or "").lower()
                title = (meta.get("title") or meta.get("post_title") or "").lower()
                
                # Check for strong matches
                if (query_lower in filename or filename in query_lower or
                    query_lower in title or title in query_lower):
                    strong_matches.append((doc, score * 1.5))  # Boost metadata matches
            
            if strong_matches:
                print(f"[METADATA_SEARCH] Found {len(strong_matches)} strong metadata matches")
                # Combine with regular retrieval
                regular_results = perplexity_style_retrieve(
                    query=query,
                    k_dense=k_dense,
                    k_bm25=k_bm25,
                    k_final=k_final,
                    use_expansion=False  # Skip expansion for specific document queries
                )
                # Merge and deduplicate, prioritizing metadata matches
                return _merge_results(strong_matches, regular_results, k_final)
        except Exception as e:
            print(f"[WARN] Metadata-first search failed: {e}")
    
    # Fallback to regular retrieval
    return perplexity_style_retrieve(
        query=query,
        k_dense=k_dense,
        k_bm25=k_bm25,
        k_final=k_final,
        use_expansion=False
    )


def _merge_results(
    results1: List[Tuple[Document, float]],
    results2: List[Tuple[Document, float]],
    k: int
) -> List[Tuple[Document, float]]:
    """Merge two result lists, deduplicating and keeping top k."""
    seen = {}
    
    # Add results1 first (prioritized)
    for doc, score in results1:
        key = (doc.page_content[:120], doc.metadata.get("source_type", ""), doc.metadata.get("page_url", ""))
        if key not in seen or score > seen[key][1]:
            seen[key] = (doc, score)
    
    # Add results2
    for doc, score in results2:
        key = (doc.page_content[:120], doc.metadata.get("source_type", ""), doc.metadata.get("page_url", ""))
        if key not in seen or score > seen[key][1]:
            seen[key] = (doc, score)
    
    # Sort and return top k
    merged = list(seen.values())
    merged.sort(key=lambda x: x[1], reverse=True)
    return merged[:k]

