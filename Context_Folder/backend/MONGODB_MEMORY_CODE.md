# MongoDB Memory Management - Code Documentation

## File: `app/mongodb_memory.py`

This file handles MongoDB-based chat history, session management, and user data storage.

---

## Class: `MongoDBMemoryManager`

**Location:** Lines 14-1340

**Purpose:** Manages MongoDB connections and operations for chat history, sessions, and user data

---

## Initialization

### `__init__()`
**Location:** Lines 17-21

**Attributes:**
- `client`: AsyncIOMotorClient (None initially)
- `database`: MongoDB database instance
- `collection`: MongoDB collection instance
- `_connection_lock`: asyncio.Lock for thread-safe connection

---

## Connection Management

### `connect()`
**Location:** Lines 23-83

**Purpose:** Initialize MongoDB connection with SSL handling

**What it does:**
1. Uses connection lock for thread safety
2. Detects if MongoDB Atlas (checks for "mongodb+srv://" or "mongodb.net")
3. **For Atlas:**
   - Uses TLS with certificate validation
   - `tlsAllowInvalidCertificates=False`
   - `tlsAllowInvalidHostnames=False`
4. **For Local MongoDB:**
   - Tries TLS disabled first
   - Falls back to TLS enabled with invalid certificates allowed
5. Sets timeouts:
   - `serverSelectionTimeoutMS=5000`
   - `connectTimeoutMS=10000`
   - `socketTimeoutMS=10000`
6. Tests connection with `admin.command('ping')`
7. Creates indexes via `_create_indexes()`

**Raises:** ConnectionFailure or Exception if connection fails

---

### `_create_indexes()`
**Location:** Lines 85-100+

**Purpose:** Create database indexes for performance

**Indexes Created:**
1. **chat_history collection:**
   - `user_id` (unique)
   - `last_updated` (for sorting)

2. **chat_sessions collection:**
   - `session_id` (unique)
   - `user_id`
   - `created_at`
   - `(created_at, -1)` (descending for recent first)

3. **shared_chats collection:**
   - `share_token` (unique)
   - `session_id`
   - `expires_at`

---

## Chat History Operations

### `add_to_conversation(user_id, role, content)`
**Location:** Lines 200-250 (approximate)

**Purpose:** Add message to user's conversation history

**What it does:**
1. Gets or creates user conversation
2. Appends message: `{"role": role, "content": content, "timestamp": datetime.utcnow()}`
3. Keeps only last 20 messages (prevents context overflow)
4. Updates `last_updated` timestamp

---

### `get_conversation_context(user_id, limit=5)`
**Location:** Lines 250-300 (approximate)

**Purpose:** Get formatted conversation context for LLM

**What it does:**
1. Gets user's conversation history
2. Takes last N messages (default: 5)
3. Formats as: `"Previous conversation:\n[role]: [content]\n..."`
4. Returns formatted string

---

### `get_user_chat_history(user_id, limit=50)`
**Location:** Lines 300-350 (approximate)

**Purpose:** Get user's chat history for display

**Returns:** List of message dictionaries with role, content, timestamp

---

### `clear_user_chat_history(user_id)`
**Location:** Lines 350-400 (approximate)

**Purpose:** Clear all chat history for user

**What it does:**
- Updates user document: `messages = []`
- Updates `last_updated` timestamp

---

## Session Management

### `save_session(session_id, user_id, title, messages)`
**Location:** Lines 500-600 (approximate)

**Purpose:** Save or update chat session

**Session Document Structure:**
```python
{
    "session_id": str,
    "user_id": str,
    "title": str,
    "messages": List[Dict],
    "created_at": datetime,
    "updated_at": datetime,
    "message_count": int
}
```

**What it does:**
1. Creates or updates session document
2. Sets `created_at` if new session
3. Updates `updated_at` and `message_count`
4. Uses `upsert=True` (create if not exists)

---

### `get_all_sessions(user_id)`
**Location:** Lines 600-700 (approximate)

**Purpose:** Get all sessions for a user

**Returns:** List of session documents, sorted by `created_at` descending

---

### `get_session_by_id(session_id)`
**Location:** Lines 700-800 (approximate)

**Purpose:** Get specific session by ID

**Returns:** Session document or None

---

## Shared Chat Operations

### `create_shared_chat(session_id, share_token, expires_at)`
**Location:** Lines 800-900 (approximate)

**Purpose:** Create shared chat session (read-only)

**Shared Chat Document Structure:**
```python
{
    "share_token": str,
    "session_id": str,
    "expires_at": datetime,
    "created_at": datetime,
    "access_count": int
}
```

**What it does:**
1. Creates shared chat document
2. Links to original session via `session_id`
3. Sets expiration (default: 7 days)
4. Initializes `access_count` to 0

---

### `get_shared_chat(share_token)`
**Location:** Lines 900-1000 (approximate)

**Purpose:** Get shared chat by token

**What it does:**
1. Finds shared chat by `share_token`
2. Checks if expired (`expires_at < datetime.utcnow()`)
3. Increments `access_count`
4. Gets original session via `session_id`
5. Returns session with `read_only=True` flag

**Raises:** HTTPException 404 if not found or expired

---

## User Profile Operations

### `update_user_profile(user_id, profile_data)`
**Location:** Lines 1000-1100 (approximate)

**Purpose:** Update user profile information

**Profile Fields:**
- `job_title`
- `department`
- `preferences`

**What it does:**
- Upserts user profile document
- Updates `last_updated` timestamp

---

### `get_user_profile(user_id)`
**Location:** Lines 1100-1200 (approximate)

**Purpose:** Get user profile

**Returns:** Profile document or default profile

---

### `get_user_statistics(user_id)`
**Location:** Lines 1200-1300 (approximate)

**Purpose:** Get user statistics (question count, session count, etc.)

**Returns:** Dictionary with statistics:
```python
{
    "total_questions": int,
    "total_sessions": int,
    "first_question_date": datetime,
    "last_question_date": datetime
}
```

---

## Analytics Operations

### `get_rankers_by_date(start_date, end_date, limit=100)`
**Location:** Lines 1300-1340

**Purpose:** Get ranked users by question count for date range

**What it does:**
1. Aggregates messages from chat_history collection
2. Filters by date range
3. Groups by user_id
4. Counts questions (role="user")
5. Sorts by count descending
6. Limits to top N users

**Returns:** List of user dictionaries with rank, question_count, user_id, name

---

## Configuration

**From `config.py`:**
- `MONGODB_URL`: MongoDB connection string
- `MONGODB_DATABASE`: Database name
- `MONGODB_CHAT_COLLECTION`: Collection name for chat history

---

## Collections

1. **chat_history:** User conversation messages
2. **chat_sessions:** Saved chat sessions
3. **shared_chats:** Shared chat sessions (read-only)
4. **user_profiles:** User profile information

---

## Error Handling

- **Connection Errors:** Logged and raised
- **Duplicate Key Errors:** Handled gracefully
- **Missing Documents:** Return None or default values
- **Expired Sessions:** Return 404 HTTPException

---

## Usage Example

```python
from app.mongodb_memory import mongodb_memory

# Connect
await mongodb_memory.connect()

# Add message
await mongodb_memory.add_to_conversation(
    user_id="user@cloudfuze.com",
    role="user",
    content="What is CloudFuze?"
)

# Get history
history = await mongodb_memory.get_user_chat_history("user@cloudfuze.com")

# Save session
await mongodb_memory.save_session(
    session_id="uuid-here",
    user_id="user@cloudfuze.com",
    title="My Chat",
    messages=[...]
)
```

---

**Last Updated:** 2025-01-09  
**File:** `app/mongodb_memory.py`
