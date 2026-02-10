# Pre-Deployment Checklist

## 🚨 IMPORTANT: Complete these steps BEFORE deploying

---

## Step 1: Backup Existing Server Project

**Run on server BEFORE deployment:**

```bash
# SSH to server
ssh laxman006@159.89.164.11

# Navigate to project directory
cd /opt/chatbot

# Create full backup
./scripts/backup_full_project.sh

# Or manually backup critical files
mkdir -p project_backups/manual_backup_$(date +%Y%m%d_%H%M%S)
cp -r weaviate project_backups/manual_backup_*/ 2>/dev/null || true
cp .env.ai project_backups/manual_backup_*/ 2>/dev/null || true
cp docker-compose.ai.yml project_backups/manual_backup_*/ 2>/dev/null || true
cp nginx-ai.conf project_backups/manual_backup_*/ 2>/dev/null || true
```

**Verify backup:**
```bash
ls -lh project_backups/
```

---

## Step 2: Push Weaviate Folder from Local to Server

**From your local machine:**

```bash
# Navigate to project root
cd /path/to/chatbot

# Push Weaviate data to server
./scripts/push_weaviate_to_server.sh laxman006@159.89.164.11 /opt/chatbot
```

**Or manually using rsync:**
```bash
rsync -avz --progress --delete weaviate/ laxman006@159.89.164.11:/opt/chatbot/weaviate/
```

**Or manually using scp:**
```bash
scp -r weaviate laxman006@159.89.164.11:/opt/chatbot/
```

**Verify on server:**
```bash
ssh laxman006@159.89.164.11 "du -sh /opt/chatbot/weaviate"
```

---

## Step 3: Setup .env.ai File on Server

**Check existing .env.ai on server:**
```bash
ssh laxman006@159.89.164.11 "cat /opt/chatbot/.env.ai | grep -E 'OPENAI_API_KEY|MICROSOFT_CLIENT|LANGFUSE|WEAVIATE|MONGODB'"
```

**Required keys in .env.ai:**

### 1. OpenAI API Key (or Gemini)
```bash
# Add to .env.ai
OPENAI_API_KEY=sk-your-openai-key-here
# OR
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-gemini-key-here
```

### 2. Microsoft OAuth (Required)
```bash
MICROSOFT_CLIENT_ID=your-client-id
MICROSOFT_CLIENT_SECRET=your-client-secret
MICROSOFT_TENANT=cloudfuze.com
```

### 3. Langfuse (Required)
```bash
LANGFUSE_PUBLIC_KEY=pk-your-public-key
LANGFUSE_SECRET_KEY=sk-your-secret-key
LANGFUSE_HOST=https://cloud.langfuse.com
```

### 4. Weaviate Configuration
```bash
WEAVIATE_URL=http://weaviate:8080
WEAVIATE_API_KEY=  # Leave empty for local instance
```

### 5. MongoDB Configuration
```bash
MONGODB_URL=mongodb://mongodb:27017
MONGODB_DATABASE=slack2teams
MONGODB_CHAT_COLLECTION=chat_histories
```

### 6. SharePoint Configuration (if enabled)
```bash
ENABLE_SHAREPOINT_SOURCE=true
SHAREPOINT_SITE_URL=https://cloudfuzecom.sharepoint.com/sites/DOC360
SHAREPOINT_START_PAGE=
SHAREPOINT_MAX_DEPTH=999
```

### 7. Jira Configuration (if enabled)
```bash
ENABLE_JIRA_SOURCE=true
JIRA_SERVER=https://cf2020.atlassian.net
JIRA_EMAIL=your-email@cloudfuze.com
JIRA_API_TOKEN=your-jira-api-token
JIRA_PROJECT_KEYS=PRI
```

**Commands to add/update keys:**

```bash
# SSH to server
ssh laxman006@159.89.164.11

# Edit .env.ai
cd /opt/chatbot
nano .env.ai  # or vi .env.ai

# Or add keys one by one
echo "OPENAI_API_KEY=sk-your-key" >> .env.ai
echo "MICROSOFT_CLIENT_ID=your-id" >> .env.ai
echo "MICROSOFT_CLIENT_SECRET=your-secret" >> .env.ai

# Verify keys are set
grep -E "OPENAI_API_KEY|MICROSOFT_CLIENT|LANGFUSE" .env.ai
```

---

## Step 4: Check Nginx Configuration

**List all nginx configs:**
```bash
ls -la nginx*.conf
```

**Files to check:**
- `nginx.conf` - Default nginx config
- `nginx-ai.conf` - AI deployment config (used by docker-compose.ai.yml)
- `nginx-prod.conf` - Production config
- `nginx-newcf3.conf` - Alternative server config

**Verify nginx config on server:**
```bash
ssh laxman006@159.89.164.11 "cd /opt/chatbot && cat nginx-ai.conf | grep -E 'server_name|listen|proxy_pass'"
```

**Test nginx config:**
```bash
ssh laxman006@159.89.164.11 "docker exec slack2teams-nginx-ai nginx -t"
```

**Common nginx settings to verify:**
- Server name: `ai.cloudfuze.com` or `159.89.164.11`
- Listen ports: `80` and `443` (if SSL)
- Proxy pass: `http://backend:8002` or `http://slack2teams-backend-ai:8002`
- SSL certificates (if using HTTPS)

---

## Step 5: Verify Docker Compose Configuration

**Check docker-compose.ai.yml on server:**
```bash
ssh laxman006@159.89.164.11 "cd /opt/chatbot && cat docker-compose.ai.yml | grep -E 'image:|volumes:|ports:'"
```

**Verify volumes:**
- Weaviate: `./weaviate:/var/lib/weaviate`
- Data: `./data:/app/data`
- Images: `./images:/app/images`
- Nginx config: `./nginx-ai.conf:/etc/nginx/conf.d/default.conf`

---

## Step 6: Pre-Deployment Verification

**Run on server:**

```bash
# Check disk space
df -h

# Check Docker
docker ps
docker-compose version || docker compose version

# Check Git
git --version
git remote -v

# Check Weaviate folder
ls -lh weaviate/ | head -10
du -sh weaviate/

# Check .env.ai exists
test -f .env.ai && echo "✅ .env.ai exists" || echo "❌ .env.ai missing"

# Check nginx config exists
test -f nginx-ai.conf && echo "✅ nginx-ai.conf exists" || echo "❌ nginx-ai.conf missing"
```

---

## Step 7: Deploy via GitHub Actions

**After completing steps 1-6:**

1. **Push to langgraph-rag branch:**
   ```bash
   git add .
   git commit -m "feat: deploy to production"
   git push origin langgraph-rag
   ```

2. **Monitor deployment:**
   - Go to GitHub → Actions tab
   - Watch "Deploy to Production" workflow
   - Check logs for any errors

3. **Verify deployment on server:**
   ```bash
   ssh laxman006@159.89.164.11
   cd /opt/chatbot
   docker-compose -f docker-compose.ai.yml ps
   docker-compose -f docker-compose.ai.yml logs --tail=50
   ```

---

## Step 8: Post-Deployment Verification

**Health checks:**

```bash
# Backend health
curl http://159.89.164.11:8002/health

# Weaviate health
docker exec slack2teams-weaviate wget -q -O- http://localhost:8080/v1/.well-known/ready

# Nginx health
curl http://159.89.164.11/health

# Check all services
docker-compose -f docker-compose.ai.yml ps
```

**Verify Weaviate data:**
```bash
docker exec slack2teams-backend-ai python -c "from app.weaviate_schema import list_collections; print(list_collections())"
```

---

## Quick Reference Commands

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

# Weaviate only
./scripts/restore_weaviate.sh weaviate_backup/weaviate_backup_YYYYMMDD_HHMMSS.tar.gz
```

### Push Weaviate
```bash
# From local to server
./scripts/push_weaviate_to_server.sh laxman006@159.89.164.11 /opt/chatbot
```

### Update .env.ai
```bash
# SSH to server
ssh laxman006@159.89.164.11
cd /opt/chatbot
nano .env.ai  # Add/update keys
```

---

## Troubleshooting

### Backup failed
- Check disk space: `df -h`
- Check permissions: `ls -la scripts/`
- Make scripts executable: `chmod +x scripts/*.sh`

### Weaviate push failed
- Check SSH access: `ssh laxman006@159.89.164.11`
- Check remote path exists: `ssh laxman006@159.89.164.11 "test -d /opt/chatbot && echo OK"`
- Check local Weaviate exists: `ls -la weaviate/`

### .env.ai missing keys
- Copy from example: `cp env.ai.example .env.ai`
- Add keys manually: `nano .env.ai`
- Verify: `grep -E "OPENAI|MICROSOFT|LANGFUSE" .env.ai`

### Nginx config issues
- Test config: `docker exec slack2teams-nginx-ai nginx -t`
- Check logs: `docker logs slack2teams-nginx-ai`
- Verify volume mount: `docker inspect slack2teams-nginx-ai | grep nginx`

---

## Emergency Rollback

If deployment fails:

```bash
# Stop new deployment
docker-compose -f docker-compose.ai.yml down

# Restore from backup
./scripts/restore_full_project.sh project_backups/project_backup_YYYYMMDD_HHMMSS.tar.gz

# Start old version
docker-compose -f docker-compose.ai.yml --env-file .env.ai up -d
```
