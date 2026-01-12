# Authentication & Authorization - Code Documentation

## File: `app/auth.py`

This file handles user authentication using Microsoft OAuth and session-based auth.

---

## Constants

### `ADMIN_EMAILS`
**Location:** Lines 28-32

**Purpose:** Restricted admin allowlist

**Value:**
```python
{
    "laxman.kadari@cloudfuze.com",
    "chaitanya.malle@cloudfuze.com",
    "nirosh.reddy@cloudfuze.com"
}
```

### `EXCLUDED_DEVELOPER_EMAILS`
**Location:** Lines 36-44

**Purpose:** Developer emails excluded from dashboard statistics

**Source:** Environment variable `EXCLUDED_DEVELOPER_EMAILS` (comma-separated) or defaults to `ADMIN_EMAILS`

---

## Functions

### `_normalize_email(email)`
**Location:** Lines 47-49

**Purpose:** Normalize email for case-insensitive comparisons

**Returns:** Lowercase, stripped email string

---

### `get_current_user(request, session_id, credentials)`
**Location:** Lines 52-133

**Purpose:** Get authenticated user from session or token

**Priority:**
1. **Session cookie** (preferred - no Graph API call)
2. **Bearer token** (legacy - calls Graph API)

**What it does:**
1. Tries session-based auth first:
   - Gets session from `session_store.get_session(session_id)`
   - Validates session has required fields (user_email, user_id, user_name)
   - Ensures user_id == email (migrates old sessions)
   - Checks if token needs refresh (non-blocking)
   - Returns user dict if valid

2. Falls back to token-based auth:
   - Calls `_get_current_user_from_token(credentials.credentials)`

3. Raises HTTPException 401 if both fail

**Returns:** Dictionary with `id`, `email`, `name`

**Raises:** HTTPException 401 if unauthorized

---

### `_get_current_user_from_token(access_token)`
**Location:** Lines 136-218

**Purpose:** Legacy token-based authentication (calls Microsoft Graph API)

**What it does:**
1. Calls Microsoft Graph API: `GET https://graph.microsoft.com/v1.0/me`
2. Validates response status (401 = invalid token, 200 = success)
3. Extracts user info from JSON response
4. Validates email exists (mail or userPrincipalName)
5. Validates email domain is `@cloudfuze.com`
6. Normalizes user_id to email (lowercase, stripped)
7. Extracts displayName or generates from email

**Returns:** Dictionary with `id`, `email`, `name`

**Raises:** 
- HTTPException 401 if token invalid/expired
- HTTPException 403 if not @cloudfuze.com email
- HTTPException 503 if network error

---

### `verify_user_access(user_id, current_user)`
**Location:** Lines 221-249

**Purpose:** Verify user has access to requested user resource (prevents IDOR)

**What it does:**
- Compares `current_user["id"]` with `user_id` from URL
- Raises 403 if mismatch (user trying to access another user's resources)

**Returns:** current_user dict if access allowed

**Raises:** HTTPException 403 if access denied

---

### `require_admin(current_user)`
**Location:** Lines 252-280

**Purpose:** Verify user has administrative privileges

**What it does:**
- Checks if email ends with `@cloudfuze.com`
- All CloudFuze users are considered admins for internal tools

**Returns:** current_user dict if admin

**Raises:** HTTPException 403 if not admin

---

### `require_restricted_admin(current_user)`
**Location:** Lines 283-303

**Purpose:** Verify user is in explicit admin allowlist

**What it does:**
- Normalizes email and checks against `ADMIN_EMAILS` set
- Only 3 users have restricted admin access

**Returns:** current_user dict if restricted admin

**Raises:** HTTPException 403 if not in allowlist

---

### `get_current_user_optional(credentials)`
**Location:** Lines 306-327

**Purpose:** Optional authentication - returns user if token provided, None otherwise

**What it does:**
- If no credentials: Returns None
- If credentials: Calls `get_current_user()` but catches HTTPException and returns None

**Returns:** User dict if authenticated, None otherwise

---

## Security Features

1. **Session-Based Auth:** Primary method - no Graph API calls on every request
2. **Token Refresh:** Background refresh when token expiring soon
3. **Email Domain Validation:** Only `@cloudfuze.com` emails allowed
4. **IDOR Prevention:** `verify_user_access()` prevents accessing other users' resources
5. **Admin Protection:** Two levels - general admin (all CloudFuze) and restricted admin (3 users)

---

## Usage in Endpoints

### Protected Endpoint
```python
from app.auth import get_current_user

@router.post("/chat")
async def chat(request: Request, auth_user: dict = Depends(get_current_user)):
    user_id = auth_user["user_id"]
    # Use authenticated user
```

### Admin Only Endpoint
```python
from app.auth import require_admin

@router.get("/admin/stats")
async def get_stats(admin_user: dict = Depends(require_admin)):
    # Only admins can access
```

### Restricted Admin Only
```python
from app.auth import require_restricted_admin

@router.delete("/admin/data")
async def delete_data(restricted_admin: dict = Depends(require_restricted_admin)):
    # Only 3 specific admins can access
```

---

## Session Store Integration

**File:** `app/session_store.py`

Sessions stored in MongoDB with:
- `session_id`: Unique session identifier
- `user_id`: User email (normalized)
- `user_email`: User email
- `user_name`: Display name
- `token_expires_at`: Token expiration timestamp

---

## Microsoft Graph API

**Endpoint Used:** `https://graph.microsoft.com/v1.0/me`

**Response Fields:**
- `mail`: Primary email
- `userPrincipalName`: UPN (fallback if mail missing)
- `displayName`: Display name

---

**Last Updated:** 2025-01-09  
**File:** `app/auth.py`
