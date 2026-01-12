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
        candidates: List[Tuple[Document, float]],
        top_k: int = 6,
    ) -> List[Tuple[Document, float]]:
        """
        candidates: list of (doc, base_score) where base_score is combined dense+bm25.
        Returns: list of (doc, final_score) sorted descending.
        """
        if not self.model or not candidates:
            return candidates[:top_k]

        pairs = [[query, d.page_content] for d, _ in candidates]
        scores = self.model.predict(pairs)  # higher is better
        
        # Normalize cross-encoder scores to 0-1 range
        # This prevents very negative scores (e.g., -7 to -8) from causing filtering issues
        if len(scores) > 1:
            ce_min, ce_max = min(scores), max(scores)
            if ce_max != ce_min:
                normalized_scores = [(s - ce_min) / (ce_max - ce_min) for s in scores]
            else:
                # All scores are the same, assign equal normalized score
                normalized_scores = [1.0] * len(scores)
        else:
            # Single score, keep as is but ensure non-negative
            normalized_scores = [max(0.0, float(scores[0]))] if scores else [0.0]
        
        # Debug logging for score normalization
        if len(scores) > 0:
            raw_min, raw_max = min(scores), max(scores)
            norm_min, norm_max = min(normalized_scores), max(normalized_scores)
            print(f"[RERANKER] Cross-encoder raw scores: min={raw_min:.4f}, max={raw_max:.4f}")
            print(f"[RERANKER] Normalized scores: min={norm_min:.4f}, max={norm_max:.4f}")

        reranked = []
        for (doc, base_score), ce_score in zip(candidates, normalized_scores):
            # Combine: 80% cross-encoder (now normalized 0-1), 20% base score
            final_score = 0.8 * float(ce_score) + 0.2 * float(base_score)
            reranked.append((doc, final_score))

        reranked.sort(key=lambda x: x[1], reverse=True)
        return reranked[:top_k]

