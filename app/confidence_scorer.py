"""
Confidence Scoring System - Detect retrieval failures and response quality.

Provides confidence scores for:
1. Retrieval quality - detects when retrieval fails or is low quality
2. Response quality - self-critique to detect hallucinations and gaps
"""

from typing import List, Tuple, Dict, Optional
from langchain_core.documents import Document
from app.llm_factory import get_llm
from config import MIN_RETRIEVAL_CONFIDENCE, MIN_RESPONSE_CONFIDENCE
import numpy as np


class RetrievalConfidenceScorer:
    """
    Score confidence in retrieval results.
    """
    
    def __init__(self):
        """Initialize retrieval confidence scorer."""
        pass
    
    def score(
        self,
        query: str,
        doc_results: List[Tuple[Document, float]],
        query_type: Optional[str] = None
    ) -> Dict:
        """
        Calculate confidence score for retrieval results.
        
        Args:
            query: Original user query
            doc_results: List of (doc, score) tuples from retrieval
            query_type: Optional query type from classifier
            
        Returns:
            Dictionary with:
                - confidence: float 0-1
                - is_low_confidence: bool
                - reasons: List of reasons for low confidence
                - score_stats: Statistics about scores
        """
        if not doc_results:
            return {
                'confidence': 0.0,
                'is_low_confidence': True,
                'reasons': ['No documents retrieved'],
                'score_stats': {}
            }
        
        scores = [score for _, score in doc_results]
        
        # Calculate statistics
        max_score = max(scores)
        avg_score = np.mean(scores)
        min_score = min(scores)
        std_score = np.std(scores)
        score_range = max_score - min_score
        
        # Confidence factors
        confidence_factors = []
        
        # Factor 1: Maximum score quality
        if max_score < 0.0:
            confidence_factors.append(('low_max_score', 0.3))
        elif max_score < 0.3:
            confidence_factors.append(('moderate_max_score', 0.6))
        else:
            confidence_factors.append(('high_max_score', 1.0))
        
        # Factor 2: Score distribution (variance)
        if score_range < 0.1:
            # All scores are very similar - might be noise
            confidence_factors.append(('low_variance', 0.5))
        elif score_range > 0.5:
            # Good separation between top and bottom
            confidence_factors.append(('good_separation', 1.0))
        else:
            confidence_factors.append(('moderate_separation', 0.8))
        
        # Factor 3: Average score quality
        if avg_score < -0.5:
            confidence_factors.append(('low_avg_score', 0.4))
        elif avg_score < 0.0:
            confidence_factors.append(('moderate_avg_score', 0.7))
        else:
            confidence_factors.append(('good_avg_score', 1.0))
        
        # Factor 4: Number of results
        num_results = len(doc_results)
        if num_results < 3:
            confidence_factors.append(('few_results', 0.6))
        elif num_results >= 5:
            confidence_factors.append(('sufficient_results', 1.0))
        else:
            confidence_factors.append(('moderate_results', 0.8))
        
        # Calculate weighted confidence
        weights = [factor[1] for factor in confidence_factors]
        confidence = np.mean(weights)
        
        # Reasons for low confidence
        reasons = []
        if max_score < MIN_RETRIEVAL_CONFIDENCE:
            reasons.append(f'Maximum score ({max_score:.2f}) below threshold ({MIN_RETRIEVAL_CONFIDENCE})')
        if score_range < 0.1:
            reasons.append('Low score variance - results may be noisy')
        if avg_score < -0.3:
            reasons.append(f'Average score ({avg_score:.2f}) is very low')
        if num_results < 3:
            reasons.append(f'Only {num_results} results retrieved')
        
        is_low_confidence = confidence < MIN_RETRIEVAL_CONFIDENCE
        
        return {
            'confidence': float(confidence),
            'is_low_confidence': is_low_confidence,
            'reasons': reasons,
            'score_stats': {
                'max': float(max_score),
                'avg': float(avg_score),
                'min': float(min_score),
                'std': float(std_score),
                'range': float(score_range),
                'count': num_results
            }
        }


class ResponseConfidenceScorer:
    """
    Score confidence in LLM-generated responses using self-critique.
    """
    
    def __init__(self, model_name: Optional[str] = None):
        """Initialize response confidence scorer."""
        self.llm = get_llm(
            model_name=model_name,
            temperature=0.1,  # Low temperature for consistent critique
            max_tokens=300
        )
    
    def score(
        self,
        query: str,
        response: str,
        context_docs: List[Document],
        max_docs_to_check: int = 5
    ) -> Dict:
        """
        Score confidence in the generated response using self-critique.
        
        Args:
            query: Original user query
            response: Generated response from LLM
            context_docs: Documents used as context
            max_docs_to_check: Maximum number of docs to check against
            
        Returns:
            Dictionary with:
                - confidence: float 0-1
                - is_low_confidence: bool
                - is_supported: bool (answer is supported by context)
                - has_gaps: bool (information gaps detected)
                - has_hallucinations: bool (potential hallucinations)
                - critique: str (detailed critique)
        """
        if not context_docs:
            return {
                'confidence': 0.0,
                'is_low_confidence': True,
                'is_supported': False,
                'has_gaps': True,
                'has_hallucinations': False,
                'critique': 'No context documents provided'
            }
        
        # Get top documents for verification
        top_docs = context_docs[:max_docs_to_check]
        context_summary = "\n\n".join([
            f"Document {i+1}:\n{doc.page_content[:500]}..."
            for i, doc in enumerate(top_docs)
        ])
        
        prompt = f"""You are evaluating the quality of an AI assistant's response.

Query: "{query}"

Context provided to the assistant:
{context_summary}

Response from assistant:
"{response}"

Evaluate the response and answer these questions in JSON format:
{{
    "is_supported": true/false - Is the answer directly supported by the context?
    "has_gaps": true/false - Are there important information gaps?
    "has_hallucinations": true/false - Does the response contain information not in the context?
    "confidence": 0.0-1.0 - Overall confidence in the response quality
    "critique": "Brief explanation of your evaluation"
}}

Be strict: If the response contains specific facts, numbers, or claims not in the context, mark has_hallucinations as true.
If the response doesn't fully answer the query, mark has_gaps as true."""
        
        try:
            result = self.llm.invoke(prompt)
            result_text = result.content.strip()
            
            # Parse JSON response
            import json
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
                result_text = result_text.strip()
            
            evaluation = json.loads(result_text)
            
            confidence = float(evaluation.get('confidence', 0.5))
            is_supported = evaluation.get('is_supported', False)
            has_gaps = evaluation.get('has_gaps', False)
            has_hallucinations = evaluation.get('has_hallucinations', False)
            critique = evaluation.get('critique', 'No critique provided')
            
            is_low_confidence = confidence < MIN_RESPONSE_CONFIDENCE or has_hallucinations
            
            return {
                'confidence': confidence,
                'is_low_confidence': is_low_confidence,
                'is_supported': is_supported,
                'has_gaps': has_gaps,
                'has_hallucinations': has_hallucinations,
                'critique': critique
            }
            
        except Exception as e:
            print(f"[WARN] Response confidence scoring failed: {e}")
            import traceback
            traceback.print_exc()
            # Fallback: assume moderate confidence
            return {
                'confidence': 0.6,
                'is_low_confidence': False,
                'is_supported': True,
                'has_gaps': False,
                'has_hallucinations': False,
                'critique': 'Could not evaluate response quality'
            }


# Global instances
_retrieval_scorer: Optional[RetrievalConfidenceScorer] = None
_response_scorer: Optional[ResponseConfidenceScorer] = None


def get_retrieval_scorer() -> RetrievalConfidenceScorer:
    """Get or create global retrieval confidence scorer."""
    global _retrieval_scorer
    if _retrieval_scorer is None:
        _retrieval_scorer = RetrievalConfidenceScorer()
    return _retrieval_scorer


def get_response_scorer() -> ResponseConfidenceScorer:
    """Get or create global response confidence scorer."""
    global _response_scorer
    if _response_scorer is None:
        _response_scorer = ResponseConfidenceScorer()
    return _response_scorer

