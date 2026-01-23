# Nginx Security Implementation Guide

## ✅ What Has Been Completed

### 1. **Rate Limiting Zones** (Lines 4-10)
- ✅ API limit: 10 requests/second
- ✅ Chat limit: 5 requests/second  
- ✅ Auth limit: 3 requests/second
- ✅ General limit: 30 requests/second
- ✅ Connection limiting: 20 connections per IP

### 2. **Connection Pooling** (Lines 15-27)
- ✅ `backend_pool` upstream with keepalive
- ✅ `frontend_pool` upstream with keepalive

### 3. **Logging Configuration** (Lines 32-40)
- ✅ Access and error logs configured
- ✅ Security log format defined

### 4. **Attack Pattern Blocking** (Lines 45-55)
- ✅ Blocks common attack patterns (.env, .git, etc.)
- ✅ Blocks suspicious user agents (sqlmap, nikto, etc.)

### 5. **SSL Enhancements** (Lines 451-458)
- ✅ OCSP stapling enabled
- ✅ Session tickets disabled
- ✅ Enhanced SSL settings

### 6. **Request Size Limits** (Lines 424-434)
- ✅ 10MB max body size
- ✅ Buffer optimizations

### 7. **Security Headers** (Lines 363-396)
- ✅ HSTS with preload
- ✅ CSP policy
- ✅ All security headers configured

## ⚠️ What Still Needs to Be Done

### HTTPS Server Location Blocks Need Rate Limiting

The following location blocks in the **HTTPS server** (starting at line 414) need rate limiting headers added. Currently, only `/analytics/` has rate limiting.

#### Template for Adding Rate Limiting:

Add these lines **immediately after** `location /path/ {`:

```nginx
        limit_req zone=ZONE_NAME burst=BURST_SIZE nodelay;
        limit_req_status 429;
        
        proxy_pass http://backend_pool/path/;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
```

#### Specific Changes Needed:

**1. `/api/proxy/` (Line 540)**
```nginx
    location /api/proxy/ {
        limit_req zone=api_limit burst=20 nodelay;
        limit_req_status 429;
        
        rewrite ^/api/proxy/(.*) /$1 break;
        proxy_pass http://backend_pool;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        # ... rest of config
```

**2. `/api/shared-chat/` (Line 565)**
```nginx
    location /api/shared-chat/ {
        limit_req zone=general_limit burst=50 nodelay;
        limit_req_status 429;
        
        proxy_pass http://frontend_pool;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        # ... rest of config
```

**3. `/api/` (Line 586)**
```nginx
    location /api/ {
        limit_req zone=api_limit burst=20 nodelay;
        limit_req_status 429;
        
        proxy_pass http://backend_pool/api/;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        # ... rest of config
```

**4. `/chat/(sessions|history|stream|share)` (Line 608)**
```nginx
    location ~ ^/chat/(sessions|history|stream|share)(/|$) {
        limit_req zone=chat_limit burst=10 nodelay;
        limit_req_status 429;
        
        proxy_pass http://backend_pool;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        # ... rest of config
```

**5. `/chat/shared/[^/]+$` (Line 627)**
```nginx
    location ~ ^/chat/shared/[^/]+$ {
        limit_req zone=general_limit burst=50 nodelay;
        limit_req_status 429;
        
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        # ... rest of config
```

**6. `/chat` (Line 656)**
```nginx
    location = /chat {
        limit_req zone=chat_limit burst=10 nodelay;
        limit_req_status 429;
        
        proxy_pass http://backend_pool/chat;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        # ... rest of config
```

**7. `/chat/` (Line 671)**
```nginx
    location = /chat/ {
        limit_req zone=chat_limit burst=10 nodelay;
        limit_req_status 429;
        
        proxy_pass http://backend_pool/chat/;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        # ... rest of config
```

**8. `/auth/microsoft/callback` (Line 686)**
```nginx
    location /auth/microsoft/callback {
        limit_req zone=auth_limit burst=5 nodelay;
        limit_req_status 429;
        
        proxy_pass http://backend_pool/auth/microsoft/callback;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        # ... rest of config
```

**9. `/auth/` (Line 702)**
```nginx
    location /auth/ {
        limit_req zone=auth_limit burst=5 nodelay;
        limit_req_status 429;
        
        proxy_pass http://backend_pool/auth/;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        # ... rest of config
```

**10. `/health` (Line 723) - NO RATE LIMITING**
```nginx
    # Health check - NO RATE LIMITING (for monitoring)
    location /health {
        proxy_pass http://backend_pool/health;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        # ... rest of config
        access_log off;  # Reduce log noise
    }
```

**11. `/feedback` (Line 732)**
```nginx
    location /feedback {
        limit_req zone=api_limit burst=10 nodelay;
        limit_req_status 429;
        
        proxy_pass http://backend_pool/feedback;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        # ... rest of config
```

**12. `/user/` (Line 743)**
```nginx
    location /user/ {
        limit_req zone=api_limit burst=20 nodelay;
        limit_req_status 429;
        
        proxy_pass http://backend_pool/user/;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        # ... rest of config
```

**13. `/teams/` (Line 764)**
```nginx
    location /teams/ {
        limit_req zone=api_limit burst=20 nodelay;
        limit_req_status 429;
        
        proxy_pass http://backend_pool/teams/;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        # ... rest of config
```

**14. `/images/` (Line 789)**
```nginx
    location /images/ {
        limit_req zone=general_limit burst=50 nodelay;
        limit_req_status 429;
        
        proxy_pass http://frontend_pool/images/;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        # ... rest of config
```

**15. `/_next/static/` (Line 800)**
```nginx
    location /_next/static/ {
        limit_req zone=general_limit burst=50 nodelay;
        limit_req_status 429;
        
        proxy_pass http://frontend_pool;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        # ... rest of config
```

**16. `/` (Line 808) - Catch-all**
```nginx
    location / {
        limit_req zone=general_limit burst=50 nodelay;
        limit_req_status 429;
        
        proxy_pass http://frontend_pool;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        # ... rest of config
```

## 📋 Next Steps

### Step 1: Test Configuration
```bash
# Test nginx configuration syntax
nginx -t

# Or if using Docker:
docker exec <nginx-container> nginx -t
```

### Step 2: Reload Nginx
```bash
# Reload nginx configuration
nginx -s reload

# Or if using Docker:
docker exec <nginx-container> nginx -s reload
```

### Step 3: Verify Rate Limiting
```bash
# Test rate limiting (should get 429 after exceeding limit)
for i in {1..15}; do 
    curl -I https://ai.cloudfuze.com/api/health
    sleep 0.1
done
```

### Step 4: Monitor Logs
```bash
# Watch for rate limit violations
tail -f /var/log/nginx/access.log | grep " 429 "

# Or if using Docker:
docker exec <nginx-container> tail -f /var/log/nginx/access.log | grep " 429 "
```

### Step 5: Test Application Functionality
- ✅ Test Microsoft OAuth login
- ✅ Test chat functionality
- ✅ Test streaming endpoints
- ✅ Test static file serving
- ✅ Test WebSocket connections

## 🔍 Verification Checklist

- [ ] All HTTPS location blocks have rate limiting
- [ ] All proxy_pass directives use connection pooling (`backend_pool` or `frontend_pool`)
- [ ] All location blocks have `proxy_http_version 1.1` and `proxy_set_header Connection ""`
- [ ] Nginx configuration test passes (`nginx -t`)
- [ ] Application functionality works correctly
- [ ] Rate limiting is working (test with curl)
- [ ] No 502/503 errors after reload

## 📊 Rate Limiting Summary

| Endpoint Type | Rate Limit | Burst | Zone |
|--------------|------------|-------|------|
| Analytics | 10 req/s | 20 | api_limit |
| API | 10 req/s | 20 | api_limit |
| Chat | 5 req/s | 10 | chat_limit |
| Auth | 3 req/s | 5 | auth_limit |
| General/Frontend | 30 req/s | 50 | general_limit |
| Health | None | - | - |

## 🚨 Important Notes

1. **Connection Pooling**: Make sure `proxy_set_header Connection ""` comes AFTER `proxy_http_version 1.1` but BEFORE other headers.

2. **WebSocket Support**: For WebSocket endpoints, keep the `Upgrade` and `Connection "upgrade"` headers AFTER the initial `Connection ""` header.

3. **Health Check**: Do NOT add rate limiting to `/health` endpoint - it's used for monitoring.

4. **Testing**: After adding rate limiting, test thoroughly to ensure legitimate users aren't blocked.

5. **Monitoring**: Watch logs for 429 responses to adjust limits if needed.

## 🎯 Current Status

- ✅ Infrastructure: Rate limiting zones, connection pooling, SSL enhancements
- ✅ Security Headers: All implemented
- ⚠️ Rate Limiting: Only `/analytics/` has it, others need manual addition
- ✅ Connection Pooling: Upstream blocks created, need to ensure all use them

---

**Last Updated**: 2025-01-09
**File**: `nginx-ai.conf`
