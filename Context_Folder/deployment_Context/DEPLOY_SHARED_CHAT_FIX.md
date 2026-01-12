# Deploy Shared Chat Fix - Step by Step

## What Was Changed

### Frontend Changes
1. **`frontend/src/app/login/page.tsx`** - Enhanced redirect URL handling
   - Added backup localStorage storage for redirect URL (in case sessionStorage is cleared)
   - Added detailed console logging to track redirect URL flow
   - File has been modified and tested ✅

2. **`frontend/src/app/chat/shared/[token]/page.tsx`** - Enhanced error handling
   - Added detailed console logging for debugging
   - Better error messages for different HTTP status codes
   - File has been modified and tested ✅

### No Backend Changes
- Backend endpoints are already working correctly
- No new API endpoints needed

---

## Deployment Steps

### Step 1: Verify Local Changes

```bash
cd C:\Users\LaxmanKadari\Desktop\v1-dev\chatbot

# Check git status
git status

# You should see these files modified:
# - frontend/src/app/login/page.tsx
# - frontend/src/app/chat/shared/[token]/page.tsx
```

### Step 2: Build Frontend

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies (if needed)
npm install

# Build the frontend
npm run build

# Expected output:
# ✓ compiled successfully
# ✓ built in XXs
```

### Step 3: Test Locally (Optional)

```bash
# Start the Next.js dev server
npm run dev

# In browser:
# 1. Open http://localhost:3000
# 2. Follow the testing guide in TESTING_SHARED_CHAT.md
```

### Step 4: Commit Changes

```bash
cd ..

# Stage the changes
git add frontend/src/app/login/page.tsx
git add frontend/src/app/chat/shared/[token]/page.tsx
git add SHARED_CHAT_LINK_FIX.md
git add TESTING_SHARED_CHAT.md
git add DEPLOY_SHARED_CHAT_FIX.md

# Commit
git commit -m "fix: Enhanced shared chat link redirect and error handling

- Add localStorage backup for oauth_redirect URL
- Add detailed console logging for debugging
- Better error messages for different HTTP status codes
- Improve reliability of redirect flow after OAuth"

# Push to main
git push origin main
```

### Step 5: Deploy to Production

**Option A: Using Docker Compose (Recommended)**

```bash
# SSH into production server
ssh user@ai.cloudfuze.com

# Navigate to app directory
cd /opt/slack2teams-ai

# Pull latest changes
git pull origin main

# Verify the changes were pulled
git log --oneline -5 | head -3

# Build and restart the frontend
docker-compose down
docker-compose up -d --build

# Wait for containers to be ready (30-60 seconds)
sleep 60

# Verify services are running
docker-compose ps

# Check frontend logs
docker logs slack2teams-ai_frontend_1 --tail 20
```

**Option B: Manual Deployment (If not using Docker)**

```bash
ssh user@ai.cloudfuze.com

cd /opt/slack2teams-ai/frontend

# Pull latest changes
git pull origin main

# Build
npm run build

# Restart the frontend service
pm2 restart frontend
# or
systemctl restart frontend
```

### Step 6: Verify Deployment

```bash
# Check if frontend is serving
curl -I https://ai.cloudfuze.com/

# Should return HTTP/1.1 200 OK

# Check frontend logs for any errors
docker logs slack2teams-ai_frontend_1 | tail -30

# Expected: No error messages, normal Next.js startup logs
```

### Step 7: Test in Production

1. **Use TESTING_SHARED_CHAT.md to verify**:
   - Have Laxman share a chat
   - Have someone else (Bharath) open the link in incognito
   - Verify all 7 tests pass

2. **Monitor logs**:
   ```bash
   # Watch frontend logs in real-time
   docker logs -f slack2teams-ai_frontend_1

   # Watch backend logs for shared chat requests
   docker logs -f slack2teams-ai_backend_1 | grep -i "share"
   ```

3. **Check for errors**:
   - No console errors in browser (F12)
   - No 4xx/5xx errors in network tab
   - Redirect happens correctly

---

## Rollback Plan (If Something Goes Wrong)

```bash
# SSH into production
ssh user@ai.cloudfuze.com

# Option 1: Revert git
cd /opt/slack2teams-ai
git revert HEAD
git push origin main

# Option 2: Restart previous container
docker-compose down
docker-compose up -d

# Option 3: Clear frontend cache
rm -rf frontend/.next
npm run build
```

---

## Success Criteria

✅ **Deployment is successful when:**
1. Frontend builds without errors
2. Services restart successfully
3. https://ai.cloudfuze.com loads without errors
4. Test 1: Laxman can share a chat ✅
5. Test 2-7: Bharath can open shared link and see redirects in console ✅
6. No error messages in production logs
7. Both incognito and logged-in scenarios work

---

## Timeline

| Step | Duration | Notes |
|------|----------|-------|
| Build frontend | 2-3 min | First time will be slower |
| Commit & Push | 1 min | Ensure git push succeeds |
| Pull on prod | 1 min | Check git log after |
| Docker rebuild | 5-10 min | Wait for image build |
| Restart services | 1-2 min | Check docker-compose ps |
| Health check | 2 min | Verify frontend loads |
| Testing | 10-15 min | Follow TESTING_SHARED_CHAT.md |
| **Total** | **~25-35 min** | Typically faster on repeat |

---

## Monitoring After Deploy

### First Hour
- Monitor frontend logs: `docker logs -f slack2teams-ai_frontend_1`
- Check for any 401/403 errors
- Monitor for memory/CPU spikes
- Watch for crash loops (restart cycles)

### First Day
- Have Bharath test the shared link feature
- Monitor for any error patterns
- Check backend logs for share-related errors
- Verify all users can still access their chats

### First Week
- Verify no performance regressions
- Check shared chat feature works for multiple users
- Monitor for memory leaks
- Collect feedback from users

---

## Quick Command Reference

```bash
# View current deployed version
cd /opt/slack2teams-ai && git log --oneline -1

# Rebuild and restart
cd /opt/slack2teams-ai
git pull origin main
docker-compose down
docker-compose up -d --build
sleep 60

# Check status
docker-compose ps

# View logs
docker logs slack2teams-ai_frontend_1 --tail 50
docker logs slack2teams-ai_backend_1 --tail 50

# Restart just frontend
docker-compose restart slack2teams-ai_frontend_1

# View real-time logs
docker logs -f slack2teams-ai_frontend_1
```

---

## Troubleshooting

### Issue: Frontend shows 404 errors

```bash
# Clear Next.js build cache
rm -rf /opt/slack2teams-ai/frontend/.next

# Rebuild
cd /opt/slack2teams-ai/frontend
npm run build

# Restart
docker-compose restart slack2teams-ai_frontend_1
```

### Issue: Redirect still not working

```bash
# Check if changes were deployed
grep "localStorage.setItem('oauth_redirect_backup'" \
  /opt/slack2teams-ai/frontend/src/app/login/page.tsx

# If not found, changes didn't deploy:
cd /opt/slack2teams-ai
git pull origin main
git log --oneline -3  # Verify latest commit is there
docker-compose up -d --build
```

### Issue: High memory usage after deploy

```bash
# Restart services
docker-compose restart

# Check Node process memory
docker stats slack2teams-ai_frontend_1
```

---

## Documentation Files

- **SHARED_CHAT_LINK_FIX.md** - Complete diagnosis and technical details
- **TESTING_SHARED_CHAT.md** - Step-by-step testing guide with expected logs
- **DEPLOY_SHARED_CHAT_FIX.md** - This file, deployment instructions

---

## Sign-Off

After successful deployment, fill out this checklist:

- [ ] Changes committed to git
- [ ] Frontend builds successfully
- [ ] Services restart without errors
- [ ] Frontend loads in browser
- [ ] No console errors in browser
- [ ] Shared chat link feature tested (all 7 tests pass)
- [ ] No new errors in production logs
- [ ] Rollback plan documented (above)
- [ ] Deployed on: ________ (date)
- [ ] Deployed by: ________ (name)
- [ ] Tested by: ________ (name)

---

## Need Help?

If deployment fails or tests don't pass, check:

1. **Frontend build errors**: Look at npm build output
2. **Runtime errors**: Check browser console (F12)
3. **Network errors**: Check network tab for failed requests
4. **Server errors**: Check backend logs for 5xx errors
5. **Auth errors**: Check browser DevTools for token issues

Share the following when reporting issues:
- Frontend build output
- Browser console logs (F12)
- Network tab errors (F12 → Network)
- Backend logs (docker logs)
- URL bar at each step
- Are you in incognito mode?







