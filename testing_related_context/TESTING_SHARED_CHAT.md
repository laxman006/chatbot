# Testing Shared Chat Link Feature

## Quick Test Guide

### Prerequisites
- You (Laxman) must be logged in
- Have access to a chat session
- Browser DevTools open (F12)

---

## Test 1: Share a Chat (As Laxman)

1. Open `https://ai.cloudfuze.com/chat/new` (or any existing chat)
2. Look for the **Share** button (usually near the top)
3. Click **Share**
4. Copy the shared link (looks like: `https://ai.cloudfuze.com/chat/shared/57329aa2-7fe7-4d77-9a3c-757742ed9160`)
5. Check browser console (F12 → Console tab):
   ```
   [SHARE] Attempting to share session cf.conversation.20251215.xxxxx for user Laxman.Kadari@cloudfuze.com
   [SHARE] ✅ Chat cf.conversation.20251215.xxxxx shared by Laxman.Kadari@cloudfuze.com with token 57329aa2-...
   ```

✅ **Expected**: You see the success message in the console

---

## Test 2: Open Shared Link (As Logged-Out User - Most Important!)

**THIS IS THE KEY TEST - This is what Bharath experiences**

1. **IMPORTANT**: Use **Incognito/Private window** to test as a logged-out user
   - Windows: Ctrl+Shift+N
   - Mac: Cmd+Shift+N

2. In the **incognito window**, paste the shared link:
   ```
   https://ai.cloudfuze.com/chat/shared/57329aa2-7fe7-4d77-9a3c-757742ed9160
   ```

3. **BEFORE logging in**, open DevTools (F12) and go to **Console tab**

4. Watch the console logs as the page loads. You should see:
   ```
   [AUTH] No user found!
   [AUTH] Redirecting to: /login?redirect=/chat/shared/57329aa2-7fe7-4d77-9a3c-757742ed9160
   ```

5. You should be redirected to the login page
   - URL should be: `https://ai.cloudfuze.com/login?redirect=/chat/shared/57329aa2-...`

6. **Check console again** - you should see:
   ```
   [AUTH] Saved redirect URL to sessionStorage: /chat/shared/57329aa2-7fe7-4d77-9a3c-757742ed9160
   [AUTH] Saved redirect URL backup to localStorage: /chat/shared/57329aa2-7fe7-4d77-9a3c-757742ed9160
   [AUTH] sessionStorage value after save: /chat/shared/57329aa2-7fe7-4d77-9a3c-757742ed9160
   [AUTH] localStorage backup value after save: /chat/shared/57329aa2-7fe7-4d77-9a3c-757742ed9160
   ```

✅ **Expected**: Both redirects saved to storage

---

## Test 3: Complete Microsoft Login

1. Click "Sign in with Microsoft"
2. Complete the Microsoft OAuth login flow
3. You'll be redirected back to the login page
4. **Check console** - you should see:
   ```
   [AUTH] Login successful, completing sign-in...
   [AUTH] Token expires in XX minutes
   [AUTH] Retrieved redirect URL from sessionStorage: /chat/shared/57329aa2-7fe7-4d77-9a3c-757742ed9160
   [AUTH] Redirect URL is default (/): false
   [AUTH] Final redirect URL: /chat/shared/57329aa2-7fe7-4d77-9a3c-757742ed9160
   [AUTH] Login successful, redirecting to: /chat/shared/57329aa2-7fe7-4d77-9a3c-757742ed9160
   ```

✅ **Expected**: Should show the shared chat redirect URL, NOT `/`

---

## Test 4: Shared Chat Page Loading

1. After login, you're redirected to `/chat/shared/57329aa2-...`
2. You should see a loading spinner with "Loading shared chat..."
3. **Check console** - you should see:
   ```
   [SHARED] Effect triggered - isAuthenticated: true, shareToken: 57329aa2-7fe7-4d77-9a3c-757742ed9160
   [SHARED] Loading shared chat with token: 57329aa2-7fe7-4d77-9a3c-757742ed9160
   [SHARED] Calling endpoint: https://ai.cloudfuze.com/chat/shared/57329aa2-7fe7-4d77-9a3c-757742ed9160
   [SHARED] Auth header: Bearer xxxxxxxxxxxxxx...
   [SHARED] API response status: 200
   [SHARED] Chat copied successfully: cf.conversation.20251215.yyyyy
   [SHARED] Redirecting to /chat/cf.conversation.20251215.yyyyy
   ```

✅ **Expected**: Status 200 (success), should redirect to `/chat/{sessionId}`

---

## Test 5: Verify Chat Loads

1. You should be redirected to `/chat/{sessionId}`
2. The chat should display with all the messages from the original chat
3. You should be able to send new messages
4. The title should show "Shared: {original title}" or similar

✅ **Expected**: Chat loads successfully with all messages visible

---

## Test 6: Open Shared Link Again (Second Time)

1. **In the same incognito window**, open the shared link again:
   ```
   https://ai.cloudfuze.com/chat/shared/57329aa2-7fe7-4d77-9a3c-757742ed9160
   ```

2. **Check console** - you should see:
   ```
   [AUTH] User authenticated successfully: bharath@cloudfuze.com
   [SHARED] Loading shared chat with token: 57329aa2-7fe7-4d77-9a3c-757742ed9160
   [SHARED] API response status: 200
   [SHARED] Chat copied successfully (or shows existing): cf.conversation.20251215.yyyyy
   [SHARED] Redirecting to /chat/cf.conversation.20251215.yyyyy
   ```

✅ **Expected**: Should work the same way, either copying again or showing existing copy

---

## Test 7: Different User Opens Shared Link

Have Bharath test:

1. Logout completely (clear localStorage/cookies)
2. Open the shared link in an **incognito window**
3. Login with Bharath's account
4. Chat should load successfully
5. It should be a **COPY** of the original chat (not the original)

✅ **Expected**: Bharath sees the shared chat as a copy in his own chat list

---

## 🔴 If Any Test Fails

### Failure Pattern 1: No console logs appear
- **Problem**: Frontend code not deployed to production
- **Solution**: Redeploy frontend

### Failure Pattern 2: Console shows "Redirect URL is default (/): true"
- **Problem**: sessionStorage/localStorage is being cleared during OAuth
- **Solution**: The backup localStorage fix should solve this. If not, check browser security settings.

### Failure Pattern 3: API response status is 401 or 403
- **Problem**: Authentication token is invalid or expired
- **Solution**: Check token expiration, ensure token refresh is working

### Failure Pattern 4: API response status is 404
- **Problem**: Share token doesn't exist or has expired
- **Solution**: Check if share token is correctly stored in the database

### Failure Pattern 5: Gets error after clicking share
- **Problem**: Backend endpoint has an issue
- **Solution**: Check backend logs for error messages

---

## Console Log Checklist

Print this and check off as you test:

### Test 2: Login Redirect
- [ ] `[AUTH] No user found!`
- [ ] `[AUTH] Redirecting to: /login?redirect=/chat/shared/...`

### Test 3: Save Redirect URL
- [ ] `[AUTH] Saved redirect URL to sessionStorage: /chat/shared/...`
- [ ] `[AUTH] Saved redirect URL backup to localStorage: /chat/shared/...`
- [ ] Both storage values match

### Test 4: Retrieve Redirect URL
- [ ] `[AUTH] Retrieved redirect URL from sessionStorage: /chat/shared/...`
- [ ] `[AUTH] Redirect URL is default (/): false`
- [ ] Final redirect URL starts with `/chat/shared/`

### Test 5: Load Shared Chat
- [ ] `[SHARED] Loading shared chat with token: ...`
- [ ] `[SHARED] API response status: 200`
- [ ] `[SHARED] Redirecting to /chat/...`

### Test 6: Chat Loads
- [ ] Chat is displayed with messages
- [ ] Can send new messages

### Test 7: Second Open
- [ ] Same steps as Test 5 work again
- [ ] No errors

---

## Sharing the Results

When reporting issues, include:

1. Which test(s) failed?
2. What's the exact console output?
3. What's the URL bar showing at each step?
4. Are you in incognito/private mode?
5. Browser type and version?
6. Is it happening on `ai.cloudfuze.com` or local dev?

---

## Quick Reproduction Steps for Bharath

1. Open incognito window
2. Paste shared link
3. Login with Microsoft
4. **Check if you get redirected to `/chat/new` or `/chat/shared/...`**
5. Take a screenshot of the URL bar
6. Share the console logs (F12 → Console)

---

## Backend Testing (For Admin)

If frontend tests pass but backend fails:

```bash
# Test the shared chat endpoint directly
SHARE_TOKEN="57329aa2-7fe7-4d77-9a3c-757742ed9160"
USER_TOKEN="<valid_microsoft_access_token>"

curl -X GET "https://ai.cloudfuze.com/chat/shared/$SHARE_TOKEN" \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -v
```

Expected response:
```json
{
  "session_id": "cf.conversation.20251215.xxxxx",
  "title": "Shared: ...",
  "messages": [...],
  "created_at": 1702637400000,
  "updated_at": 1702637400000,
  "original_owner": "Laxman.Kadari@cloudfuze.com",
  "message": "Chat copied successfully to your chats",
  "is_existing": false
}
```

---

## Success Criteria

All 7 tests must pass with the expected console logs and UI behavior.

✅ **Shared chat link feature is working correctly when:**
1. Logged-out user opens link → redirects to login
2. Login saves redirect URL → retrieved after OAuth
3. User is redirected to shared chat page → API returns 200
4. Chat loads successfully → all messages visible
5. User can interact with chat → send messages, etc.
6. Second open works → either copies again or shows existing copy
7. Different user can open → creates copy in their account







