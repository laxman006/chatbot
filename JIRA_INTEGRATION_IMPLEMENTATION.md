# Jira Integration Implementation - Complete Documentation

## Table of Contents
1. [Overview](#overview)
2. [Decision: Option 1 vs Option 2](#decision-option-1-vs-option-2)
3. [Migration KB Board Implementation](#migration-kb-board-implementation)
4. [AI Suggestions Extraction](#ai-suggestions-extraction)
5. [Data Refinement Process](#data-refinement-process)
6. [Field Extraction Details](#field-extraction-details)
7. [Testing](#testing)
8. [Configuration](#configuration)
9. [Next Steps](#next-steps)

---

## Overview

This document outlines the complete implementation of Jira ticket integration into the chatbot's knowledge base. The system extracts tickets from the **Migration KB Board (PRI project)** in the **Production Issue** space, focusing on closed/resolved tickets with specific fields prioritized.

### Key Requirements
- ✅ Extract tickets from Migration KB Board (PRI project)
- ✅ Only closed/resolved tickets
- ✅ Priority fields: Ticket ID, Date/Time, Description, Root Cause, Combination
- ✅ Comments are less priority (but included)
- ✅ No attachments
- ✅ Extract AI suggestions when available

---

## Decision: Option 1 vs Option 2

### Option 1: VectorDB with Existing Tickets (✅ CHOSEN)
**Approach:** Add existing Jira tickets to vectorDB, retrieve similar issues when users ask questions.

**Pros:**
- ✅ Fast responses (no API calls during queries)
- ✅ Works offline
- ✅ Lower API rate limit risk
- ✅ Cost-effective (no per-query API calls)
- ✅ Leverages existing hybrid retrieval (dense + BM25 + reranking)
- ✅ Learns from historical resolved tickets
- ✅ Scales well with many tickets

**Cons:**
- ⚠️ Data can become stale (requires periodic updates)
- ⚠️ May miss very recent tickets

### Option 2: Live API Integration
**Approach:** Use live API to get tickets and understand/resolve in real-time.

**Pros:**
- ✅ Always up-to-date
- ✅ Can access latest tickets immediately
- ✅ Can fetch specific tickets by ID

**Cons:**
- ❌ Slower (API call per query)
- ❌ Higher API rate limit risk
- ❌ Higher cost (per-query calls)
- ❌ May return incomplete/unresolved tickets
- ❌ Network dependency

### Final Decision
**Option 1 (VectorDB) is the primary approach** - it's already working and efficient. Option 2 should complement it for specific cases like:
- User asks for specific ticket ID (e.g., "CFITS-123")
- User asks for latest/recent tickets
- Real-time status checks

---

## Migration KB Board Implementation

### Project Details
- **Project Key:** PRI
- **Board:** Migration KB Board
- **Space:** Production Issue
- **Status Filter:** Closed OR Resolved
- **Order:** Updated DESC (most recent first)

### JQL Query
```jql
project = PRI AND (status = Closed OR status = Resolved) ORDER BY updated DESC
```

### Required Fields (Priority Order)

1. **Ticket ID** (`issue.key`)
   - Example: `PRI-9314`
   - Source: `issue.key`

2. **Date/Time**
   - Created: `issue.fields.created`
   - Updated: `issue.fields.updated`
   - Resolved: `issue.fields.resolutiondate`
   - Format: ISO 8601 (e.g., `2026-01-08T12:54:00.001+0200`)

3. **Description** (`issue.fields.description`)
   - Customer query/issue description
   - HTML cleaned and converted to plain text
   - **REQUIRED** - tickets without description are skipped

4. **Root Cause** (`customfield_10059`)
   - Fix description field
   - Field Name: "Root Cause :- Describe the root cause.(why, where, when)"
   - **HIGH PRIORITY** - Contains solution information

5. **Combination** (`customfield_10236`)
   - Migration combination type
   - Examples: "Teams to Teams", "Gmail - Gmail", "Dropbox - SharePoint"
   - Multi-select field (extracted as comma-separated values)

6. **Comments** (`issue.fields.comment.comments`)
   - Developer solutions/responses
   - **LOWER PRIORITY** - Included but not required
   - Extracted with author, body, created date

### Excluded Fields
- ❌ Attachments (not fetched)
- ❌ Worklogs
- ❌ Subtasks

---

## AI Suggestions Extraction

### Current Status
AI suggestions shown in Jira UI sidebar (Rovo) are **NOT directly accessible via REST API** until they are saved as comments.

### Implementation
The system detects AI suggestions when they appear as comments by looking for markers:
- "Uses AI"
- "Verify Results"
- "Rovo"
- "AI-generated"
- "↑ Uses AI"

### Extraction Logic
```python
def _is_ai_suggestion_comment(self, comment_body: str) -> bool:
    """Check if a comment contains AI-generated suggestions."""
    ai_markers = [
        'uses ai', 'verify results', 'ai-generated',
        'rovo', 'ai suggestion', '↑ uses ai'
    ]
    return any(marker in comment_body.lower() for marker in ai_markers)
```

### Structured Extraction
When AI suggestions are detected, the system extracts:
- **Summary:** Text before "Solution:" section
- **Solution Steps:** Numbered list (1. 2. 3. etc.)
- **Step Count:** Number of solution steps
- **Source:** "ai_suggestion_comment"

### Available Options to Access AI Suggestions

1. **Comments API** (✅ Implemented)
   - Works when suggestions are saved as comments
   - Automatic detection and extraction

2. **Comment Properties API**
   - Endpoint: `/rest/api/3/issue/{issueIdOrKey}/comment/{commentId}/properties`
   - May contain AI-related metadata

3. **Activity Stream / Changelog**
   - Endpoint: `/rest/api/3/issue/{issueIdOrKey}/changelog`
   - May contain suggestion events

4. **Custom Fields** (Tested - Not Found)
   - Searched all custom fields
   - No dedicated AI suggestion field found

5. **Service Management API**
   - Endpoint: `/rest/servicedeskapi/request/{issueIdOrKey}/suggestions`
   - May be available for Jira Service Management

6. **Jira Automation / Webhooks**
   - Set up automation to auto-save suggestions as comments

7. **GraphQL API** (If Available)
   - Some Jira instances support GraphQL queries

8. **Web Scraping** (Not Recommended)
   - Fragile, may violate terms of service

9. **Atlassian Intelligence API** (Requires Verification)
   - May require special permissions

### Current Behavior
- ✅ Detection logic implemented
- ✅ Extraction logic implemented
- ✅ Document formatting includes AI suggestions when found
- ⚠️ Requires suggestions to be saved as comments first

---

## Data Refinement Process

### Where Data is Added

**File:** `app/jira_processor.py`

**Main Entry Point:**
```python
def process_jira_content() -> List[Document]:
    """Main entry point for processing Jira content."""
    processor = JiraProcessor()
    return processor.process_jira_content()
```

**Integration Point:** `app/vectorstore.py`
```python
if "jira" in changed_sources:
    from app.jira_processor import process_jira_content
    jira_docs = process_jira_content()
    new_docs.extend(jira_docs)
```

### Data Flow

```
Jira API → JiraProcessor.fetch_tickets()
         → JiraProcessor._extract_ticket_data()
         → JiraProcessor.format_ticket_document()
         → Enhanced Pipeline (chunking, deduplication)
         → Vectorstore (ChromaDB)
```

### Refinement Steps

1. **HTML Cleaning**
   - Removes HTML tags from descriptions and comments
   - Uses BeautifulSoup for parsing

2. **Custom Field Extraction**
   - Handles multiple field types (string, list, dict, CustomFieldOption)
   - Extracts Combination values correctly

3. **Semantic Chunking**
   - Splits large tickets into chunks
   - Target: 800 tokens per chunk
   - Overlap: 200 tokens

4. **Deduplication**
   - Removes duplicate content
   - Threshold: 0.85 cosine similarity

5. **Graph Storage**
   - Stores document-chunk relationships
   - Enables relationship queries

---

## Field Extraction Details

### Custom Field Extraction Method

```python
def _extract_custom_field(self, issue, field_id: str, field_name: str) -> Optional[str]:
    """Extract custom field value safely."""
    try:
        if hasattr(issue.fields, field_id):
            field_value = getattr(issue.fields, field_id)
            if field_value:
                # Handle string fields
                if isinstance(field_value, str):
                    return self._clean_html(field_value)
                
                # Handle multi-select fields (like Combination)
                elif isinstance(field_value, list):
                    values = []
                    for item in field_value:
                        if hasattr(item, 'value'):
                            values.append(str(item.value))
                        elif isinstance(item, dict):
                            values.append(str(item.get('value', item)))
                        else:
                            values.append(str(item))
                    return ', '.join(values) if values else None
                
                # Handle dict fields
                elif isinstance(field_value, dict):
                    return str(field_value.get('value', field_value))
                
                # Handle JIRA CustomFieldOption objects
                elif hasattr(field_value, 'value'):
                    return str(field_value.value)
                
                else:
                    return str(field_value)
    except Exception as e:
        print(f"[WARNING] Could not extract {field_name} ({field_id}): {e}")
    return None
```

### Field Mappings

| Field | Jira Field | Custom Field ID | Type | Priority |
|-------|-----------|----------------|------|----------|
| Ticket ID | `issue.key` | - | String | High |
| Summary | `issue.fields.summary` | - | String | High |
| Created Date | `issue.fields.created` | - | DateTime | High |
| Updated Date | `issue.fields.updated` | - | DateTime | High |
| Resolved Date | `issue.fields.resolutiondate` | - | DateTime | High |
| Description | `issue.fields.description` | - | Text | **REQUIRED** |
| Root Cause | `issue.fields.customfield_10059` | customfield_10059 | Text | **HIGH** |
| Combination | `issue.fields.customfield_10236` | customfield_10236 | Multi-select | High |
| Comments | `issue.fields.comment.comments` | - | List | Low |
| Status | `issue.fields.status` | - | String | High |

---

## Testing

### Test File: `test_migration_kb_tickets.py`

**Purpose:** Verify data extraction from Migration KB Board

**What it Tests:**
- ✅ Connection to Jira
- ✅ JQL query execution
- ✅ Field extraction (all required fields)
- ✅ Data validation
- ✅ Field mapping verification

### Test Results (Latest Run)

```
Total Tickets Processed: 10
Tickets with Description: 10 (100%)
Tickets with Root Cause: 10 (100%)
Tickets with Combination: 10 (100%)
Total Comments: 33
```

### Sample Extracted Data

```json
{
  "ticket_id": "PRI-9314",
  "summary": "Tailor IT|T2T|Pilot Channel went into conflict...",
  "created_date": "2026-01-08T12:54:00.001+0200",
  "updated_date": "2026-01-08T16:18:15.095+0200",
  "resolved_date": "2026-01-08T16:18:15.050+0200",
  "status": "Resolved",
  "description": "Hi Team,\nDuring the pilot migration...",
  "root_cause": "Mapping issue.",
  "combination": "Teams to Teams",
  "comments_count": 6,
  "url": "https://cf2020.atlassian.net/browse/PRI-9314"
}
```

### Running Tests

```bash
# Test Migration KB Board extraction
python test_migration_kb_tickets.py

# Test AI suggestions extraction
python test_ai_suggestions_extraction.py

# Test general Jira suggestions (comprehensive)
python test_jira_suggestions.py
```

---

## Configuration

### Environment Variables (.env)

```env
# Jira Connection
JIRA_SERVER=https://cf2020.atlassian.net
JIRA_EMAIL=your-email@cloudfuze.com
JIRA_API_TOKEN=your-api-token

# Jira Project Configuration
JIRA_PROJECT_KEYS=PRI  # Migration KB Board
JIRA_MAX_ISSUES=1000
JIRA_DATE_FILTER=last_3_months  # Options: last_month, last_3_months, last_6_months, last_year

# Optional: Custom JQL Query (overrides project keys)
JIRA_JQL_QUERY=project = PRI AND (status = Closed OR status = Resolved) ORDER BY updated DESC

# Enable Jira Source
ENABLE_JIRA_SOURCE=true

# Vectorstore Initialization
INITIALIZE_VECTORSTORE=true  # Set to true to rebuild vectorstore
```

### Config File: `config.py`

Key settings:
- `JIRA_PROJECT_KEYS`: Comma-separated project keys
- `JIRA_MAX_ISSUES`: Maximum tickets to fetch
- `JIRA_DATE_FILTER`: Date range filter
- `ENABLE_JIRA_SOURCE`: Enable/disable Jira processing

---

## Document Formatting

### Structure

The formatted document includes:

```
# Jira Ticket: PRI-9314
Summary: [Ticket Summary]
Status: Resolved
Priority: Medium
Created: 2026-01-08T12:54:00.001+0200
Updated: 2026-01-08T16:18:15.095+0200
Resolved: 2026-01-08T16:18:15.050+0200

## Description
Reporter: [Reporter Name]

[Description content]

## Combination
[Combination value, e.g., "Teams to Teams"]

## Root Cause (Fix Description)
[Root cause content - HIGH PRIORITY]

## AI-Generated Solution (Rovo) [if available]
**Note:** This is an AI-generated solution. Verify results.

**Summary:** [Summary if available]

**Solution Steps:**
1. [Step 1]
2. [Step 2]
...

## Developer Solutions/Comments [if available]
### Solution 1 - [Author] ([Date])
[Comment body]
...
```

### Metadata

Each document includes metadata:
```python
{
    "source_type": "jira",
    "source": "jira_ticket",
    "tag": "jira/pri",
    "ticket_key": "PRI-9314",
    "ticket_summary": "[Summary]",
    "status": "Resolved",
    "root_cause": "[Root cause text]",
    "combination": "Teams to Teams",
    "has_ai_suggestions": true/false,
    "ai_solution_steps": 4,
    "comments_count": 6,
    "url": "https://cf2020.atlassian.net/browse/PRI-9314"
}
```

---

## Implementation Files

### Core Files

1. **`app/jira_processor.py`**
   - Main Jira processing logic
   - Ticket fetching and extraction
   - Custom field handling
   - AI suggestion detection

2. **`app/vectorstore.py`**
   - Integration point for Jira documents
   - Adds Jira tickets to vectorstore

3. **`config.py`**
   - Configuration settings
   - Environment variable handling

### Test Files

1. **`test_migration_kb_tickets.py`**
   - Tests Migration KB Board extraction
   - Validates field extraction
   - Generates test report

2. **`test_ai_suggestions_extraction.py`**
   - Tests AI suggestion detection
   - Validates extraction logic

3. **`test_jira_suggestions.py`**
   - Comprehensive AI suggestions testing
   - Tests multiple extraction methods

---

## Next Steps

### Immediate Actions

1. **Update Configuration**
   ```env
   JIRA_PROJECT_KEYS=PRI
   ENABLE_JIRA_SOURCE=true
   ```

2. **Rebuild Vectorstore** (if needed)
   ```env
   INITIALIZE_VECTORSTORE=true
   ```

3. **Monitor Extraction**
   - Check logs for extraction success
   - Verify field completeness
   - Monitor for missing Root Cause or Combination fields

### Future Enhancements

1. **Periodic Updates**
   - Set up scheduled sync for new tickets
   - Incremental updates (only new/updated tickets)

2. **AI Suggestions Enhancement**
   - Monitor for tickets with AI suggestions saved as comments
   - Consider automation to auto-save suggestions

3. **Data Quality**
   - Add validation for required fields
   - Filter out low-quality tickets
   - Prioritize tickets with Root Cause

4. **Performance Optimization**
   - Batch processing for large ticket volumes
   - Caching for frequently accessed tickets

---

## Troubleshooting

### Common Issues

1. **No tickets found**
   - Check JQL query syntax
   - Verify project key (PRI)
   - Check date filter settings
   - Verify status names (Closed, Resolved)

2. **Missing Root Cause or Combination**
   - Verify custom field IDs are correct
   - Check if fields exist in project
   - Verify field permissions

3. **Combination field shows object instead of value**
   - ✅ Fixed: Updated `_extract_custom_field()` to handle CustomFieldOption objects

4. **AI suggestions not detected**
   - Suggestions must be saved as comments first
   - Check comment content for AI markers
   - Verify detection logic

### Debug Commands

```bash
# Test specific ticket
python -c "from app.jira_processor import JiraProcessor; p = JiraProcessor(); issue = p.jira.issue('PRI-9314'); print(p._extract_ticket_data(issue))"

# Check field availability
python test_jira_suggestions.py
```

---

## Summary

✅ **Implementation Complete**
- Migration KB Board ticket extraction implemented
- All required fields extracted correctly
- AI suggestions detection ready
- Tested and verified with 10 tickets
- 100% field extraction success rate

✅ **Ready for Production**
- Configuration documented
- Test files available
- Error handling implemented
- Data validation in place

The system is ready to extract tickets from the Migration KB Board and add them to the vectorstore for knowledge base queries.

---

## Contact & Support

For issues or questions:
1. Check test files for examples
2. Review logs for error messages
3. Verify configuration settings
4. Test with individual tickets first

---

**Last Updated:** 2026-01-08
**Status:** ✅ Implementation Complete & Tested
