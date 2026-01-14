# Complete Authentication & Session Workflow

## Overview

This document describes the complete workflow for user authentication and session management in the CloudFuze Chatbot application. It covers Microsoft OAuth authentication, session creation, validation, chat session management, and logout processes.

---

## Table of Contents

1. [Authentication Flow](#1-authentication-flow)
2. [Session Creation](#2-session-creation)
3. [Session Validation](#3-session-validation)
4. [Chat Session Management](#4-chat-session-management)
5. [User Data Storage](#5-user-data-storage)
6. [Token Refresh](#6-token-refresh)
7. [Logout Flow](#7-logout-flow)
8. [Error Handling](#8-error-handling)

---

## 1. Authentication Flow

### 1.1 Initial Login Request

**Frontend:** `frontend/src/app/login/page.tsx`

```
User visits /login
    ↓
Page loads and checks existing session
    ↓
If session exists → Redirect to /chat/new
If no session → Show login page
```

**Code Flow:**
```typescript
// Check if user already has valid session
async function checkSessionStatus() {
  const isLoggedIn = await checkSession();
  if (isLoggedIn) {
    window.location.href = "/";
  }
}
```

### 1.2 Microsoft OAuth Initiation

**Frontend:** User clicks "Sign in with Microsoft"

```
User clicks login button
    ↓
Generate PKCE code_verifier and code_challenge
    ↓
Store code_verifier in sessionStorage
    ↓
Redirect to Microsoft OAuth URL with:
  - client_id
  - redirect_uri
  - response_type=code
  - code_challenge (PKCE)
  - scope=openid profile email
```

**Code Flow:**
```typescript
async function handleMicrosoftLogin(event: Event) {
  // Generate PKCE parameters
  const codeVerifier = generateCodeVerifier();
  const codeChallenge = await generateCodeChallenge(codeVerifier);
  
  // Store for later verification
  sessionStorage.setItem('code_verifier', codeVerifier);
  sessionStorage.setItem('login_in_progress', 'true');
  
  // Redirect to Microsoft
  const authUrl = `https://login.microsoftonline.com/${MICROSOFT_TENANT}/oauth2/v2.0/authorize?...`;
  window.location.href = authUrl;
}
```

### 1.3 Microsoft Authentication

```
User authenticates with Microsoft
    ↓
Microsoft validates credentials
    ↓
Microsoft redirects back to app with authorization code
    ↓
URL: /login?code=AUTHORIZATION_CODE&state=STATE
```

### 1.4 OAuth Callback Processing

**Frontend:** `frontend/src/app/login/page.tsx` → `exchangeCodeForToken()`

```
Page detects authorization code in URL
    ↓
Extract code from URL parameters
    ↓
Retrieve code_verifier from sessionStorage
    ↓
POST /auth/microsoft/callback with:
  - code
  - redirect_uri
  - code_verifier
```

**Backend:** `app/endpoints.py` → `POST /auth/microsoft/callback`

```
Receive authorization code
    ↓
Exchange code for access token (Microsoft Token Endpoint)
    ↓
Fetch user info from Microsoft Graph API (/me endpoint)
    ↓
Validate email domain (@cloudfuze.com)
    ↓
Extract user data:
  - user_id: email (normalized)
  - user_email: email
  - user_name: displayName or extracted from email
```

**Code Flow:**
```python
@router.post("/auth/microsoft/callback")
async def microsoft_oauth_callback(request, http_request):
    # 1. Exchange code for token
    token_response = await exchange_code_for_token(code, code_verifier)
    access_token = token_response["access_token"]
    
    # 2. Fetch user info from Graph API
    graph_response = await fetch_user_info(access_token)
    user_info = graph_response.json()
    
    # 3. Extract and validate user data
    user_email = user_info.get("mail") or user_info.get("userPrincipalName")
    user_id = user_email.lower().strip()  # Always use email as ID
    user_name = user_info.get("displayName") or extract_from_email(user_email)
    
    # 4. Validate domain
    if not user_email.endswith("@cloudfuze.com"):
        raise HTTPException(403, "Only CloudFuze accounts allowed")
```

---

## 2. Session Creation

### 2.1 Backend Session Creation

**Backend:** `app/session_store.py` → `create_session()`

```
After successful OAuth authentication
    ↓
Create session in MongoDB (app_sessions collection)
    ↓
Generate secure session_id (64-char hex string)
    ↓
Store session data:
  - session_id
  - user_id (email)
  - user_email
  - user_name
  - access_token (encrypted)
  - refresh_token (encrypted)
  - token_expires_at
  - created_at
  - last_accessed_at
  - expires_at (8 hours from now)
    ↓
Return session_id to frontend
```

**Code Flow:**
```python
session_id = await session_store.create_session(
    user_id=user_id,
    user_email=user_email,
    user_name=user_name,
    access_token=access_token,
    refresh_token=refresh_token,
    token_expires_in=3600
)

# Session document structure:
{
    "session_id": "abc123...",
    "user_id": "user@cloudfuze.com",
    "user_email": "user@cloudfuze.com",
    "user_name": "User Name",
    "access_token": "encrypted_token",
    "refresh_token": "encrypted_refresh_token",
    "token_expires_at": datetime,
    "created_at": datetime,
    "last_accessed_at": datetime,
    "expires_at": datetime  # 8 hours from creation
}
```

### 2.2 Cookie Setting

**Backend:** `app/endpoints.py` → OAuth callback response

```
Create JSONResponse with user data
    ↓
Set HttpOnly cookie: session_id
    ↓
Cookie settings:
  - HttpOnly: true (prevents XSS)
  - Secure: true (HTTPS only in production)
  - SameSite: "lax" (dev) or "none" (production cross-origin)
  - Max-Age: 8 hours (matches session expiry)
  - Path: "/"
    ↓
Return response to frontend
```

**Code Flow:**
```python
response = JSONResponse(content={
    "user_id": user_id,
    "name": user_name,
    "email": user_email
})

response.set_cookie(
    key="session_id",
    value=session_id,
    max_age=3600 * SESSION_EXPIRY_HOURS,
    httponly=True,
    secure=secure_cookie,
    samesite=samesite_setting,
    path="/"
)
```

### 2.3 Frontend User Data Storage

**Frontend:** `frontend/src/app/login/page.tsx` → `exchangeCodeForToken()`

```
Receive response from backend
    ↓
Extract user data (id, name, email)
    ↓
Store in localStorage:
  {
    "id": "user@cloudfuze.com",
    "name": "User Name",
    "email": "user@cloudfuze.com"
  }
    ↓
Clear session flags
    ↓
Check if user needs onboarding
    ↓
Redirect to main app or onboarding
```

**Code Flow:**
```typescript
const user = {
  id: data.user_id,
  name: data.name,
  email: data.email
};

localStorage.setItem('user', JSON.stringify(user));
sessionStorage.removeItem('session_expired');
sessionStorage.removeItem('manual_logout');

// Check onboarding
const profileResponse = await apiFetch('/user/profile');
if (profileData.needs_onboarding) {
  showOnboardingModal();
} else {
  window.location.href = redirectUrl;
}
```

---

## 3. Session Validation

### 3.1 Frontend Session Check

**Frontend:** `frontend/src/lib/session-utils.ts` → `checkSession()`

```
User navigates to protected page
    ↓
Page component mounts
    ↓
useEffect triggers checkSession()
    ↓
GET /chat/sessions/all?limit=1
    ↓
If status 200 → Session valid
If status 401/403 → Session invalid
    ↓
If invalid → Redirect to /login
If valid → Continue rendering
```

**Code Flow:**
```typescript
export async function checkSession(): Promise<boolean> {
  try {
    const response = await apiFetch('/chat/sessions/all?limit=1', {
      method: 'GET'
    });
    return response.status === 200;
  } catch (error) {
    return false;
  }
}
```

### 3.2 Backend Session Validation

**Backend:** `app/auth.py` → `get_current_user()`

```
API request arrives with session_id cookie
    ↓
Extract session_id from cookie
    ↓
Query MongoDB for session:
  - session_id matches
  - expires_at > now (not expired)
    ↓
If found:
  - Update last_accessed_at
  - Decrypt tokens
  - Return user data
If not found:
  - Try legacy token auth (fallback)
  - If no token → 401 Unauthorized
```

**Code Flow:**
```python
async def get_current_user(request, session_id: Optional[str] = Cookie(None)):
    # Priority 1: Session-based auth
    if session_id:
        session = await session_store.get_session(session_id)
        if session:
            return {
                "id": session["user_id"],
                "email": session["user_email"],
                "name": session["user_name"]
            }
    
    # Priority 2: Legacy token auth (fallback)
    if credentials:
        return await _get_current_user_from_token(credentials.credentials)
    
    # No valid auth
    raise HTTPException(401, "Unauthorized")
```

### 3.3 Protected Endpoint Access

**Backend:** `app/endpoints.py` → Protected routes

```
API endpoint requires authentication
    ↓
Use Depends(require_auth) or Depends(get_current_user)
    ↓
get_current_user() validates session
    ↓
If valid → Request proceeds with user context
If invalid → 401 Unauthorized response
```

**Code Flow:**
```python
@router.get("/chat/sessions/all")
async def get_all_sessions(
    auth_user: dict = Depends(require_auth)
):
    user_id = auth_user["user_id"]
    # ... fetch sessions for user_id
    return sessions
```

---

## 4. Chat Session Management

### 4.1 Chat Session Creation

**Frontend:** `frontend/src/lib/session-utils.ts` → `createNewSessionId()`

```
User starts new chat
    ↓
Generate session ID: cf.conversation.YYYYMMDD.randomId
    ↓
Store in localStorage: chatbot_session_id_{userId}
    ↓
Initialize empty session object
```

**Code Flow:**
```typescript
export function createNewSessionId(): string {
  const date = new Date().toISOString().slice(0, 10).replace(/-/g, '');
  const randomId = Math.random().toString(36).substr(2, 9);
  return `cf.conversation.${date}.${randomId}`;
}
```

### 4.2 Saving Chat Sessions

**Frontend:** User sends messages → Session accumulates messages

```
User sends message
    ↓
Message added to session.messages array
    ↓
Session saved to localStorage: chat_sessions_{userId}
    ↓
Periodically sync to backend: POST /chat/sessions/save
```

**Backend:** `app/endpoints.py` → `POST /chat/sessions/save`

```
Receive session data from frontend
    ↓
Validate user authentication
    ↓
Save to MongoDB (chat_sessions collection):
  {
    "session_id": "cf.conversation...",
    "user_id": "user@cloudfuze.com",
    "user_email": "user@cloudfuze.com",
    "user_name": "User Name",
    "title": "Session Title",
    "messages": [...],
    "created_at": datetime,
    "updated_at": datetime,
    "message_count": int
  }
```

### 4.3 Loading Chat Sessions

**Frontend:** `frontend/src/components/ChatSidebar.tsx`

```
Component mounts
    ↓
Load sessions from localStorage: getAllSessions()
    ↓
Fetch sessions from backend: GET /chat/sessions/all
    ↓
Merge local and remote sessions
    ↓
Display in sidebar
```

**Backend:** `app/endpoints.py` → `GET /chat/sessions/all`

```
Validate user session
    ↓
Query MongoDB for user's sessions
    ↓
Filter and sort by updated_at
    ↓
Return session list
```

### 4.4 Session Deletion

**Frontend:** User deletes session from sidebar

```
User clicks delete on session
    ↓
Remove from localStorage
    ↓
Call backend: DELETE /chat/sessions/{session_id}
    ↓
Update UI
```

**Backend:** `app/mongodb_memory.py` → Delete from MongoDB

```
Validate user owns session
    ↓
Delete session document from MongoDB
    ↓
Return success
```

---

## 5. User Data Storage

### 5.1 Frontend Storage (localStorage)

**Location:** Browser localStorage

**Data Structure:**
```json
{
  "user": {
    "id": "user@cloudfuze.com",
    "name": "User Name",
    "email": "user@cloudfuze.com"
  },
  "chat_sessions_{userId}": [
    {
      "id": "cf.conversation...",
      "title": "Session Title",
      "messages": [...],
      "createdAt": timestamp,
      "timestamp": timestamp
    }
  ],
  "chatbot_session_id_{userId}": "cf.conversation..."
}
```

**Purpose:**
- UI display (username, email)
- Offline session access
- Fast initial load

### 5.2 Backend Storage (MongoDB)

**Collections:**

#### app_sessions
```json
{
  "session_id": "abc123...",
  "user_id": "user@cloudfuze.com",
  "user_email": "user@cloudfuze.com",
  "user_name": "User Name",
  "access_token": "encrypted",
  "refresh_token": "encrypted",
  "token_expires_at": datetime,
  "created_at": datetime,
  "last_accessed_at": datetime,
  "expires_at": datetime
}
```

#### chat_sessions
```json
{
  "session_id": "cf.conversation...",
  "user_id": "user@cloudfuze.com",
  "user_email": "user@cloudfuze.com",
  "user_name": "User Name",
  "title": "Session Title",
  "messages": [...],
  "created_at": datetime,
  "updated_at": datetime,
  "message_count": int
}
```

#### user_activity
```json
{
  "user_id": "user@cloudfuze.com",
  "user_email": "user@cloudfuze.com",
  "user_name": "User Name",
  "team_name": "Team Name",
  "manager_email": "manager@cloudfuze.com",
  "manager_name": "Manager Name",
  "role": "Software Engineer"
}
```

---

## 6. Token Refresh

### 6.1 Token Expiration Detection

**Backend:** `app/auth.py` → `get_current_user()`

```
Session validated
    ↓
Check token_expires_at
    ↓
If expires in < 5 minutes:
  - Log warning
  - Trigger background refresh (non-blocking)
    ↓
Request continues with current token
```

### 6.2 Token Refresh Process

**Backend:** Token refresh endpoint (if implemented)

```
Background task detects expiring token
    ↓
Use refresh_token to get new access_token
    ↓
Call session_store.refresh_session_tokens()
    ↓
Update session in MongoDB:
  - new access_token (encrypted)
  - new refresh_token (encrypted)
  - new token_expires_at
    ↓
Session continues without interruption
```

**Code Flow:**
```python
async def refresh_session_tokens(session_id, new_access_token, new_refresh_token):
    await self.collection.update_one(
        {"session_id": session_id},
        {
            "$set": {
                "access_token": encrypted_access_token,
                "refresh_token": encrypted_refresh_token,
                "token_expires_at": new_expires_at
            }
        }
    )
```

---

## 7. Logout Flow

> **📖 For complete logout workflow documentation, see:** [LOGOUT_WORKFLOW.md](./LOGOUT_WORKFLOW.md)

### 7.1 Quick Overview

**Frontend:** `frontend/src/components/ChatSidebar.tsx` → `handleLogoutConfirm()`

```
User clicks logout
    ↓
Show confirmation modal
    ↓
User confirms
    ↓
POST /auth/logout
    ↓
Clear localStorage:
  - Remove 'user'
  - Clear session flags
    ↓
Set manual_logout flag
    ↓
Redirect to /login
```

**Backend:** `app/endpoints.py` → `POST /auth/logout`

```
Receive logout request
    ↓
Extract session_id from cookie
    ↓
Delete session from MongoDB
    ↓
Clear session_id cookie
    ↓
Return success
```

### 7.2 Detailed Documentation

For complete logout workflow including:
- User interaction and confirmation modal
- Frontend and backend logout processes
- Session deletion and cookie clearing
- Local storage cleanup
- Login page handling
- Error handling and edge cases

See: [LOGOUT_WORKFLOW.md](./LOGOUT_WORKFLOW.md)

---

## 8. Error Handling

### 8.1 Session Expired

**Scenario:** User's session expires (8 hours of inactivity)

```
User makes API request
    ↓
Backend checks session
    ↓
Session not found or expired
    ↓
Return 401 Unauthorized
    ↓
Frontend detects 401
    ↓
Set session_expired flag
    ↓
Redirect to /login with error message
```

### 8.2 Missing User Data

**Scenario:** Session valid but localStorage empty

```
User visits page
    ↓
checkSession() returns true (session valid)
    ↓
getCurrentUser() returns null (localStorage empty)
    ↓
UI shows "User" instead of name
    ↓
Solution: Fetch from /user/profile endpoint
```

### 8.3 Invalid Session Cookie

**Scenario:** Cookie exists but session not in database

```
Request arrives with session_id cookie
    ↓
Backend queries MongoDB
    ↓
Session not found
    ↓
Fallback to token auth (if available)
    ↓
If no token → 401 Unauthorized
```

---

## Flow Diagrams

### Complete Authentication Flow

```
┌─────────┐
│  User   │
└────┬────┘
     │
     │ 1. Visits /login
     ▼
┌─────────────────┐
│  Login Page     │
│  (Frontend)     │
└────┬────────────┘
     │
     │ 2. Clicks "Sign in with Microsoft"
     ▼
┌─────────────────┐
│  Microsoft OAuth│
│  Authorization   │
└────┬────────────┘
     │
     │ 3. User authenticates
     ▼
┌─────────────────┐
│  OAuth Callback │
│  (Backend)      │
└────┬────────────┘
     │
     │ 4. Exchange code for token
     │ 5. Fetch user info from Graph API
     │ 6. Create session in MongoDB
     │ 7. Set session_id cookie
     ▼
┌─────────────────┐
│  Frontend       │
│  Receives user  │
│  data           │
└────┬────────────┘
     │
     │ 8. Store user in localStorage
     │ 9. Redirect to /chat/new
     ▼
┌─────────────────┐
│  Main App       │
└─────────────────┘
```

### Session Validation Flow

```
┌─────────┐
│  User   │
└────┬────┘
     │
     │ 1. Makes API request
     ▼
┌─────────────────┐
│  Frontend       │
│  Sends request  │
│  with cookie    │
└────┬────────────┘
     │
     │ 2. Request includes session_id cookie
     ▼
┌─────────────────┐
│  Backend        │
│  get_current_user│
└────┬────────────┘
     │
     │ 3. Extract session_id from cookie
     │ 4. Query MongoDB for session
     ▼
┌─────────────────┐
│  MongoDB        │
│  app_sessions   │
└────┬────────────┘
     │
     │ 5. Return session if valid
     ▼
┌─────────────────┐
│  Backend        │
│  Validates      │
│  session        │
└────┬────────────┘
     │
     │ 6. Return user data
     ▼
┌─────────────────┐
│  API Endpoint   │
│  Processes      │
│  request        │
└─────────────────┘
```

---

## Key Configuration

### Environment Variables

**Backend:**
- `SESSION_EXPIRY_HOURS`: Session expiration time (default: 8)
- `MONGODB_URL`: MongoDB connection string
- `MONGODB_DATABASE`: Database name
- `MICROSOFT_CLIENT_ID`: OAuth client ID
- `MICROSOFT_CLIENT_SECRET`: OAuth client secret
- `MICROSOFT_TENANT`: Microsoft tenant ID

**Frontend:**
- `NEXT_PUBLIC_API_URL`: Backend API URL
- Cookie settings (automatic based on environment)

### Session Expiry

- **Session Lifetime:** 8 hours (configurable)
- **Token Lifetime:** 1 hour (Microsoft default)
- **Token Refresh Margin:** 5 minutes before expiration
- **Auto-cleanup:** Expired sessions removed by MongoDB TTL index

---

## Security Considerations

1. **HttpOnly Cookies:** Prevents XSS attacks
2. **Secure Cookies:** HTTPS only in production
3. **SameSite Policy:** Prevents CSRF attacks
4. **Token Encryption:** Tokens encrypted in database
5. **Session Validation:** Every request validates session
6. **Domain Validation:** Only @cloudfuze.com emails allowed
7. **PKCE:** Prevents authorization code interception

---

## Troubleshooting

### Issue: User sees interface without username

**Cause:** Session valid but localStorage empty

**Solution:**
1. Check if session cookie exists
2. Fetch user data from `/user/profile` endpoint
3. Store in localStorage

### Issue: Session expires unexpectedly

**Cause:** Session not accessed for 8 hours

**Solution:**
1. Check `last_accessed_at` in MongoDB
2. Verify session expiry configuration
3. Implement session refresh on activity

### Issue: Cookie not being sent

**Cause:** Cookie settings mismatch

**Solution:**
1. Check SameSite setting (Lax vs None)
2. Verify Secure flag (HTTPS required)
3. Check domain and path settings

---

**Last Updated:** 2025-01-09
**Version:** 1.0
