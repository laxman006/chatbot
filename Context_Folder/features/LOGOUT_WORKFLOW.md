# Complete Logout Workflow

## Overview

This document describes the complete logout functionality workflow, from user interaction to complete session cleanup and redirect. The logout process ensures secure session termination, proper cleanup of client-side data, and prevents error messages on subsequent login page visits.

---

## Table of Contents

1. [User Interaction](#1-user-interaction)
2. [Confirmation Modal](#2-confirmation-modal)
3. [Frontend Logout Process](#3-frontend-logout-process)
4. [Backend Logout Process](#4-backend-logout-process)
5. [Session Deletion](#5-session-deletion)
6. [Cookie Clearing](#6-cookie-clearing)
7. [Local Storage Cleanup](#7-local-storage-cleanup)
8. [Redirect to Login](#8-redirect-to-login)
9. [Login Page Handling](#9-login-page-handling)
10. [Error Handling](#10-error-handling)
11. [Edge Cases](#11-edge-cases)

---

## 1. User Interaction

### 1.1 Logout Button Location

**Component:** `frontend/src/components/ChatSidebar.tsx`

The logout button is located in the user dropdown menu in the sidebar footer.

**UI Structure:**
```
Sidebar Footer
  └── User Menu (clickable)
      └── User Dropdown
          ├── User Email
          ├── Admin Menu (if admin)
          └── Log out Button ← User clicks here
```

**Code Location:**
```typescript
<div className="dropdown-item logout" onClick={handleLogoutClick}>
  <svg>...</svg>
  <span>Log out</span>
</div>
```

### 1.2 User Clicks Logout

**Flow:**
```
User clicks "Log out" button
    ↓
handleLogoutClick() triggered
    ↓
Close user dropdown
    ↓
Show confirmation modal
```

**Code:**
```typescript
const handleLogoutClick = () => {
  setShowLogoutModal(true);
  // Close the dropdown
  const dropdown = document.getElementById('userDropdown');
  if (dropdown) {
    dropdown.classList.remove('show');
  }
};
```

---

## 2. Confirmation Modal

### 2.1 Modal Display

**Component:** `frontend/src/components/ChatSidebar.tsx`

A confirmation modal appears to prevent accidental logouts.

**Modal Structure:**
```
┌─────────────────────────────────┐
│  Overlay (darkens background)   │
│  ┌───────────────────────────┐  │
│  │  Logout Confirmation      │  │
│  │                            │  │
│  │  "Are you sure you want    │  │
│  │   to log out?"             │  │
│  │                            │  │
│  │  "Log out of ai.cloudfuze  │  │
│  │   as user@cloudfuze.com?"  │  │
│  │                            │  │
│  │  [Cancel]  [Log out]      │  │
│  └───────────────────────────┘  │
└─────────────────────────────────┘
```

**Code:**
```typescript
{showLogoutModal && (
  <>
    <div 
      className="logout-modal-overlay" 
      onClick={handleLogoutCancel}
    />
    <div className="logout-modal">
      <div className="logout-modal-content">
        <h3>Are you sure you want to log out?</h3>
        <p>Log out of ai.cloudfuze as {user?.email || 'user'}?</p>
        <div className="logout-modal-buttons">
          <button onClick={handleLogoutCancel}>Cancel</button>
          <button onClick={handleLogoutConfirm} autoFocus>Log out</button>
        </div>
      </div>
    </div>
  </>
)}
```

### 2.2 User Options

**Option 1: Cancel**
```
User clicks "Cancel" or clicks outside modal
    ↓
handleLogoutCancel() triggered
    ↓
setShowLogoutModal(false)
    ↓
Modal closes, user stays logged in
```

**Option 2: Confirm**
```
User clicks "Log out" or presses Enter
    ↓
handleLogoutConfirm() triggered
    ↓
Logout process begins
```

**Code:**
```typescript
const handleLogoutCancel = () => {
  setShowLogoutModal(false);
};
```

### 2.3 Keyboard Support

**Escape Key:**
- Pressing Escape closes the modal (same as Cancel)

**Tab Navigation:**
- Modal supports keyboard navigation
- Focus trapped within modal
- Auto-focus on "Log out" button

**Code:**
```typescript
useEffect(() => {
  const handleEscape = (e: KeyboardEvent) => {
    if (e.key === 'Escape' && showLogoutModal) {
      setShowLogoutModal(false);
    }
  };
  
  document.addEventListener('keydown', handleEscape);
  return () => document.removeEventListener('keydown', handleEscape);
}, [showLogoutModal]);
```

---

## 3. Frontend Logout Process

### 3.1 Logout Confirmation Handler

**Component:** `frontend/src/components/ChatSidebar.tsx` → `handleLogoutConfirm()`

**Complete Flow:**
```
User confirms logout
    ↓
handleLogoutConfirm() executes
    ↓
Try block:
  ├── POST /auth/logout (with session_id cookie)
  ├── Wait for response
  └── Log success/failure
    ↓
Finally block (always executes):
  ├── Remove 'user' from localStorage
  ├── Remove 'session_expired' from sessionStorage
  ├── Set 'manual_logout' flag in sessionStorage
  └── Redirect to /login
```

**Code:**
```typescript
const handleLogoutConfirm = async () => {
  try {
    // ✅ Session-based auth - session_id cookie sent automatically via proxy
    const response = await apiFetch('/auth/logout', {
      method: 'POST'
    });
    
    if (response.ok) {
      console.log('[AUTH] ✅ Logged out successfully');
    } else {
      console.warn('[AUTH] Logout endpoint failed, clearing local data anyway');
    }
  } catch (error) {
    console.error('[AUTH] Logout error:', error);
  } finally {
    // Always clear local data, even if backend call fails
    localStorage.removeItem('user');
    
    // 🔒 CRITICAL: Clear session expiration flag on manual logout
    // This prevents showing "session expired" error when user manually logs out
    sessionStorage.removeItem('session_expired');
    
    // Set manual logout flag to prevent error message
    sessionStorage.setItem('manual_logout', 'true');
    
    router.replace('/login');
  }
};
```

### 3.2 API Request Details

**Request:**
- **Method:** POST
- **Endpoint:** `/auth/logout`
- **Headers:** 
  - `Content-Type: application/json`
  - `Cookie: session_id=abc123...` (automatically sent by browser)
- **Body:** None (session identified by cookie)

**Response Handling:**
- **Success (200):** Log success message
- **Failure (4xx/5xx):** Log warning but continue with cleanup
- **Network Error:** Log error but continue with cleanup

**Important:** The `finally` block always executes, ensuring cleanup happens even if the backend call fails.

---

## 4. Backend Logout Process

### 4.1 Logout Endpoint

**File:** `app/endpoints.py` → `POST /auth/logout`

**Flow:**
```
Request arrives at /auth/logout
    ↓
Extract session_id from cookie
    ↓
If session_id exists:
  ├── Connect to MongoDB
  ├── Delete session from app_sessions collection
  └── Log deletion result
    ↓
Create JSONResponse
    ↓
Delete session_id cookie from response
    ↓
Return success response
```

**Code:**
```python
@router.post("/auth/logout")
async def logout(request: Request):
    """
    ✅ NEW: Logout endpoint - deletes session.
    """
    from app.session_store import session_store
    
    session_id = request.cookies.get("session_id")
    
    if session_id:
        try:
            await session_store.connect()
            await session_store.delete_session(session_id)
            logger.info(f"[AUTH] User logged out: {session_id[:8]}...")
        except Exception as e:
            logger.error(f"[AUTH] Logout error: {e}")
    
    # Clear session cookie
    response = JSONResponse(content={
        "success": True, 
        "message": "Logged out successfully"
    })
    response.delete_cookie(key="session_id")
    
    return response
```

### 4.2 Cookie Extraction

**Process:**
1. FastAPI automatically extracts cookies from request
2. `request.cookies.get("session_id")` retrieves the session ID
3. If cookie doesn't exist, `session_id` is `None`
4. Logout still proceeds (cookie will be cleared anyway)

---

## 5. Session Deletion

### 5.1 Session Store Deletion

**File:** `app/session_store.py` → `delete_session()`

**Flow:**
```
delete_session(session_id) called
    ↓
Connect to MongoDB
    ↓
Delete session document:
  - Query: {"session_id": session_id}
  - Operation: delete_one()
    ↓
Check deletion result
    ↓
If deleted_count > 0:
  ├── Log success
  └── Return True
Else:
  ├── Log warning (session not found)
  └── Return False
```

**Code:**
```python
async def delete_session(self, session_id: str) -> bool:
    """
    Delete a session (logout).
    
    Args:
        session_id: Session identifier
        
    Returns:
        True if deleted, False if not found
    """
    await self.connect()
    
    result = await self.collection.delete_one({"session_id": session_id})
    
    if result.deleted_count > 0:
        logger.info(f"[SESSION] Deleted session: {session_id[:8]}...")
        return True
    return False
```

### 5.2 MongoDB Operation

**Collection:** `app_sessions`

**Operation:**
```python
# MongoDB delete operation
result = await self.collection.delete_one({"session_id": session_id})
```

**What Gets Deleted:**
- Entire session document including:
  - session_id
  - user_id, user_email, user_name
  - access_token (encrypted)
  - refresh_token (encrypted)
  - All timestamps
  - Expiration dates

**Result:**
- `deleted_count`: Number of documents deleted (0 or 1)
- If session doesn't exist, `deleted_count = 0` (not an error)

---

## 6. Cookie Clearing

### 6.1 Backend Cookie Deletion

**File:** `app/endpoints.py` → `logout()`

**Process:**
```
Create JSONResponse
    ↓
Call response.delete_cookie()
    ↓
Cookie marked for deletion
    ↓
Response sent to browser
    ↓
Browser removes cookie
```

**Code:**
```python
response = JSONResponse(content={"success": True, "message": "Logged out successfully"})
response.delete_cookie(key="session_id")
```

**Cookie Deletion Details:**
- **Key:** `session_id`
- **Path:** `/` (default, matches cookie path)
- **Domain:** Not specified (uses current domain)
- **HttpOnly:** Inherited from original cookie settings
- **Secure:** Inherited from original cookie settings
- **SameSite:** Inherited from original cookie settings

**What Happens:**
1. Backend sets `Set-Cookie: session_id=; expires=Thu, 01 Jan 1970 00:00:00 GMT`
2. Browser receives response
3. Browser removes cookie from cookie store
4. Future requests won't include the cookie

---

## 7. Local Storage Cleanup

### 7.1 Frontend Cleanup

**Component:** `frontend/src/components/ChatSidebar.tsx` → `handleLogoutConfirm()`

**Items Removed:**

#### localStorage
```typescript
localStorage.removeItem('user');
```

**What Gets Removed:**
```json
{
  "id": "user@cloudfuze.com",
  "name": "User Name",
  "email": "user@cloudfuze.com"
}
```

**Note:** Chat sessions in localStorage are NOT removed during logout. They remain for:
- Offline access
- Faster loading on next login
- User convenience

#### sessionStorage
```typescript
// Remove session expiration flag
sessionStorage.removeItem('session_expired');

// Set manual logout flag
sessionStorage.setItem('manual_logout', 'true');
```

**Purpose of `manual_logout` Flag:**
- Prevents showing "session expired" error message on login page
- Indicates user intentionally logged out
- Cleared when login page loads

### 7.2 What Stays in Storage

**localStorage (Preserved):**
- `chat_sessions_{userId}` - Chat history
- `chatbot_session_id_{userId}` - Current session ID
- `sidebarOpen` - UI preferences

**Why Preserve:**
- User convenience (don't lose chat history)
- Faster loading on next login
- Better user experience

**Note:** If you want to clear everything on logout, you can add:
```typescript
// Clear all user-specific data
const user = getCurrentUser();
if (user) {
  localStorage.removeItem(`chat_sessions_${user.id}`);
  localStorage.removeItem(`chatbot_session_id_${user.id}`);
}
```

---

## 8. Redirect to Login

### 8.1 Navigation

**Component:** `frontend/src/components/ChatSidebar.tsx`

**Method:**
```typescript
router.replace('/login');
```

**Why `replace` instead of `push`:**
- `replace`: Replaces current history entry (can't go back)
- `push`: Adds new history entry (can go back with browser back button)
- Logout should prevent going back to authenticated pages

**Alternative (in chat-initialization.ts):**
```typescript
window.location.href = "/login";
```

**Why `window.location.href`:**
- Full page reload
- Ensures all state is cleared
- More reliable for logout scenarios

### 8.2 Redirect Timing

**Flow:**
```
Logout process completes
    ↓
All cleanup done
    ↓
Redirect initiated
    ↓
Browser navigates to /login
    ↓
Login page loads
    ↓
checkSessionStatus() runs
```

---

## 9. Login Page Handling

### 9.1 Session Status Check

**File:** `frontend/src/app/login/page.tsx` → `checkSessionStatus()`

**Flow:**
```
Login page loads
    ↓
checkSessionStatus() executes
    ↓
Check for manual_logout flag
    ↓
If manual_logout === 'true':
  ├── Remove manual_logout flag
  ├── Remove session_expired flag
  ├── Log "Manual logout detected"
  └── Return early (don't check session)
    ↓
If no manual_logout flag:
  ├── Check session with backend
  ├── If valid → Redirect to main app
  └── If invalid → Show error (if session_expired)
```

**Code:**
```typescript
async function checkSessionStatus() {
  console.log('[AUTH] Checking session status...');
  
  // 🔒 CRITICAL: Check if this is a manual logout (don't show error)
  const isManualLogout = sessionStorage.getItem('manual_logout') === 'true';
  if (isManualLogout) {
    // User manually logged out - clear flags and don't show error
    sessionStorage.removeItem('manual_logout');
    sessionStorage.removeItem('session_expired');
    console.log('[AUTH] Manual logout detected - no error message');
    return; // Don't check session, just stay on login page
  }
  
  const isLoggedIn = await checkSession();
  
  if (isLoggedIn) {
    // Session is valid - user is logged in
    console.log('[AUTH] ✅ Session valid, redirecting to main page');
    sessionStorage.removeItem('session_expired');
    sessionStorage.removeItem('manual_logout');
    window.location.href = "/";
  } else {
    // Session expired or invalid - stay on login page
    console.log('[AUTH] No valid session');
    localStorage.removeItem('user');
    
    // Only show error if it's actually a session expiration (not manual logout)
    const hasStoredExpiration = sessionStorage.getItem('session_expired') === 'true';
    if (hasStoredExpiration) {
      sessionStorage.setItem('session_expired', 'true');
      showError('⚠️ Your session has expired. Please log in again.', true);
    }
  }
}
```

### 9.2 Manual Logout Detection

**Purpose:**
- Prevents showing "session expired" error after manual logout
- Provides clean login experience
- Distinguishes between manual logout and session expiration

**Flow:**
```
User manually logs out
    ↓
manual_logout flag set to 'true'
    ↓
Redirect to /login
    ↓
Login page loads
    ↓
Detects manual_logout flag
    ↓
Clears flags
    ↓
Stays on login page (no error message)
```

---

## 10. Error Handling

### 10.1 Backend Errors

**Scenario 1: Session Not Found**
```
Backend tries to delete session
    ↓
Session doesn't exist in MongoDB
    ↓
delete_session() returns False
    ↓
Log warning (not an error)
    ↓
Continue with cookie deletion
    ↓
Return success response
```

**Why Not an Error:**
- Session might have already expired
- User might have logged out from another device
- Cookie deletion still succeeds

**Scenario 2: MongoDB Connection Error**
```
Backend tries to connect to MongoDB
    ↓
Connection fails
    ↓
Exception caught
    ↓
Error logged
    ↓
Continue with cookie deletion
    ↓
Return success response
```

**Code:**
```python
if session_id:
    try:
        await session_store.connect()
        await session_store.delete_session(session_id)
        logger.info(f"[AUTH] User logged out: {session_id[:8]}...")
    except Exception as e:
        logger.error(f"[AUTH] Logout error: {e}")
# Cookie deletion happens regardless
```

### 10.2 Frontend Errors

**Scenario 1: Network Error**
```
Frontend calls /auth/logout
    ↓
Network request fails
    ↓
Catch block executes
    ↓
Error logged
    ↓
Finally block executes (cleanup)
    ↓
Redirect to /login
```

**Code:**
```typescript
try {
  const response = await apiFetch('/auth/logout', { method: 'POST' });
  // ...
} catch (error) {
  console.error('[AUTH] Logout error:', error);
} finally {
  // Always cleanup, even on error
  localStorage.removeItem('user');
  sessionStorage.setItem('manual_logout', 'true');
  router.replace('/login');
}
```

**Why Finally Block:**
- Ensures cleanup happens even if backend fails
- User can still log out (local cleanup)
- Prevents being stuck in logged-in state

**Scenario 2: Backend Returns Error**
```
Frontend calls /auth/logout
    ↓
Backend returns 500 error
    ↓
response.ok === false
    ↓
Warning logged
    ↓
Finally block executes (cleanup)
    ↓
Redirect to /login
```

---

## 11. Edge Cases

### 11.1 Multiple Tabs

**Scenario:** User logs out in one tab

**Current Behavior:**
- Other tabs remain logged in
- Session still valid in other tabs
- User can continue using other tabs

**Why:**
- Each tab has its own JavaScript context
- Session cookie is shared across tabs
- Backend session still exists until other tabs make requests

**Solution (if needed):**
- Implement BroadcastChannel API
- Listen for logout events
- Redirect all tabs on logout

### 11.2 Session Already Expired

**Scenario:** User tries to logout but session already expired

**Flow:**
```
User clicks logout
    ↓
Backend receives request
    ↓
Session not found in MongoDB (expired)
    ↓
delete_session() returns False
    ↓
Cookie still deleted
    ↓
Response returned
    ↓
Frontend cleanup executes
    ↓
Redirect to /login
```

**Result:** Logout succeeds (cookie cleared, local data cleared)

### 11.3 No Session Cookie

**Scenario:** Cookie was already deleted or never existed

**Flow:**
```
User clicks logout
    ↓
Backend receives request
    ↓
request.cookies.get("session_id") returns None
    ↓
Skip session deletion
    ↓
Cookie deletion still attempted (harmless)
    ↓
Response returned
    ↓
Frontend cleanup executes
    ↓
Redirect to /login
```

**Result:** Logout succeeds (local data cleared)

### 11.4 Concurrent Logout Requests

**Scenario:** User clicks logout multiple times quickly

**Flow:**
```
First request:
  ├── Deletes session
  ├── Clears cookie
  └── Returns success
    ↓
Second request:
  ├── Session not found (already deleted)
  ├── Clears cookie (already cleared)
  └── Returns success
    ↓
Both requests succeed
```

**Result:** Idempotent operation (safe to call multiple times)

---

## Complete Flow Diagram

```
┌─────────┐
│  User   │
└────┬────┘
     │
     │ 1. Clicks "Log out"
     ▼
┌─────────────────┐
│  Confirmation   │
│  Modal          │
└────┬────────────┘
     │
     │ 2. User confirms
     ▼
┌─────────────────┐
│  Frontend       │
│  handleLogout   │
│  Confirm()      │
└────┬────────────┘
     │
     │ 3. POST /auth/logout
     │    (with session_id cookie)
     ▼
┌─────────────────┐
│  Backend        │
│  /auth/logout   │
└────┬────────────┘
     │
     │ 4. Extract session_id
     │ 5. Delete from MongoDB
     │ 6. Clear cookie
     ▼
┌─────────────────┐
│  MongoDB        │
│  Delete Session │
└────┬────────────┘
     │
     │ 7. Return success
     ▼
┌─────────────────┐
│  Frontend       │
│  Cleanup        │
└────┬────────────┘
     │
     │ 8. Remove 'user' from localStorage
     │ 9. Set 'manual_logout' flag
     │ 10. Redirect to /login
     ▼
┌─────────────────┐
│  Login Page     │
└────┬────────────┘
     │
     │ 11. Detect manual_logout flag
     │ 12. Clear flags
     │ 13. Show login page (no error)
     ▼
┌─────────────────┐
│  User can       │
│  login again    │
└─────────────────┘
```

---

## Key Points Summary

### Security
- ✅ Session deleted from database
- ✅ Cookie cleared (HttpOnly, Secure)
- ✅ Local user data removed
- ✅ Cannot go back to authenticated pages

### User Experience
- ✅ Confirmation modal prevents accidents
- ✅ No error message after manual logout
- ✅ Clean login page experience
- ✅ Chat history preserved (optional)

### Reliability
- ✅ Cleanup happens even if backend fails
- ✅ Idempotent operation (safe to retry)
- ✅ Handles edge cases gracefully
- ✅ Proper error logging

### Data Cleanup
- ✅ Backend session deleted
- ✅ Cookie removed
- ✅ User data removed from localStorage
- ✅ Session flags cleared
- ⚠️ Chat sessions preserved (by design)

---

## Code Locations

### Frontend
- **Logout Button:** `frontend/src/components/ChatSidebar.tsx` (line 870)
- **Logout Handler:** `frontend/src/components/ChatSidebar.tsx` (line 463)
- **Confirmation Modal:** `frontend/src/components/ChatSidebar.tsx` (line 880)
- **Legacy Handler:** `frontend/src/lib/chat-initialization.ts` (line 3766)
- **Login Page Handler:** `frontend/src/app/login/page.tsx` (line 133)

### Backend
- **Logout Endpoint:** `app/endpoints.py` (line 6643)
- **Session Deletion:** `app/session_store.py` (line 234)

---

**Last Updated:** 2025-01-09
**Version:** 1.0
