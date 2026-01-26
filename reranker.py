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

        # ✅ FIX 3: Dynamic CE fusion using spread (more stable than variance)
        # Use top1-top5 spread instead of variance for better stability with small candidate sets
        sorted_ce = np.sort(ce_prob)[::-1]  # Descending order
        ce_mean = np.mean(ce_prob)
        
        if len(sorted_ce) >= 5:
            # Calculate spread: top1 - top5 (how much top doc stands out)
            ce_spread = sorted_ce[0] - sorted_ce[4]
        elif len(sorted_ce) >= 2:
            # Fallback for small sets: top1 - top2
            ce_spread = sorted_ce[0] - sorted_ce[1]
        else:
            ce_spread = 0.0
        
        # Normalize spread (typical range: 0.0-0.3 for sigmoid outputs)
        # Spread < 0.05 = uncertain (flat scores), spread > 0.20 = confident (clear winner)
        normalized_spread = min(ce_spread / 0.20, 1.0)  # Cap at 1.0
        mean_component = ce_mean  # Already 0-1
        
        # Certainty: combination of spread and mean
        # Spread is more important (70%) because it indicates clear winner
        ce_certainty = 0.7 * normalized_spread + 0.3 * mean_component
        
        # Dynamic weight: more certain = more CE weight
        # Range: 0.6 (uncertain, spread < 0.05) to 0.95 (very certain, spread > 0.20)
        ce_weight = 0.6 + (0.35 * ce_certainty)
        base_weight = 1.0 - ce_weight
        
        # Fuse with dynamic weights
        final = ce_weight * ce_prob + base_weight * base_prob
        
        if len(candidates) > 5:  # Only log for larger batches
            print(f"[RERANKER] Dynamic fusion: CE_weight={ce_weight:.3f}, base_weight={base_weight:.3f}, spread={ce_spread:.3f}, certainty={ce_certainty:.3f}")

        reranked = list(zip(docs, final.tolist()))
        reranked.sort(key=lambda x: x[1], reverse=True)
        return reranked[:top_k]

