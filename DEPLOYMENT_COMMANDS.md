# Deployment Commands for Server 159.89.164.11

## Prerequisites
- SSH access to server `159.89.164.11` as `root`
- Docker installed on your local machine
- Docker Hub account (for pushing frontend image)
- Git repository access

## Step-by-Step Deployment

### Step 1: Navigate to Project Directory
```bash
cd C:\Users\LaxmanKadari\Desktop\v1-dev\chatbot
```

### Step 2: Make Deployment Script Executable (if on Linux/Mac)
```bash
# On Windows, skip this step - PowerShell handles it
# On Linux/Mac:
chmod +x deploy-new-server.sh
```

### Step 3: Run Deployment Script
```bash
# On Windows PowerShell:
.\deploy-new-server.sh

# On Linux/Mac:
./deploy-new-server.sh
```

### Step 4: Follow Interactive Prompts
The script will:
1. Build and push frontend Docker image
2. Prepare the server
3. Clone repository to `/opt/chatbot`
4. Sync data folder
5. **Pause and wait for you to create `.env.ai` file on server**

### Step 5: Create Environment File on Server
While the script is waiting, SSH into the server and create the environment file:

```bash
# SSH into server
ssh root@159.89.164.11

# Navigate to project directory
cd /opt/chatbot

# Copy example environment file
cp env.ai.example .env.ai

# Edit the file with your production secrets
nano .env.ai
# OR use vi:
# vi .env.ai
```

**Required values in `.env.ai`:**
- `OPENAI_API_KEY` - Your OpenAI API key
- `MICROSOFT_CLIENT_ID` - Microsoft OAuth client ID
- `MICROSOFT_CLIENT_SECRET` - Microsoft OAuth client secret
- `MICROSOFT_TENANT` - Usually `cloudfuze.com`
- `LANGFUSE_PUBLIC_KEY` - Langfuse public key
- `LANGFUSE_SECRET_KEY` - Langfuse secret key
- `MONGODB_URL` - MongoDB connection string
- All other required environment variables

**Save and exit:**
- In nano: `Ctrl+X`, then `Y`, then `Enter`
- In vi: Press `Esc`, type `:wq`, press `Enter`

**Exit SSH:**
```bash
exit
```

### Step 6: Continue Deployment
Go back to your local terminal and press `Enter` to continue the deployment script.

### Step 7: Verify Deployment
After deployment completes, verify services are running:

```bash
# SSH into server
ssh root@159.89.164.11

# Check Docker containers
cd /opt/chatbot
docker-compose -f docker-compose.ai.yml ps

# Check backend health
curl http://localhost:8002/health

# Check logs
docker-compose -f docker-compose.ai.yml logs -f
```

### Step 8: Test Application
```bash
# Test via IP (before domain mapping)
curl http://159.89.164.11/health

# Or open in browser:
# http://159.89.164.11
```

### Step 9: Map Domain and Setup SSL (After DNS Propagation)
Once `ai.cloudfuze.com` DNS is pointing to `159.89.164.11`:

```bash
# SSH into server
ssh root@159.89.164.11

# Install certbot if not already installed
apt-get install -y certbot python3-certbot-nginx

# Get SSL certificate
cd /opt/chatbot
certbot certonly --standalone -d ai.cloudfuze.com --agree-tos --non-interactive --email admin@cloudfuze.com

# Update nginx config to enable HTTPS redirect
# Edit nginx-ai.conf and uncomment the redirect line in HTTP server block
nano nginx-ai.conf
# Find line: # return 301 https://$host$request_uri;
# Uncomment it: return 301 https://$host$request_uri;

# Restart nginx
docker restart slack2teams-nginx-ai
```

## Quick Reference Commands

### Check Service Status
```bash
ssh root@159.89.164.11 "cd /opt/chatbot && docker-compose -f docker-compose.ai.yml ps"
```

### View Logs
```bash
# All services
ssh root@159.89.164.11 "cd /opt/chatbot && docker-compose -f docker-compose.ai.yml logs -f"

# Backend only
ssh root@159.89.164.11 "cd /opt/chatbot && docker logs slack2teams-backend-ai -f"

# Frontend only
ssh root@159.89.164.11 "cd /opt/chatbot && docker logs slack2teams-frontend-ai -f"
```

### Restart Services
```bash
ssh root@159.89.164.11 "cd /opt/chatbot && docker-compose -f docker-compose.ai.yml restart"
```

### Stop Services
```bash
ssh root@159.89.164.11 "cd /opt/chatbot && docker-compose -f docker-compose.ai.yml down"
```

### Update Code and Redeploy
```bash
# On server
ssh root@159.89.164.11
cd /opt/chatbot
git pull origin before-agentic-rag
docker-compose -f docker-compose.ai.yml build backend
docker-compose -f docker-compose.ai.yml --env-file .env.ai up -d
```

## Troubleshooting

### If deployment fails:
1. Check SSH connection: `ssh root@159.89.164.11`
2. Verify Docker is running: `docker ps`
3. Check disk space: `df -h`
4. Check logs: `docker-compose -f docker-compose.ai.yml logs`

### If services won't start:
```bash
# Check environment file exists
ssh root@159.89.164.11 "ls -la /opt/chatbot/.env.ai"

# Check backend logs
ssh root@159.89.164.11 "cd /opt/chatbot && docker logs slack2teams-backend-ai --tail=100"
```

### If SSL certificate fails:
- Ensure DNS is pointing to the server: `nslookup ai.cloudfuze.com`
- Ensure ports 80 and 443 are open
- Check firewall: `ufw status`

## Deployment Summary

**Server:** 159.89.164.11  
**Project Directory:** /opt/chatbot  
**Domain:** ai.cloudfuze.com (to be mapped)  
**Branch:** before-agentic-rag  
**Docker Compose File:** docker-compose.ai.yml  
**Environment File:** .env.ai
