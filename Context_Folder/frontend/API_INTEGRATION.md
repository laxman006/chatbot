# API Integration Documentation

## Overview

How the frontend integrates with the FastAPI backend, including API helper functions, error handling, and authentication.

---

## API Helper Functions

### `getApiBase()`
**Location:** `src/lib/api.ts` (line 21)

**Purpose:** Get API base URL (proxy or direct)

**Logic:**
```typescript
// Development: Use Next.js proxy
if (NEXT_PUBLIC_USE_PROXY === 'true') {
  return '/api/proxy';
}

// Production: Use direct backend URL
return NEXT_PUBLIC_BACKEND_URL || NEXT_PUBLIC_API_URL || '';
```

**Returns:** Base URL string

---

### `apiFetch()`
**Location:** `src/lib/api.ts` (line 41)

**Purpose:** Centralized fetch with credentials

**Parameters:**
- `path: string` - API endpoint path
- `options: RequestInit` - Fetch options

**Features:**
- Automatically includes credentials (cookies)
- Sets Content-Type header
- Handles proxy vs direct URL
- Consistent error handling

**Usage:**
```typescript
const response = await apiFetch('/chat/stream', {
  method: 'POST',
  body: JSON.stringify({ question: '...' })
});
```

---

## API Endpoints Used

### Authentication

#### `POST /auth/microsoft/callback`
**Purpose:** OAuth callback handler

**Usage:** Handled by backend, frontend receives redirect

---

### Chat

#### `POST /chat/stream`
**Purpose:** Streaming chat endpoint

**Request:**
```typescript
{
  question: string;
  session_id: string;
  user_id: string;
  user_name: string;
  user_email: string;
}
```

**Response:** Server-Sent Events (SSE) stream

**Usage:**
```typescript
const response = await apiFetch('/chat/stream', {
  method: 'POST',
  body: JSON.stringify({
    question: userMessage,
    session_id: sessionId,
    user_id: user.id,
    user_name: user.name,
    user_email: user.email
  })
});

const reader = response.body?.getReader();
// Stream processing...
```

---

#### `POST /chat`
**Purpose:** Non-streaming chat endpoint

**Request:** Same as `/chat/stream`

**Response:**
```typescript
{
  answer: string;
  session_id: string;
  trace_id: string;
}
```

---

### Sessions

#### `GET /chat/sessions/user/{user_id}`
**Purpose:** Get user's sessions

**Response:**
```typescript
{
  sessions: ChatSession[];
}
```

---

#### `GET /chat/sessions/{session_id}`
**Purpose:** Get specific session

**Response:**
```typescript
{
  session: ChatSession;
}
```

---

#### `POST /chat/sessions/save`
**Purpose:** Save session

**Request:**
```typescript
{
  session_id: string;
  title: string;
  messages: Message[];
}
```

---

#### `DELETE /chat/sessions/{session_id}`
**Purpose:** Delete session

---

### Shared Chat

#### `POST /chat/share/{session_id}`
**Purpose:** Share session

**Response:**
```typescript
{
  share_token: string;
  share_url: string;
  expires_at: string;
}
```

---

#### `GET /chat/shared/{share_token}`
**Purpose:** Get shared chat

**Response:**
```typescript
{
  session: ChatSession;
  read_only: boolean;
}
```

---

### Analytics

#### `GET /admin/users/summary`
**Purpose:** All-time user statistics

**Response:**
```typescript
{
  total_users: number;
  total_questions: number;
  unique_questions: number;
  total_sessions: number;
}
```

---

#### `GET /admin/rankers`
**Purpose:** Ranked users by date range

**Query Parameters:**
- `start_date`: YYYY-MM-DD
- `end_date`: YYYY-MM-DD
- `limit`: number

**Response:**
```typescript
{
  rankers: UserStat[];
  total_rankers: number;
  date_range: { start: string; end: string };
}
```

---

#### `GET /admin/teams`
**Purpose:** Team analytics

**Response:**
```typescript
{
  teams: TeamStat[];
}
```

---

#### `GET /analytics/langfuse/teams/summary`
**Purpose:** Langfuse teams summary

**Query Parameters:**
- `start_date`: YYYY-MM-DD
- `end_date`: YYYY-MM-DD

---

### Feedback

#### `POST /feedback`
**Purpose:** Submit feedback

**Request:**
```typescript
{
  trace_id: string;
  rating: 'thumbs_up' | 'thumbs_down';
  comment?: string;
}
```

---

## Authentication in API Calls

### Cookie-Based Auth
**Method:** Session cookies (httpOnly)

**Implementation:**
```typescript
apiFetch('/endpoint', {
  credentials: 'include'  // Always included
});
```

**Flow:**
1. User logs in → Backend sets session cookie
2. Frontend makes API call → Cookie automatically included
3. Backend validates cookie → Returns response

---

### Token-Based Auth (Legacy)
**Method:** Bearer token in Authorization header

**Implementation:**
```typescript
apiFetch('/endpoint', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
});
```

**Status:** Legacy, being phased out in favor of cookies

---

## Error Handling

### Network Errors
```typescript
try {
  const response = await apiFetch('/endpoint');
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  const data = await response.json();
} catch (error) {
  console.error('API error:', error);
  // Handle error
}
```

### HTTP Status Codes
- `200` - Success
- `401` - Unauthorized → Redirect to `/login`
- `403` - Forbidden → Show error message
- `404` - Not Found → Show not found message
- `500` - Server Error → Show error message

---

## Streaming Responses

### Server-Sent Events (SSE)
**Endpoint:** `/chat/stream`

**Implementation:**
```typescript
const response = await apiFetch('/chat/stream', {
  method: 'POST',
  body: JSON.stringify(request)
});

const reader = response.body?.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  
  const chunk = decoder.decode(value);
  // Process chunk (parse SSE format)
  // Update UI with tokens
}
```

**SSE Format:**
```
data: {"type": "token", "content": "Hello"}
data: {"type": "token", "content": " world"}
data: {"type": "done", "trace_id": "..."}
```

---

## API Proxy (Development)

### Next.js API Route
**File:** `src/app/api/proxy/[...path]/route.ts`

**Purpose:** Proxy backend requests in development

**Why:** Same-origin requests for cookie handling

**Usage:**
- When `NEXT_PUBLIC_USE_PROXY=true`
- All API calls go through `/api/proxy`
- Proxy forwards to backend
- Cookies preserved

---

## Production API Calls

### Direct Backend URL
**Configuration:**
- `NEXT_PUBLIC_BACKEND_URL` - Backend URL
- `NEXT_PUBLIC_API_URL` - Alternative API URL

**Usage:**
- When `NEXT_PUBLIC_USE_PROXY=false` or not set
- Direct calls to backend URL
- Cookies work via same domain (reverse proxy)

---

## API Call Patterns

### GET Request
```typescript
const response = await apiFetch('/endpoint');
const data = await response.json();
```

### POST Request
```typescript
const response = await apiFetch('/endpoint', {
  method: 'POST',
  body: JSON.stringify({ key: 'value' })
});
const data = await response.json();
```

### With Query Parameters
```typescript
const params = new URLSearchParams({
  start_date: '2025-01-01',
  end_date: '2025-01-09'
});
const response = await apiFetch(`/endpoint?${params}`);
```

---

## Type Safety

### TypeScript Types
**Location:** `src/types/chat.ts`

**Types:**
- `User` - User interface
- `Message` - Message interface
- `ChatSession` - Session interface
- `OtherUserChat` - Other user's chat

**Usage:**
```typescript
import { User, ChatSession } from '@/types/chat';

const user: User = await response.json();
const session: ChatSession = await response.json();
```

---

## API Helper Functions

### Session Utilities
**Location:** `src/lib/session-utils.ts`

**Functions:**
- `checkSession()` - Check if session valid
- `getCurrentUser()` - Get current user
- `getAllSessions()` - Get all sessions
- `getSessionById()` - Get session by ID

**API Calls:**
- Uses `apiFetch()` internally
- Handles authentication
- Manages localStorage sync

---

## Configuration

### Environment Variables
```typescript
NEXT_PUBLIC_USE_PROXY=true        // Use Next.js proxy (dev)
NEXT_PUBLIC_BACKEND_URL=...       // Backend URL (prod)
NEXT_PUBLIC_API_URL=...           // Alternative API URL
```

### API Base URL Logic
1. Check `NEXT_PUBLIC_USE_PROXY`
2. If true → Use `/api/proxy`
3. If false → Use `NEXT_PUBLIC_BACKEND_URL` or `NEXT_PUBLIC_API_URL`
4. If none → Use empty string (same origin)

---

## Error Handling Patterns

### Try-Catch
```typescript
try {
  const data = await apiFetch('/endpoint');
} catch (error) {
  // Handle error
}
```

### Response Check
```typescript
const response = await apiFetch('/endpoint');
if (!response.ok) {
  throw new Error(`HTTP ${response.status}`);
}
```

### User Feedback
```typescript
try {
  await apiFetch('/endpoint');
  // Show success message
} catch (error) {
  // Show error message to user
}
```

---

## Key API Files

### Core
- **`src/lib/api.ts`** - API helper functions
- **`src/lib/session-utils.ts`** - Session API calls

### API Routes
- **`src/app/api/proxy/[...path]/route.ts`** - API proxy
- **`src/app/api/shared-chat/[token]/route.ts`** - Shared chat API

---

**Last Updated:** 2025-01-09  
**Location:** `frontend/src/lib/api.ts`
