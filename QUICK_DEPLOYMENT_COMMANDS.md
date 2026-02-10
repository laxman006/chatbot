# Quick Deployment Commands Reference

## 🚀 Pre-Deployment Steps

### ⚠️ IMPORTANT: Migrating from Langchain/ChromaDB to Langgraph/Weaviate

**If you're migrating from the old langchain/chromadb project, see `MIGRATION_GUIDE.md` first!**

### 1. Backup Existing Project on Server

```bash
# SSH to server
ssh laxman006@159.89.164.11

# Navigate to project
cd /opt/chatbot

# Create full backup
chmod +x scripts/backup_full_project.sh
./scripts/backup_full_project.sh
```

**Or quick manual backup:**
```bash
mkdir -p project_backups/manual_$(date +%Y%m%d_%H%M%S)
cp -r weaviate project_backups/manual_*/ 2>/dev/null || true
cp .env.ai project_backups/manual_*/ 2>/dev/null || true
cp docker-compose.ai.yml project_backups/manual_*/ 2>/dev/null || true
cp nginx-ai.conf project_backups/manual_*/ 2>/dev/null || true
```

---

### 2. Push Weaviate Folder from Local to Server

**From your local machine:**

```bash
# Make script executable
chmod +x scripts/push_weaviate_to_server.sh

# Push Weaviate data
./scripts/push_weaviate_to_server.sh laxman006@159.89.164.11 /opt/chatbot
```

**Or using rsync (faster):**
```bash
rsync -avz --progress --delete weaviate/ laxman006@159.89.164.11:/opt/chatbot/weaviate/
```

**Or using scp:**
```bash
scp -r weaviate laxman006@159.89.164.11:/opt/chatbot/
```

---

### 3. Setup .env.ai File on Server

**SSH to server and edit .env.ai:**

```bash
ssh laxman006@159.89.164.11
cd /opt/chatbot
nano .env.ai  # or vi .env.ai
```

**Required keys to add/verify:**

```bash
# OpenAI (Required)
OPENAI_API_KEY=sk-your-openai-api-key-here

# Microsoft OAuth (Required)
MICROSOFT_CLIENT_ID=your-microsoft-client-id
MICROSOFT_CLIENT_SECRET=your-microsoft-client-secret
MICROSOFT_TENANT=cloudfuze.com

# Langfuse (Required)
LANGFUSE_PUBLIC_KEY=pk-your-langfuse-public-key
LANGFUSE_SECRET_KEY=sk-your-langfuse-secret-key
LANGFUSE_HOST=https://cloud.langfuse.com

# Weaviate (Optional - leave empty for local)
WEAVIATE_URL=http://weaviate:8080
WEAVIATE_API_KEY=

# MongoDB (Default)
MONGODB_URL=mongodb://mongodb:27017
MONGODB_DATABASE=slack2teams
MONGODB_CHAT_COLLECTION=chat_histories

# SharePoint (if enabled)
ENABLE_SHAREPOINT_SOURCE=true
SHAREPOINT_SITE_URL=https://cloudfuzecom.sharepoint.com/sites/DOC360

# Jira (if enabled)
ENABLE_JIRA_SOURCE=true
JIRA_SERVER=https://cf2020.atlassian.net
JIRA_EMAIL=your-email@cloudfuze.com
JIRA_API_TOKEN=your-jira-api-token
```

**Quick add commands (one by one):**
```bash
# Add OpenAI key
echo "OPENAI_API_KEY=sk-your-key" >> .env.ai

# Add Microsoft OAuth
echo "MICROSOFT_CLIENT_ID=your-id" >> .env.ai
echo "MICROSOFT_CLIENT_SECRET=your-secret" >> .env.ai
echo "MICROSOFT_TENANT=cloudfuze.com" >> .env.ai

# Add Langfuse
echo "LANGFUSE_PUBLIC_KEY=pk-your-key" >> .env.ai
echo "LANGFUSE_SECRET_KEY=sk-your-key" >> .env.ai
echo "LANGFUSE_HOST=https://cloud.langfuse.com" >> .env.ai
```

**Verify keys are set:**
```bash
grep -E "OPENAI_API_KEY|MICROSOFT_CLIENT|LANGFUSE" .env.ai
```

---

### 4. Check Nginx Configuration

**List nginx configs:**
```bash
ls -la nginx*.conf
```

**Files:**
- `nginx-ai.conf` - Used by docker-compose.ai.yml (main config)
- `nginx.conf` - Default config
- `nginx-prod.conf` - Production config
- `nginx-newcf3.conf` - Alternative server config

**Verify nginx-ai.conf on server:**
```bash
ssh laxman006@159.89.164.11 "cd /opt/chatbot && cat nginx-ai.conf | grep -E 'server_name|listen'"
```

**Expected output:**
```
listen 80;
server_name ai.cloudfuze.com 159.89.164.11;
```

**Test nginx config after deployment:**
```bash
docker exec slack2teams-nginx-ai nginx -t
```

---

## 🚀 Deploy

### Option 1: GitHub Actions (Automatic)

```bash
# Push to langgraph-rag branch
git add .
git commit -m "feat: deploy to production"
git push origin langgraph-rag
```

**Monitor:**
- GitHub → Actions → "Deploy to Production"

---

### Option 2: Manual Deployment

```bash
# SSH to server
ssh laxman006@159.89.164.11
cd /opt/chatbot

# Pull latest code
git fetch origin
git checkout langgraph-rag
git pull origin langgraph-rag

# Stop services
docker-compose -f docker-compose.ai.yml down || docker compose -f docker-compose.ai.yml down

# Start services
docker-compose -f docker-compose.ai.yml --env-file .env.ai up -d --build
```

---

## ✅ Post-Deployment Verification

### Health Checks

```bash
# Backend
curl http://159.89.164.11:8002/health

# Weaviate
docker exec slack2teams-weaviate wget -q -O- http://localhost:8080/v1/.well-known/ready

# Nginx
curl http://159.89.164.11/health

# All services status
docker-compose -f docker-compose.ai.yml ps
```

### Verify Weaviate Data

```bash
# Check collections
docker exec slack2teams-backend-ai python -c "from app.weaviate_schema import list_collections; print(list_collections())"

# Check Weaviate data size
du -sh weaviate/
```

### Check Logs

```bash
# Backend logs
docker logs slack2teams-backend-ai --tail=50

# Weaviate logs
docker logs slack2teams-weaviate --tail=50

# Nginx logs
docker logs slack2teams-nginx-ai --tail=50

# All logs
docker-compose -f docker-compose.ai.yml logs --tail=50
```

---

## 🔧 Useful Commands

### Backup
```bash
# Full backup
./scripts/backup_full_project.sh

# Weaviate only
./scripts/backup_weaviate.sh
```

### Restore
```bash
# Full restore
./scripts/restore_full_project.sh project_backups/project_backup_YYYYMMDD_HHMMSS.tar.gz

# Weaviate restore
./scripts/restore_weaviate.sh weaviate_backup/weaviate_backup_YYYYMMDD_HHMMSS.tar.gz
```

### Push Weaviate
```bash
# From local
./scripts/push_weaviate_to_server.sh laxman006@159.89.164.11 /opt/chatbot
```

### Update .env.ai
```bash
nano .env.ai  # Add/update keys
```

### Restart Services
```bash
docker-compose -f docker-compose.ai.yml restart
```

### Stop Services
```bash
docker-compose -f docker-compose.ai.yml down
```

### Start Services
```bash
docker-compose -f docker-compose.ai.yml --env-file .env.ai up -d
```

---

## 🆘 Troubleshooting

### Backup failed
```bash
# Check disk space
df -h

# Make scripts executable
chmod +x scripts/*.sh
```

### Weaviate push failed
```bash
# Test SSH
ssh laxman006@159.89.164.11 "echo OK"

# Check remote path
ssh laxman006@159.89.164.11 "test -d /opt/chatbot && echo OK"
```

### .env.ai missing keys
```bash
# Copy from example
cp env.ai.example .env.ai

# Edit
nano .env.ai
```

### Services won't start
```bash
# Check logs
docker-compose -f docker-compose.ai.yml logs

# Check .env.ai
cat .env.ai | grep -E "OPENAI|MICROSOFT|LANGFUSE"

# Check disk space
df -h
```

---

## 📋 Complete Deployment Checklist

- [ ] Backup existing project on server
- [ ] Push Weaviate folder from local to server
- [ ] Verify .env.ai has all required keys
- [ ] Check nginx-ai.conf exists on server
- [ ] Verify disk space on server
- [ ] Push code to langgraph-rag branch (or deploy manually)
- [ ] Monitor GitHub Actions workflow
- [ ] Verify all services are running
- [ ] Run health checks
- [ ] Verify Weaviate data is intact
- [ ] Test application functionality
