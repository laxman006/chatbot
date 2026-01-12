# Authentication Feature

## Overview

Microsoft OAuth-based authentication with session management. Users authenticate via Microsoft OAuth and receive JWT tokens or session cookies.

---

## Related Files

### Backend Files

#### Authentication Core
- **`app/auth.py`**
  - `get_current_user()` - Get authenticated user from session/token (line 52)
  - `_get_current_user_from_token()` - Legacy token-based auth (line 136)
  - `verify_user_access()` - Verify user has access to resource (line 221)
  - `require_admin()` - Require admin privileges (line 252)
  - `require_restricted_admin()` - Require restricted admin (line 283)
  - `get_current_user_optional()` - Optional authentication (line 306)
  - `_normalize_email()` - Normalize email (line 47)
  - `ADMIN_EMAILS` - Admin allowlist (line 28)
  - `EXCLUDED_DEVELOPER_EMAILS` - Excluded developers (line 36)

#### Session Management
- **`app/session_store.py`**
  - Session storage and management
  - Session creation, retrieval, validation

#### OAuth Endpoints
- **`app/endpoints.py`**
  - `POST /auth/microsoft/callback` - OAuth callback handler
  - Microsoft Graph API integration

#### Configuration
- **`config.py`**
  - `MICROSOFT_CLIENT_ID` - OAuth client ID
  - `MICROSOFT_CLIENT_SECRET` - OAuth client secret
  - `MICROSOFT_TENANT` - Microsoft tenant

### Frontend Files

#### Login Page
- **`frontend/src/app/login/page.tsx`**
  - Login page with Microsoft OAuth button
  - Redirect URL handling
  - Token storage

#### Authentication Utilities
- **`frontend/src/lib/api.ts`**
  - API calls with authentication
  - Token handling

#### Constants
- **`frontend/src/constants/admins.ts`**
  - Admin user list (if exists)

---

## Feature Workflow

1. **User clicks "Sign in with Microsoft"** → Redirects to Microsoft OAuth
2. **Microsoft authenticates** → User logs in with Microsoft account
3. **OAuth callback** → Backend receives authorization code
4. **Token exchange** → Backend exchanges code for access token
5. **User info fetch** → Backend fetches user info from Graph API
6. **Domain validation** → Validates `@cloudfuze.com` email
7. **Session creation** → Creates session in MongoDB
8. **Token return** → Returns JWT token or session cookie
9. **Frontend storage** → Frontend stores token/cookie

---

## Key Functions

### Backend
- `get_current_user()` - Primary authentication function
- `require_admin()` - Admin check
- `require_restricted_admin()` - Restricted admin check
- `verify_user_access()` - IDOR prevention

### Frontend
- Login page component
- OAuth redirect handling
- Token storage

---

## Security Features

1. **Email Domain Validation** - Only `@cloudfuze.com` emails
2. **Session-Based Auth** - Primary method (no Graph API calls on every request)
3. **Token Fallback** - Legacy token support for migration
4. **IDOR Prevention** - `verify_user_access()` prevents accessing other users' resources
5. **Admin Protection** - Two levels: general admin and restricted admin

---

## Admin Levels

### General Admin
- All `@cloudfuze.com` users
- Checked via `require_admin()`

### Restricted Admin
- Only 3 users:
  - `laxman.kadari@cloudfuze.com`
  - `chaitanya.malle@cloudfuze.com`
  - `nirosh.reddy@cloudfuze.com`
- Checked via `require_restricted_admin()`

---

## Configuration

```python
MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID")
MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET")
MICROSOFT_TENANT = os.getenv("MICROSOFT_TENANT", "cloudfuze.com")
```

---

**Last Updated:** 2025-01-09
