# Jira Vectorstore Integration - Context & Fixes

## Overview
This document summarizes the work done to integrate and fix the Jira vectorstore loading in the CloudFuze AI Assistant production deployment.

## Problem Statement
The Jira vectorstore was not loading in the production backend container, despite:
- Jira environment variables being correctly set in `.env.ai`
- The `jira_chroma_db` folder existing at `/app/data/jira_chroma_db` in the container
- `ENABLE_JIRA_VECTORSTORE=true` being set

## Root Causes Identified

### 1. Missing Environment Variables in Docker Compose
**Issue:** Jira-related environment variables were not explicitly passed to the backend service in `docker-compose.ai.yml`.

**Fix:** Added all Jira environment variables to the `backend` service's `environment` section:
```yaml
# Jira Configuration
JIRA_SERVER: "${JIRA_SERVER}"
JIRA_EMAIL: "${JIRA_EMAIL}"
JIRA_API_TOKEN: "${JIRA_API_TOKEN}"
JIRA_PROJECT_KEYS: "${JIRA_PROJECT_KEYS}"
JIRA_DATE_FILTER: "${JIRA_DATE_FILTER}"
JIRA_MAX_ISSUES: "${JIRA_MAX_ISSUES}"
JIRA_VECTORSTORE_PATH: "${JIRA_VECTORSTORE_PATH}"
ENABLE_JIRA_VECTORSTORE: "${ENABLE_JIRA_VECTORSTORE}"
INITIALIZE_JIRA_VECTORSTORE: "${INITIALIZE_JIRA_VECTORSTORE}"
JIRA_CHUNK_TARGET_TOKENS: "${JIRA_CHUNK_TARGET_TOKENS}"
JIRA_CHUNK_OVERLAP_TOKENS: "${JIRA_CHUNK_OVERLAP_TOKENS}"
JIRA_CHUNK_MIN_TOKENS: "${JIRA_CHUNK_MIN_TOKENS}"
ENABLE_JIRA_SOURCE: "${ENABLE_JIRA_SOURCE}"
```

**Commit:** `24bdb4a` - "feat: Add Jira environment variables to docker-compose.ai.yml for Jira vectorstore support"

### 2. Missing jira_vectorstore.py File in Container
**Issue:** The `app/jira_vectorstore.py` file was not present in the backend Docker container, causing `ModuleNotFoundError: No module named 'app.jira_vectorstore'`.

**Root Cause:** The backend container was built before `jira_vectorstore.py` was added to the repository, or the build failed due to disk space issues.

**Fix:** 
- Updated `.dockerignore` to exclude `data/` folder from Docker builds (prevents copying large files into image)
- Rebuilt backend container to include `jira_vectorstore.py`

**Commit:** `6586cfb` - "fix: Exclude data folder from Docker build to prevent disk space issues"

### 3. Missing jira Python Package
**Issue:** The `jira` Python package was missing from `requirements.prod.light.txt`, causing `ModuleNotFoundError: No module named 'jira'` during import.

**Fix:** Added `jira>=3.5.0` to `requirements.prod.light.txt`:
```txt
# Jira Integration
jira>=3.5.0
```

**Commit:** `66e083b` - "fix: Add jira package to requirements.prod.light.txt for Jira vectorstore support"

### 4. Disk Space Issues During Build
**Issue:** Docker build was failing with "No space left on device" error when trying to copy the `data/` folder (containing large vectorstore files) into the image.

**Fix:** Updated `.dockerignore` to exclude:
```
# Data folder (mounted as volume, don't copy into image)
data/
data_backup_*.tar.gz
```

This ensures the `data/` folder is mounted as a volume at runtime rather than being copied into the image during build.

## Files Modified

### 1. `docker-compose.ai.yml`
- Added Jira environment variables to `backend` service

### 2. `.dockerignore`
- Added `data/` folder exclusion
- Added `data_backup_*.tar.gz` exclusion

### 3. `requirements.prod.light.txt`
- Added `jira>=3.5.0` package

### 4. `.env.ai` (on server)
- Updated `JIRA_VECTORSTORE_PATH` from `./data/jira_chroma_db` to `/app/data/jira_chroma_db` (absolute path)

## Deployment Steps

### Step 1: Update Code on Server
```bash
cd /opt/slack2teams-ai
git pull origin before-agentic-rag
```

### Step 2: Free Disk Space (if needed)
```bash
# Remove backup files
rm -f data_backup_*.tar.gz

# Clean Docker system
docker system prune -a -f

# Check disk space
df -h
```

### Step 3: Rebuild Backend Container
```bash
# Rebuild backend (will install jira package and include jira_vectorstore.py)
docker-compose -f docker-compose.ai.yml build backend

# Or rebuild without cache if needed
docker-compose -f docker-compose.ai.yml build --no-cache backend
```

### Step 4: Restart Services
```bash
# Stop services
docker-compose -f docker-compose.ai.yml down

# Start services with updated image
docker-compose -f docker-compose.ai.yml --env-file .env.ai up -d

# Wait for startup
sleep 20
```

### Step 5: Verify Installation
```bash
# Check if jira package is installed
docker exec slack2teams-backend-ai python -c "import jira; print('✅ Jira package installed')"

# Check if jira_vectorstore.py exists
docker exec slack2teams-backend-ai ls -la /app/app/jira_vectorstore.py

# Check if Jira environment variables are loaded
docker exec slack2teams-backend-ai env | grep -i jira

# Check backend logs for Jira vectorstore loading
docker logs slack2teams-backend-ai --tail=50 | grep -i jira
```

## Expected Results

### Successful Jira Vectorstore Loading
After successful deployment, you should see in the backend logs:
```
[*] Loading existing Jira vectorstore...
[OK] Loaded Jira vectorstore with 632 documents
[OK] Jira retriever ready for issue resolution queries
```

### Environment Variables Verification
All Jira-related environment variables should be present:
```
JIRA_SERVER=https://cf2020.atlassian.net
JIRA_EMAIL=laxman.kadari@cloudfuze.com
JIRA_API_TOKEN=ATATT3x...
JIRA_PROJECT_KEYS=PRI
JIRA_MAX_ISSUES=300
JIRA_VECTORSTORE_PATH=/app/data/jira_chroma_db
ENABLE_JIRA_VECTORSTORE=true
INITIALIZE_JIRA_VECTORSTORE=false
JIRA_CHUNK_TARGET_TOKENS=500
JIRA_CHUNK_OVERLAP_TOKENS=100
JIRA_CHUNK_MIN_TOKENS=120
ENABLE_JIRA_SOURCE=false
```

## Troubleshooting

### Issue: ModuleNotFoundError: No module named 'app.jira_vectorstore'
**Solution:** Rebuild backend container to include the file:
```bash
docker-compose -f docker-compose.ai.yml build backend
```

### Issue: ModuleNotFoundError: No module named 'jira'
**Solution:** Ensure `jira>=3.5.0` is in `requirements.prod.light.txt` and rebuild:
```bash
git pull origin before-agentic-rag
docker-compose -f docker-compose.ai.yml build backend
```

### Issue: Jira vectorstore not loading despite ENABLE_JIRA_VECTORSTORE=true
**Check:**
1. Environment variables are passed to container: `docker exec slack2teams-backend-ai env | grep JIRA`
2. Vectorstore path exists: `docker exec slack2teams-backend-ai ls -la /app/data/jira_chroma_db`
3. Path is absolute (not relative): `JIRA_VECTORSTORE_PATH=/app/data/jira_chroma_db`
4. Check backend logs for errors: `docker logs slack2teams-backend-ai --tail=100 | grep -i jira`

### Issue: "No space left on device" during build
**Solution:**
1. Clean Docker system: `docker system prune -a -f`
2. Remove backup files: `rm -f data_backup_*.tar.gz`
3. Ensure `.dockerignore` excludes `data/` folder
4. Rebuild: `docker-compose -f docker-compose.ai.yml build backend`

## Git Commits

1. **24bdb4a** - "feat: Add Jira environment variables to docker-compose.ai.yml for Jira vectorstore support"
2. **6586cfb** - "fix: Exclude data folder from Docker build to prevent disk space issues"
3. **66e083b** - "fix: Add jira package to requirements.prod.light.txt for Jira vectorstore support"

## Branch
All changes were made on the `before-agentic-rag` branch.

## Related Files
- `app/jira_vectorstore.py` - Jira vectorstore initialization and loading
- `app/jira_processor.py` - Jira ticket processing and content extraction
- `app/endpoints.py` - Imports `jira_retriever` and `jira_vectorstore` for use in chat endpoints
- `config.py` - Contains Jira configuration loading from environment variables

## Notes
- The Jira vectorstore is separate from the main vectorstore
- It's loaded at module import time (when `app/jira_vectorstore.py` is imported)
- The vectorstore path must be absolute (`/app/data/jira_chroma_db`) not relative (`./data/jira_chroma_db`)
- The `data/` folder is mounted as a volume, so it persists across container rebuilds
- The `.dockerignore` ensures `data/` is not copied into the image during build
