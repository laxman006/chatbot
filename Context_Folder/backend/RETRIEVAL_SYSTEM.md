# Retrieval System Documentation

## Overview

The CloudFuze Chatbot uses a **hybrid retrieval system** combining dense (semantic) and sparse (keyword) retrieval, with cross-encoder reranking and intelligent tier-based filtering.

**Location:** `app/endpoints.py` - `perplexity_style_retrieve()` function

---

## 🏗️ Architecture

```
User Query
    │
    ├─► Query Expansion (Optional)
    │
    ├─► Dense Retrieval (Embeddings)
    │   └─► ChromaDB Vector Search
    │
    ├─► Sparse Retrieval (BM25)
    │   └─► Keyword Matching
    │
    ├─► Score Normalization
    │   ├─► Dense: Distance → Similarity (0-1)
    │   └─► BM25: Raw Score → Normalized (0-1)
    │
    ├─► Base Score Calculation
    │   └─► Weighted Combination: DENSE_WEIGHT * dense + BM25_WEIGHT * bm25
    │
    ├─► Metadata Boosting
    │   ├─► KB Tier (Primary/Secondary)
    │   ├─► Artifact Type (Q&A, Objection, Feature)
    │   ├─► Source Type (SharePoint)
    │   └─► Priority (High/Medium)
    │
    ├─► Hybrid Retrieval (Quota-Based)
    │   ├─► Separate Primary & Secondary KB
    │   ├─► Tier-Aware Filtering
    │   ├─► Adaptive Quota (9:1, 7:3, or 5:5)
    │   └─► Artifact Prioritization
    │
    └─► Cross-Encoder Reranking
        └─► Final Top-K Documents
```

---

## 📊 Retrieval Stages

### Stage 1: Query Expansion (Optional)

**Function:** `QueryExpander.expand(query, n=3)`

**Purpose:** Generate query variations for better retrieval coverage

**Example:**
```
Original: "How does license management work?"
Expansions:
  - "license management features"
  - "license tracking and optimization"
  - "SaaS license management"
```

**Configuration:**
- `ENABLE_QUERY_EXPANSION` in `config.py`
- Uses LLM to generate semantically similar queries

---

### Stage 2: Dense Retrieval (Semantic Search)

**Function:** `vectorstore.similarity_search_with_score(query, k=k_dense)`

**Technology:** 
- **Embeddings:** OpenAI `text-embedding-3-small`
- **Vector Store:** ChromaDB
- **Default K:** 60 documents

**Process:**
1. Convert query to embedding vector
2. Search ChromaDB for similar document embeddings
3. Return documents with cosine distance scores
4. Lower distance = higher similarity

**Normalization:**
```python
# Convert distance (0.2-0.8) to similarity (0-1)
norm_dense = (d_max - dist) / (d_max - d_min)
```

---

### Stage 3: Sparse Retrieval (Keyword Search)

**Function:** `bm25_retriever.search(query, k=k_bm25)`

**Technology:**
- **Algorithm:** BM25 (Best Matching 25)
- **Default K:** 60 documents

**Process:**
1. Tokenize query and documents
2. Calculate BM25 scores based on term frequency
3. Return documents with raw BM25 scores
4. Higher score = better keyword match

**Normalization:**
```python
# Normalize BM25 scores to 0-1 range
norm_bm25 = (score - s_min) / (s_max - s_min)
```

---

### Stage 4: Score Merging & Normalization

**Function:** Merge dense and BM25 results

**Process:**
1. Deduplicate documents by content hash
2. For each document:
   - Get best dense score (if found)
   - Get best BM25 score (if found)
   - Normalize both to 0-1 range
3. Calculate base score:
   ```python
   base_score = DENSE_WEIGHT * dense_sim + BM25_WEIGHT * bm25_sim
   ```
   - Default: `DENSE_WEIGHT = 0.7`, `BM25_WEIGHT = 0.3`

---

### Stage 5: Metadata-Based Boosting

**Purpose:** Prioritize high-quality, relevant documents

**Boosts Applied:**

1. **KB Tier Boost:**
   - Primary KB: `+PRIMARY_KB_PRIORITY_BOOST` (default: 0.1)
   - Secondary KB: `+SECONDARY_KB_PRIORITY_BOOST` (default: 0.05)

2. **Artifact Type Boost:**
   - Transcript artifacts (Q&A, Objection, Feature): `+TRANSCRIPT_ARTIFACT_BOOST` (default: 0.10)
   - Raw transcripts: `+SECONDARY_KB_PRIORITY_BOOST` (default: 0.05)

3. **Source Type Boost:**
   - SharePoint documents: `+0.05`

4. **Priority Boost:**
   - High priority: `+0.05`
   - Medium priority: `+0.02`

**Example:**
```python
# Primary KB SharePoint document with high priority
base_score = 0.6
base_score += 0.1  # Primary KB boost
base_score += 0.05  # SharePoint boost
base_score += 0.05  # High priority boost
final_score = 0.8
```

---

### Stage 6: Hybrid Retrieval (Quota-Based)

**Purpose:** Always include both primary and secondary KB documents

**Process:**

1. **Separate by KB Tier:**
   ```python
   primary_candidates = [doc for doc in candidates if kb_tier == "primary"]
   secondary_candidates = [doc for doc in candidates if kb_tier == "secondary"]
   ```

2. **Apply Tier-Aware Filtering:**
   - Primary KB threshold: `0.3` (higher - structured content scores better)
   - Secondary KB threshold: `0.15` (lower - conversational content scores lower but valuable)

3. **Calculate Primary Confidence:**
   ```python
   primary_confidence = (max_primary_score + avg_primary_score) / 2
   ```

4. **Adaptive Quota Assembly:**
   - High confidence (≥0.75): **9:1** ratio (9 primary, 1 secondary)
   - Medium confidence (≥0.5): **7:3** ratio (7 primary, 3 secondary)
   - Low confidence (<0.5): **5:5** ratio (5 primary, 5 secondary)

5. **Prioritize Artifacts:**
   - Within secondary KB, prioritize artifacts (Q&A, objections, features) over raw transcripts

**Example:**
```
Primary candidates: 20 docs (avg score: 0.65)
Secondary candidates: 15 docs (avg score: 0.42)

Primary confidence: (0.75 + 0.65) / 2 = 0.70 (Medium)

Quota: 7 primary, 3 secondary
Final: 7 primary KB docs + 3 transcript artifacts
```

---

### Stage 7: Cross-Encoder Reranking

**Function:** `CrossEncoderReranker.rerank(query, candidates, top_k=k_final)`

**Technology:**
- **Model:** `cross-encoder/ms-marco-MiniLM-L-6-v2`
- **Purpose:** Fine-grained relevance scoring

**Process:**
1. For each candidate document:
   - Create query-document pair
   - Pass to cross-encoder model
   - Get raw logit score (can be negative)
2. Normalize scores to 0-1 range
3. Combine with base score:
   ```python
   final_score = 0.8 * normalized_ce_score + 0.2 * base_score
   ```
4. Sort by final score (descending)
5. Return top K documents

**Default K:** 10 documents

---

## 🎯 Retrieval Configuration

**Location:** `config.py`

```python
# Retrieval Parameters
DENSE_RETRIEVAL_K = 60      # Documents from dense retrieval
BM25_RETRIEVAL_K = 60       # Documents from BM25 retrieval
FINAL_RETRIEVAL_K = 10      # Final documents after reranking

# Score Weights
DENSE_WEIGHT = 0.7          # Weight for dense retrieval
BM25_WEIGHT = 0.3           # Weight for BM25 retrieval
RERANKER_WEIGHT = 0.8       # Weight for cross-encoder in final score

# Boosts
PRIMARY_KB_PRIORITY_BOOST = 0.1
SECONDARY_KB_PRIORITY_BOOST = 0.05
TRANSCRIPT_ARTIFACT_BOOST = 0.10

# Thresholds
PRIMARY_SCORE_THRESHOLD = 0.3
SECONDARY_SCORE_THRESHOLD = 0.15
MIN_SCORE_THRESHOLD = 0.3
```

---

## 🔍 Query-Specific Retrieval

### Transcript-Specific Queries

**Function:** `is_transcript_specific_query(query)`

**Detection Methods:**
1. **Pattern Matching:**
   - "What did [name] ask?"
   - "What concerns did customers raise?"
   - "During the demo..."

2. **Dynamic Keywords:**
   - Extracted from transcript metadata
   - Cached for performance

3. **LLM Semantic Detection:**
   - Uses LLM to understand query intent
   - Enabled when `ENABLE_ARTIFACT_EXTRACTION = true`

**Effect:**
- Ensures secondary KB (transcripts) are always considered
- Adjusts quota ratios to favor transcripts when relevant

---

## 📈 Performance Metrics

**Retrieval Quality:**
- **Precision:** Top-K documents are highly relevant
- **Recall:** Relevant documents are retrieved
- **Diversity:** Documents from multiple sources

**Logging:**
```
[HYBRID RETRIEVAL] Primary: 20 candidates → 15 after filtering (threshold: 0.3)
[HYBRID RETRIEVAL] Secondary: 15 candidates → 8 after filtering (threshold: 0.15)
[HYBRID RETRIEVAL] Added 7 primary KB documents
[HYBRID RETRIEVAL] Added 3 transcript artifacts
[HYBRID RETRIEVAL] Final assembly: 10 docs (ratio: 7:3, reason: medium confidence, primary confidence: 0.700)
```

---

## 🔧 Key Functions

### Main Retrieval Function
```python
def perplexity_style_retrieve(
    query: str,
    k_dense: int = 60,
    k_bm25: int = 60,
    k_final: int = 10,
    use_expansion: bool = True
) -> List[Tuple[Document, float]]
```

### Query Expansion
```python
class QueryExpander:
    def expand(query: str, n: int = 3) -> List[str]
```

### Cross-Encoder Reranking
```python
class CrossEncoderReranker:
    def rerank(query: str, candidates: List[Tuple[Document, float]], top_k: int) -> List[Tuple[Document, float]]
```

---

## 🎓 Best Practices

1. **Tune Weights:** Adjust `DENSE_WEIGHT` and `BM25_WEIGHT` based on query types
2. **Monitor Thresholds:** Adjust tier thresholds based on retrieval quality
3. **Balance Quotas:** Ensure both primary and secondary KB are represented
4. **Artifact Prioritization:** Always prefer structured artifacts over raw transcripts
5. **Logging:** Monitor retrieval logs to identify issues

---

**Last Updated:** 2025-01-09  
**File:** `app/endpoints.py` (lines 1077-1348)
