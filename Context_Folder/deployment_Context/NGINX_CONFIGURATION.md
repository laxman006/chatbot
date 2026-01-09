# Nginx Configuration Documentation

## Overview

Nginx reverse proxy and static file server configuration for the CloudFuze Chatbot.

---

## Configuration Files

### `nginx.conf` (Main Configuration)
**Location:** `nginx.conf`

**Purpose:** Main Nginx configuration for development/production

**Features:**
- Reverse proxy to FastAPI backend
- Static file serving
- Gzip compression
- Security headers
- WebSocket support
- SSL/TLS configuration (if enabled)

---

### `nginx-prod.conf` (Production)
**Location:** `nginx-prod.conf`

**Purpose:** Production-optimized Nginx configuration

**Features:**
- Production security settings
- Optimized caching
- Rate limiting
- Enhanced logging

---

### `nginx-ai.conf` (AI Services)
**Location:** `nginx-ai.conf`

**Purpose:** Configuration for AI/ML services

**Features:**
- AI service routing
- Model serving endpoints
- GPU routing (if available)

---

### `nginx-newcf3.conf` (New CF3 Server)
**Location:** `nginx-newcf3.conf`

**Purpose:** Configuration for new CF3 server deployment

**Features:**
- Server-specific settings
- Custom routing rules

---

## Configuration Sections

### Server Block
```nginx
server {
    listen 80;
    server_name _;

    # Configuration...
}
```

**Ports:**
- `80` - HTTP
- `443` - HTTPS (if SSL configured)

---

### Gzip Compression
```nginx
gzip on;
gzip_vary on;
gzip_min_length 1024;
gzip_types text/plain text/css text/xml text/javascript 
           application/javascript application/xml+rss application/json;
```

**Benefits:**
- Reduced bandwidth
- Faster page loads
- Better user experience

---

### Security Headers
```nginx
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "no-referrer-when-downgrade" always;
add_header Content-Security-Policy "default-src 'self' http: https: data: blob: 'unsafe-inline'" always;
```

**Security Features:**
- XSS protection
- Clickjacking protection
- MIME type sniffing prevention
- Referrer policy
- Content Security Policy

---

### Static File Serving
```nginx
location / {
    root /var/www/html;
    try_files $uri $uri/ @backend;
    
    # Cache static assets
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

**Features:**
- Static file root
- Fallback to backend
- Long-term caching for assets

---

### Backend Proxy
```nginx
location @backend {
    proxy_pass http://backend:8002;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Port $server_port;
    
    # WebSocket support
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    
    # Timeouts
    proxy_connect_timeout 180s;
    proxy_send_timeout 180s;
    proxy_read_timeout 180s;
}
```

**Features:**
- Proxy to FastAPI backend
- Header forwarding
- WebSocket support
- Extended timeouts for initialization

---

### API Routes
```nginx
location /api/ {
    proxy_pass http://backend:8002;
    # API-specific configuration
}
```

**Routes:**
- `/api/` - API endpoints
- `/chat/` - Chat endpoints
- `/admin/` - Admin endpoints

---

## SSL/TLS Configuration

### SSL Certificate Setup
```nginx
server {
    listen 443 ssl;
    server_name example.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
}
```

**SSL Features:**
- TLS 1.2 and 1.3
- Strong cipher suites
- Certificate validation

---

## Rate Limiting

### Rate Limit Configuration
```nginx
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;

location /api/ {
    limit_req zone=api_limit burst=20 nodelay;
    proxy_pass http://backend:8002;
}
```

**Features:**
- IP-based rate limiting
- Burst handling
- Configurable limits

---

## Logging

### Access Logs
```nginx
access_log /var/log/nginx/access.log;
error_log /var/log/nginx/error.log warn;
```

**Log Levels:**
- `debug` - Detailed debugging
- `info` - Informational
- `warn` - Warnings
- `error` - Errors only

---

## Docker Integration

### Volume Mount
```yaml
nginx:
  volumes:
    - ./nginx.conf:/etc/nginx/conf.d/default.conf
```

**Configuration:**
- Mounted as default configuration
- Hot reload on changes (if configured)

---

## Performance Optimization

### Caching
```nginx
# Static assets
location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
    expires 1y;
    add_header Cache-Control "public, immutable";
}

# API responses (if appropriate)
location /api/cache/ {
    proxy_cache_valid 200 1h;
    proxy_cache_key "$scheme$request_method$host$request_uri";
}
```

---

### Connection Pooling
```nginx
upstream backend {
    server backend:8002;
    keepalive 32;
}
```

**Benefits:**
- Reduced connection overhead
- Better performance
- Connection reuse

---

## Troubleshooting

### Common Issues

**502 Bad Gateway:**
- Backend not running
- Backend not accessible
- Port mismatch

**504 Gateway Timeout:**
- Increase timeout values
- Check backend performance
- Verify network connectivity

**Static Files Not Serving:**
- Check file paths
- Verify volume mounts
- Check permissions

---

## Best Practices

1. **Security Headers:** Always include security headers
2. **Gzip Compression:** Enable for text-based content
3. **SSL/TLS:** Use HTTPS in production
4. **Rate Limiting:** Implement rate limiting for APIs
5. **Caching:** Cache static assets aggressively
6. **Logging:** Configure appropriate log levels
7. **Timeouts:** Set appropriate timeout values

---

## Key Files

- **`nginx.conf`** - Main Nginx configuration
- **`nginx-prod.conf`** - Production configuration
- **`nginx-ai.conf`** - AI services configuration
- **`nginx-newcf3.conf`** - New CF3 server configuration

---

**Last Updated:** 2025-01-09  
**Location:** Root directory
