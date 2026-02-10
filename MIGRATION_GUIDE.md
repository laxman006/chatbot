# Migration Guide: Langchain/ChromaDB → Langgraph/Weaviate

## Overview

This guide helps you migrate from the **existing langchain/chromadb project** to the **new langgraph/weaviate project** on the server.

---

## Current Situation

- **Server:** `159.89.164.11` (docker-ubuntu-s-2vcpu-4gb-amd-blr1-01)
- **Current project:** Langchain with ChromaDB
- **New project:** Langgraph with Weaviate
- **Location:** `/opt/chatbot`

---

## Step 1: Backup Existing Project

**On the server, BEFORE deploying new code:**

```bash
# SSH to server
ssh laxman006@159.89.164.11

# Navigate to project directory
cd /opt/chatbot

# Create manual backup (since backup script doesn't exist yet)
mkdir -p project_backups/langchain_backup_$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=$(ls -td project_backups/langchain_backup_* | head -1)

# Backup critical files
cp -r chroma "$BACKUP_DIR/" 2>/dev/null || echo "No chroma folder"
cp -r chromadb "$BACKUP_DIR/" 2>/dev/null || echo "No chromadb folder"
cp -r vectorstore "$BACKUP_DIR/" 2>/dev/null || echo "No vectorstore folder"
cp -r data "$BACKUP_DIR/" 2>/dev/null || echo "No data folder"
cp .env "$BACKUP_DIR/" 2>/dev/null || echo "No .env file"
cp .env.ai "$BACKUP_DIR/" 2>/dev/null || echo "No .env.ai file"
cp docker-compose.yml "$BACKUP_DIR/" 2>/dev/null || echo "No docker-compose.yml"
cp docker-compose.ai.yml "$BACKUP_DIR/" 2>/dev/null || echo "No docker-compose.ai.yml"
cp nginx.conf "$BACKUP_DIR/" 2>/dev/null || echo "No nginx.conf"
cp nginx-ai.conf "$BACKUP_DIR/" 2>/dev/null || echo "No nginx-ai.conf"
cp -r images "$BACKUP_DIR/" 2>/dev/null || echo "No images folder"

# Backup Docker volumes (if running)
if docker ps | grep -q slack2teams; then
    docker ps --format "{{.Names}}" > "$BACKUP_DIR/running_containers.txt"
    docker-compose ps > "$BACKUP_DIR/docker_compose_ps.txt" 2>/dev/null || docker compose ps > "$BACKUP_DIR/docker_compose_ps.txt" 2>/dev/null || true
fi

# Create compressed backup
cd project_backups
tar -czf "$(basename $BACKUP_DIR).tar.gz" "$(basename $BACKUP_DIR)"
rm -rf "$(basename $BACKUP_DIR)"
cd ..

echo "✅ Backup created: project_backups/$(basename $BACKUP_DIR).tar.gz"
ls -lh project_backups/*.tar.gz | tail -1
```

---

## Step 2: Stop Existing Services

```bash
# Stop all containers
docker-compose down || docker compose down || true

# Or stop specific containers
docker stop $(docker ps -q --filter "name=slack2teams") 2>/dev/null || true
docker stop $(docker ps -q --filter "name=chatbot") 2>/dev/null || true
```

---

## Step 3: Deploy New Langgraph/Weaviate Code

### Option A: Via GitHub Actions (Recommended)

```bash
# From your local machine, push to langgraph-rag branch
git add .
git commit -m "feat: migrate to langgraph/weaviate"
git push origin langgraph-rag
```

The GitHub Actions workflow will:
1. Create backup automatically
2. Pull new code
3. Deploy new services

### Option B: Manual Deployment

```bash
# On server
cd /opt/chatbot

# Pull new code
git fetch origin
git checkout langgraph-rag
git pull origin langgraph-rag

# Now the backup scripts will be available
chmod +x scripts/*.sh
```

---

## Step 4: Setup New Environment (.env.ai)

**Copy keys from old .env to new .env.ai:**

```bash
# On server
cd /opt/chatbot

# If old .env exists, copy important keys
if [ -f ".env" ]; then
    echo "Copying keys from old .env to .env.ai..."
    
    # Copy OpenAI key
    grep "OPENAI_API_KEY" .env >> .env.ai 2>/dev/null || true
    
    # Copy Microsoft OAuth
    grep "MICROSOFT_CLIENT" .env >> .env.ai 2>/dev/null || true
    
    # Copy Langfuse
    grep "LANGFUSE" .env >> .env.ai 2>/dev/null || true
    
    # Copy MongoDB
    grep "MONGODB" .env >> .env.ai 2>/dev/null || true
fi

# Edit .env.ai to add/update keys
nano .env.ai
```

**Required keys for new project:**

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

# Weaviate (New - for langgraph project)
WEAVIATE_URL=http://weaviate:8080
WEAVIATE_API_KEY=

# MongoDB (Same as before)
MONGODB_URL=mongodb://mongodb:27017
MONGODB_DATABASE=slack2teams
MONGODB_CHAT_COLLECTION=chat_histories
```

---

## Step 5: Push Weaviate Data from Local

**From your local machine:**

```bash
# Make script executable
chmod +x scripts/push_weaviate_to_server.sh

# Push Weaviate folder
./scripts/push_weaviate_to_server.sh laxman006@159.89.164.11 /opt/chatbot
```

**Or using rsync:**
```bash
rsync -avz --progress --delete weaviate/ laxman006@159.89.164.11:/opt/chatbot/weaviate/
```

---

## Step 6: Start New Services

```bash
# On server
cd /opt/chatbot

# Start new langgraph/weaviate services
docker-compose -f docker-compose.ai.yml --env-file .env.ai up -d --build
```

---

## Step 7: Initialize Weaviate Schema

**If Weaviate folder is empty (first time):**

```bash
# Wait for Weaviate to be ready
sleep 30

# Initialize schema
docker exec slack2teams-backend-ai python scripts/init_weaviate_schema.py

# Ingest data
docker exec slack2teams-backend-ai python scripts/ingest_to_weaviate.py --source blog
docker exec slack2teams-backend-ai python scripts/ingest_to_weaviate.py --source sharepoint
docker exec slack2teams-backend-ai python scripts/ingest_to_weaviate.py --source jira
```

**If Weaviate folder was pushed from local:**
- Schema should already exist
- Data should already be there
- Just verify: `docker exec slack2teams-backend-ai python -c "from app.weaviate_schema import list_collections; print(list_collections())"`

---

## Step 8: Verify Deployment

```bash
# Health checks
curl http://159.89.164.11:8002/health
docker exec slack2teams-weaviate wget -q -O- http://localhost:8080/v1/.well-known/ready

# Check services
docker-compose -f docker-compose.ai.yml ps

# Check Weaviate collections
docker exec slack2teams-backend-ai python -c "from app.weaviate_schema import list_collections; print(list_collections())"

# Check logs
docker-compose -f docker-compose.ai.yml logs --tail=50
```

---

## Differences: Old vs New

| Component | Old (Langchain/ChromaDB) | New (Langgraph/Weaviate) |
|-----------|-------------------------|-------------------------|
| Vector DB | ChromaDB (`chroma/` folder) | Weaviate (`weaviate/` folder) |
| Framework | Langchain | Langgraph |
| Docker Compose | `docker-compose.yml` | `docker-compose.ai.yml` |
| Environment | `.env` | `.env.ai` |
| Container Names | `slack2teams-*` | `slack2teams-*-ai` |

---

## Rollback (If Needed)

**If you need to rollback to old langchain/chromadb:**

```bash
# Stop new services
docker-compose -f docker-compose.ai.yml down

# Restore backup
cd /opt/chatbot
tar -xzf project_backups/langchain_backup_YYYYMMDD_HHMMSS.tar.gz
mv langchain_backup_YYYYMMDD_HHMMSS/* .

# Start old services
docker-compose up -d
```

---

## Troubleshooting

### Backup script not found
- **Cause:** Scripts don't exist on server yet
- **Solution:** Use manual backup commands in Step 1

### Weaviate folder empty
- **Cause:** First deployment or not pushed yet
- **Solution:** Push from local or initialize schema and ingest data

### Old containers still running
- **Cause:** Old docker-compose still active
- **Solution:** `docker-compose down` then `docker-compose -f docker-compose.ai.yml up -d`

### .env.ai missing keys
- **Cause:** New file, keys not copied
- **Solution:** Copy from old `.env` or add manually

---

## Quick Reference

### Backup Old Project
```bash
mkdir -p project_backups/langchain_backup_$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=$(ls -td project_backups/langchain_backup_* | head -1)
cp -r chroma chromadb vectorstore data .env .env.ai docker-compose.yml nginx.conf "$BACKUP_DIR/" 2>/dev/null || true
cd project_backups && tar -czf "$(basename $BACKUP_DIR).tar.gz" "$(basename $BACKUP_DIR)" && rm -rf "$(basename $BACKUP_DIR)"
```

### Push Weaviate from Local
```bash
./scripts/push_weaviate_to_server.sh laxman006@159.89.164.11 /opt/chatbot
```

### Start New Services
```bash
docker-compose -f docker-compose.ai.yml --env-file .env.ai up -d --build
```
