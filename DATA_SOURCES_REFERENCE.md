# Data Sources Reference Guide

Quick reference for understanding what data exists in each source for intelligent routing and system prompt optimization.

---

## Source Overview

| Source | Total Chunks | Content Type | Primary Use Cases |
|--------|--------------|--------------|-------------------|
| **Blog** | ~40% | HTML/Text | Migration guides, product info, how-tos |
| **SharePoint** | ~30% | Docs/PDFs/PPTX | Certificates, internal docs, policies |
| **Jira** | Variable | Tickets | Bug fixes, troubleshooting, known issues |
| **PDFs** | ~15% | Documents | Technical docs, API guides |
| **Transcripts** | ~10% | Text | Sales calls, customer conversations |
| **Excel** | ~5% | Structured | Pricing, feature matrices |

---

## 1. Blog (Tag: `blog`)

### Metadata Fields
```python
{
    "source_type": "web",
    "source": "cloudfuze_blog",
    "tag": "blog",
    "post_title": "Blog Post Title",
    "post_slug": "blog-post-slug",
    "post_url": "https://cloudfuze.com/...",
    "is_blog_post": True
}
```

### Content Characteristics
- **Format:** HTML cleaned to text, chunked at 1500 tokens (300 overlap)
- **Structure:** Title + content, well-formatted
- **Topics:**
  - Migration procedures and guides
  - Product announcements
  - Feature explanations
  - How-to articles
  - Best practices
  - Use cases and customer stories

### Best For
- General product information
- Migration setup and procedures
- Feature overviews
- Step-by-step guides
- Conceptual understanding
- "How to" questions

### Routing Weight Recommendations
- **Migration procedures:** 0.7-0.9
- **General info:** 0.7-1.0
- **Configuration:** 0.7-0.9
- **Best practices:** 0.7-0.9
- **Troubleshooting:** 0.4-0.7 (secondary to Jira)

---

## 2. SharePoint (Tag: `sharepoint/*`)

### Metadata Fields
```python
{
    "source_type": "sharepoint",
    "source": "cloudfuze_doc360",
    "file_name": "document.pdf",
    "file_url": "https://...",
    "folder_path": "Documents > Subfolder",
    "folder_tags": "sharepoint/documents/subfolder",
    "tag": "sharepoint/documents/...",
    "content_type": "pdf|docx|pptx|...",
    "is_certificate": True/False,
    "is_downloadable": True/False
}
```

### Content Characteristics
- **Format:** Mixed (PDFs, Word, PowerPoint, etc.)
- **Structure:** Hierarchical folders, tagged by path
- **Topics:**
  - SOC 2 certificates (in 2025 folder)
  - Internal policies
  - Compliance documentation
  - Security documents
  - Official forms
  - Internal procedures
  - Setup guides

### Best For
- Compliance questions (SOC, security)
- Certificate requests
- Internal policies
- Official documentation
- Legal/contractual information

### Routing Weight Recommendations
- **Compliance:** 0.8-1.0 (primary source)
- **Security:** 0.8-1.0
- **Configuration:** 0.3-0.5 (internal procedures)
- **General info:** 0.2-0.4 (secondary)

### Special Handling
- Certificate queries → Check `is_certificate` metadata
- Download requests → Check `is_downloadable` metadata
- Use `folder_tags` for hierarchical filtering

---

## 3. Jira (Tag: `jira/*`)

### Metadata Fields
```python
{
    "source_type": "jira",
    "source": "jira_ticket",
    "tag": "jira/project_key",
    "ticket_key": "PRI-9314",
    "ticket_summary": "...",
    "status": "Resolved",
    "issue_type": "Bug",
    "priority": "High",
    "project_key": "PRI",
    "combination": "Teams to Teams",
    "root_cause": "...",
    "fix_description": "...",
    "section": "root_cause|description|comment|...",
    "section_priority": "critical|normal",
    "url": "https://jira.../browse/PRI-9314"
}
```

### Content Characteristics
- **Format:** Field-aware chunks (summary, description, root cause, comments)
- **Chunk Strategy:**
  - Summary: Single chunk
  - Description: Semantic chunking (400-500 tokens)
  - Root Cause: Single chunk (never split)
  - Comments: One per comment
  - AI Suggestions: Single chunk
- **Topics:**
  - Bug resolutions
  - Error troubleshooting
  - Known issues
  - Workarounds
  - Edge cases
  - Migration failures
  - Root cause analysis

### Best For
- Error messages and stack traces
- Migration failures
- Known issues
- Troubleshooting steps
- Workarounds for limitations
- Past incident resolution
- Specific ticket references

### Routing Weight Recommendations
- **Troubleshooting:** 0.7-1.0 (primary)
- **Error with stack trace:** 1.0 (always include)
- **Migration procedures:** 0.5-0.7 (workarounds)
- **General info:** 0.2-0.4 (background context)
- **Ticket ID mentioned:** 1.0 (must include)

### Special Handling
- Prioritize `section="root_cause"` and `section_priority="critical"`
- Check `combination` for migration-type matching
- Use `status="Resolved"` to filter for solutions

---

## 4. PDFs (Tag: varies)

### Metadata Fields
```python
{
    "source_type": "pdf",
    "file_name": "document.pdf",
    "url": "...",
    "page_number": 5,
    # ... varies by source
}
```

### Content Characteristics
- **Format:** Text extracted from PDFs, chunked at 1500 tokens
- **Structure:** Page-based chunks
- **Topics:**
  - Technical documentation
  - User guides
  - API documentation
  - Detailed specifications
  - Architecture documents
  - Technical references

### Best For
- Deep technical questions
- API documentation
- Detailed specifications
- Architectural details
- Technical implementation

### Routing Weight Recommendations
- **Technical:** 0.7-1.0 (primary)
- **Configuration:** 0.5-0.7
- **General info:** 0.3-0.5
- **Troubleshooting:** 0.3-0.5

---

## 5. Transcripts (Tag: `transcript/*`)

### Metadata Fields
```python
{
    "source_type": "transcript",
    "tag": "transcript/...",
    "artifact_type": "Q&A|Objection|Feature|Decision Driver",
    "customer": "...",
    "industry": "...",
    # ... varies
}
```

### Content Characteristics
- **Format:** Pre-grouped artifacts (180-300 tokens)
- **Structure:** Conversation snippets, Q&A pairs
- **Topics:**
  - Sales conversations
  - Customer objections
  - Feature discussions
  - Real-world use cases
  - Customer requirements
  - Objection handling

### Best For
- Sales scenarios
- Customer objections
- Feature discussions
- Real-world conversation examples
- Use case validation
- Customer requirements

### Routing Weight Recommendations
- **Sales:** 0.7-1.0 (primary)
- **Best practices:** 0.4-0.6 (customer experiences)
- **Pricing:** 0.5-0.7
- **General info:** 0.2-0.4 (examples only)

### Special Notes
- Never present as official guarantees
- Use phrases: "Based on a customer demo...", "In a recent conversation..."
- SECONDARY to official documentation

---

## 6. Excel (Tag: varies)

### Metadata Fields
```python
{
    "source_type": "excel",
    "file_name": "pricing.xlsx",
    # ... varies
}
```

### Content Characteristics
- **Format:** Structured data, tables
- **Structure:** Rows/columns extracted as text
- **Topics:**
  - Pricing tables
  - Feature comparisons
  - Migration checklists
  - Data matrices
  - Feature matrices

### Best For
- Pricing information
- Feature comparisons
- Structured data queries
- Checklists

### Routing Weight Recommendations
- **Pricing:** 0.8-1.0 (primary)
- **Feature comparison:** 0.6-0.8
- **Configuration:** 0.3-0.5 (checklists)
- **General info:** 0.0-0.2 (rarely relevant)

---

## Query Type → Source Mapping

Quick reference for routing decisions:

### troubleshooting
**Primary:** Jira (0.7-1.0)  
**Secondary:** Blog (0.4-0.7), PDFs (0.3-0.5)  
**Why:** Jira has resolved tickets with fixes; blog has troubleshooting guides

### migration_procedure
**Primary:** Blog (0.7-0.9)  
**Secondary:** Jira (0.5-0.7), PDFs (0.3-0.5)  
**Why:** Blog has step-by-step procedures; Jira has workarounds

### general_info
**Primary:** Blog (0.7-1.0)  
**Secondary:** PDFs (0.3-0.5), Jira (0.2-0.4)  
**Why:** Blog is primary product information source

### configuration
**Primary:** Blog (0.7-0.9)  
**Secondary:** PDFs (0.5-0.7), SharePoint (0.3-0.5)  
**Why:** Blog has setup guides; PDFs have technical details

### compliance
**Primary:** SharePoint (0.8-1.0)  
**Secondary:** Blog (0.3-0.5)  
**Why:** SharePoint has certificates and official docs

### sales
**Primary:** Transcripts (0.7-1.0)  
**Secondary:** Blog (0.4-0.6)  
**Why:** Transcripts have real customer conversations

### technical
**Primary:** PDFs (0.7-1.0)  
**Secondary:** Blog (0.3-0.5)  
**Why:** PDFs have detailed technical documentation

### pricing
**Primary:** Excel (0.8-1.0)  
**Secondary:** Transcripts (0.5-0.7), Blog (0.3-0.5)  
**Why:** Excel has pricing tables; transcripts have discussions

### best_practices
**Primary:** Blog (0.7-0.9)  
**Secondary:** Transcripts (0.4-0.6), Jira (0.3-0.5)  
**Why:** Blog has best practices articles; transcripts have customer experiences

---

## Common Patterns

### Signals for Each Source

**Jira Signals:**
- Error codes (500, 404, etc.)
- Stack traces
- "failed", "error", "not working", "broken"
- Ticket references (PRI-, CFITS-)
- "migration failed"

**Blog Signals:**
- "how to", "step by step", "guide"
- "during migration", "ongoing migration"
- "best practice", "recommended"
- General product questions

**SharePoint Signals:**
- "SOC", "certificate", "certification"
- "compliance", "security", "policy"
- "official", "legal"

**Transcript Signals:**
- "customer", "sales", "objection"
- "pricing discussion", "customer asked"
- "demo", "conversation"

**PDF Signals:**
- "API", "technical specification"
- "architecture", "detailed documentation"
- "deep dive", "technical details"

**Excel Signals:**
- "pricing", "cost", "how much"
- "feature comparison", "compare"
- "matrix", "table"

---

## Anti-Patterns to Avoid

### Don't Use Blog For:
- ❌ Compliance certificates (use SharePoint)
- ❌ Specific error resolutions (use Jira)
- ❌ Detailed API docs (use PDFs)

### Don't Use Jira For:
- ❌ General product info (use Blog)
- ❌ Official certificates (use SharePoint)
- ❌ Sales conversations (use Transcripts)

### Don't Use SharePoint For:
- ❌ How-to guides (use Blog)
- ❌ Error troubleshooting (use Jira)

### Don't Use Transcripts For:
- ❌ Official product features (use Blog/PDFs)
- ❌ Technical documentation (use PDFs)
- ❌ Definitive answers (ALWAYS secondary to official docs)

---

## Update History

- **2026-01-22:** Initial creation based on log analysis
- **Source:** Terminal log analysis, routing test results

---

**Note:** This reference is based on observed patterns. Actual content may vary. Update this document as new data sources are added or content patterns change.
