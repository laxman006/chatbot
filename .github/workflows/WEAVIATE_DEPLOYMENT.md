# Weaviate Data Deployment Guide

## Overview

Weaviate data is stored in the `weaviate/` folder, which is **not pushed to GitHub** (correctly excluded in `.gitignore`). This guide explains how to handle Weaviate data during deployment.

---

## Current Setup

- **Local path:** `./weaviate/` (in project root)
- **Container path:** `/var/lib/weaviate` (mounted via Docker volume)
- **Docker Compose:** `docker-compose.ai.yml` mounts `./weaviate:/var/lib/weaviate`
- **Git status:** Excluded from Git (in `.gitignore`)

---

## Deployment Strategy

### ✅ Automatic Deployment (GitHub Actions)

The deployment workflow **preserves existing Weaviate data** automatically:

1. **Before stopping containers:** Checks if `weaviate/` folder exists and has data
2. **During deployment:** Stops containers, pulls code, rebuilds images
3. **Data preservation:** Weaviate data persists because:
   - The `weaviate/` folder is **not touched** by `git pull`
   - Docker volume mount `./weaviate:/var/lib/weaviate` preserves data
   - Container restart doesn't delete mounted volumes

**Result:** Existing Weaviate data remains intact after deployment.

---

## First-Time Server Setup

If deploying to a **new server** or **fresh clone**, follow these steps:

### Option 1: Manual Setup (Empty Weaviate)

1. **Deploy code** (via GitHub Actions or manual)
2. **Start services:**
   ```bash
   cd /opt/chatbot
   docker-compose -f docker-compose.ai.yml --env-file .env.ai up -d
   ```
3. **Initialize schema:**
   ```bash
   docker exec slack2teams-backend-ai python scripts/init_weaviate_schema.py
   ```
4. **Ingest data:**
   ```bash
   # Ingest blogs
   docker exec slack2teams-backend-ai python scripts/ingest_to_weaviate.py --source blog
   
   # Ingest SharePoint docs
   docker exec slack2teams-backend-ai python scripts/ingest_to_weaviate.py --source sharepoint
   
   # Ingest Jira tickets
   docker exec slack2teams-backend-ai python scripts/ingest_to_weaviate.py --source jira
   ```

### Option 2: Copy Existing Weaviate Data

If you have Weaviate data from another server/environment:

1. **On source server:** Create backup
   ```bash
   cd /opt/chatbot
   ./scripts/backup_weaviate.sh
   ```

2. **Copy backup to new server:**
   ```bash
   scp weaviate_backup/weaviate_backup_*.tar.gz laxman006@159.89.164.11:/opt/chatbot/weaviate_backup/
   ```

3. **On new server:** Restore backup
   ```bash
   cd /opt/chatbot
   ./scripts/restore_weaviate.sh weaviate_backup/weaviate_backup_YYYYMMDD_HHMMSS.tar.gz
   ```

### Option 3: Sync from Local Development

If you have Weaviate data locally and want to sync to server:

```bash
# From local machine
./scripts/sync_weaviate_to_server.sh laxman006@159.89.164.11 /opt/chatbot
```

**Note:** This stops Weaviate on the server, syncs data, then restarts it.

---

## Backup & Restore

### Create Backup

```bash
# On server
cd /opt/chatbot
./scripts/backup_weaviate.sh [optional_backup_name]
```

Backup is saved to `weaviate_backup/weaviate_backup_YYYYMMDD_HHMMSS.tar.gz`

### Restore from Backup

```bash
# On server
cd /opt/chatbot
./scripts/restore_weaviate.sh weaviate_backup/weaviate_backup_YYYYMMDD_HHMMSS.tar.gz
```

**Warning:** This replaces existing Weaviate data. A backup of existing data is created automatically.

---

## Troubleshooting

### Weaviate folder is empty after deployment

**Cause:** First deployment or Weaviate was never initialized.

**Solution:**
1. Initialize schema: `python scripts/init_weaviate_schema.py`
2. Ingest data: `python scripts/ingest_to_weaviate.py --source <source>`

### Weaviate data lost after git pull

**Cause:** `git pull` shouldn't affect `weaviate/` folder (it's in `.gitignore`).

**If this happens:**
1. Check `.gitignore` includes `weaviate/`
2. Restore from backup: `./scripts/restore_weaviate.sh <backup_file>`
3. Or re-ingest data

### Disk space issues

Weaviate data can grow large. Monitor disk usage:

```bash
du -sh weaviate/
df -h
```

If needed:
- Clean up old backups: `rm weaviate_backup/old_backup_*.tar.gz`
- Prune Docker: `docker system prune -a`
- Consider Weaviate data retention policies

### Permission issues

If Weaviate can't write to `weaviate/` folder:

```bash
chmod -R 755 weaviate/
chown -R $USER:$USER weaviate/  # Adjust user as needed
```

---

## Best Practices

1. **Regular backups:** Schedule weekly backups of `weaviate/` folder
2. **Before major deployments:** Create backup before deploying
3. **Monitor disk space:** Weaviate data can grow to several GB
4. **Version control:** Don't commit `weaviate/` folder (already in `.gitignore`)
5. **Documentation:** Keep track of what data sources are ingested

---

## Scripts Reference

| Script | Purpose |
|--------|---------|
| `scripts/backup_weaviate.sh` | Create backup of Weaviate data |
| `scripts/restore_weaviate.sh` | Restore Weaviate data from backup |
| `scripts/sync_weaviate_to_server.sh` | Sync local Weaviate data to server |
| `scripts/init_weaviate_schema.py` | Initialize Weaviate collections (schema) |
| `scripts/ingest_to_weaviate.py` | Ingest data into Weaviate |

---

## Quick Reference

### Check Weaviate health
```bash
docker exec slack2teams-weaviate wget -q -O- http://localhost:8080/v1/.well-known/ready
```

### Check Weaviate data size
```bash
du -sh weaviate/
```

### List Weaviate collections
```bash
docker exec slack2teams-backend-ai python -c "from app.weaviate_schema import list_collections; print(list_collections())"
```

### View Weaviate logs
```bash
docker logs slack2teams-weaviate --tail=50
```
