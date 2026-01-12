# Deployment Documentation Index

## Complete Deployment Documentation

This index provides navigation to all deployment-related documentation.

---

## 📋 All Documentation Files

### 1. [Docker Configuration](./DOCKER_CONFIGURATION.md)
**Purpose:** Docker configuration files and containerization

**Contents:**
- Dockerfiles (Dockerfile, Dockerfile.prod, Dockerfile.prod.light)
- Docker Compose files (docker-compose.yml, docker-compose.prod.yml, etc.)
- Service configurations
- Build and run commands
- Volume mounts
- Health checks

---

### 2. [Nginx Configuration](./NGINX_CONFIGURATION.md)
**Purpose:** Nginx reverse proxy and static file server

**Contents:**
- Nginx configuration files
- Server blocks
- Gzip compression
- Security headers
- Static file serving
- Backend proxy
- SSL/TLS configuration
- Rate limiting
- Logging

---

### 3. [Deployment Scripts](./DEPLOYMENT_SCRIPTS.md)
**Purpose:** Shell scripts for deployment

**Contents:**
- Main deployment script (deploy.sh)
- AI services deployment (deploy-ai.sh)
- Server-specific deployments
- Service management scripts
- Setup scripts
- Quick start scripts

---

### 4. [Environment Setup](./ENVIRONMENT_SETUP.md)
**Purpose:** Environment configuration and variables

**Contents:**
- Environment files (.env, env.ai.example)
- Configuration file (config.py)
- Setup instructions
- Environment variables reference
- Security best practices

---

## 🗂️ Quick Reference

### By File Type

**Docker Files:**
- `Dockerfile` - Full-featured development
- `Dockerfile.prod` - Production
- `Dockerfile.prod.light` - Lightweight production
- `docker-compose.yml` - Development
- `docker-compose.prod.yml` - Production

**Nginx Files:**
- `nginx.conf` - Main configuration
- `nginx-prod.conf` - Production
- `nginx-ai.conf` - AI services
- `nginx-newcf3.conf` - New CF3 server

**Deployment Scripts:**
- `deploy.sh` - Main deployment
- `deploy-ai.sh` - AI services
- `deploy-newcf3.sh` - New CF3 server
- `deploy-ubuntu.sh` - Ubuntu
- `deploy-with-frontend.sh` - Full stack
- `deploy.bat` - Windows

**Environment Files:**
- `.env` - Main environment (not in repo)
- `env.ai.example` - AI template
- `config.py` - Python configuration

---

## 🚀 Common Deployment Tasks

### Development Deployment
```bash
# Using Docker Compose
docker-compose up --build

# Or using deployment script
./deploy.sh
```

### Production Deployment
```bash
# Build production image
docker build -f Dockerfile.prod -t slack2teams-backend:prod .

# Deploy with production compose
docker-compose -f docker-compose.prod.yml up -d
```

### Quick Start
```bash
./quick-start.sh
```

---

## 🔧 Configuration

### Environment Variables
- Required: API keys, database URLs
- Optional: Feature flags, source paths
- See [Environment Setup](./ENVIRONMENT_SETUP.md) for full list

### Docker Configuration
- Development: Full features, larger image
- Production: Optimized, smaller image
- See [Docker Configuration](./DOCKER_CONFIGURATION.md) for details

### Nginx Configuration
- Reverse proxy to backend
- Static file serving
- Security headers
- See [Nginx Configuration](./NGINX_CONFIGURATION.md) for details

---

## 📖 Documentation Structure

```
deployment_context/
├── DOCKER_CONFIGURATION.md      # Docker files and setup
├── NGINX_CONFIGURATION.md        # Nginx configuration
├── DEPLOYMENT_SCRIPTS.md         # Deployment scripts
├── ENVIRONMENT_SETUP.md          # Environment setup
└── DEPLOYMENT_INDEX.md           # This file
```

---

## 🎯 Deployment Workflows

### Development Workflow
1. Set up environment (`.env` file)
2. Install dependencies
3. Run `./deploy.sh` or `docker-compose up`
4. Access at `http://localhost:8002`

### Production Workflow
1. Set up production environment
2. Build production image
3. Deploy with `docker-compose.prod.yml`
4. Configure Nginx
5. Set up SSL/TLS
6. Monitor health checks

---

## 🔍 Related Documentation

### Backend
- [Backend API Endpoints](../Context_Folder/backend/API_ENDPOINTS.md)
- [Vectorstore System](../Context_Folder/infrastructure/VECTORSTORE.md)

### Infrastructure
- [MongoDB Integration](../Context_Folder/infrastructure/MONGODB.md)
- [Langfuse Observability](../Context_Folder/infrastructure/LANGFUSE.md)

---

**Last Updated:** 2025-01-09  
**Location:** `deployment_context/`
