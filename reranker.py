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
        ce_scores = self.model.predict(pairs)  # Raw logits (can be negative)
        
        # Normalize cross-encoder scores to 0-1 range
        # This prevents negative scores from dominating the final score
        if len(ce_scores) > 0:
            ce_min = float(min(ce_scores))
            ce_max = float(max(ce_scores))
            
            if ce_max != ce_min:
                # Normalize: (score - min) / (max - min) -> maps to [0, 1]
                normalized_ce_scores = [
                    (float(ce_score) - ce_min) / (ce_max - ce_min)
                    for ce_score in ce_scores
                ]
            else:
                # All scores are the same, set to 0.5 (neutral)
                normalized_ce_scores = [0.5] * len(ce_scores)
        else:
            normalized_ce_scores = []

        reranked = []
        for (doc, base_score), ce_score_norm in zip(candidates, normalized_ce_scores):
            # Combine: 80% normalized cross-encoder (0-1), 20% base score (0-1)
            # Now both components are in 0-1 range, so final_score will be 0-1
            final_score = 0.8 * float(ce_score_norm) + 0.2 * float(base_score)
            reranked.append((doc, final_score))

        reranked.sort(key=lambda x: x[1], reverse=True)
        return reranked[:top_k]

