# CloudFuze AI Assistant - Deployment Context

## Overview
This document provides comprehensive context for deploying the CloudFuze AI Assistant application to production. It covers the complete deployment process, server configuration, troubleshooting, and maintenance procedures.

## Server Information

### Production Server
- **IP Address:** `64.227.160.206`
- **Domain:** `ai.cloudfuze.com`
- **User:** `root`
- **Project Directory:** `/opt/slack2teams-ai`
- **Branch:** `before-agentic-rag`

### Server Specifications
- **OS:** Ubuntu Server
- **CPU:** 1 vCPU
- **RAM:** 1GB
- **Storage:** 24GB (main) + 9.8GB (volume)
- **Docker:** Installed and configured

## Architecture

### Services
1. **Nginx** - Reverse proxy, SSL termination, static file serving
2. **Frontend** - Next.js application (port 3000)
3. **Backend** - FastAPI application (port 8002)

### Network
- **Port 80:** HTTP (redirects to HTTPS)
- **Port 443:** HTTPS (SSL/TLS)
- **Internal Network:** Docker bridge network (`app-network`)

## Deployment Methods

### Method 1: Automated Deployment Script

#### Prerequisites
- Local machine with Docker installed
- SSH access to server
- Docker Hub account (for pushing frontend image)
- Git repository access

#### Usage
```bash
# Make script executable
chmod +x deploy-ai.sh

# Run deployment
./deploy-ai.sh
```

#### What the Script Does
1. **Step 0:** Commits uncommitted changes
2. **Step 1:** Builds frontend Docker image locally
3. **Step 2:** Pushes frontend image to Docker Hub
4. **Step 3:** Prepares server (installs dependencies)
5. **Step 4:** Clones/pulls repository on server
6. **Step 4.5:** Syncs local `data/` folder to server
7. **Step 5:** Prompts for `.env.ai` file setup
8. **Step 6:** Pulls frontend image on server
9. **Step 7:** Sets up SSL certificate (Let's Encrypt)
10. **Step 8:** Copies Nginx configuration
11. **Step 9:** Deploys services with Docker Compose

### Method 2: Manual Deployment

#### Step 1: Prepare Local Environment
```bash
# Clone repository
git clone -b before-agentic-rag https://github.com/laxman006/chatbot.git
cd chatbot

# Build frontend image
cd frontend
docker build -f Dockerfile.frontend -t laxman006/slack2teams-frontend:ai \
  --build-arg NEXT_PUBLIC_API_URL=https://ai.cloudfuze.com .
docker push laxman006/slack2teams-frontend:ai
cd ..
```

#### Step 2: Server Setup
```bash
# SSH into server
ssh root@64.227.160.206

# Create project directory
mkdir -p /opt/slack2teams-ai
cd /opt/slack2teams-ai

# Clone repository
git clone -b before-agentic-rag https://github.com/laxman006/chatbot.git .
```

#### Step 3: Environment Configuration
```bash
# Copy environment template
cp env.ai.example .env.ai

# Edit environment file with production values
nano .env.ai
```

**Required Environment Variables:**
- `OPENAI_API_KEY` - OpenAI API key
- `MONGODB_URL` - MongoDB connection string
- `MICROSOFT_CLIENT_ID` - Microsoft OAuth client ID
- `MICROSOFT_CLIENT_SECRET` - Microsoft OAuth client secret
- `MICROSOFT_TENANT` - Microsoft tenant (e.g., `cloudfuze.com`)
- `LANGFUSE_PUBLIC_KEY` - Langfuse public key
- `LANGFUSE_SECRET_KEY` - Langfuse secret key
- `LANGFUSE_HOST` - Langfuse host URL
- Jira configuration (if using Jira vectorstore)

#### Step 4: Data Folder Setup
```bash
# Option A: Copy data folder from local machine
scp -r ./data root@64.227.160.206:/opt/slack2teams-ai/

# Option B: Use rsync (more efficient)
rsync -avz --progress ./data/ root@64.227.160.206:/opt/slack2teams-ai/data/

# Set permissions
ssh root@64.227.160.206
chmod -R 755 /opt/slack2teams-ai/data
```

#### Step 5: SSL Certificate Setup
```bash
# Install certbot
apt-get update
apt-get install -y certbot python3-certbot-nginx

# Get SSL certificate
certbot certonly --standalone -d ai.cloudfuze.com \
  --agree-tos --non-interactive --email admin@cloudfuze.com
```

#### Step 6: Nginx Configuration
```bash
# Copy Nginx config
scp nginx-ai.conf root@64.227.160.206:/opt/slack2teams-ai/nginx-ai.conf

# Verify Nginx config
ssh root@64.227.160.206
docker run --rm -v /opt/slack2teams-ai/nginx-ai.conf:/etc/nginx/conf.d/default.conf:ro \
  nginx:alpine nginx -t
```

#### Step 7: Deploy Services
```bash
cd /opt/slack2teams-ai

# Pull frontend image
docker pull laxman006/slack2teams-frontend:ai

# Build backend image
docker-compose -f docker-compose.ai.yml build backend

# Start services
docker-compose -f docker-compose.ai.yml --env-file .env.ai up -d

# Check status
docker-compose -f docker-compose.ai.yml ps

# View logs
docker-compose -f docker-compose.ai.yml logs -f
```

## Docker Compose Configuration

### File: `docker-compose.ai.yml`

#### Services

**Nginx:**
- Image: `nginx:alpine`
- Ports: `80:80`, `443:443`
- Volumes:
  - `./nginx-ai.conf:/etc/nginx/conf.d/default.conf:ro`
  - `./images:/var/www/html/images:ro`
  - `/etc/letsencrypt:/etc/letsencrypt:ro`
- Depends on: frontend, backend

**Frontend:**
- Image: `laxman006/slack2teams-frontend:ai`
- Environment:
  - `NODE_ENV=production`
  - `NEXT_PUBLIC_API_URL=https://ai.cloudfuze.com`
- Health check: HTTP check on port 3000

**Backend:**
- Build: `Dockerfile.prod.light`
- Port: `8002` (internal)
- Environment: Loaded from `.env.ai`
- Volumes:
  - `./data:/app/data`
  - `./logs:/app/logs`
- Health check: HTTP check on `/health`

### Environment Variables

All environment variables are loaded from `.env.ai` file. Key variables include:

**AI/LLM:**
- `LLM_PROVIDER` - `openai` or `gemini`
- `OPENAI_API_KEY` - OpenAI API key
- `GEMINI_API_KEY` - Google Gemini API key

**Authentication:**
- `MICROSOFT_CLIENT_ID`
- `MICROSOFT_CLIENT_SECRET`
- `MICROSOFT_TENANT`

**Database:**
- `MONGODB_URL`
- `MONGODB_DATABASE`
- `MONGODB_CHAT_COLLECTION`

**Observability:**
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`
- `LANGFUSE_HOST`

**Vectorstore:**
- `CHROMA_DB_PATH=/app/data/chroma_db`
- `JIRA_VECTORSTORE_PATH=/app/data/jira_chroma_db`
- `ENABLE_JIRA_VECTORSTORE=true`
- `INITIALIZE_JIRA_VECTORSTORE=false`

## Nginx Configuration

### File: `nginx-ai.conf`

#### Key Features
- SSL/TLS termination
- HTTP to HTTPS redirect
- Reverse proxy to backend (port 8002)
- Reverse proxy to frontend (port 3000)
- Static file serving
- WebSocket support
- CORS headers
- Gzip compression
- Security headers

#### Important Routes
- `/` - Frontend (Next.js)
- `/api/` - Backend API
- `/analytics/` - Backend analytics
- `/chat/` - Backend chat endpoints
- `/auth/` - Backend authentication
- `/user/` - Backend user endpoints
- `/teams/` - Backend teams endpoints
- `/images/` - Static images (proxied to frontend)
- `/api/shared-chat/` - Frontend API route (for shared chats)
- `/_next/static/` - Next.js static assets

## Common Deployment Tasks

### Update Code
```bash
# On server
cd /opt/slack2teams-ai
git pull origin before-agentic-rag

# Rebuild backend if needed
docker-compose -f docker-compose.ai.yml build backend

# Restart services
docker-compose -f docker-compose.ai.yml down
docker-compose -f docker-compose.ai.yml --env-file .env.ai up -d
```

### Update Frontend
```bash
# On local machine
cd frontend
docker build -f Dockerfile.frontend -t laxman006/slack2teams-frontend:ai \
  --build-arg NEXT_PUBLIC_API_URL=https://ai.cloudfuze.com .
docker push laxman006/slack2teams-frontend:ai

# On server
cd /opt/slack2teams-ai
docker pull laxman006/slack2teams-frontend:ai
docker-compose -f docker-compose.ai.yml up -d frontend
```

### Update Data Folder
```bash
# From local machine
rsync -avz --progress ./data/ root@64.227.160.206:/opt/slack2teams-ai/data/

# On server, restart backend to reload data
docker restart slack2teams-backend-ai
```

### Update Environment Variables
```bash
# On server
cd /opt/slack2teams-ai
nano .env.ai

# Restart services to apply changes
docker-compose -f docker-compose.ai.yml down
docker-compose -f docker-compose.ai.yml --env-file .env.ai up -d
```

### Update Nginx Configuration
```bash
# On local machine
scp nginx-ai.conf root@64.227.160.206:/opt/slack2teams-ai/nginx-ai.conf

# On server
docker restart slack2teams-nginx-ai

# Or reload Nginx
docker exec slack2teams-nginx-ai nginx -s reload
```

## Monitoring and Logs

### View Logs
```bash
# All services
docker-compose -f docker-compose.ai.yml logs -f

# Specific service
docker logs slack2teams-backend-ai -f
docker logs slack2teams-frontend-ai -f
docker logs slack2teams-nginx-ai -f

# Last N lines
docker logs slack2teams-backend-ai --tail=100
```

### Check Service Status
```bash
# Docker Compose status
docker-compose -f docker-compose.ai.yml ps

# Container health
docker ps

# Resource usage
docker stats --no-stream
```

### Health Checks
```bash
# Backend health
curl http://localhost:8002/health

# Frontend health
curl http://localhost:3000

# Through Nginx
curl https://ai.cloudfuze.com/health
curl https://ai.cloudfuze.com/api/health
```

## Troubleshooting

### Service Won't Start
```bash
# Check logs
docker logs slack2teams-backend-ai --tail=50

# Check environment variables
docker exec slack2teams-backend-ai env | grep -i jira

# Check file permissions
ls -la /opt/slack2teams-ai/data
```

### Disk Space Issues
```bash
# Check disk usage
df -h

# Clean Docker system
docker system prune -a -f

# Remove old images
docker image prune -a -f

# Remove backup files
rm -f /opt/slack2teams-ai/data_backup_*.tar.gz
```

### Build Failures
```bash
# Check if .dockerignore excludes data folder
cat .dockerignore | grep data

# Rebuild without cache
docker-compose -f docker-compose.ai.yml build --no-cache backend

# Check build logs
docker-compose -f docker-compose.ai.yml build backend 2>&1 | tee build.log
```

### SSL Certificate Issues
```bash
# Check certificate
certbot certificates

# Renew certificate
certbot renew

# Test certificate
openssl s_client -connect ai.cloudfuze.com:443 -servername ai.cloudfuze.com
```

### Network Issues
```bash
# Check Docker network
docker network ls
docker network inspect slack2teams-ai_app-network

# Test connectivity between containers
docker exec slack2teams-nginx-ai ping -c 3 frontend
docker exec slack2teams-nginx-ai ping -c 3 backend
```

### High Load/Performance Issues
```bash
# Check system resources
top
htop

# Check Docker resource usage
docker stats

# Check specific container
docker stats slack2teams-backend-ai

# Check logs for errors
docker logs slack2teams-backend-ai --tail=100 | grep -i error
```

## Backup and Recovery

### Backup Data Folder
```bash
# On server
cd /opt/slack2teams-ai
tar -czf data_backup_$(date +%Y%m%d_%H%M%S).tar.gz data/

# Copy to local machine
scp root@64.227.160.206:/opt/slack2teams-ai/data_backup_*.tar.gz ./
```

### Restore Data Folder
```bash
# On server
cd /opt/slack2teams-ai
tar -xzf data_backup_YYYYMMDD_HHMMSS.tar.gz

# Restart backend
docker restart slack2teams-backend-ai
```

### Backup Environment File
```bash
# On server
cp .env.ai .env.ai.backup

# Copy to local (secure location)
scp root@64.227.160.206:/opt/slack2teams-ai/.env.ai.backup ./env.ai.backup
```

## Security Considerations

### Environment Variables
- Never commit `.env.ai` to Git
- Use strong, unique API keys
- Rotate keys regularly
- Use environment-specific values

### SSL/TLS
- SSL certificates auto-renew via certbot
- Monitor certificate expiration
- Use HTTPS for all connections

### Docker Security
- Run containers as non-root user (backend uses `app` user)
- Use read-only volumes where possible
- Keep Docker images updated
- Scan images for vulnerabilities

### Network Security
- Only expose necessary ports (80, 443)
- Use Docker internal network for inter-container communication
- Implement rate limiting in Nginx
- Use security headers

## Maintenance

### Regular Tasks
1. **Weekly:**
   - Check disk space
   - Review logs for errors
   - Check SSL certificate expiration

2. **Monthly:**
   - Update dependencies
   - Review security patches
   - Backup data folder

3. **Quarterly:**
   - Review and rotate API keys
   - Update Docker images
   - Review and optimize resource usage

### Updates
```bash
# Update system packages
apt-get update && apt-get upgrade -y

# Update Docker
apt-get install docker.io docker-compose

# Update application code
git pull origin before-agentic-rag
docker-compose -f docker-compose.ai.yml build backend
docker-compose -f docker-compose.ai.yml up -d
```

## Rollback Procedure

### Rollback Code Changes
```bash
# On server
cd /opt/slack2teams-ai

# Checkout previous commit
git log --oneline -10
git checkout <previous-commit-hash>

# Rebuild and restart
docker-compose -f docker-compose.ai.yml build backend
docker-compose -f docker-compose.ai.yml down
docker-compose -f docker-compose.ai.yml --env-file .env.ai up -d
```

### Rollback Frontend Image
```bash
# Pull previous image tag
docker pull laxman006/slack2teams-frontend:ai:<previous-tag>

# Update docker-compose.ai.yml with previous tag
# Restart frontend
docker-compose -f docker-compose.ai.yml up -d frontend
```

### Rollback Data Folder
```bash
# Stop services
docker-compose -f docker-compose.ai.yml down

# Restore backup
cd /opt/slack2teams-ai
tar -xzf data_backup_YYYYMMDD_HHMMSS.tar.gz

# Restart services
docker-compose -f docker-compose.ai.yml --env-file .env.ai up -d
```

## Quick Reference Commands

### Service Management
```bash
# Start services
docker-compose -f docker-compose.ai.yml --env-file .env.ai up -d

# Stop services
docker-compose -f docker-compose.ai.yml down

# Restart services
docker-compose -f docker-compose.ai.yml restart

# Restart specific service
docker restart slack2teams-backend-ai
```

### Logs
```bash
# Follow logs
docker-compose -f docker-compose.ai.yml logs -f

# Backend logs
docker logs slack2teams-backend-ai -f --tail=100

# Frontend logs
docker logs slack2teams-frontend-ai -f --tail=100
```

### Debugging
```bash
# Execute command in container
docker exec -it slack2teams-backend-ai bash

# Check environment variables
docker exec slack2teams-backend-ai env

# Check file existence
docker exec slack2teams-backend-ai ls -la /app/app/jira_vectorstore.py

# Test Python import
docker exec slack2teams-backend-ai python -c "import jira; print('OK')"
```

## Related Documentation
- [Jira Vectorstore Integration](./JIRA_VECTORSTORE_INTEGRATION.md) - Jira vectorstore setup and troubleshooting
- `deploy-ai.sh` - Automated deployment script
- `docker-compose.ai.yml` - Docker Compose configuration
- `nginx-ai.conf` - Nginx configuration
- `env.ai.example` - Environment variables template

## Support and Contacts
- **Repository:** https://github.com/laxman006/chatbot
- **Branch:** `before-agentic-rag`
- **Server:** `root@64.227.160.206`
- **Domain:** `ai.cloudfuze.com`
