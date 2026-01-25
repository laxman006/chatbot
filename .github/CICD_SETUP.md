# GitHub Actions CI/CD Setup Guide

## Overview

This repository uses GitHub Actions for automatic deployment to `ai.cloudfuze.com` (159.89.164.11).

**Workflow:** Push to `before-agentic-rag` branch → Automatic deployment

---

## Step 1: Add GitHub Secrets

Go to your GitHub repository:
1. Navigate to **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Add these secrets:

### Required Secrets

| Secret Name | Value | Description |
|------------|-------|-------------|
| `SERVER_HOST` | `159.89.164.11` | Server IP address |
| `SERVER_USER` | `laxman006` | SSH username |
| `SERVER_PASSWORD` | `your_server_password` | SSH password |

### How to add each secret:

1. Click "New repository secret"
2. Name: `SERVER_HOST`, Value: `159.89.164.11`
3. Click "Add secret"
4. Repeat for `SERVER_USER` and `SERVER_PASSWORD`

---

## Step 2: Test the workflow

### First deployment

1. Make any small change (e.g., add a comment to a file)
2. Commit and push:
   ```bash
   git add .
   git commit -m "test: trigger CI/CD pipeline"
   git push origin before-agentic-rag
   ```

3. Go to GitHub → **Actions** tab
4. Watch the workflow run
5. Check deployment logs in the workflow

### Monitor deployment

- **GitHub Actions tab**: See deployment status and logs
- **Server**: SSH to server and check logs
  ```bash
  ssh laxman006@159.89.164.11
  cd /opt/chatbot
  docker compose -f docker-compose.ai.yml ps
  docker compose -f docker-compose.ai.yml logs --tail=50
  ```

---

## Step 3: Verify deployment

After workflow completes:

1. Check GitHub Actions for green checkmark
2. Visit: `https://ai.cloudfuze.com`
3. Test application functionality
4. Check backend logs: `docker logs slack2teams-backend-ai --tail=50`

---

## Workflow Details

**File:** `.github/workflows/deploy-ai.yml`

**Triggers:** 
- Push to `before-agentic-rag` branch

**Actions:**
1. Checkout code
2. SSH to server
3. Pull latest code
4. Rebuild backend and frontend
5. Restart services
6. Health checks
7. Report status

**Duration:** ~3-5 minutes (depending on build time)

---

## Troubleshooting

### Workflow fails at SSH step

**Issue:** "Permission denied" or "Connection refused"

**Fix:**
- Verify secrets are set correctly
- Check server is accessible: `ssh laxman006@159.89.164.11`
- Verify SSH port 22 is open in firewall

### Workflow fails at build step

**Issue:** "Build failed" or "Out of memory"

**Fix:**
- SSH to server and check disk space: `df -h`
- Check Docker resources: `docker system df`
- Clean up old images: `docker system prune -a`

### Services don't start after deployment

**Issue:** Containers exit or restart loop

**Fix:**
- Check logs: `docker compose -f docker-compose.ai.yml logs`
- Verify `.env.ai` file exists and is correct
- Check data folder permissions: `ls -ld /opt/chatbot/data`

---

## Manual Deployment (Fallback)

If CI/CD fails, deploy manually:

```bash
ssh laxman006@159.89.164.11
cd /opt/chatbot
git pull origin before-agentic-rag
docker compose -f docker-compose.ai.yml down
docker compose -f docker-compose.ai.yml build backend frontend
docker compose -f docker-compose.ai.yml --env-file .env.ai up -d
```

---

## Security Notes

1. **SSH Password vs Key:** Consider using SSH keys instead of password for better security
2. **Secrets Protection:** GitHub secrets are encrypted and not visible in logs
3. **Branch Protection:** Consider protecting the `before-agentic-rag` branch to require reviews

---

## Next Steps (Advanced Features)

After basic CI/CD is working:

1. **Slack notifications** - Get notified on deployment success/failure
2. **Health checks** - Automated health verification after deployment
3. **Rollback automation** - Auto-rollback on failure
4. **Environment variables** - Sync `.env.ai` from GitHub secrets
5. **Docker image registry** - Use Docker Hub for faster deployments
6. **Blue-green deployments** - Zero-downtime deployments
7. **Automated testing** - Run tests before deployment

---

## Quick Reference

### View workflow runs
- Go to GitHub → **Actions** tab
- Click on latest workflow run to see logs

### Force manual workflow run
- Go to **Actions** → Select workflow → **Run workflow**

### Disable workflow
- Edit `.github/workflows/deploy-ai.yml`
- Comment out or remove the `on:` trigger

### Re-run failed workflow
- Go to failed workflow run → Click **Re-run all jobs**

---

## Current Deployment Status

- **Server:** ai.cloudfuze.com (159.89.164.11)
- **User:** laxman006
- **Branch:** before-agentic-rag
- **Services:** backend, frontend, nginx
- **SSL:** Enabled (Let's Encrypt)
- **Domain:** ai.cloudfuze.com

---

## Support

If deployment fails:
1. Check GitHub Actions logs
2. SSH to server and check service logs
3. Verify secrets are correct
4. Run manual deployment as fallback
