# ⚡ Quick Backup - Run This NOW on Server

## One-Liner Backup Command

**SSH to server and run this single command:**

```bash
ssh laxman006@159.89.164.11 "cd /opt/chatbot && mkdir -p project_backups && BACKUP_NAME=langchain_backup_\$(date +%Y%m%d_%H%M%S) && mkdir -p project_backups/\$BACKUP_NAME && cp -r chroma chromadb vectorstore data .env .env.ai docker-compose.yml docker-compose.ai.yml nginx.conf nginx-ai.conf images project_backups/\$BACKUP_NAME/ 2>/dev/null && docker ps > project_backups/\$BACKUP_NAME/running_containers.txt 2>/dev/null && cd project_backups && tar -czf \${BACKUP_NAME}.tar.gz \$BACKUP_NAME && rm -rf \$BACKUP_NAME && cd .. && echo '✅ Backup created:' && ls -lh project_backups/*.tar.gz | tail -1"
```

---

## Step-by-Step (Easier to Understand)

**SSH to server:**
```bash
ssh laxman006@159.89.164.11
cd /opt/chatbot
```

**Create backup directory:**
```bash
mkdir -p project_backups/langchain_backup_$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=$(ls -td project_backups/langchain_backup_* | head -1)
```

**Backup all important files:**
```bash
# Backup ChromaDB/vectorstore
cp -r chroma "$BACKUP_DIR/" 2>/dev/null || echo "No chroma folder"
cp -r chromadb "$BACKUP_DIR/" 2>/dev/null || echo "No chromadb folder"
cp -r vectorstore "$BACKUP_DIR/" 2>/dev/null || echo "No vectorstore folder"

# Backup data
cp -r data "$BACKUP_DIR/" 2>/dev/null || echo "No data folder"

# Backup config files
cp .env "$BACKUP_DIR/" 2>/dev/null || echo "No .env file"
cp .env.ai "$BACKUP_DIR/" 2>/dev/null || echo "No .env.ai file"
cp docker-compose.yml "$BACKUP_DIR/" 2>/dev/null || echo "No docker-compose.yml"
cp docker-compose.ai.yml "$BACKUP_DIR/" 2>/dev/null || echo "No docker-compose.ai.yml"
cp nginx.conf "$BACKUP_DIR/" 2>/dev/null || echo "No nginx.conf"
cp nginx-ai.conf "$BACKUP_DIR/" 2>/dev/null || echo "No nginx-ai.conf"

# Backup images
cp -r images "$BACKUP_DIR/" 2>/dev/null || echo "No images folder"

# Save container info
docker ps > "$BACKUP_DIR/running_containers.txt" 2>/dev/null || true
docker-compose ps > "$BACKUP_DIR/docker_compose_ps.txt" 2>/dev/null || docker compose ps > "$BACKUP_DIR/docker_compose_ps.txt" 2>/dev/null || true
```

**Create compressed backup:**
```bash
cd project_backups
tar -czf "$(basename $BACKUP_DIR).tar.gz" "$(basename $BACKUP_DIR)"
rm -rf "$(basename $BACKUP_DIR)"
cd ..

# Verify backup
ls -lh project_backups/*.tar.gz | tail -1
```

---

## What Gets Backed Up

- ✅ `chroma/` - ChromaDB database
- ✅ `chromadb/` - Alternative ChromaDB location
- ✅ `vectorstore/` - Vectorstore data
- ✅ `data/` - Application data
- ✅ `.env` - Environment file
- ✅ `.env.ai` - Environment file
- ✅ `docker-compose.yml` - Docker config
- ✅ `docker-compose.ai.yml` - Docker config
- ✅ `nginx.conf` - Nginx config
- ✅ `nginx-ai.conf` - Nginx config
- ✅ `images/` - Static images
- ✅ Container information

---

## After Backup

1. ✅ Backup is complete
2. ✅ You can now deploy new langgraph/weaviate code
3. ✅ If rollback needed: `tar -xzf project_backups/langchain_backup_*.tar.gz`

---

## Next Steps

1. **Backup complete** ✅
2. **Deploy new code** (via GitHub Actions or manual)
3. **Push Weaviate folder** from local to server
4. **Setup .env.ai** with required keys
5. **Start new services**

See `MIGRATION_GUIDE.md` for complete migration steps.
