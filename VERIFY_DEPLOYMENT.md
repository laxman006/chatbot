# Verify GitHub Deployment Configuration

## ✅ Confirmed Configuration

### Repository Details:
- **GitHub Repository:** `https://github.com/laxman006/chatbot.git`
- **Branch:** `before-agentic-rag`
- **Server:** `159.89.164.11`
- **Project Directory:** `/opt/chatbot`

### Deployment Scripts:
Both deployment scripts are configured correctly:

1. **deploy-on-server.sh** (Server-side deployment)
   - `BRANCH="before-agentic-rag"`
   - `REPO_URL="https://github.com/laxman006/chatbot.git"`
   - Clones: `git clone -b before-agentic-rag https://github.com/laxman006/chatbot.git .`

2. **deploy-new-server.sh** (Local deployment script)
   - `BRANCH="before-agentic-rag"`
   - `REPO_URL="https://github.com/laxman006/chatbot.git"`

## Commands to Verify Deployment from GitHub

### On Server - Verify Repository and Branch:

```bash
# SSH into server
ssh root@159.89.164.11

# Check if repository is cloned
cd /opt/chatbot
git remote -v
git branch
git log --oneline -5
```

Expected output:
```
origin  https://github.com/laxman006/chatbot.git (fetch)
origin  https://github.com/laxman006/chatbot.git (push)
* before-agentic-rag
```

### Verify Latest Code from GitHub:

```bash
# On server
cd /opt/chatbot

# Check current branch
git branch

# Pull latest changes from GitHub
git fetch origin
git pull origin before-agentic-rag

# Verify latest commit
git log --oneline -1
```

## Complete Deployment from GitHub

### Option 1: Fresh Deployment (Clone from GitHub)

```bash
# SSH into server
ssh root@159.89.164.11

# Remove old directory (if exists)
rm -rf /opt/chatbot

# Clone fresh from GitHub
mkdir -p /opt/chatbot
cd /opt/chatbot
git clone -b before-agentic-rag https://github.com/laxman006/chatbot.git .

# Verify branch
git branch
git log --oneline -5
```

### Option 2: Update Existing Deployment

```bash
# SSH into server
ssh root@159.89.164.11

# Navigate to project
cd /opt/chatbot

# Verify current branch
git branch

# Pull latest from GitHub
git fetch origin
git checkout before-agentic-rag
git pull origin before-agentic-rag

# Verify update
git log --oneline -5
```

## Verify Deployment Script Uses GitHub

The `deploy-on-server.sh` script automatically:
1. Clones from GitHub: `git clone -b before-agentic-rag https://github.com/laxman006/chatbot.git .`
2. Or updates if exists: `git pull origin before-agentic-rag`

## Quick Verification Commands

```bash
# Check repository URL
ssh root@159.89.164.11 "cd /opt/chatbot && git remote -v"

# Check current branch
ssh root@159.89.164.11 "cd /opt/chatbot && git branch"

# Check latest commit
ssh root@159.89.164.11 "cd /opt/chatbot && git log --oneline -1"

# Pull latest from GitHub
ssh root@159.89.164.11 "cd /opt/chatbot && git pull origin before-agentic-rag"
```
