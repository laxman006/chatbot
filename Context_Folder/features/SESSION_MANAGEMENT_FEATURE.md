# Session Management Feature

## Overview

Manages chat sessions, conversation history, and user data persistence. Sessions can be saved, retrieved, shared, and managed across multiple devices.

---

## Related Files

### Backend Files

#### Session Storage
- **`app/mongodb_memory.py`**
  - `save_session()` - Save or update chat session (line 278)
  - `get_all_sessions()` - Get all user sessions (line 400+)
  - `get_user_sessions()` - Get sessions for specific user (line 450+)
  - `get_session_by_id()` - Get session by ID (line 500+)
  - `get_user_chat_messages()` - Get messages for user (line 600+)

#### Session Store
- **`app/session_store.py`**
  - Session cookie management
  - Session creation, retrieval, validation
  - Token refresh handling

#### Session Endpoints
- **`app/endpoints.py`**
  - `POST /chat/sessions/save` - Save session (line 2607)
  - `GET /chat/sessions/all` - Get all sessions (line 2667)
  - `GET /chat/sessions/user/{user_id}` - Get user sessions (line 2724)
  - `GET /chat/sessions/{session_id}` - Get specific session (line 2738)
  - `GET /chat/sessions/messages/{user_id}` - Get user messages (line 2755)
  - `GET /chat/history/{user_id}` - Get chat history (line 2552)
  - `DELETE /chat/history/{user_id}` - Clear chat history (line 2564)
  - `POST /chat/history/rebuild` - Rebuild chat history (line 2576)

#### Conversation History
- **`app/mongodb_memory.py`**
  - `add_to_conversation()` - Add message to conversation (line 165)
  - `get_conversation_context()` - Get conversation context (line 200)
  - `get_user_chat_history()` - Get full chat history (line 215)
  - `clear_user_chat_history()` - Clear chat history (line 219)
  - `get_or_create_user_conversation()` - Get/create conversation (line 140)

### Frontend Files

#### Session Pages
- **`frontend/src/app/chats/page.tsx`**
  - All sessions list page

- **`frontend/src/app/chat/[sessionId]/page.tsx`**
  - Individual session page

#### Session Components
- **`frontend/src/components/ChatSidebar.tsx`**
  - Sidebar with session list
  - Session selection, creation, deletion

- **`frontend/src/components/SessionCard.tsx`**
  - Session card component
  - Displays session title, message count, date

#### Session Utilities
- **`frontend/src/lib/session-utils.ts`**
  - Session utility functions
  - Session creation, retrieval, management

#### API Integration
- **`frontend/src/lib/api.ts`**
  - `saveSession()` - Save session API call
  - `getSessions()` - Get sessions API call
  - `getSession()` - Get specific session API call
  - `deleteSession()` - Delete session API call

---

## Feature Workflow

1. **User starts chat** → Creates new session or loads existing
2. **Messages sent** → Saved to conversation history
3. **Session save** → User saves session with title
4. **Session retrieval** → Load session from MongoDB
5. **Session list** → Display all user sessions
6. **Session deletion** → Remove session from database

---

## Key Functions

### Backend
- `save_session()` - Save chat session
- `get_user_sessions()` - Get user's sessions
- `get_session_by_id()` - Get specific session
- `add_to_conversation()` - Add message to history
- `get_user_chat_history()` - Get conversation history

### Frontend
- `ChatSidebar` - Session list component
- `SessionCard` - Session display component
- `saveSession()` - Save session API call

---

## Database Collections

### chat_sessions
```python
{
    "session_id": str,
    "user_id": str,
    "user_email": str,
    "user_name": str,
    "title": str,
    "messages": List[Dict],
    "created_at": datetime,
    "updated_at": datetime,
    "message_count": int
}
```

### chat_history (legacy)
```python
{
    "user_id": str,
    "messages": List[Dict],
    "created_at": datetime,
    "last_updated": datetime
}
```

---

## Session Operations

### Create Session
- Automatically created when user starts new chat
- Session ID: UUID v4

### Save Session
- User can save session with custom title
- Updates `updated_at` timestamp

### Load Session
- Retrieve session by ID
- Load all messages

### Delete Session
- Remove session from database
- Clear associated messages

### List Sessions
- Get all sessions for user
- Sorted by `created_at` descending

---

## Configuration

**MongoDB:**
- `MONGODB_DATABASE` - Database name
- `MONGODB_CHAT_COLLECTION` - Collection name

**Session Limits:**
- Max messages per conversation: 20 (for context)
- Conversation context: Last 5 messages

---

**Last Updated:** 2025-01-09
