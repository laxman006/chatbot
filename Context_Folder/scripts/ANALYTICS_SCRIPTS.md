# Analytics Scripts Documentation

## Overview

Scripts for analytics, monitoring, Langfuse integration, and auto-correction of low-scored responses.

---

## Analytics & Monitoring

### `analyze_user_questions.py`
**Location:** `scripts/analyze_user_questions.py`

**Purpose:** Analyze user questions for patterns and insights

**What it does:**
1. Connects to MongoDB
2. Fetches user questions from chat history
3. Analyzes question patterns (topics, frequency, trends)
4. Generates analytics report
5. Exports insights to file

**Usage:**
```bash
python scripts/analyze_user_questions.py
```

**Options:**
- `--output PATH` - Output file path
- `--date-range START END` - Analyze specific date range
- `--top-n N` - Show top N questions

**Output:**
- Most asked questions
- Question frequency distribution
- Topic analysis
- Trend analysis

---

### `check_email_tracing.py`
**Location:** `scripts/check_email_tracing.py`

**Purpose:** Check email tracing and delivery status

**What it does:**
1. Connects to email service (if configured)
2. Checks email delivery status
3. Verifies tracing setup
4. Reports email statistics

**Usage:**
```bash
python scripts/check_email_tracing.py
```

**Use case:** Debug email delivery issues

---

## Langfuse Integration

### `auto_correct_low_scores.py`
**Location:** `scripts/auto_correct_low_scores.py`

**Purpose:** Auto-correct low-scored responses from Langfuse LLM Judge

**What it does:**
1. Polls Langfuse for traces with evaluation score < 6
2. For each low-scored trace:
   - Extracts question and bad response
   - Generates improved response using RAG (vectorstore + GPT-4o-mini)
   - Logs correction to Langfuse as "improved_response" observation
3. Sleeps and repeats (if polling mode)

**Usage:**
```bash
# Run once
python scripts/auto_correct_low_scores.py

# Continuous polling mode (checks every 5 minutes)
python scripts/auto_correct_low_scores.py --poll --interval 300
```

**Options:**
- `--poll` - Enable continuous polling mode
- `--interval SECONDS` - Polling interval (default: 300 = 5 minutes)
- `--min-score SCORE` - Minimum score threshold (default: 6)
- `--limit N` - Max number of traces to process per run (default: 10)
- `--dry-run` - Show what would be corrected without actually doing it

**Workflow:**
```
1. Poll Langfuse for traces with evaluation score < 6
2. For each low-scored trace:
   - Extract question and bad response
   - Generate improved response using RAG
   - Log correction to Langfuse as observation
3. Sleep and repeat (if polling)
```

**Integration:**
- Uses `generate_improved_response()` from `app/endpoints.py`
- Uses `langfuse_tracker` from `app/langfuse_integration.py`
- Connects to Langfuse API

---

### `process_bad_traces_and_log_to_langfuse.py`
**Location:** `scripts/process_bad_traces_and_log_to_langfuse.py`

**Purpose:** Process bad traces and log corrections to Langfuse

**What it does:**
1. Fetches bad traces from Langfuse
2. Processes each trace
3. Generates improved responses
4. Logs corrections back to Langfuse

**Usage:**
```bash
python scripts/process_bad_traces_and_log_to_langfuse.py
```

**Options:**
- `--limit N` - Max traces to process
- `--dry-run` - Preview only

**Use case:** Batch processing of bad traces

---

## Script Details

### Langfuse Integration Pattern

**Connection:**
```python
from langfuse import Langfuse
from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST

langfuse = Langfuse(
    public_key=LANGFUSE_PUBLIC_KEY,
    secret_key=LANGFUSE_SECRET_KEY,
    host=LANGFUSE_HOST
)
```

**Fetching Traces:**
```python
traces = langfuse.fetch_traces(
    project_id=project_id,
    user_id=user_id,
    limit=limit
)
```

**Logging Observations:**
```python
trace.observation(
    name="improved_response",
    type="GENERATION",
    input={"question": question},
    output={"answer": improved_answer}
)
```

---

### RAG Response Generation

**Using Endpoints:**
```python
from app.endpoints import generate_improved_response

improved_response = generate_improved_response(
    question=question,
    bad_response=bad_response
)
```

**Direct Vectorstore:**
```python
from app.vectorstore import load_existing_vectorstore
from app.llm import setup_qa_chain

vectorstore = load_existing_vectorstore()
qa_chain = setup_qa_chain(vectorstore)
response = qa_chain.invoke({"question": question})
```

---

## Integration Points

### Langfuse
- **`app/langfuse_integration.py`** - Langfuse tracker
- **`config.py`** - Langfuse configuration

### RAG System
- **`app/endpoints.py`** - `generate_improved_response()` function
- **`app/vectorstore.py`** - Vectorstore access
- **`app/llm.py`** - LLM chain setup

### MongoDB
- **`app/mongodb_memory.py`** - User data access

---

## Error Handling

### Common Errors

**Langfuse Connection:**
- API key invalid → Check credentials
- Network error → Check network connection
- Rate limiting → Implement backoff

**RAG Generation:**
- Vectorstore not found → Check vectorstore path
- LLM API error → Check API key
- Timeout → Increase timeout

**Data Errors:**
- Missing trace data → Validate trace structure
- Invalid question → Sanitize input

---

## Best Practices

1. **Polling Interval:** Use appropriate polling intervals (5+ minutes)
2. **Rate Limiting:** Respect Langfuse API rate limits
3. **Error Handling:** Handle API errors gracefully
4. **Dry Run:** Use `--dry-run` to preview changes
5. **Logging:** Log all corrections for audit trail

---

## Output Examples

### Auto-Correction
```
[*] Polling Langfuse for low-scored traces...
[*] Found 5 traces with score < 6
[*] Processing trace: trace-id-1
[*] Generating improved response...
[OK] Generated improved response (length: 500 chars)
[*] Logging to Langfuse...
[OK] Logged observation: improved_response
[*] Processing trace: trace-id-2
...
[OK] Processed 5 traces
[*] Sleeping for 300 seconds...
```

### Question Analysis
```
[*] Analyzing user questions...
[*] Fetching questions from MongoDB...
[OK] Found 1,000 questions
[*] Analyzing patterns...
[OK] Top 10 questions:
  1. "How does CloudFuze Manage work?" (50 occurrences)
  2. "What is shadow IT?" (45 occurrences)
  ...
[OK] Generated report: analytics_report_2025-01-09.json
```

---

## Key Files

- **`scripts/auto_correct_low_scores.py`** - Auto-correction script
- **`scripts/process_bad_traces_and_log_to_langfuse.py`** - Bad trace processing
- **`scripts/analyze_user_questions.py`** - Question analysis
- **`scripts/check_email_tracing.py`** - Email tracing check

---

**Last Updated:** 2025-01-09  
**Location:** `scripts/`
