"""
Multi-Hop Reasoning - Answer complex queries requiring multiple document synthesis.

Handles:
- Query decomposition into sub-questions
- Iterative retrieval for each sub-query
- Synthesis of information from multiple unrelated documents
- Comparative queries
- Contextual queries requiring multiple steps
"""

from typing import List, Tuple, Dict, Optional
from langchain_core.documents import Document
from app.llm_factory import get_llm
# Lazy import to avoid circular dependency
def _get_perplexity_retrieve():
    from app.endpoints import perplexity_style_retrieve
    return perplexity_style_retrieve
from app.adaptive_retrieval import get_adaptive_k_values


class MultiHopReasoner:
    """
    Multi-hop reasoning for complex queries.
    """
    
    def __init__(self, model_name: Optional[str] = None):
        """Initialize multi-hop reasoner."""
        self.llm = get_llm(
            model_name=model_name,
            temperature=0.1,
            max_tokens=500
        )
    
    def reason(
        self,
        query: str,
        query_type: str,
        complexity: str,
        initial_results: List[Tuple[Document, float]]
    ) -> Tuple[List[Tuple[Document, float]], Dict]:
        """
        Perform multi-hop reasoning for complex queries.
        
        Args:
            query: Original user query
            query_type: Query type from classifier
            complexity: Query complexity
            initial_results: Initial retrieval results
            
        Returns:
            Tuple of (enhanced_results, reasoning_info)
        """
        if query_type != 'complex_multi_part':
            # Only apply multi-hop reasoning to complex queries
            return initial_results, {'applied': False, 'reason': 'not_complex_query'}
        
        # Step 1: Decompose query into sub-questions
        sub_questions = self._decompose_query(query)
        
        if not sub_questions or len(sub_questions) <= 1:
            # No decomposition needed or failed
            return initial_results, {'applied': False, 'reason': 'no_decomposition'}
        
        print(f"[MULTI_HOP] Decomposed into {len(sub_questions)} sub-questions")
        
        # Step 2: Retrieve for each sub-question
        all_results = list(initial_results)
        seen_docs = set()
        
        for i, sub_q in enumerate(sub_questions):
            print(f"[MULTI_HOP] Retrieving for sub-question {i+1}: {sub_q[:60]}...")
            
            # Get adaptive k values for sub-query
            k_values = get_adaptive_k_values('complex_multi_part', complexity)
            
            try:
                perplexity_style_retrieve = _get_perplexity_retrieve()
                sub_results = perplexity_style_retrieve(
                    query=sub_q,
                    k_dense=k_values['k_dense'],
                    k_bm25=k_values['k_bm25'],
                    k_final=k_values['k_final'],
                    use_expansion=True
                )
                
                # Add new documents (deduplicate)
                for doc, score in sub_results:
                    doc_key = (doc.page_content[:120], doc.metadata.get("source_type", ""), doc.metadata.get("page_url", ""))
                    if doc_key not in seen_docs:
                        seen_docs.add(doc_key)
                        all_results.append((doc, score))
                        
            except Exception as e:
                print(f"[WARN] Multi-hop retrieval failed for sub-question: {e}")
                continue
        
        # Step 3: Merge and deduplicate results
        merged_results = self._merge_results(all_results)
        
        # Step 4: Re-rank merged results
        if merged_results:
            # Re-rank using original query
            try:
                from reranker import CrossEncoderReranker
                reranker = CrossEncoderReranker()
                reranked = reranker.rerank(
                    query=query,
                    candidates=merged_results,
                    top_k=min(20, len(merged_results))
                )
            except Exception as e:
                print(f"[WARN] Failed to rerank in multi-hop reasoning: {e}")
                # Fallback: just sort by score
                reranked = sorted(merged_results, key=lambda x: x[1], reverse=True)[:20]
        else:
            reranked = initial_results
        
        return reranked, {
            'applied': True,
            'sub_questions': sub_questions,
            'initial_count': len(initial_results),
            'final_count': len(reranked)
        }
    
    def _decompose_query(self, query: str) -> List[str]:
        """
        Decompose complex query into sub-questions.
        
        Args:
            query: Original complex query
            
        Returns:
            List of sub-questions
        """
        prompt = f"""You are analyzing a complex query that may require information from multiple sources.

Query: "{query}"

Break this query down into 2-4 sub-questions that need to be answered separately.
Each sub-question should be:
- Specific and answerable
- Focused on one aspect of the original query
- Clear and unambiguous

Return ONLY the sub-questions, each on a new line, no numbering, no bullets."""
        
        try:
            response = self.llm.invoke(prompt)
            text = response.content.strip()
            
            # Parse sub-questions
            sub_questions = []
            for line in text.splitlines():
                line = line.strip()
                # Remove common prefixes
                line = line.lstrip("0123456789.-*• ").strip()
                if line and len(line) > 10:  # Filter out very short lines
                    sub_questions.append(line)
            
            # If decomposition failed or produced too many, return original as single question
            if not sub_questions or len(sub_questions) > 5:
                return [query]
            
            return sub_questions[:4]  # Limit to 4 sub-questions
            
        except Exception as e:
            print(f"[WARN] Query decomposition failed: {e}")
            return [query]  # Fallback to original query
    
    def _merge_results(
        self,
        results: List[Tuple[Document, float]]
    ) -> List[Tuple[Document, float]]:
        """Merge and deduplicate results, keeping best scores."""
        seen = {}
        
        for doc, score in results:
            key = (doc.page_content[:120], doc.metadata.get("source_type", ""), doc.metadata.get("page_url", ""))
            if key not in seen or score > seen[key][1]:
                seen[key] = (doc, score)
        
        merged = list(seen.values())
        merged.sort(key=lambda x: x[1], reverse=True)
        return merged
    
    def synthesize_answer(
        self,
        query: str,
        documents: List[Document],
        sub_questions: List[str]
    ) -> str:
        """
        Synthesize answer from multiple documents for complex query.
        
        This is called after retrieval to help the LLM synthesize information.
        
        Args:
            query: Original query
            documents: Retrieved documents
            sub_questions: Sub-questions that were answered
            
        Returns:
            Synthesis guidance for the LLM
        """
        if not documents:
            return ""
        
        # Create synthesis prompt
        doc_summaries = []
        for i, doc in enumerate(documents[:10]):  # Limit to top 10
            meta = doc.metadata or {}
            title = meta.get("title") or meta.get("post_title") or meta.get("filename", "Document")
            summary = f"Document {i+1} ({title}): {doc.page_content[:300]}..."
            doc_summaries.append(summary)
        
        synthesis_guidance = f"""
The user asked: "{query}"

This query was broken down into these sub-questions:
{chr(10).join(f"- {q}" for q in sub_questions)}

The following documents were retrieved to answer different aspects:
{chr(10).join(doc_summaries)}

When answering, synthesize information from multiple documents to provide a comprehensive answer.
"""
        
        return synthesis_guidance


# Global instance
_multi_hop_reasoner: Optional[MultiHopReasoner] = None


def get_multi_hop_reasoner() -> MultiHopReasoner:
    """Get or create global multi-hop reasoner instance."""
    global _multi_hop_reasoner
    if _multi_hop_reasoner is None:
        _multi_hop_reasoner = MultiHopReasoner()
    return _multi_hop_reasoner

