# GitHub Actions CI/CD Setup Checklist

Follow these steps to set up automated deployment.

---

## ✅ Step 1: Verify Files Created

Check that these files exist:
- [ ] `.github/workflows/deploy-ai.yml`
- [ ] `.github/CICD_SETUP.md`
- [ ] `.github/README.md`

---

## ✅ Step 2: Commit and Push Workflow Files

```powershell
# From your local machine
cd C:\Users\LaxmanKadari\Desktop\v1-dev\chatbot

# Check what's new
git status

# Stage GitHub Actions files
git add .github/

# Commit
git commit -m "ci: add GitHub Actions workflow for automatic deployment"

# Push to GitHub
git push origin before-agentic-rag
```

---

## ✅ Step 3: Add GitHub Secrets

1. Go to your repository on GitHub: `https://github.com/laxman006/chatbot`
2. Click **Settings** (top menu)
3. Click **Secrets and variables** → **Actions** (left sidebar)
4. Click **New repository secret**

### Add these 3 secrets:

#### Secret 1: SERVER_HOST
- Name: `SERVER_HOST`
- Secret: `159.89.164.11`
- Click **Add secret**

#### Secret 2: SERVER_USER
- Name: `SERVER_USER`
- Secret: `laxman006`
- Click **Add secret**

#### Secret 3: SERVER_PASSWORD
- Name: `SERVER_PASSWORD`
- Secret: `your_actual_server_password` (the password you use to SSH)
- Click **Add secret**

**Important:** Make sure the secret names are EXACTLY as shown (case-sensitive).

---

## ✅ Step 4: Test the Workflow

### Option A: Make a test commit

```powershell
# Make a small change (add a comment)
# Then commit and push

git add .
git commit -m "test: trigger CI/CD pipeline"
git push origin before-agentic-rag
```

### Option B: Manually trigger workflow

1. Go to GitHub → **Actions** tab
2. Click on "Deploy to Production Server" workflow
3. Click **Run workflow** button
4. Select branch: `before-agentic-rag`
5. Click **Run workflow**

---

## ✅ Step 5: Monitor Workflow

1. Go to GitHub → **Actions** tab
2. Click on the running workflow
3. Watch the logs in real-time
4. Look for:
   - ✅ Green checkmark = Success
   - ❌ Red X = Failed

**Typical duration:** 3-5 minutes

---

## ✅ Step 6: Verify Deployment on Server

After workflow completes, verify:

```bash
# SSH to server
ssh laxman006@159.89.164.11

# Check services are running
cd /opt/chatbot
docker compose -f docker-compose.ai.yml ps

# Check backend logs
docker logs slack2teams-backend-ai --tail=50

# Test application
curl -k https://ai.cloudfuze.com/health
```

---

## ✅ Step 7: Test Application in Browser

1. Open: `https://ai.cloudfuze.com`
2. Login and test chat functionality
3. Test admin dashboard: `https://ai.cloudfuze.com/admin/dashboard`

---

## Troubleshooting

### Workflow fails at "Deploy to server via SSH"

**Possible causes:**
- Secrets not set correctly
- Server not accessible
- Wrong username/password

**Fix:**
- Verify secrets in GitHub Settings → Secrets
- Test SSH manually: `ssh laxman006@159.89.164.11`
- Check password is correct

### Workflow succeeds but application doesn't work

**Check:**
- Services running: `docker compose -f docker-compose.ai.yml ps`
- Backend logs: `docker logs slack2teams-backend-ai --tail=100`
- Environment file: `ls -la /opt/chatbot/.env.ai`

---

## Next Steps After Basic Setup

Once basic CI/CD is working:

1. **Add Slack notifications** - Get notified on deployment status
2. **Add health checks** - Verify services are healthy after deployment
3. **Add rollback** - Automatic rollback if deployment fails
4. **Use SSH keys** - More secure than password authentication
5. **Add staging environment** - Test before production

---

## Quick Reference

### View all workflow runs
`https://github.com/laxman006/chatbot/actions`

### Workflow file location
`.github/workflows/deploy-ai.yml`

### Manual deployment (if CI/CD fails)
```bash
ssh laxman006@159.89.164.11
cd /opt/chatbot
git pull origin before-agentic-rag
docker compose -f docker-compose.ai.yml down
docker compose -f docker-compose.ai.yml build backend frontend
docker compose -f docker-compose.ai.yml --env-file .env.ai up -d
```

---

## Security Best Practices

1. ✅ Use SSH keys instead of passwords (future improvement)
2. ✅ Keep secrets in GitHub Secrets (never commit)
3. ✅ Use different passwords for different environments
4. ✅ Regularly rotate passwords/keys
5. ✅ Enable branch protection for production branch

---

## Current Status

- [x] Workflow file created
- [ ] GitHub secrets added
- [ ] First deployment tested
- [ ] Application verified working

Complete the checklist items to finish setup.
