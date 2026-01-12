# Docker Configuration Documentation

## Overview

Docker configuration files for containerizing the CloudFuze Chatbot application.

---

## Dockerfiles

### `Dockerfile` (Full-Featured)
**Location:** `Dockerfile`

**Purpose:** Full-featured Dockerfile for development and initialization

**Use when:**
- `INITIALIZE_VECTORSTORE=true` (vectorstore rebuild needed)
- Running SharePoint Selenium extraction
- Development/testing with all features

**Base Image:** `python:3.11-slim`

**Features:**
- Chrome/Chromium for Selenium
- All Python dependencies
- Full requirements.txt
- System dependencies (gcc, g++, curl, wget)

**Key Sections:**
```dockerfile
# Install system dependencies including Chrome for Selenium
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    wget \
    google-chrome-stable

# Install ALL Python dependencies
RUN pip install --no-cache-dir -r requirements.txt
```

**Size:** Larger (~2GB+)

---

### `Dockerfile.prod` (Production)
**Location:** `Dockerfile.prod`

**Purpose:** Production-optimized Dockerfile

**Use when:**
- Production deployment
- Pre-built vectorstore available
- No Selenium needed
- Minimal dependencies

**Base Image:** `python:3.11-slim`

**Features:**
- Minimal system dependencies
- Production requirements only
- No Chrome/Selenium
- Optimized for size

**Key Sections:**
```dockerfile
# Install minimal system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install production requirements only
RUN pip install --no-cache-dir -r requirements.prod.txt
```

**Size:** Smaller (~500MB-1GB)

---

### `Dockerfile.prod.light` (Lightweight Production)
**Location:** `Dockerfile.prod.light`

**Purpose:** Ultra-lightweight production Dockerfile

**Use when:**
- Minimal production deployment
- Very small image size required
- Only essential features

**Features:**
- Minimal dependencies
- Lightweight requirements
- Optimized layers

**Size:** Smallest (~300-500MB)

---

### `frontend/Dockerfile.frontend` (Frontend)
**Location:** `frontend/Dockerfile.frontend`

**Purpose:** Frontend Next.js application Dockerfile

**Features:**
- Node.js base image
- Next.js build
- Static file serving
- Production optimization

---

## Docker Compose Files

### `docker-compose.yml` (Development)
**Location:** `docker-compose.yml`

**Purpose:** Development environment with all services

**Services:**
- `backend` - FastAPI backend
- `nginx` - Reverse proxy
- `mongodb` - MongoDB database
- `langfuse` - Observability (optional, profile: observability)
- `postgres` - PostgreSQL for Langfuse (optional, profile: observability)

**Features:**
- Volume mounts for development
- Hot reload support
- Full environment variables
- Health checks

---

### `docker-compose.prod.yml` (Production)
**Location:** `docker-compose.prod.yml`

**Purpose:** Production environment configuration

**Features:**
- Production-optimized settings
- Resource limits
- Restart policies
- Security configurations

---

### `docker-compose.ai.yml` (AI/ML Services)
**Location:** `docker-compose.ai.yml`

**Purpose:** Configuration for AI/ML services

**Features:**
- AI service configurations
- ML model serving
- GPU support (if available)

---

### `docker-compose.atlas.yml` (MongoDB Atlas)
**Location:** `docker-compose.atlas.yml`

**Purpose:** Configuration using MongoDB Atlas (cloud)

**Features:**
- External MongoDB Atlas connection
- No local MongoDB container
- Cloud database configuration

---

## Service Configurations

### Backend Service

**Common Configuration:**
```yaml
backend:
  build: .
  container_name: slack2teams-backend
  ports:
    - "8002:8002"
  environment:
    - OPENAI_API_KEY=${OPENAI_API_KEY}
    - MONGODB_URL=${MONGODB_URL}
    # ... more env vars
  volumes:
    - ./data:/app/data
    - ./images:/app/images
  restart: unless-stopped
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8002/health"]
    interval: 30s
    timeout: 10s
    retries: 3
```

**Environment Variables:**
- API keys (OpenAI, Microsoft, Langfuse)
- Database URLs
- Feature flags (ENABLE_*_SOURCE)
- Source paths

---

### Nginx Service

**Configuration:**
```yaml
nginx:
  image: nginx:alpine
  container_name: slack2teams-nginx
  ports:
    - "80:80"
    - "443:443"
  volumes:
    - ./nginx.conf:/etc/nginx/conf.d/default.conf
    - ./images:/var/www/html/images
  depends_on:
    - backend
  restart: unless-stopped
```

**Features:**
- Reverse proxy to backend
- Static file serving
- SSL/TLS support (if configured)
- Gzip compression

---

### MongoDB Service

**Configuration:**
```yaml
mongodb:
  image: mongo:7.0
  container_name: slack2teams-mongodb
  ports:
    - "27017:27017"
  environment:
    - MONGO_INITDB_DATABASE=slack2teams
  volumes:
    - mongodb_data:/data/db
  restart: unless-stopped
```

**Features:**
- Persistent data volume
- Health checks
- Initial database setup

---

## Build Commands

### Build Development Image
```bash
docker build -t slack2teams-backend .
```

### Build Production Image
```bash
docker build -f Dockerfile.prod -t slack2teams-backend:prod .
```

### Build Lightweight Image
```bash
docker build -f Dockerfile.prod.light -t slack2teams-backend:light .
```

### Build Frontend
```bash
cd frontend
docker build -f Dockerfile.frontend -t slack2teams-frontend .
```

---

## Run Commands

### Development
```bash
docker-compose up --build
```

### Production
```bash
docker-compose -f docker-compose.prod.yml up -d
```

### With Observability
```bash
docker-compose --profile observability up -d
```

### MongoDB Atlas
```bash
docker-compose -f docker-compose.atlas.yml up -d
```

---

## Volume Mounts

### Data Volumes
- `./data:/app/data` - Vectorstore and chat history
- `./images:/app/images` - Static images
- `mongodb_data:/data/db` - MongoDB data (named volume)

### Configuration Volumes
- `./nginx.conf:/etc/nginx/conf.d/default.conf` - Nginx config
- `./.env` - Environment variables (if mounted)

---

## Health Checks

### Backend Health Check
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8002/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

### Nginx Health Check
```yaml
healthcheck:
  test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost/health"]
  interval: 30s
  timeout: 10s
  retries: 3
```

### MongoDB Health Check
```yaml
healthcheck:
  test: ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]
  interval: 30s
  timeout: 10s
  retries: 3
```

---

## Environment Variables

### Required Variables
- `OPENAI_API_KEY` - OpenAI API key
- `MICROSOFT_CLIENT_ID` - Microsoft OAuth client ID
- `MICROSOFT_CLIENT_SECRET` - Microsoft OAuth secret
- `MICROSOFT_TENANT` - Microsoft tenant ID
- `MONGODB_URL` - MongoDB connection string

### Optional Variables
- `LANGFUSE_PUBLIC_KEY` - Langfuse public key
- `LANGFUSE_SECRET_KEY` - Langfuse secret key
- `LANGFUSE_HOST` - Langfuse host URL
- `ENABLE_*_SOURCE` - Feature flags
- `*_SOURCE_DIR` - Source directories

---

## Best Practices

1. **Use Production Dockerfile:** Use `Dockerfile.prod` for production
2. **Health Checks:** Always include health checks
3. **Resource Limits:** Set resource limits in production
4. **Secrets Management:** Use secrets management (not .env in production)
5. **Volume Persistence:** Use named volumes for data
6. **Multi-stage Builds:** Consider multi-stage builds for smaller images
7. **Layer Caching:** Optimize layer order for caching

---

## Troubleshooting

### Build Issues
- **Dependencies:** Check requirements.txt
- **System Packages:** Verify apt-get packages
- **Permissions:** Check file permissions

### Runtime Issues
- **Port Conflicts:** Check port availability
- **Volume Mounts:** Verify volume paths
- **Environment Variables:** Check .env file

### Health Check Failures
- **Service Startup:** Check service logs
- **Network:** Verify container networking
- **Dependencies:** Check service dependencies

---

## Key Files

- **`Dockerfile`** - Full-featured development Dockerfile
- **`Dockerfile.prod`** - Production Dockerfile
- **`Dockerfile.prod.light`** - Lightweight production Dockerfile
- **`docker-compose.yml`** - Development compose file
- **`docker-compose.prod.yml`** - Production compose file
- **`docker-compose.ai.yml`** - AI services compose file
- **`docker-compose.atlas.yml`** - MongoDB Atlas compose file

---

**Last Updated:** 2025-01-09  
**Location:** Root directory
