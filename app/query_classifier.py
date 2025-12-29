"""
Query Classifier - Classify user queries into types for adaptive retrieval.

Classifies queries into:
- simple_factual: Simple questions requiring 1-2 documents
- complex_multi_part: Complex questions requiring multiple documents or sub-queries
- specific_document: Queries looking for specific files/documents
- conversational: Follow-up questions or conversational queries
"""

from typing import Dict, Optional, Tuple
from app.llm_factory import get_llm
import hashlib
import json
from datetime import datetime, timedelta

# Simple in-memory cache (can be upgraded to Redis later)
_query_cache: Dict[str, Tuple[Dict, datetime]] = {}


class QueryClassifier:
    """
    Classify user queries to determine optimal retrieval strategy.
    """
    
    def __init__(self, model_name: Optional[str] = None):
        """Initialize query classifier with LLM."""
        self.llm = get_llm(
            model_name=model_name,
            temperature=0.1,  # Low temperature for consistent classification
            max_tokens=200
        )
    
    def classify(self, query: str, conversation_history: Optional[list] = None) -> Dict:
        """
        Classify a query into one of four types with confidence score.
        
        Args:
            query: User query string
            conversation_history: Optional list of previous messages for context
            
        Returns:
            Dictionary with:
                - query_type: 'simple_factual', 'complex_multi_part', 'specific_document', or 'conversational'
                - confidence: float 0-1
                - complexity: 'low', 'medium', 'high'
                - sub_questions: List of sub-questions if complex
                - required_doc_types: List of document types needed
        """
        # Check cache first
        cache_key = self._get_cache_key(query, conversation_history)
        if cache_key in _query_cache:
            cached_result, expiry = _query_cache[cache_key]
            if datetime.now() < expiry:
                print(f"[QUERY_CLASSIFIER] Cache hit for query: {query[:50]}...")
                return cached_result
        
        # Build context from conversation history
        context = ""
        if conversation_history:
            recent_messages = conversation_history[-3:]  # Last 3 messages for context
            context = "\n".join([f"Previous: {msg}" for msg in recent_messages])
        
        # Build context section separately to avoid f-string backslash issue
        context_section = ""
        if context:
            context_section = f"Context from conversation:\n{context}\n\n"
        
        # Create classification prompt
        prompt = f"""You are a query classifier for a RAG system. Classify the user query into one of these types:

1. **simple_factual**: Simple, direct questions that can be answered with 1-2 documents
   - Examples: "What is CloudFuze?", "How do I migrate Slack to Teams?"
   - Usually short, single question, clear intent

2. **complex_multi_part**: Complex questions requiring multiple documents or sub-questions
   - Examples: "How do I migrate Slack channels to Teams while preserving permissions and maintaining user access?"
   - Usually contains multiple parts, requires synthesis from multiple sources

3. **specific_document**: Queries looking for a specific file, document, or resource
   - Examples: "Download SOC 2 certificate", "Show me the pricing document", "Where is the migration guide?"
   - Usually mentions specific document names, certificates, downloads, or files

4. **conversational**: Follow-up questions, clarifications, or conversational queries
   - Examples: "Tell me more about that", "What about security?", "Can you explain further?", "How does it work?", "What are the features?"
   - Usually short, refers to previous context, uses pronouns like "it", "that", "this", or is a continuation of a previous topic
   - Often vague without context from previous messages

{context_section}Query: "{query}"

Respond in JSON format:
{{
    "query_type": "one of: simple_factual, complex_multi_part, specific_document, conversational",
    "confidence": 0.0-1.0,
    "complexity": "low, medium, or high",
    "sub_questions": ["list of sub-questions if complex_multi_part, else empty list"],
    "required_doc_types": ["list of document types needed: sharepoint, blog, email, pdf, etc."]
}}"""
        
        try:
            response = self.llm.invoke(prompt)
            result_text = response.content.strip()
            
            # Try to parse JSON response
            # Remove markdown code blocks if present
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
                result_text = result_text.strip()
            
            result = json.loads(result_text)
            
            # Validate result
            valid_types = ['simple_factual', 'complex_multi_part', 'specific_document', 'conversational']
            if result.get('query_type') not in valid_types:
                print(f"[WARN] Invalid query type: {result.get('query_type')}, defaulting to simple_factual")
                result['query_type'] = 'simple_factual'
            
            # Ensure all required fields
            result.setdefault('confidence', 0.7)
            result.setdefault('complexity', 'medium')
            result.setdefault('sub_questions', [])
            result.setdefault('required_doc_types', [])
            
            # Cache result
            from config import QUERY_CLASSIFIER_CACHE_TTL
            expiry = datetime.now() + timedelta(seconds=QUERY_CLASSIFIER_CACHE_TTL)
            _query_cache[cache_key] = (result, expiry)
            
            # Clean old cache entries (simple cleanup)
            self._clean_cache()
            
            print(f"[QUERY_CLASSIFIER] Classified as: {result['query_type']} (confidence: {result['confidence']:.2f})")
            return result
            
        except json.JSONDecodeError as e:
            print(f"[WARN] Failed to parse classification JSON: {e}")
            print(f"[WARN] Response was: {result_text[:200]}")
            # Fallback to simple_factual
            return {
                'query_type': 'simple_factual',
                'confidence': 0.5,
                'complexity': 'medium',
                'sub_questions': [],
                'required_doc_types': []
            }
        except Exception as e:
            print(f"[ERROR] Query classification failed: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to simple_factual
            return {
                'query_type': 'simple_factual',
                'confidence': 0.5,
                'complexity': 'medium',
                'sub_questions': [],
                'required_doc_types': []
            }
    
    def _get_cache_key(self, query: str, conversation_history: Optional[list] = None) -> str:
        """Generate cache key for query."""
        key_data = query.lower().strip()
        if conversation_history:
            key_data += "|" + "|".join([str(msg).lower() for msg in conversation_history[-2:]])
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def _clean_cache(self, max_size: int = 1000):
        """Clean old cache entries if cache gets too large."""
        global _query_cache
        if len(_query_cache) > max_size:
            # Remove expired entries
            now = datetime.now()
            _query_cache = {
                k: v for k, v in _query_cache.items()
                if v[1] > now
            }
            # If still too large, remove oldest 20%
            if len(_query_cache) > max_size:
                sorted_items = sorted(_query_cache.items(), key=lambda x: x[1][1])
                _query_cache = dict(sorted_items[-int(max_size * 0.8):])


# Global instance
_query_classifier: Optional[QueryClassifier] = None


def get_query_classifier() -> QueryClassifier:
    """Get or create global query classifier instance."""
    global _query_classifier
    if _query_classifier is None:
        _query_classifier = QueryClassifier()
    return _query_classifier

