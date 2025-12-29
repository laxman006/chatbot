# query_expander.py
from typing import List, Optional, Dict, Tuple
from app.llm_factory import get_llm
from config import (
    QUERY_EXPANSION_CACHE_ENABLED,
    QUERY_EXPANSION_MIN_SIMILARITY
)
import hashlib
from datetime import datetime, timedelta

# Simple in-memory cache (can be upgraded to Redis later)
_expansion_cache: Dict[str, Tuple[List[str], datetime]] = {}

# Lazy-loaded sentence transformer for similarity checking
_similarity_model = None


def _get_similarity_model():
    """Lazy-load sentence transformer for similarity checking."""
    global _similarity_model
    if _similarity_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _similarity_model = SentenceTransformer('all-MiniLM-L6-v2')
            print("[OK] Loaded sentence transformer for query expansion validation")
        except Exception as e:
            print(f"[WARN] Could not load sentence transformer: {e}")
            _similarity_model = None
    return _similarity_model


class QueryExpander:
    """
    Enhanced LLM-based query expansion with caching, validation, and adaptive n values.
    
    Features:
    - Caching for identical/similar queries
    - Semantic similarity validation
    - Adaptive n based on query complexity
    - Quality filtering
    """
    
    def __init__(self, model_name: str = None):
        # Use factory function to get appropriate LLM based on configuration
        # model_name parameter is ignored when using factory function
        self.llm = get_llm(
            model_name=model_name,
            temperature=0.3
        )

    def expand(
        self,
        query: str,
        n: Optional[int] = None,
        query_type: Optional[str] = None,
        complexity: Optional[str] = None
    ) -> List[str]:
        """
        Expand query into semantically related rewrites with caching and validation.
        
        Args:
            query: Original query string
            n: Number of expansions (if None, determined adaptively)
            query_type: Query type from classifier (for adaptive n)
            complexity: Query complexity (for adaptive n)
        
        Returns:
            List of alternative query strings (deduped, validated, excluding original)
        """
        # Determine adaptive n if not provided
        if n is None:
            n = self._get_adaptive_n(query_type, complexity)
        
        # Skip expansion for specific document queries
        if query_type == 'specific_document':
            print(f"[QUERY_EXPANSION] Skipping expansion for specific_document query")
            return []
        
        # Check cache first
        if QUERY_EXPANSION_CACHE_ENABLED:
            cache_key = self._get_cache_key(query, n)
            if cache_key in _expansion_cache:
                cached_result, expiry = _expansion_cache[cache_key]
                if datetime.now() < expiry:
                    print(f"[QUERY_EXPANSION] Cache hit for query: {query[:50]}...")
                    return cached_result
        
        # Generate expansions
        expansions = self._generate_expansions(query, n)
        
        # Validate and filter expansions (pass query_type for adaptive thresholds)
        validated = self._validate_expansions(query, expansions, query_type=query_type)
        
        # Cache result
        if QUERY_EXPANSION_CACHE_ENABLED and validated:
            expiry = datetime.now() + timedelta(hours=24)  # 24 hour TTL
            cache_key = self._get_cache_key(query, n)
            _expansion_cache[cache_key] = (validated, expiry)
            self._clean_cache()
        
        return validated
    
    def _get_adaptive_n(self, query_type: Optional[str], complexity: Optional[str]) -> int:
        """Determine adaptive n based on query type and complexity."""
        if query_type == 'simple_factual':
            return 1
        elif query_type == 'complex_multi_part':
            if complexity == 'high':
                return 5
            else:
                return 3
        elif query_type == 'conversational':
            return 2
        else:
            return 3  # Default
    
    def _generate_expansions(self, query: str, n: int) -> List[str]:
        """Generate query expansions using LLM."""
        prompt = f"""You are helping a search system for technical documentation.

Given the user query below, generate {n} alternative ways of asking the same thing:
- Use different synonyms
- Use related technical terms
- Keep each variation short (max 15 words)
- Make sure variations are meaningfully different

Return ONLY the variations, each on a new line, no numbering, no bullets, no extra text.

Query: "{query}"

Variations:"""
        
        try:
            resp = self.llm.invoke(prompt)
            if not resp or not resp.content:
                print(f"[WARN] Query expansion returned empty response")
                return []
            
            text = resp.content.strip()
            if not text:
                print(f"[WARN] Query expansion returned empty content")
                return []
            
            # Parse newline-separated variations
            lines = []
            for line in text.splitlines():
                # Clean up common prefixes (1., -, *, etc.)
                line = line.strip()
                line = line.lstrip("0123456789.-*• ").strip()
                if line:
                    lines.append(line)
            
            # Dedup + remove exact original
            uniq = []
            query_lower = query.lower()
            for q in lines:
                if q and q.lower() != query_lower and q not in uniq:
                    uniq.append(q)
            
            return uniq[:n]
            
        except TimeoutError:
            print(f"[WARN] Query expansion timed out, continuing without expansion")
            return []
        except Exception as e:
            print(f"[WARN] Query expansion failed ({type(e).__name__}): {e}")
            return []
    
    def _validate_expansions(self, original_query: str, expansions: List[str], query_type: Optional[str] = None) -> List[str]:
        """Validate expansions using semantic similarity."""
        if not expansions:
            return []
        
        model = _get_similarity_model()
        if model is None:
            # If similarity model not available, return all expansions
            print(f"[WARN] Similarity model not available, skipping validation")
            return expansions
        
        try:
            # Adjust similarity threshold for conversational queries (they're often shorter/vaguer)
            min_similarity = QUERY_EXPANSION_MIN_SIMILARITY
            if query_type == 'conversational':
                min_similarity = 0.55  # Lower threshold for conversational queries
                print(f"[QUERY_EXPANSION] Using lower similarity threshold ({min_similarity}) for conversational query")
            
            # Compute embeddings
            texts = [original_query] + expansions
            embeddings = model.encode(texts, convert_to_numpy=True)
            
            # Calculate similarity to original
            original_emb = embeddings[0:1]
            expansion_embs = embeddings[1:]
            
            from sklearn.metrics.pairwise import cosine_similarity
            similarities = cosine_similarity(original_emb, expansion_embs)[0]
            
            # Filter expansions
            validated = []
            for i, (exp, sim) in enumerate(zip(expansions, similarities)):
                # Check similarity to original (should be similar but not too similar)
                if sim < min_similarity:
                    print(f"[QUERY_EXPANSION] Filtered expansion (too different, sim={sim:.2f}): {exp[:50]}")
                    continue
                if sim > 0.95:
                    print(f"[QUERY_EXPANSION] Filtered expansion (too similar, sim={sim:.2f}): {exp[:50]}")
                    continue
                
                # Check similarity to other expansions (avoid duplicates)
                is_duplicate = False
                for validated_exp in validated:
                    validated_emb = model.encode([validated_exp], convert_to_numpy=True)
                    exp_emb = model.encode([exp], convert_to_numpy=True)
                    exp_sim = cosine_similarity(validated_emb, exp_emb)[0][0]
                    if exp_sim > 0.85:
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    validated.append(exp)
            
            print(f"[QUERY_EXPANSION] Validated {len(validated)}/{len(expansions)} expansions")
            return validated
            
        except Exception as e:
            print(f"[WARN] Expansion validation failed: {e}")
            # Return all expansions if validation fails
            return expansions
    
    def _get_cache_key(self, query: str, n: int) -> str:
        """Generate cache key for query."""
        key_data = f"{query.lower().strip()}:{n}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def _clean_cache(self, max_size: int = 1000):
        """Clean old cache entries if cache gets too large."""
        global _expansion_cache
        if len(_expansion_cache) > max_size:
            # Remove expired entries
            now = datetime.now()
            _expansion_cache = {
                k: v for k, v in _expansion_cache.items()
                if v[1] > now
            }
            # If still too large, remove oldest 20%
            if len(_expansion_cache) > max_size:
                sorted_items = sorted(_expansion_cache.items(), key=lambda x: x[1][1])
                _expansion_cache = dict(sorted_items[-int(max_size * 0.8):])

