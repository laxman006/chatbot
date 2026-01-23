# Intelligent Query Routing System - Complete Guide

## 📋 Overview

The **Intelligent Query Routing System** uses an LLM to analyze user queries and dynamically allocate retrieval across multiple knowledge sources. Unlike keyword-based routing, this system understands query intent even when explicit keywords are missing.

### Key Features

✅ **Intent-aware** - Understands what users want, not just what they say  
✅ **Dynamic allocation** - Adjusts retrieval budget per source based on relevance  
✅ **Multi-modal** - Handles diverse query types (troubleshooting, sales, compliance, etc.)  
✅ **Explainable** - LLM provides reasoning for each routing decision  
✅ **Robust fallback** - Uses balanced retrieval if LLM routing fails  

---

## 🏗️ Architecture

```
User Query
    ↓
┌─────────────────────────────────────────┐
│  LLM QUERY ROUTER                       │
│  • Analyzes query intent & context      │
│  • Determines source relevance (0-1.0)  │
│  • Allocates retrieval budget           │
└─────────────────────────────────────────┘
    ↓
Routing Plan:
{
  "blog": {"relevance": 0.8, "k": 15},
  "jira": {"relevance": 0.9, "k": 20},
  "sharepoint": {"relevance": 0.3, "k": 5},
  ...
}
    ↓
┌─────────────────────────────────────────┐
│  PARALLEL MULTI-SOURCE RETRIEVAL        │
│  • Blog (15 docs)                       │
│  • Jira (20 tickets)                    │
│  • SharePoint (5 docs)                  │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│  DEDUPLICATION & MERGING                │
│  50 retrieved → 43 unique               │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│  CROSS-ENCODER RERANKING                │
│  43 candidates → Top 10 selected        │
└─────────────────────────────────────────┘
    ↓
Final Answer with Top 10 Documents
```

---

## 🚀 Quick Start

### 1. Enable Intelligent Routing

Set environment variable:

```bash
ENABLE_INTELLIGENT_ROUTING=true
```

Or in `.env` file:

```env
ENABLE_INTELLIGENT_ROUTING=true
ROUTING_TOTAL_BUDGET=50
ROUTING_FINAL_K=10
```

### 2. Configuration Options

```env
# Core Configuration
ENABLE_INTELLIGENT_ROUTING=true      # Enable/disable intelligent routing
ROUTING_TOTAL_BUDGET=50              # Total docs retrieved across all sources
ROUTING_FINAL_K=10                   # Final docs returned to LLM after reranking

# Routing Behavior
ROUTING_MIN_CONFIDENCE=0.6           # Min confidence to trust LLM router
ROUTING_FALLBACK_MODE=balanced       # Fallback mode if LLM fails

# Source-Specific Limits
MAX_JIRA_K=30                        # Max Jira tickets per query
MAX_BLOG_K=20                        # Max blog articles per query
MAX_SHAREPOINT_K=15                  # Max SharePoint docs per query
MAX_PDF_K=15                         # Max PDF docs per query
MAX_TRANSCRIPT_K=10                  # Max transcript chunks per query
MAX_EXCEL_K=10                       # Max Excel rows per query

# Advanced
ROUTING_USE_PARALLEL_RETRIEVAL=true  # Parallel vs sequential retrieval
ROUTING_ENABLE_DEDUPLICATION=true    # Remove duplicates across sources
```

### 3. Test the System

```bash
python test_intelligent_routing.py
```

---

## 📊 How It Works

### Step-by-Step Flow

#### **Step 1: Query Analysis (1-2s)**

LLM analyzes the query to understand:
- **Query Type**: troubleshooting, general_info, compliance, sales, technical, pricing
- **Intent**: What the user wants to achieve
- **Relevant Sources**: Which knowledge sources would help

**Example:**
```
Query: "Migration stuck at pending status, worker_status is null"

LLM Decision:
{
  "query_type": "troubleshooting",
  "query_intent": "Debug stuck migration with null worker status",
  "confidence": 0.92
}
```

#### **Step 2: Budget Allocation (instant)**

Based on query type, allocate the 50-document budget:

```
Jira:       25 docs (50%) - Primary troubleshooting source
Blog:       12 docs (24%) - Migration guides
PDFs:       8 docs  (16%) - Technical docs
SharePoint: 3 docs  (6%)  - Internal docs
Transcripts:2 docs  (4%)  - Customer issues
Excel:      0 docs  (0%)  - Not relevant
```

#### **Step 3: Parallel Retrieval (2-3s)**

Query all sources simultaneously:

```python
# Each source queried independently
blog_results = vectorstore.search(query, filter={"source_type": "blog"}, k=12)
jira_results = jira_vectorstore.search(query, k=25)
pdf_results = vectorstore.search(query, filter={"source_type": "pdf"}, k=8)
# ... etc
```

#### **Step 4: Deduplication (<1s)**

Remove duplicates across sources:

```
50 retrieved → 43 unique (14% duplicates removed)
```

#### **Step 5: Reranking (1-2s)**

Cross-encoder deep semantic scoring:

```
Top 10 documents selected from 43 candidates:
1. PRI-4523 Root Cause (0.94) - Jira
2. PRI-4401 AI Suggestions (0.89) - Jira
3. Delta Migration Guide (0.82) - Blog
4. Worker Architecture (0.75) - PDF
...
```

#### **Step 6: LLM Generation (3-5s)**

Generate answer using top 10 documents as context.

---

## 🎯 Query Type Examples

### 1. Troubleshooting Queries

**Detected when:**
- Error messages, stack traces, failure descriptions
- Words like "stuck", "not working", "failed"
- Technical problem descriptions WITHOUT explicit keywords

**Examples:**
```
✓ "Migration shows pending for 10 minutes, worker_status null"
✓ "How to fix delta migration error?"
✓ "java.lang.NullPointerException at MigrationWorker.java:245"
```

**Routing:**
- **Primary**: Jira (70-90%)
- **Secondary**: Blog, PDFs (10-30%)

---

### 2. General Information Queries

**Detected when:**
- "What is...", "Tell me about...", "Explain..."
- General product questions
- Feature explanations

**Examples:**
```
✓ "What is CloudFuze?"
✓ "Explain delta migration"
✓ "How does CloudFuze work?"
```

**Routing:**
- **Primary**: Blog (60-80%)
- **Secondary**: PDFs, Transcripts (20-40%)

---

### 3. Compliance/Security Queries

**Detected when:**
- Mentions certificates, compliance, security
- SOC, GDPR, HIPAA, etc.
- Policy and legal questions

**Examples:**
```
✓ "Do you have SOC 2 Type II certification?"
✓ "What is your data privacy policy?"
✓ "GDPR compliance documentation"
```

**Routing:**
- **Primary**: SharePoint (70-90%)
- **Secondary**: Blog (10-30%)

---

### 4. Pricing Queries

**Detected when:**
- Mentions cost, pricing, plans
- "How much...", "What does it cost..."

**Examples:**
```
✓ "How much does enterprise plan cost?"
✓ "Pricing for 1000 users"
✓ "Compare pricing plans"
```

**Routing:**
- **Primary**: Excel (60-80%)
- **Secondary**: Transcripts, Blog (20-40%)

---

### 5. Sales/Competitive Queries

**Detected when:**
- Competitor comparisons
- Value propositions, differentiation
- Customer objections, use cases

**Examples:**
```
✓ "What differentiates CloudFuze from competitors?"
✓ "Why choose CloudFuze over ShareGate?"
✓ "Customer success stories"
```

**Routing:**
- **Primary**: Transcripts (60-80%)
- **Secondary**: Blog (20-40%)

---

### 6. Technical Deep-Dive

**Detected when:**
- API documentation requests
- Technical specifications
- Architecture details

**Examples:**
```
✓ "API documentation for delta migration"
✓ "Technical architecture of worker system"
✓ "Rate limiting specifications"
```

**Routing:**
- **Primary**: PDFs (60-80%)
- **Secondary**: Blog (20-40%)

---

## 📈 Performance Metrics

### Time Breakdown

| Phase | Time | Description |
|-------|------|-------------|
| Routing (LLM) | 1-2s | LLM analyzes query and returns routing plan |
| Retrieval | 2-3s | Parallel retrieval from all sources |
| Deduplication | <0.5s | Hash-based duplicate removal |
| Reranking | 1-2s | Cross-encoder semantic scoring |
| Compression (optional) | 0.5-1s | Extract relevant sentences |
| LLM Generation | 3-5s | Final answer generation |
| **TOTAL** | **8-12s** | End-to-end response time |

### Document Flow

```
50 retrieved → 43 deduped → 10 final → 1 answer
```

### Token Usage

```
Routing:     ~800 tokens (system prompt + query)
Context:     ~6,000 tokens (10 documents compressed)
Generation:  ~500 tokens (answer)
Total:       ~7,300 tokens per query
```

---

## 🔧 Customization

### Adjusting Budget

For faster responses (trade accuracy for speed):

```env
ROUTING_TOTAL_BUDGET=30    # Reduce to 30 docs
ROUTING_FINAL_K=7          # Return 7 instead of 10
```

For better accuracy (trade speed for quality):

```env
ROUTING_TOTAL_BUDGET=70    # Increase to 70 docs
ROUTING_FINAL_K=15         # Return 15 instead of 10
```

### Adjusting Source Limits

Prioritize specific sources:

```env
MAX_JIRA_K=40              # Allow more Jira tickets
MAX_BLOG_K=30              # Allow more blog articles
MAX_TRANSCRIPT_K=5         # Limit transcripts
```

### Confidence Threshold

Control when to use LLM routing vs fallback:

```env
ROUTING_MIN_CONFIDENCE=0.7  # Higher = stricter (use fallback more often)
ROUTING_MIN_CONFIDENCE=0.5  # Lower = more trusting (use LLM more)
```

---

## 🧪 Testing

### Run Test Suite

```bash
python test_intelligent_routing.py
```

### Expected Output

```
================================================================================
INTELLIGENT QUERY ROUTING - TEST SUITE
================================================================================
Started: 2026-01-22 15:30:45
Total Budget: 50 documents
Test Queries: 8
================================================================================

[*] Initializing LLM and Router...
[OK] Router initialized successfully

================================================================================
TEST 1: Copy-pasted error (no explicit keywords)
================================================================================
Query: Migration shows pending status for 10 minutes, worker_status is null
Expected Type: troubleshooting
Expected Primary Source: jira
--------------------------------------------------------------------------------

📍 INTELLIGENT QUERY ROUTING
======================================================================
Query: Migration shows pending status for 10 minutes, worker_status is null
Type: troubleshooting
Intent: Debug stuck migration with null worker_status
Confidence: 0.92

📊 Retrieval Allocation:
  ████████████ jira         k=25  relevance=0.95
     └─ Primary source - likely matches resolved tickets
  ██████ blog         k=12  relevance=0.60
     └─ May have migration guides
  ████ pdfs        k= 8  relevance=0.40
     └─ Technical docs on worker architecture

📦 Total documents: 45/50
======================================================================

📊 ROUTING RESULTS:
  Query Type: troubleshooting ✓
  Primary Source: jira (k=25) ✓
  Total Budget: 45/50 ✓
  Confidence: 0.92
  Active Sources: 5 - jira, blog, pdfs, sharepoint, transcripts

✅ TEST PASSED
```

---

## 🐛 Troubleshooting

### Issue: LLM routing fails

**Symptoms:** 
- Fallback routing always used
- Errors in logs about JSON parsing

**Solutions:**
1. Check LLM API key is valid
2. Verify LLM model supports JSON output
3. Check network connectivity
4. Review system prompt in `intelligent_router.py`

### Issue: Wrong sources prioritized

**Symptoms:**
- Jira prioritized for general questions
- Blog prioritized for errors

**Solutions:**
1. Review routing decision logs
2. Adjust system prompt in `intelligent_router.py`
3. Add more examples to prompt
4. Increase confidence threshold

### Issue: Over budget

**Symptoms:**
- Total k exceeds ROUTING_TOTAL_BUDGET
- Warning messages in logs

**Solutions:**
1. LLM should auto-scale, but verify in logs
2. Check MAX_*_K limits aren't too high
3. Reduce ROUTING_TOTAL_BUDGET if needed

---

## 📚 API Reference

### IntelligentQueryRouter

```python
from intelligent_router import IntelligentQueryRouter
from app.llm_factory import get_llm

llm = get_llm()
router = IntelligentQueryRouter(llm, total_budget=50)

# Get routing plan
routing_plan = router.route_query("How to fix migration error?")
```

### intelligent_route_and_retrieve

```python
from app.endpoints import intelligent_route_and_retrieve
from app.vectorstore import vectorstore
from app.jira_vectorstore import jira_vectorstore

# Retrieve documents using intelligent routing
doc_results = intelligent_route_and_retrieve(
    query="Migration stuck",
    k_final=10,
    use_routing=True
)
```

---

## 🎓 Best Practices

1. **Start with default settings** - They're optimized for most use cases
2. **Monitor routing decisions** - Check logs to ensure reasonable allocations
3. **Test with real queries** - Use production-like queries in testing
4. **Adjust gradually** - Make small config changes and measure impact
5. **Keep fallback enabled** - Ensures system works even if LLM fails

---

## 📊 Comparison: Keyword vs Intelligent Routing

| Query | Keyword Routing | Intelligent Routing |
|-------|----------------|---------------------|
| "Migration stuck at pending, worker_status null" | ❌ Miss (no keywords) | ✅ Jira (90%) |
| "How to fix error?" | ⚠️ Jira (50%) | ✅ Jira (80%) |
| "What is CloudFuze?" | ✅ Blog (80%) | ✅ Blog (90%) |
| "SOC 2 certification?" | ⚠️ Blog (60%) | ✅ SharePoint (95%) |
| "Enterprise pricing?" | ⚠️ Blog (70%) | ✅ Excel (85%) |

---

## 🚀 What's Next?

- **Fine-tune routing prompt** based on production usage
- **Add more query type categories** as needed
- **Implement caching** for repeated queries
- **A/B test** against keyword routing
- **Monitor metrics** and optimize

---

## 📞 Support

For issues or questions about intelligent routing:
1. Check logs for routing decisions
2. Run test suite to validate
3. Review this guide for configuration options
4. Check `intelligent_router.py` for system prompt

---

**Happy Routing! 🎯**
