# Development Proxy Setup

## ✅ Why This Exists

Browsers block cross-origin cookies on localhost (security policy). This makes session-based auth difficult when:
- Frontend: `http://localhost:3000` (Next.js)
- Backend: `http://localhost:8002` (FastAPI)

**Solution:** Use Next.js API proxy in development (same-origin = cookies work automatically).

## 🏗️ Architecture

### Development (Local)
```
Browser → localhost:3000 → Next.js API Proxy → localhost:8002 (FastAPI)
         (same-origin)      (forwards request)   (backend)
```

### Production
```
Browser → ai.cloudfuze.com → Nginx/Cloud LB → FastAPI
         (HTTPS)            (reverse proxy)   (backend)
```

**Same backend logic, different routing.**

## 📁 Files Created

### `frontend/src/app/api/proxy/[...path]/route.ts`
- Next.js API route that proxies all requests to FastAPI backend
- Forwards cookies automatically (same-origin)
- Handles all HTTP methods (GET, POST, PUT, DELETE, PATCH)

## 🔧 Configuration

### Environment Variables

Create `frontend/.env.local`:
```bash
# Enable Next.js proxy in development (default: true)
NEXT_PUBLIC_USE_PROXY=true

# Direct backend URL (used if proxy disabled or in production)
NEXT_PUBLIC_API_URL=http://127.0.0.1:8002
```

### How It Works

1. **Development (proxy enabled):**
   - Frontend calls: `/api/proxy/chat/sessions/all`
   - Next.js proxy forwards to: `http://127.0.0.1:8002/chat/sessions/all`
   - Cookies work automatically (same-origin)

2. **Production (proxy disabled):**
   - Frontend calls: `https://ai.cloudfuze.com/chat/sessions/all`
   - Direct backend call (handled by reverse proxy)
   - Cookies work (HTTPS + proper CORS)

## 🧪 Testing

1. **Start backend:**
   ```bash
   python server.py
   ```

2. **Start frontend:**
   ```bash
   cd frontend
   npm run dev
   ```

3. **Test login:**
   - Go to `http://localhost:3000/login`
   - Login with Microsoft
   - Check DevTools → Application → Cookies
   - Should see `session_id` cookie

4. **Verify proxy:**
   - Check browser Network tab
   - API calls should go to `/api/proxy/...`
   - Backend logs should show requests from Next.js

## 🔒 Cookie Settings

### Development (via proxy)
- `secure=False` (HTTP)
- `samesite="lax"` (same-origin)
- `httponly=True`
- Works automatically ✅

### Production (direct)
- `secure=True` (HTTPS)
- `samesite="none"` (cross-origin)
- `httponly=True`
- Requires proper CORS ✅

## 🚀 Production Deployment

When deploying to production:

1. **Disable proxy** (set `NEXT_PUBLIC_USE_PROXY=false`)
2. **Set production backend URL** (`NEXT_PUBLIC_API_URL=https://ai.cloudfuze.com`)
3. **Configure reverse proxy** (nginx/cloud load balancer)
4. **Backend automatically uses production cookie settings**

## 📝 Notes

- ✅ This is **standard practice** (used by many production apps)
- ✅ **No security compromise** (proxy only in development)
- ✅ **Matches production architecture** (reverse proxy model)
- ✅ **Easy to disable** (just set env variable)

## 🐛 Troubleshooting

### Cookies not working?
1. Check `NEXT_PUBLIC_USE_PROXY=true` in `.env.local`
2. Restart Next.js dev server
3. Clear browser cookies
4. Check Network tab - requests should go to `/api/proxy/...`

### Proxy not forwarding?
1. Check backend is running on port 8002
2. Check Next.js console for proxy errors
3. Verify `getApiBase()` returns `/api/proxy` in development

### Still seeing CORS errors?
- Proxy should eliminate CORS (same-origin)
- If you see CORS errors, proxy might not be working
- Check `frontend/src/lib/session-utils.ts` - `getApiBase()` should return `/api/proxy`

