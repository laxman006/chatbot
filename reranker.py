# reranker.py
import numpy as np
from typing import List, Tuple, Optional
from langchain_core.documents import Document

def sigmoid(x):
    """Stable sigmoid implementation without SciPy dependency."""
    # Clip to prevent overflow
    x = np.clip(x, -500, 500)
    return 1.0 / (1.0 + np.exp(-x))

class CrossEncoderReranker:
    """
    Cross-encoder reranker using sentence-transformers.
    Install: pip install sentence-transformers
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-12-v2"):
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
        Supports:
        - (doc, base_score)
        - (doc, base_score, dense_sim, bm25_sim)

        Returns: list of (doc, final_score) sorted descending (higher is better).
        """
        if not candidates:
            return []

        # Extract docs + base scores safely
        docs = []
        base_scores = []
        for item in candidates:
            doc = item[0]
            base_score = item[1]
            docs.append(doc)
            base_scores.append(float(base_score))

        # If model missing, fallback to base_score ranking
        if not self.model:
            ranked = list(zip(docs, base_scores))
            ranked.sort(key=lambda x: x[1], reverse=True)
            return ranked[:top_k]

        # Cross-encoder prediction
        pairs = [[query, d.page_content] for d in docs]
        ce_scores = np.array(self.model.predict(pairs), dtype=float)

        # 1) Calibrate CE to [0, 1] using sigmoid (globally consistent, no per-batch min-max)
        ce_prob = sigmoid(ce_scores)

        # 2) Ensure base score is in [0, 1] (should already be normalized from hybrid fusion)
        base_prob = np.clip(np.array(base_scores, dtype=float), 0.0, 1.0)

        # 3) Fuse: CE dominates, base is tie-breaker
        final = 0.9 * ce_prob + 0.1 * base_prob

        reranked = list(zip(docs, final.tolist()))
        reranked.sort(key=lambda x: x[1], reverse=True)
        return reranked[:top_k]

