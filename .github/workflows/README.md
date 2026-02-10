# GitHub Actions Workflows

This directory contains GitHub Actions workflows for CI/CD.

## Workflows

### 1. `ci.yml` - Continuous Integration
- **Triggers:** Push/PR to `main`, `master`, `develop`
- **Jobs:**
  - Backend: Python linting (Ruff) and import verification
  - Frontend: Next.js lint and build

### 2. `docker-build.yml` - Docker Image Build
- **Triggers:** Push/PR to `main`/`master`, or manual dispatch
- **Job:** Builds backend Docker image (no push to registry)

### 3. `deploy.yml` - Production Deployment
- **Triggers:** Push to `langgraph-rag` branch, or manual dispatch
- **Job:** Deploys to production server `159.89.164.11`
- **Weaviate Data:** Automatically preserved during deployment (see `WEAVIATE_DEPLOYMENT.md`)

## Setup for Deployment

### Option 1: Password Authentication (Same as before-agentic-rag branch)

This is the **recommended** method if you already have `SERVER_PASSWORD` set up.

1. Go to your GitHub repository
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Ensure these secrets exist (same as before-agentic-rag branch):

| Secret Name | Value | Description |
|------------|-------|-------------|
| `SERVER_HOST` | `159.89.164.11` | Server IP address |
| `SERVER_USER` | `laxman006` | SSH username |
| `SERVER_PASSWORD` | `your_server_password` | SSH password |

### Option 2: SSH Key Authentication (More Secure)

If you prefer SSH keys instead of password:

1. Generate SSH Key Pair (if you don't have one):
   ```bash
   ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github_actions_deploy
   ```

2. Add Public Key to Server:
   ```bash
   ssh-copy-id -i ~/.ssh/github_actions_deploy.pub laxman006@159.89.164.11
   ```

3. Add Private Key to GitHub Secrets:
   - Name: `SSH_PRIVATE_KEY`
   - Value: Copy the entire contents of `~/.ssh/github_actions_deploy`
   - **Note:** Remove `SERVER_PASSWORD` secret if using SSH key

### 4. Verify Server Setup

Ensure on the server (`159.89.164.11`):
- `/opt/chatbot` directory exists
- Git repository is cloned in `/opt/chatbot`
- `.env.ai` file exists in `/opt/chatbot`
- Docker and docker-compose are installed
- User `laxman006` has permissions to run docker commands

### 5. Test Deployment

Push to `langgraph-rag` branch or manually trigger:
1. Go to **Actions** tab in GitHub
2. Select **Deploy to Production** workflow
3. Click **Run workflow** → Select branch → **Run workflow**

## Deployment Process

When triggered, the workflow:
1. Checks out the code from the specified branch
2. Connects to the server via SSH
3. Stops existing containers (`docker-compose down`)
4. Pulls latest code (`git pull`)
5. Rebuilds and starts containers (`docker-compose up -d --build`)
6. Checks container health

## Troubleshooting

### SSH Connection Failed
- **If using password:** Verify `SERVER_PASSWORD` secret is set correctly
- **If using SSH key:** Verify `SSH_PRIVATE_KEY` secret is set correctly and public key is in `~/.ssh/authorized_keys` on server
- Check server firewall allows SSH (port 22)
- Test connection manually: `ssh laxman006@159.89.164.11`

### Deployment Fails
- Check server logs: `ssh laxman006@159.89.164.11 "cd /opt/chatbot && docker-compose -f docker-compose.ai.yml logs"`
- Verify `.env.ai` exists on server
- Check disk space: `df -h`
- Check Docker: `docker ps` and `docker-compose version`

### Branch Not Found
- Ensure branch exists: `git branch -a`
- Push branch to remote: `git push origin langgraph-rag`
