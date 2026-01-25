# GitHub Actions Workflows

This directory contains GitHub Actions workflows for automated CI/CD.

## Available Workflows

### 1. `deploy-ai.yml` - Production Deployment

**Purpose:** Automatically deploy to ai.cloudfuze.com when pushing to `before-agentic-rag` branch

**Trigger:** Push to `before-agentic-rag` branch

**Actions:**
- Pull latest code on server
- Rebuild backend and frontend containers
- Restart services
- Run health checks

**Required Secrets:**
- `SERVER_HOST`: 159.89.164.11
- `SERVER_USER`: laxman006
- `SERVER_PASSWORD`: Your server password

---

## Setup Instructions

See [CICD_SETUP.md](./CICD_SETUP.md) for detailed setup instructions.

**Quick setup:**

1. Add secrets to GitHub repository (Settings → Secrets)
2. Push to `before-agentic-rag` branch
3. Watch deployment in Actions tab

---

## Workflow Status

Check deployment status:
- Go to GitHub → **Actions** tab
- See all workflow runs and their status
- Click on a run to see detailed logs

---

## Manual Deployment

If automated deployment fails, deploy manually:

```bash
ssh laxman006@159.89.164.11
cd /opt/chatbot
git pull origin before-agentic-rag
docker compose -f docker-compose.ai.yml down
docker compose -f docker-compose.ai.yml build backend frontend
docker compose -f docker-compose.ai.yml --env-file .env.ai up -d
```

---

## Adding New Workflows

To add a new workflow:

1. Create a new `.yml` file in `.github/workflows/`
2. Define triggers, jobs, and steps
3. Commit and push
4. Workflow appears in Actions tab

Example workflow structure:

```yaml
name: My Workflow
on:
  push:
    branches: [main]
jobs:
  my-job:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: My step
        run: echo "Hello"
```

---

## Documentation

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [SSH Action Documentation](https://github.com/appleboy/ssh-action)
