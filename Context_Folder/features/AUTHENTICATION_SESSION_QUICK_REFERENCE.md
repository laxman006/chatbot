# Authentication & Session Quick Reference

## 🚀 Quick Start

### Authentication Flow (5 Steps)

```
1. User → /login → Click "Sign in with Microsoft"
2. Microsoft → Authenticates user → Returns authorization code
3. Frontend → POST /auth/microsoft/callback → Sends code
4. Backend → Creates session → Sets session_id cookie
5. Frontend → Stores user data → Redirects to /chat/new
```

### Session Validation (Every Request)

```
Request → Includes session_id cookie
    ↓
Backend → Queries MongoDB (app_sessions)
    ↓
If valid → Request proceeds
If invalid → 401 → Redirect to /login
```

---

## 📋 Key Components

### Frontend Files

| File | Purpose |
|------|---------|
| `frontend/src/app/login/page.tsx` | Login page, OAuth initiation |
| `frontend/src/lib/session-utils.ts` | Session utilities, checkSession() |
| `frontend/src/components/ChatSidebar.tsx` | User display, logout |
| `frontend/src/lib/api.ts` | API calls with cookie handling |

### Backend Files

| File | Purpose |
|------|---------|
| `app/endpoints.py` | OAuth callback, session endpoints |
| `app/session_store.py` | Session creation, validation |
| `app/auth.py` | get_current_user(), require_auth() |
| `app/mongodb_memory.py` | Chat session storage |

---

## 🔑 Key Functions

### Frontend

```typescript
// Check if user has valid session
checkSession(): Promise<boolean>

// Get current user from localStorage
getCurrentUser(): User | null

// Create new chat session ID
createNewSessionId(): string

// Get all chat sessions
getAllSessions(): ChatSession[]
```

### Backend

```python
# Create session after login
session_store.create_session(...) -> str

# Get session by ID
session_store.get_session(session_id) -> dict

# Validate user (use in endpoints)
get_current_user(request) -> dict

# Require authentication
require_auth(request) -> dict
```

---

## 🗄️ Data Storage

### Frontend (localStorage)

```javascript
{
  "user": {
    "id": "user@cloudfuze.com",
    "name": "User Name",
    "email": "user@cloudfuze.com"
  },
  "chat_sessions_{userId}": [...],
  "chatbot_session_id_{userId}": "cf.conversation..."
}
```

### Backend (MongoDB)

**Collection: `app_sessions`**
```json
{
  "session_id": "abc123...",
  "user_id": "user@cloudfuze.com",
  "access_token": "encrypted",
  "expires_at": datetime
}
```

**Collection: `chat_sessions`**
```json
{
  "session_id": "cf.conversation...",
  "user_id": "user@cloudfuze.com",
  "title": "Session Title",
  "messages": [...]
}
```

---

## 🔄 Common Flows

### User Login

```
1. User visits /login
2. Clicks "Sign in with Microsoft"
3. Redirects to Microsoft
4. User authenticates
5. Microsoft redirects back with code
6. Frontend exchanges code for session
7. Backend creates session, sets cookie
8. Frontend stores user data
9. Redirects to /chat/new
```

### User Logout

```
1. User clicks "Log out" in sidebar
2. Confirmation modal appears
3. User confirms logout
4. Frontend: POST /auth/logout
5. Backend: Delete session from MongoDB
6. Backend: Clear session_id cookie
7. Frontend: Clear localStorage user data
8. Frontend: Set manual_logout flag
9. Redirect to /login
10. Login page detects manual logout (no error shown)
```

### Making API Request

```
1. Frontend makes API call
2. Browser automatically includes session_id cookie
3. Backend extracts cookie
4. Queries MongoDB for session
5. If valid → Returns user data
6. Endpoint processes request
7. Returns response
```

### Session Expiry

```
1. User inactive for 8 hours
2. Session expires in MongoDB
3. Next API request fails
4. Frontend receives 401
5. Redirects to /login
6. User must login again
```

---

## ⚙️ Configuration

### Environment Variables

```bash
# Backend
SESSION_EXPIRY_HOURS=8
MONGODB_URL=mongodb://...
MICROSOFT_CLIENT_ID=...
MICROSOFT_CLIENT_SECRET=...
MICROSOFT_TENANT=...

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Cookie Settings

**Development:**
- `HttpOnly: true`
- `Secure: false`
- `SameSite: "lax"`

**Production:**
- `HttpOnly: true`
- `Secure: true`
- `SameSite: "lax"` (proxy) or `"none"` (cross-origin)

---

## 🐛 Troubleshooting

### Issue: User sees "User" instead of name

**Cause:** localStorage empty but session valid

**Fix:**
```typescript
// Fetch user data from backend
const response = await apiFetch('/user/profile');
const userData = await response.json();
localStorage.setItem('user', JSON.stringify(userData));
```

### Issue: Session expires unexpectedly

**Check:**
1. `SESSION_EXPIRY_HOURS` setting
2. MongoDB TTL index on `expires_at`
3. `last_accessed_at` updates

### Issue: Cookie not sent

**Check:**
1. SameSite setting (Lax vs None)
2. Secure flag (HTTPS required)
3. Domain/path settings
4. Browser cookie settings

---

## 📚 Full Documentation

- **Complete Workflow:** [AUTHENTICATION_SESSION_WORKFLOW.md](./AUTHENTICATION_SESSION_WORKFLOW.md)
- **Logout Workflow:** [LOGOUT_WORKFLOW.md](./LOGOUT_WORKFLOW.md)
- **Session Management:** [SESSION_MANAGEMENT_FEATURE.md](./SESSION_MANAGEMENT_FEATURE.md)
- **Authentication Feature:** [AUTHENTICATION_FEATURE.md](./AUTHENTICATION_FEATURE.md)

---

**Last Updated:** 2025-01-09
