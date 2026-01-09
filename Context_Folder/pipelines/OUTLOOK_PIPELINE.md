# Outlook Email Processing Pipeline Documentation

## Overview

Fetches email conversation threads from Outlook using Microsoft Graph API and converts them into LangChain Documents for the knowledge base.

**Location:** `app/outlook_processor.py`

---

## Pipeline Architecture

```
Outlook Mailbox
    │
    ├─► Authenticate (Microsoft Graph API)
    │   └─► sharepoint_auth.get_headers()
    │
    ├─► Get Folder ID
    │   ├─► Search by folder name
    │   └─► Recursive search in child folders
    │
    ├─► Fetch Emails
    │   ├─► Filter by date range (optional)
    │   ├─► Limit to MAX_EMAILS
    │   └─► Get email properties
    │
    ├─► Group into Threads
    │   ├─► Group by conversation ID
    │   ├─► Sort by date
    │   └─► Combine related emails
    │
    ├─► Extract Thread Content
    │   ├─► Subject
    │   ├─► Participants
    │   ├─► Date range
    │   ├─► Email count
    │   └─► Combined email content
    │
    ├─► Create Documents
    │   └─► One document per thread
    │
    ├─► Chunk Documents
    │   └─► RecursiveCharacterTextSplitter (1500 tokens, 200 overlap)
    │
    └─► Add Metadata
        └─► source_type, tag, conversation_topic, participants, date_range
```

---

## Class: `OutlookProcessor`

**Location:** `app/outlook_processor.py` (line 25)

**Purpose:** Process Outlook emails and group them into conversation threads

---

## Initialization

### `__init__()`
**Location:** Lines 28-31

**Configuration:**
- `auth`: SharePoint auth instance (shared with SharePoint)
- `base_url`: Microsoft Graph API base URL
- `user_email`: Outlook user email (from `OUTLOOK_USER_EMAIL`)

---

## Key Functions

### `get_folder_id(folder_name)`
**Location:** Lines 52-82

**Purpose:** Get folder ID by folder name

**What it does:**
1. Gets all mail folders for user
2. Searches for folder by display name (case-insensitive)
3. If not found in root, searches child folders recursively
4. Returns folder ID or None

**Returns:** Folder ID string or None

---

### `_search_child_folders(parent_folder_id, folder_name)`
**Location:** Lines 84-100+

**Purpose:** Recursively search child folders

**What it does:**
1. Gets child folders of parent
2. Searches for matching folder name
3. Recursively searches deeper if not found
4. Returns folder ID or None

**Returns:** Folder ID string or None

---

### `fetch_emails(folder_id, max_emails, date_filter)`
**Location:** Lines 100-200+

**Purpose:** Fetch emails from folder

**What it does:**
1. Builds Graph API URL for folder emails
2. Applies date filter if provided
3. Fetches emails with pagination
4. Limits to `max_emails`
5. Returns list of email dictionaries

**Email Properties:**
- `id` - Email ID
- `subject` - Email subject
- `body` - Email body (HTML or text)
- `from` - Sender
- `toRecipients` - Recipients
- `conversationId` - Conversation ID
- `receivedDateTime` - Received date
- `sentDateTime` - Sent date

**Returns:** List of email dictionaries

---

### `group_emails_into_threads(emails)`
**Location:** Lines 200-300+

**Purpose:** Group emails into conversation threads

**What it does:**
1. Groups emails by `conversationId`
2. Sorts emails within thread by date
3. Combines related emails
4. Returns list of thread dictionaries

**Thread Dictionary:**
```python
{
    "conversation_id": str,
    "subject": str,
    "participants": List[str],
    "emails": List[EmailDict],
    "first_email_date": datetime,
    "last_email_date": datetime,
    "email_count": int
}
```

**Returns:** List of thread dictionaries

---

### `process_outlook_content()`
**Location:** Lines 300-400+

**Purpose:** Main processing function

**What it does:**
1. Gets folder ID from `OUTLOOK_FOLDER_NAME`
2. Fetches emails (with date filter if configured)
3. Groups emails into threads
4. Converts threads to LangChain Documents
5. Chunks documents
6. Returns list of documents

**Returns:** List of LangChain Documents

---

## Document Creation

### Thread to Document
```python
Document(
    page_content=f"""
Thread Subject: {subject}
Participants: {participants}
Date Range: {date_range}
Number of Emails: {email_count}

--- Email Thread Content ---

{combined_email_content}
""",
    metadata={
        "source_type": "outlook" or "email",
        "tag": "email" or "outlook",
        "conversation_topic": subject,
        "participants": ", ".join(participants),
        "date_range": f"{first_date} to {last_date}",
        "email_count": email_count,
        "first_email_date": first_date,
        "last_email_date": last_date,
        "conversation_id": conversation_id,
        "kb_tier": "primary"
    }
)
```

---

## Chunking

### Text Splitter
```python
RecursiveCharacterTextSplitter(
    chunk_size=1500,
    chunk_overlap=200,
    separators=["\n\n", "\n", ". ", " ", ""]
)
```

**Note:** Entire thread kept together when possible (thread = one chunk)

---

## Configuration

**From `config.py`:**
```python
ENABLE_OUTLOOK_SOURCE = True
OUTLOOK_USER_EMAIL = "user@cloudfuze.com"
OUTLOOK_FOLDER_NAME = "Folder Name"
OUTLOOK_MAX_EMAILS = 1000
OUTLOOK_DATE_FILTER = 30  # Days (optional)
```

---

## Authentication

**Location:** `app/sharepoint_auth.py`

**Method:** Microsoft Graph API authentication (shared with SharePoint)

**Functions:**
- `sharepoint_auth.get_headers()` - Get auth headers
- Uses application permissions

---

## Email Thread Formatting

### Combined Thread Content
```
From: sender@cloudfuze.com
To: recipient@cloudfuze.com
Date: 2025-01-09 10:00:00
Subject: Email Subject

Email body content here...

---

From: recipient@cloudfuze.com
To: sender@cloudfuze.com
Date: 2025-01-09 10:30:00
Subject: Re: Email Subject

Reply content here...
```

---

## Usage

### Process Outlook Content
```python
from app.outlook_processor import process_outlook_content

documents = process_outlook_content()
# Returns List[Document]
```

### Custom Folder
```python
from app.outlook_processor import OutlookProcessor

processor = OutlookProcessor()
folder_id = processor.get_folder_id("Custom Folder")
emails = processor.fetch_emails(folder_id, max_emails=100)
```

---

## Processing Statistics

```
[*] Looking for folder: Folder Name
[OK] Found folder 'Folder Name' with ID: folder-id-here
[*] Fetching emails...
[OK] Fetched 50 emails
[OK] Grouped into 10 conversation threads
[OK] Created 10 documents
[OK] Chunked into 15 documents
```

---

## Error Handling

### Authentication Errors
- Invalid credentials → Log error, raise exception
- Token expired → Re-authenticate, retry

### Folder Errors
- Folder not found → Log warning, return empty
- Permission denied → Log error, skip

### Email Errors
- API error → Log error, skip email
- Invalid email → Log warning, continue

---

## Integration

### Vectorstore Integration
```python
from app.outlook_processor import process_outlook_content
from app.enhanced_helpers import EnhancedVectorstoreBuilder

outlook_docs = process_outlook_content()
builder = EnhancedVectorstoreBuilder()
chunks = builder.process_documents(outlook_docs, "email")
```

---

## Key Files

- **`app/outlook_processor.py`** - Main Outlook processor
- **`app/sharepoint_auth.py`** - Authentication (shared)
- **`app/enhanced_helpers.py`** - Enhanced processing

---

## Best Practices

1. **Thread Grouping:** Keep entire threads together
2. **Date Filtering:** Use date filters to limit emails
3. **Participant Tracking:** Include all participants
4. **Subject Preservation:** Keep original subject
5. **Chunk Appropriately:** Thread-based chunking preferred

---

**Last Updated:** 2025-01-09  
**File:** `app/outlook_processor.py`
