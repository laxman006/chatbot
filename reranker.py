# reranker.py
from typing import List, Tuple, Optional
from langchain_core.documents import Document

class CrossEncoderReranker:
    """
    Cross-encoder reranker using sentence-transformers.
    Install: pip install sentence-transformers
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        try:
            from sentence_transformers import CrossEncoder
            self.model = CrossEncoder(model_name)
            print(f"[OK] CrossEncoder model loaded: {model_name}")
        except Exception as e:
            print(f"[WARN] Could not load CrossEncoder model: {e}")
            self.model = None

    def rerank(
        self,
        query: str,
        candidates: List[Tuple],
        top_k: int = 6,
    ) -> List[Tuple[Document, float]]:
        """
        STEP 2 & 3: Normalize all scores to same space and fuse properly.
        
        candidates: list of (doc, base_score, dense_sim, bm25_sim) 
                   OR list of (doc, base_score) for backward compatibility.
        Returns: list of (doc, final_score) sorted descending.
        """
        if not candidates:
            return []
        
        # Handle backward compatibility: check if candidates have dense/bm25 scores
        has_separate_scores = len(candidates[0]) >= 4
        
        if not self.model:
            # No model: return top K by base_score
            if has_separate_scores:
                return [(item[0], item[1]) for item in candidates[:top_k]]
            else:
                return candidates[:top_k]

        pairs = [[query, d.page_content] for d, _, _, _ in candidates] if has_separate_scores else [[query, d.page_content] for d, _ in candidates]
        ce_scores = self.model.predict(pairs)  # Raw logits (can be negative)
        
        # RISK 2 FIX: Track absolute CE scores for monitoring batch-relative bias
        # BUG FIX: Check length instead of truthiness (numpy arrays are ambiguous)
        if len(ce_scores) > 0:
            ce_scores_float = [float(s) for s in ce_scores]
            mean_ce_absolute = sum(ce_scores_float) / len(ce_scores_float)
            
            # Maintain history for monitoring (keep last 100 queries)
            if not hasattr(self, '_ce_score_history'):
                self._ce_score_history = []
            
            self._ce_score_history.append(mean_ce_absolute)
            
            # Keep only last 100 for rolling average
            if len(self._ce_score_history) > 100:
                self._ce_score_history = self._ce_score_history[-100:]
            
            # Log rolling mean every 10 queries to detect corpus/chunking issues
            if len(self._ce_score_history) % 10 == 0:
                rolling_mean = sum(self._ce_score_history) / len(self._ce_score_history)
                print(f"[CE MONITOR] Mean absolute CE score (last {len(self._ce_score_history)} queries): {rolling_mean:.3f}")
                # Alert if mean drops significantly (potential corpus mismatch)
                if len(self._ce_score_history) >= 20:
                    recent_mean = sum(self._ce_score_history[-20:]) / 20
                    older_mean = sum(self._ce_score_history[-40:-20]) / 20 if len(self._ce_score_history) >= 40 else recent_mean
                    if recent_mean < older_mean * 0.7:  # 30% drop
                        print(f"[CE MONITOR] ⚠️ WARNING: CE scores dropped 30% (recent: {recent_mean:.3f}, older: {older_mean:.3f}) - possible corpus/chunking issue")
        
        # STEP 2: Normalize ALL scores to the same space (0-1 range)
        def normalize(scores):
            """Global min-max normalization per query batch."""
            if not scores:
                return scores
            min_s, max_s = min(scores), max(scores)
            if max_s - min_s < 1e-6:
                return [0.5] * len(scores)  # All same, set to neutral
            return [(s - min_s) / (max_s - min_s) for s in scores]
        
        # Normalize cross-encoder scores
        normalized_ce_scores = normalize([float(s) for s in ce_scores])
        
        if has_separate_scores:
            # STEP 2: Normalize dense and BM25 scores together with CE scores
            # Extract all scores
            dense_scores = [item[2] for item in candidates]
            bm25_scores = [item[3] for item in candidates]
            
            # Normalize dense and BM25 separately (they're already in 0-1, but normalize for consistency)
            normalized_dense = normalize(dense_scores)
            normalized_bm25 = normalize(bm25_scores)
            
            # STEP 3: Proper fusion: 0.4 dense + 0.3 BM25 + 0.3 CE
            reranked = []
            for i, item in enumerate(candidates):
                doc = item[0]
                dense_norm = normalized_dense[i]
                bm25_norm = normalized_bm25[i]
                ce_norm = normalized_ce_scores[i]
                
                # Production-safe fusion weights
                final_score = 0.4 * dense_norm + 0.3 * bm25_norm + 0.3 * ce_norm
                reranked.append((doc, final_score))
        else:
            # Backward compatibility: use base_score
            base_scores = [item[1] for item in candidates]
            normalized_base = normalize(base_scores)
            
            # Fallback fusion: 0.6 base + 0.4 CE
            reranked = []
            for i, item in enumerate(candidates):
                doc = item[0]
                base_norm = normalized_base[i]
                ce_norm = normalized_ce_scores[i]
                final_score = 0.6 * base_norm + 0.4 * ce_norm
                reranked.append((doc, final_score))

        reranked.sort(key=lambda x: x[1], reverse=True)
        return reranked[:top_k]

