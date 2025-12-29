"""
Fallback & Recovery Mechanisms - Multi-tier fallback system for retrieval failures.

Provides fallback strategies when initial retrieval fails or has low confidence:
- Tier 1: Query expansion with validation
- Tier 2: Query rephrasing
- Tier 3: Pure semantic search (if BM25 fails)
- Tier 4: Pure BM25 search (if dense fails)
- Tier 5: Clarifying questions
"""

from typing import List, Tuple, Optional, Dict
from langchain_core.documents import Document
from app.llm_factory import get_llm
from config import ENABLE_FALLBACK_STRATEGIES, MAX_FALLBACK_ATTEMPTS

# Import these lazily to avoid circular dependency
def _get_retrieval_components():
    """Lazy import to avoid circular dependency."""
    from app.endpoints import perplexity_style_retrieve
    from app.vectorstore import vectorstore, bm25_retriever
    return perplexity_style_retrieve, vectorstore, bm25_retriever


class FallbackStrategy:
    """
    Multi-tier fallback system for retrieval failures.
    """
    
    def __init__(self):
        """Initialize fallback strategy handler."""
        self.llm = get_llm(temperature=0.3, max_tokens=200)
        self.attempts = 0
    
    def execute_fallback(
        self,
        query: str,
        original_results: List[Tuple[Document, float]],
        confidence_score: float,
        query_type: str,
        tier: int = 1
    ) -> Tuple[List[Tuple[Document, float]], str]:
        """
        Execute fallback strategy based on tier.
        
        Args:
            query: Original user query
            original_results: Results from initial retrieval attempt
            confidence_score: Confidence score from retrieval
            query_type: Query type from classifier
            tier: Fallback tier (1-5)
            
        Returns:
            Tuple of (new_results, strategy_used)
        """
        if not ENABLE_FALLBACK_STRATEGIES:
            return original_results, "no_fallback"
        
        if self.attempts >= MAX_FALLBACK_ATTEMPTS:
            return original_results, "max_attempts_reached"
        
        self.attempts += 1
        
        if tier == 1:
            return self._tier1_query_expansion(query, original_results, query_type)
        elif tier == 2:
            return self._tier2_query_rephrasing(query, original_results)
        elif tier == 3:
            return self._tier3_pure_semantic(query, original_results)
        elif tier == 4:
            return self._tier4_pure_bm25(query, original_results)
        elif tier == 5:
            return self._tier5_clarifying_questions(query, original_results)
        else:
            return original_results, "unknown_tier"
    
    def _tier1_query_expansion(
        self,
        query: str,
        original_results: List[Tuple[Document, float]],
        query_type: str
    ) -> Tuple[List[Tuple[Document, float]], str]:
        """Tier 1: Query expansion with validation."""
        try:
            from query_expander import query_expander
            
            # Use adaptive expansion based on query type
            if query_type == 'simple_factual':
                n = 2
            elif query_type == 'complex_multi_part':
                n = 5
            else:
                n = 3
            
            expansions = query_expander.expand(query, n=n)
            
            if not expansions:
                return original_results, "expansion_failed"
            
            print(f"[FALLBACK_TIER1] Expanding query with {len(expansions)} variations")
            
            # Get retrieval components
            perplexity_style_retrieve, _, _ = _get_retrieval_components()
            
            # Try retrieval with expanded queries
            expanded_results = []
            for expanded_query in expansions[:3]:  # Limit to 3 expansions
                try:
                    results = perplexity_style_retrieve(
                        query=expanded_query,
                        k_dense=40,
                        k_bm25=40,
                        k_final=8,
                        use_expansion=False  # Don't expand the expansion
                    )
                    expanded_results.extend(results)
                except Exception as e:
                    print(f"[WARN] Fallback retrieval failed for expansion: {e}")
            
            # Merge with original results
            if expanded_results:
                merged = self._merge_results(original_results, expanded_results)
                return merged, "query_expansion"
            else:
                return original_results, "expansion_no_results"
                
        except Exception as e:
            print(f"[WARN] Tier 1 fallback failed: {e}")
            return original_results, "expansion_error"
    
    def _tier2_query_rephrasing(
        self,
        query: str,
        original_results: List[Tuple[Document, float]]
    ) -> Tuple[List[Tuple[Document, float]], str]:
        """Tier 2: Query rephrasing."""
        try:
            prompt = f"""Rephrase this query in a different way that might find better results.
Keep the same intent and meaning, but use different words or structure.

Original query: "{query}"

Provide a single rephrased version:"""
            
            response = self.llm.invoke(prompt)
            rephrased = response.content.strip()
            
            # Remove quotes if present
            if rephrased.startswith('"') and rephrased.endswith('"'):
                rephrased = rephrased[1:-1]
            
            print(f"[FALLBACK_TIER2] Rephrased query: {rephrased}")
            
            # Get retrieval components
            perplexity_style_retrieve, _, _ = _get_retrieval_components()
            
            # Try retrieval with rephrased query
            try:
                results = perplexity_style_retrieve(
                    query=rephrased,
                    k_dense=40,
                    k_bm25=40,
                    k_final=8,
                    use_expansion=False
                )
                
                if results:
                    merged = self._merge_results(original_results, results)
                    return merged, "query_rephrasing"
                else:
                    return original_results, "rephrasing_no_results"
            except Exception as e:
                print(f"[WARN] Rephrased query retrieval failed: {e}")
                return original_results, "rephrasing_error"
                
        except Exception as e:
            print(f"[WARN] Tier 2 fallback failed: {e}")
            return original_results, "rephrasing_error"
    
    def _tier3_pure_semantic(
        self,
        query: str,
        original_results: List[Tuple[Document, float]]
    ) -> Tuple[List[Tuple[Document, float]], str]:
        """Tier 3: Pure semantic search (if BM25 failed)."""
        try:
            _, vectorstore, _ = _get_retrieval_components()
            if not vectorstore:
                return original_results, "no_vectorstore"
            
            print(f"[FALLBACK_TIER3] Trying pure semantic search")
            
            # Pure dense retrieval only
            results = vectorstore.similarity_search_with_score(query, k=40)
            
            if results:
                # Convert to (doc, score) format, normalize scores
                doc_results = [(doc, float(1.0 - dist)) for doc, dist in results]  # Convert distance to similarity
                merged = self._merge_results(original_results, doc_results)
                return merged, "pure_semantic"
            else:
                return original_results, "semantic_no_results"
                
        except Exception as e:
            print(f"[WARN] Tier 3 fallback failed: {e}")
            return original_results, "semantic_error"
    
    def _tier4_pure_bm25(
        self,
        query: str,
        original_results: List[Tuple[Document, float]]
    ) -> Tuple[List[Tuple[Document, float]], str]:
        """Tier 4: Pure BM25 search (if dense failed)."""
        try:
            _, _, bm25_retriever = _get_retrieval_components()
            if not bm25_retriever:
                return original_results, "no_bm25"
            
            print(f"[FALLBACK_TIER4] Trying pure BM25 search")
            
            # Pure BM25 retrieval only
            results = bm25_retriever.search(query, k=40)
            
            if results:
                merged = self._merge_results(original_results, results)
                return merged, "pure_bm25"
            else:
                return original_results, "bm25_no_results"
                
        except Exception as e:
            print(f"[WARN] Tier 4 fallback failed: {e}")
            return original_results, "bm25_error"
    
    def _tier5_clarifying_questions(
        self,
        query: str,
        original_results: List[Tuple[Document, float]]
    ) -> Tuple[List[Tuple[Document, float]], str]:
        """Tier 5: Generate clarifying questions (no retrieval, just return empty)."""
        # This tier doesn't do retrieval, it's meant to be handled by the endpoint
        # to ask the user for clarification
        print(f"[FALLBACK_TIER5] All retrieval strategies exhausted, should ask clarifying questions")
        return original_results, "clarifying_questions"
    
    def _merge_results(
        self,
        results1: List[Tuple[Document, float]],
        results2: List[Tuple[Document, float]]
    ) -> List[Tuple[Document, float]]:
        """Merge two result lists, deduplicating and keeping best scores."""
        seen = {}
        
        # Add results1
        for doc, score in results1:
            key = (doc.page_content[:120], doc.metadata.get("source_type", ""), doc.metadata.get("page_url", ""))
            if key not in seen or score > seen[key][1]:
                seen[key] = (doc, score)
        
        # Add results2
        for doc, score in results2:
            key = (doc.page_content[:120], doc.metadata.get("source_type", ""), doc.metadata.get("page_url", ""))
            if key not in seen or score > seen[key][1]:
                seen[key] = (doc, score)
        
        # Sort and return
        merged = list(seen.values())
        merged.sort(key=lambda x: x[1], reverse=True)
        return merged[:15]  # Limit to top 15
    
    def generate_clarifying_questions(self, query: str) -> List[str]:
        """
        Generate clarifying questions when all retrieval strategies fail.
        
        Args:
            query: Original user query
            
        Returns:
            List of clarifying questions
        """
        try:
            prompt = f"""The user asked: "{query}"

I couldn't find relevant information. Generate 2-3 clarifying questions to help understand what they're looking for.

Return ONLY the questions, each on a new line, no numbering."""
            
            response = self.llm.invoke(prompt)
            questions = [
                q.strip() for q in response.content.strip().split('\n')
                if q.strip() and not q.strip().startswith(('1.', '2.', '3.', '-', '*'))
            ]
            
            return questions[:3]  # Limit to 3 questions
            
        except Exception as e:
            print(f"[WARN] Failed to generate clarifying questions: {e}")
            return [
                "Could you provide more details about what you're looking for?",
                "Is there a specific document or topic you need help with?"
            ]


# Global instance
_fallback_strategy: Optional[FallbackStrategy] = None


def get_fallback_strategy() -> FallbackStrategy:
    """Get or create global fallback strategy instance."""
    global _fallback_strategy
    if _fallback_strategy is None:
        _fallback_strategy = FallbackStrategy()
    return _fallback_strategy

