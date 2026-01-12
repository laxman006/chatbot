# Shared Chat Feature

## Overview

Allows users to share chat sessions with others via unique share tokens. Shared chats are read-only and have expiration dates.

---

## Related Files

### Backend Files

#### Shared Chat Storage
- **`app/mongodb_memory.py`**
  - `create_shared_chat()` - Create shared chat session (line 800+)
  - `get_shared_chat()` - Get shared chat by token (line 900+)
  - `increment_share_count()` - Increment access count (line 1000+)

#### Shared Chat Endpoints
- **`app/endpoints.py`**
  - `POST /chat/share/{session_id}` - Share session (line 2939)
  - `GET /chat/shared/{share_token}` - Get shared chat (line 3023)

#### Session Management
- **`app/mongodb_memory.py`**
  - `get_session_by_id()` - Get original session (line 500+)

### Frontend Files

#### Shared Chat Pages
- **`frontend/src/app/chat/shared/[token]/page.tsx`**
  - Shared chat view page
  - Read-only chat interface

- **`frontend/src/app/api/shared-chat/[token]/route.ts`**
  - API route for shared chat (if exists)

#### Chat Components
- **`frontend/src/components/ChatInterface.tsx`**
  - Handles read-only mode for shared chats
  - Disables input when `readOnly={true}`

- **`frontend/src/components/ChatHeader.tsx`**
  - Share button
  - Share link generation

#### API Integration
- **`frontend/src/lib/api.ts`**
  - `shareSession()` - Share session API call
  - `getSharedChat()` - Get shared chat API call

---

## Feature Workflow

1. **User clicks share** → Frontend calls `POST /chat/share/{session_id}`
2. **Backend generates token** → Creates unique share token
3. **Creates shared chat** → Stores in `shared_chats` collection
4. **Returns share URL** → Frontend receives share link
5. **User shares link** → Others can access via token
6. **Access shared chat** → `GET /chat/shared/{token}`
7. **Read-only view** → Messages displayed but input disabled
8. **Access tracking** → Increments `access_count`

---

## Key Functions

### Backend
- `share_chat_session()` - Create shared chat
- `get_shared_chat_session()` - Get shared chat
- `create_shared_chat()` - Store shared chat in MongoDB
- `get_shared_chat()` - Retrieve shared chat

### Frontend
- Share button in chat header
- Shared chat page component
- Read-only chat interface

---

## Database Schema

### shared_chats Collection
```python
{
    "share_token": str,  # Unique token (UUID)
    "session_id": str,   # Original session ID
    "user_email": str,   # Creator email
    "expires_at": datetime,  # Expiration (7 days default)
    "created_at": datetime,
    "access_count": int,  # Number of accesses
    "read_only": True
}
```

---

## Share Token Generation

- **Format:** UUID v4
- **Uniqueness:** Guaranteed by MongoDB unique index
- **Expiration:** 7 days from creation (default)
- **Access:** Unlimited reads until expiration

---

## Security Features

1. **Read-Only Access** - Shared chats cannot be modified
2. **Expiration** - Tokens expire after 7 days
3. **Token Validation** - Validates token exists and not expired
4. **Access Tracking** - Tracks number of accesses
5. **Session Isolation** - Original session remains private

---

## Share URL Format

```
/chat/shared/{share_token}
```

Example:
```
/chat/shared/550e8400-e29b-41d4-a716-446655440000
```

---

## Frontend Behavior

### Share Button
- Located in chat header
- Generates share link
- Copies to clipboard
- Shows share count

### Shared Chat View
- Read-only mode
- Input disabled
- "Continue in thread" button to create editable copy
- Shows expiration date
- Displays access count

---

## Configuration

**Expiration:**
- Default: 7 days
- Configurable in `create_shared_chat()`

**Token Format:**
- UUID v4
- Stored in MongoDB with unique index

---

**Last Updated:** 2025-01-09
