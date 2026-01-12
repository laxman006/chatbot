# Transcript Processing Pipeline Documentation

## Overview

The transcript processing pipeline extracts customer demo transcripts from SharePoint, processes them into structured artifacts (Q&A, objections, features, decision drivers), and adds them to the vectorstore as secondary knowledge base.

**Location:** `app/transcript_processor.py`  
**Script:** `scripts/process_transcripts_from_sharepoint.py`

---

## 🏗️ Pipeline Architecture

```
SharePoint Transcript Folder
    │
    ├─► Extract Word Documents (.docx)
    │   └─► SharePointGraphExtractor
    │
    ├─► Extract Text from Documents
    │   └─► doc_processor.extract_text_from_docx()
    │
    ├─► Normalize Transcript Text (Optional)
    │   └─► TranscriptNormalizer
    │       ├─► Remove timestamps
    │       ├─► Remove filler words
    │       └─► Deduplicate phrases
    │
    ├─► Extract Structured Artifacts
    │   └─► TranscriptArtifactExtractor
    │       ├─► Q&A Pairs
    │       ├─► Objections
    │       ├─► Features
    │       └─► Decision Drivers
    │
    ├─► Build Retrieval Text
    │   └─► build_retrieval_text()
    │       ├─► Convert to natural language
    │       ├─► Add customer context
    │       ├─► Add industry context
    │       └─► Remove conversational fillers
    │
    ├─► Group Artifacts for Chunking
    │   └─► group_artifacts_for_chunking()
    │       ├─► Group by type and topic
    │       ├─► Target: 180-300 tokens per chunk
    │       └─► Ideal: 250 tokens
    │
    ├─► Create LangChain Documents
    │   └─► Document(
    │       page_content=retrieval_text,
    │       metadata={...}
    │   )
    │
    └─► Add to Vectorstore
        └─► EnhancedVectorstoreBuilder
            └─► ChromaDB (Secondary KB)
```

---

## 📋 Processing Stages

### Stage 1: SharePoint Extraction

**Function:** `TranscriptProcessor.extract_transcripts_from_sharepoint()`

**Process:**
1. Authenticate with SharePoint (Microsoft Graph API)
2. List files in transcript folder
3. Filter for `.docx` files
4. Download each file
5. Extract text using `doc_processor.extract_text_from_docx()`

**Configuration:**
- `SHAREPOINT_TRANSCRIPTS_SITE_URL`
- `SHAREPOINT_TRANSCRIPTS_FOLDER_PATH`

---

### Stage 2: Text Normalization (Optional)

**Function:** `TranscriptNormalizer.normalize(text)`

**Purpose:** Clean transcript text for better processing

**Operations:**
1. **Remove Timestamps:**
   ```python
   # Patterns: "00:12:34", "[12:34]", etc.
   ```

2. **Remove Filler Words:**
   ```python
   FILLER_WORDS = {
       'yeah', 'uh', 'um', 'uh-huh', 'hmm',
       'like', 'you know', 'i mean', 'sort of',
       'right', 'ok', 'okay', 'sure'
   }
   ```

3. **Deduplicate Phrases:**
   - Remove repetitive sentences
   - Keep unique content

4. **Normalize Speaker Names:**
   - Standardize name formats
   - Preserve speaker roles

**Configuration:**
- `ENABLE_TRANSCRIPT_NORMALIZATION` in `config.py`

---

### Stage 3: Artifact Extraction

**Function:** `TranscriptArtifactExtractor.extract_artifacts(text)`

**Purpose:** Extract structured knowledge from transcript text

**Artifact Types:**

1. **Q&A Pairs:**
   ```json
   {
     "type": "Q&A",
     "question": "How does license management work?",
     "answer": "CloudFuze tracks license utilization...",
     "speaker": "Customer",
     "topic": "License Management"
   }
   ```

2. **Objections:**
   ```json
   {
     "type": "Objection",
     "objection": "We're concerned about data security",
     "response": "CloudFuze uses encryption...",
     "status": "resolved"
   }
   ```

3. **Features:**
   ```json
   {
     "type": "Feature",
     "feature": "Shadow IT Detection",
     "description": "Identifies unauthorized applications...",
     "capability": "Real-time monitoring"
   }
   ```

4. **Decision Drivers:**
   ```json
   {
     "type": "Decision Driver",
     "driver": "Cost Optimization",
     "description": "Customer wants to reduce SaaS spend",
     "impact": "high"
   }
   ```

**Technology:**
- Uses LLM (OpenAI/Gemini) for intelligent extraction
- Temperature: 0.3 (for consistency)
- Structured JSON output

**Configuration:**
- `ENABLE_ARTIFACT_EXTRACTION` in `config.py`

---

### Stage 4: Retrieval Text Building

**Function:** `build_retrieval_text(artifact_type, artifact_data, metadata)`

**Purpose:** Convert structured artifacts into natural language for semantic search

**Process:**

1. **Extract Customer Context:**
   ```python
   customer = metadata.get("customer", "a customer")
   industry = metadata.get("industry")
   product = metadata.get("product", "CloudFuze Manage")
   ```

2. **Build Customer Prefix:**
   ```python
   if customer and customer != "None":
       customer_prefix = f"During a {product} demo with {customer}"
       if industry:
           customer_prefix += f" from the {industry} sector"
   else:
       customer_prefix = f"During a {product} demo"
   ```

3. **Format by Artifact Type:**

   **Q&A:**
   ```python
   retrieval_text = f"""{customer_prefix}, a question was asked: {question}
   
   The CloudFuze team explained: {answer_clean}
   
   This discussion was about {topic}.
   
   This information was shared in a customer discussion context..."""
   ```

   **Objection:**
   ```python
   retrieval_text = f"""{customer_prefix}, a concern was raised: {objection}
   
   The CloudFuze team addressed this by: {response}
   
   Status: {status}"""
   ```

   **Feature:**
   ```python
   retrieval_text = f"""{customer_prefix}, the {feature} feature was discussed.
   
   Description: {description}
   
   Capabilities: {capability}"""
   ```

4. **Clean Conversational Fillers:**
   ```python
   conversational_phrases = [
       "that's where we come to the picture",
       "so we'll show you that",
       "let me show you",
       "right, so",
       "ok, so"
   ]
   ```

---

### Stage 5: Customer Name Extraction

**Function:** `_extract_customer_name(filename, meeting_title)`

**Purpose:** Extract customer name from filename or meeting title

**Filename Patterns:**
1. `"CloudFuze _ CloudFuze Manage Demo - Customer Name.docx"`
2. `"CloudFuze Manage Demo - Customer Name.docx"`
3. `"Customer Name - Demo.docx"`

**Process:**
1. Try regex patterns to extract customer name
2. Remove "CloudFuze" and "CloudFuze Manage" if found
3. Fallback to extracting after last dash
4. Clean and normalize name

**Example:**
```
Input: "CloudFuze _ CloudFuze Manage Demo - Phillips Exeter Academy.docx"
Output: "Phillips Exeter Academy"
```

---

### Stage 6: Industry Inference

**Function:** `_infer_industry(customer_name, meeting_title)`

**Purpose:** Infer industry from customer name or meeting title

**Method:** Keyword-based inference

**Keywords:**
- Education: "academy", "university", "school", "college"
- Healthcare: "hospital", "medical", "health"
- Finance: "bank", "financial", "credit"
- Technology: "tech", "software", "IT"

---

### Stage 7: Artifact Grouping

**Function:** `group_artifacts_for_chunking(artifacts, metadata)`

**Purpose:** Group related artifacts into optimal chunks (180-300 tokens)

**Process:**
1. **Group by Type:**
   - Q&A pairs together
   - Objections together
   - Features together

2. **Group by Topic:**
   - Related artifacts on same topic

3. **Token Counting:**
   ```python
   tokenizer = tiktoken.get_encoding("cl100k_base")
   token_count = len(tokenizer.encode(text))
   ```

4. **Target Size:**
   - Minimum: 180 tokens
   - Target: 250 tokens
   - Maximum: 350 tokens

5. **Create Groups:**
   - Combine artifacts until reaching target size
   - Ensure 2-5 chunks per transcript (not 1 per artifact)

**Example:**
```
Input: 10 Q&A pairs, 5 objections, 3 features
Output: 4 grouped chunks:
  - Chunk 1: 3 Q&A pairs (240 tokens)
  - Chunk 2: 4 Q&A pairs (280 tokens)
  - Chunk 3: 3 Q&A pairs + 2 objections (260 tokens)
  - Chunk 4: 3 objections + 2 features (220 tokens)
```

---

### Stage 8: Document Creation

**Function:** `process_transcript_file(file_path, file_content)`

**Process:**
1. Extract metadata from filename
2. Extract artifacts from content
3. Build retrieval text for each artifact
4. Group artifacts for chunking
5. Create LangChain Documents:
   ```python
   Document(
       page_content=combined_retrieval_text,
       metadata={
           "source_type": "transcript",
           "kb_tier": "secondary",
           "artifact_type": "Q&A",
           "customer": "Customer Name",
           "industry": "Education",
           "file_name": "filename.docx",
           "raw_content": original_artifact_json  # Stored for reference
       }
   )
   ```

---

### Stage 9: Vectorstore Integration

**Function:** `EnhancedVectorstoreBuilder.process_documents(transcript_docs, "transcript")`

**Process:**
1. **Skip Re-chunking:**
   - Transcript documents are already optimally chunked
   - Skip default chunking (800 tokens)

2. **Add Metadata:**
   - Ensure `kb_tier = "secondary"`
   - Add artifact type
   - Add customer and industry info

3. **Add to ChromaDB:**
   ```python
   vectorstore.add_documents(processed_chunks)
   ```

---

## 🔧 Configuration

**Location:** `config.py`

```python
# Transcript Processing
ENABLE_TRANSCRIPT_PROCESSING = True
ENABLE_TRANSCRIPT_NORMALIZATION = True
ENABLE_ARTIFACT_EXTRACTION = True
TRANSCRIPT_KB_TIER = "secondary"

# SharePoint Configuration
SHAREPOINT_TRANSCRIPTS_SITE_URL = "..."
SHAREPOINT_TRANSCRIPTS_FOLDER_PATH = "Neutara Labs/Transcripts"

# Chunking Configuration
TRANSCRIPT_TARGET_TOKENS = 250
TRANSCRIPT_MAX_TOKENS = 350
TRANSCRIPT_MIN_TOKENS = 180
```

---

## 📊 Processing Statistics

**Output:**
```
[*] Extraction Summary:
   Transcript files: 5
   Total documents: 23
   
   Document Types:
   - Q&A pairs: 15
   - Objections: 5
   - Features: 8
   - Decision Drivers: 3
   
   Chunks created: 12
   Average chunks per document: 2.4
```

---

## 🚀 Usage

### Process Transcripts from SharePoint

```bash
python scripts/process_transcripts_from_sharepoint.py
```

### Dry Run (Preview Only)

```bash
python scripts/process_transcripts_from_sharepoint.py --dry-run
```

### Custom Folder Path

```bash
python scripts/process_transcripts_from_sharepoint.py --folder-path "Custom/Path"
```

---

## 🔍 Key Functions Reference

### Main Processing
- `TranscriptProcessor.extract_transcripts_from_sharepoint()` - Extract from SharePoint
- `TranscriptProcessor.process_transcript_file()` - Process single file
- `build_retrieval_text()` - Convert artifact to retrieval text
- `group_artifacts_for_chunking()` - Group artifacts optimally

### Extraction
- `TranscriptArtifactExtractor.extract_artifacts()` - Extract structured artifacts
- `TranscriptNormalizer.normalize()` - Normalize transcript text

### Utilities
- `_extract_customer_name()` - Extract customer name
- `_infer_industry()` - Infer industry
- `count_tokens()` - Count tokens in text

---

## 🎯 Best Practices

1. **Optimal Chunking:** Target 180-300 tokens per chunk (ideal: 250)
2. **Customer Context:** Always include customer name and industry
3. **Artifact Prioritization:** Prioritize structured artifacts over raw transcripts
4. **Natural Language:** Convert artifacts to natural language for better retrieval
5. **Metadata Rich:** Include all relevant metadata for filtering and boosting

---

## 📝 Example Output

**Input Transcript:**
```
Customer: "How does license management work?"
CloudFuze: "We track license utilization in real-time..."
```

**Extracted Artifact:**
```json
{
  "type": "Q&A",
  "question": "How does license management work?",
  "answer": "We track license utilization in real-time...",
  "topic": "License Management"
}
```

**Retrieval Text:**
```
During a CloudFuze Manage demo with Phillips Exeter Academy from the Education sector, a question was asked: How does license management work?

The CloudFuze team explained: We track license utilization in real-time...

This discussion was about License Management.

This information was shared in a customer discussion context and reflects how the product works based on the demo conversation.
```

---

**Last Updated:** 2025-01-09  
**File:** `app/transcript_processor.py`
