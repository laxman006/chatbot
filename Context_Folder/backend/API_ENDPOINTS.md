# API Endpoints Documentation

## Overview

The CloudFuze Chatbot backend is built with **FastAPI** and provides RESTful API endpoints for chat functionality, session management, analytics, and administration.

**Location:** `app/endpoints.py`  
**Server:** `server.py`

---

## 🔐 Authentication Endpoints

### `POST /auth/microsoft/callback`
**Purpose:** Microsoft OAuth callback handler  
**Authentication:** None (public endpoint)

**Flow:**
1. Receives authorization code from Microsoft
2. Exchanges code for access token
3. Fetches user info from Microsoft Graph API
4. Validates email domain (`@cloudfuze.com`)
5. Returns JWT token to frontend

**Response:**
```json
{
  "access_token": "jwt_token_here",
  "user": {
    "user_id": "user@cloudfuze.com",
    "name": "User Name",
    "email": "user@cloudfuze.com"
  }
}
```

---

## 💬 Chat Endpoints

### `POST /chat`
**Purpose:** Non-streaming chat endpoint  
**Authentication:** Required (Bearer token)

**Request Body:**
```json
{
  "question": "What is CloudFuze?",
  "session_id": "uuid-here",
  "user_id": "user@cloudfuze.com",
  "user_name": "User Name",
  "user_email": "user@cloudfuze.com"
}
```

**Response:**
```json
{
  "answer": "CloudFuze is...",
  "session_id": "uuid-here",
  "trace_id": "langfuse-trace-id"
}
```

**Workflow:**
1. Authenticate user
2. Check for corrected responses (auto-correction system)
3. Classify query type (conversational vs informational)
4. If informational:
   - Classify intent
   - Expand query
   - Retrieve documents (hybrid retrieval)
   - Rerank documents
   - Generate response with LLM
5. Track analytics (Langfuse)
6. Save to session

---

### `POST /chat/stream`
**Purpose:** Streaming chat endpoint (SSE)  
**Authentication:** Required

**Request Body:** Same as `/chat`

**Response:** Server-Sent Events (SSE) stream
```
data: {"type": "token", "content": "CloudFuze"}
data: {"type": "token", "content": " is"}
...
data: {"type": "done", "trace_id": "trace-id"}
```

**Features:**
- Real-time token streaming
- Progress updates
- Error handling
- Token monitoring

---

## 📚 Session Management Endpoints

### `GET /chat/history`
**Purpose:** Get user's chat history  
**Authentication:** Required

**Query Parameters:**
- `limit` (optional): Number of messages to return

**Response:**
```json
{
  "messages": [
    {
      "role": "user",
      "content": "What is CloudFuze?",
      "timestamp": "2025-01-09T10:00:00Z"
    },
    {
      "role": "assistant",
      "content": "CloudFuze is...",
      "timestamp": "2025-01-09T10:00:01Z"
    }
  ]
}
```

---

### `DELETE /chat/history`
**Purpose:** Clear user's chat history  
**Authentication:** Required

**Response:**
```json
{
  "status": "success",
  "message": "Chat history cleared"
}
```

---

### `POST /chat/sessions`
**Purpose:** Save a chat session  
**Authentication:** Required

**Request Body:**
```json
{
  "session_id": "uuid-here",
  "title": "Session Title",
  "messages": [...]
}
```

---

### `GET /chat/sessions`
**Purpose:** Get all user's chat sessions  
**Authentication:** Required

**Response:**
```json
{
  "sessions": [
    {
      "session_id": "uuid-here",
      "title": "Session Title",
      "created_at": "2025-01-09T10:00:00Z",
      "message_count": 10
    }
  ]
}
```

---

### `GET /chat/sessions/{session_id}`
**Purpose:** Get specific session  
**Authentication:** Required

---

### `GET /chat/sessions/{session_id}/messages`
**Purpose:** Get messages for a session  
**Authentication:** Required

---

## 🔗 Shared Chat Endpoints

### `POST /chat/sessions/{session_id}/share`
**Purpose:** Share a chat session  
**Authentication:** Required

**Response:**
```json
{
  "share_token": "unique-token",
  "share_url": "/chat/shared/{token}",
  "expires_at": "2025-01-16T10:00:00Z"
}
```

**Features:**
- Generates unique share token
- Sets expiration (7 days default)
- Creates read-only shared session
- Tracks share count

---

### `GET /chat/shared/{token}`
**Purpose:** Get shared chat session (read-only)  
**Authentication:** None (public)

**Response:**
```json
{
  "session": {
    "title": "Shared Session",
    "messages": [...],
    "read_only": true
  }
}
```

---

## 👤 User Profile Endpoints

### `GET /user/profile`
**Purpose:** Get user profile  
**Authentication:** Required

**Response:**
```json
{
  "user_id": "user@cloudfuze.com",
  "name": "User Name",
  "email": "user@cloudfuze.com",
  "job_title": "Software Engineer",
  "statistics": {
    "total_questions": 150,
    "total_sessions": 20
  }
}
```

---

### `PUT /user/profile`
**Purpose:** Update user profile  
**Authentication:** Required

**Request Body:**
```json
{
  "job_title": "Senior Software Engineer"
}
```

---

## 📊 Analytics Endpoints (Admin Only)

### `GET /admin/users/summary`
**Purpose:** Get all-time user statistics  
**Authentication:** Admin required

**Response:**
```json
{
  "total_users": 100,
  "total_questions": 5000,
  "unique_questions": 2000,
  "total_sessions": 500
}
```

---

### `GET /admin/rankers`
**Purpose:** Get ranked users by date range  
**Authentication:** Admin required

**Query Parameters:**
- `start_date`: YYYY-MM-DD
- `end_date`: YYYY-MM-DD
- `limit`: Number of results

**Response:**
```json
{
  "rankers": [
    {
      "user_id": "user@cloudfuze.com",
      "name": "User Name",
      "question_count": 50,
      "rank": 1
    }
  ],
  "date_range": {
    "start": "2025-01-01",
    "end": "2025-01-09"
  }
}
```

---

### `GET /admin/questions/top`
**Purpose:** Get most asked questions  
**Authentication:** Admin required

**Query Parameters:**
- `limit`: Number of questions (default: 10)

---

### `GET /admin/teams`
**Purpose:** Get team analytics  
**Authentication:** Admin required

**Response:**
```json
{
  "teams": [
    {
      "team_name": "Development",
      "total_questions": 500,
      "unique_questions": 200,
      "active_members": 10,
      "members": [...]
    }
  ]
}
```

---

## 👍 Feedback Endpoints

### `POST /feedback`
**Purpose:** Submit feedback for a response  
**Authentication:** Required

**Request Body:**
```json
{
  "trace_id": "langfuse-trace-id",
  "rating": "thumbs_up" | "thumbs_down",
  "comment": "Optional comment"
}
```

**Features:**
- Tracks feedback in Langfuse
- Triggers auto-correction for negative feedback
- Aggregates feedback statistics

---

## 🔧 Utility Endpoints

### `GET /health`
**Purpose:** Health check  
**Authentication:** None

**Response:**
```json
{
  "status": "healthy",
  "vectorstore": "initialized",
  "mongodb": "connected"
}
```

---

## 🔄 Query Processing Pipeline

### 1. Intent Classification
- **Function:** `classify_intent(query)`
- **Branches:**
  - `general_business`
  - `slack_teams_migration`
  - `sharepoint_docs`
  - `pricing`
  - `troubleshooting`
- **Method:** Pattern matching + LLM classification

### 2. Query Expansion
- **Function:** `expand_query_with_intent(query, intent)`
- **Purpose:** Add intent-specific keywords for better retrieval

### 3. Document Retrieval
- **Function:** `perplexity_style_retrieve(query, k_dense, k_bm25, k_final)`
- **Steps:**
  1. Dense retrieval (embeddings)
  2. Sparse retrieval (BM25)
  3. Score normalization
  4. Metadata boosting
  5. Hybrid retrieval (primary + secondary KB)
  6. Cross-encoder reranking

### 4. Response Generation
- **LLM:** OpenAI GPT-4o-mini or Google Gemini
- **Prompt:** System prompt + context + question
- **Streaming:** Real-time token generation

---

## 🛡️ Security Features

1. **JWT Authentication:** All protected endpoints require valid JWT
2. **Email Domain Validation:** Only `@cloudfuze.com` emails allowed
3. **Session Isolation:** Users can only access their own sessions
4. **Read-Only Shared Sessions:** Shared chats are read-only
5. **Admin Protection:** Admin endpoints require admin role

---

## 📝 Error Handling

All endpoints return consistent error responses:

```json
{
  "error": "Error message",
  "status": 400,
  "details": "Additional details"
}
```

**Common Status Codes:**
- `200`: Success
- `400`: Bad Request
- `401`: Unauthorized
- `403`: Forbidden
- `404`: Not Found
- `500`: Internal Server Error

---

## 🔍 Key Functions Reference

### Intent Classification
- `classify_intent(query)` - Classify user intent
- `is_transcript_specific_query(query)` - Detect transcript queries

### Retrieval
- `perplexity_style_retrieve()` - Main retrieval function
- `retrieve_with_branch_filter()` - Intent-based retrieval
- `hybrid_ranking()` - Combine semantic + keyword scores

### Session Management
- `save_session()` - Save chat session
- `get_user_sessions()` - Get user's sessions
- `create_shared_chat()` - Create shared session

### Analytics
- `get_user_statistics()` - Get user stats
- `get_rankers_by_date()` - Get ranked users
- `get_most_asked_questions()` - Top questions

---

**Last Updated:** 2025-01-09  
**File:** `app/endpoints.py`
