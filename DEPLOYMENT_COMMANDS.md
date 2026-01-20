# Deployment Commands for Digital Ocean Server 159.89.164.11

## Server Information
- **Server IP:** 159.89.164.11
- **Username:** root
- **Password:** 2026@Cloudfuze
- **Project Directory:** /opt/chatbot
- **Domain:** ai.cloudfuze.com (to be mapped)

---

## Quick Start (TL;DR)

If you're familiar with the process, here's the condensed version:

```powershell
# 1. Test SSH connection
ssh root@159.89.164.11
# Password: 2026@Cloudfuze

# 2. On server: Install Docker, clone repo, create .env.ai
ssh root@159.89.164.11 "apt-get update && apt-get install -y docker.io docker-compose git && systemctl start docker && mkdir -p /opt/chatbot && cd /opt/chatbot && git clone -b before-agentic-rag https://github.com/laxman006/chatbot.git . && cp env.ai.example .env.ai && nano .env.ai"

# 3. On server: Build and deploy
ssh root@159.89.164.11 "cd /opt/chatbot && docker-compose -f docker-compose.ai.yml build && docker-compose -f docker-compose.ai.yml --env-file .env.ai up -d"

# 4. Verify
ssh root@159.89.164.11 "cd /opt/chatbot && docker-compose -f docker-compose.ai.yml ps && curl http://localhost:8002/health"
```

**For detailed step-by-step instructions, see below.**

---

## Prerequisites
- SSH access to server `159.89.164.11` as `root`
- Docker installed on your local machine
- Docker Hub account (for pushing frontend image) - OR build directly on server
- Git repository access
- PowerShell or Git Bash on Windows

---

## Step-by-Step Deployment Guide

### Step 1: Navigate to Project Directory (Windows PowerShell)
```powershell
cd C:\Users\ChaitanyaMalle\Slack2teams-2-confident-chatbot
```

### Step 2: Test SSH Connection
First, verify you can connect to the server:

```powershell
# Test SSH connection (you'll be prompted for password: 2026@Cloudfuze)
ssh root@159.89.164.11
```

**If SSH connection fails:**
- Make sure port 22 is open in Digital Ocean firewall
- Verify the server is running
- Try: `ssh -o PreferredAuthentications=password root@159.89.164.11`

**Exit SSH after testing:**
```bash
exit
```

### Step 3: Prepare Server (SSH into server and run these commands)
```powershell
# Connect to server (password: 2026@Cloudfuze)
ssh root@159.89.164.11
```

Once connected, run these commands on the server:

```bash
# Update system packages
apt-get update

# Install required packages
apt-get install -y docker.io docker-compose git curl wget nano

# Start and enable Docker
systemctl start docker
systemctl enable docker

# Verify Docker installation
docker --version
docker-compose --version

# Create project directory
mkdir -p /opt/chatbot
cd /opt/chatbot

# Stop any existing services
docker-compose -f docker-compose.ai.yml down 2>/dev/null || true
```

### Step 4: Clone Repository on Server
```bash
# Still on the server, in /opt/chatbot directory
# Remove old repo if exists (but keep data folder if it exists)
if [ -d ".git" ]; then
    rm -rf .git
fi

# Clone repository (replace with your actual repository URL)
# If using GitHub:
git clone -b before-agentic-rag https://github.com/laxman006/chatbot.git .

# OR if repository is private, you may need to set up SSH keys or use HTTPS with token
# After cloning, pull latest changes
git pull origin before-agentic-rag
```

**Exit SSH temporarily:**
```bash
exit
```

### Step 5: Create Environment File on Server
```powershell
# Connect to server again
ssh root@159.89.164.11
```

```bash
# Navigate to project directory
cd /opt/chatbot

# Copy example environment file
cp env.ai.example .env.ai

# Edit the environment file with your production secrets
nano .env.ai
```

**Fill in the required values in `.env.ai`:**
- `OPENAI_API_KEY` - Your OpenAI API key
- `MICROSOFT_CLIENT_ID` - Microsoft OAuth client ID
- `MICROSOFT_CLIENT_SECRET` - Microsoft OAuth client secret
- `MICROSOFT_TENANT` - Usually `cloudfuze.com`
- `LANGFUSE_PUBLIC_KEY` - Langfuse public key
- `LANGFUSE_SECRET_KEY` - Langfuse secret key
- `MONGODB_URL` - MongoDB connection string
- All other required environment variables from `env.ai.example`

**Save and exit nano:**
- Press `Ctrl+X`
- Press `Y` to confirm
- Press `Enter` to save

**Verify the file was created:**
```bash
ls -la .env.ai
```

### Step 6: Build and Deploy Services

**Option A: Build Frontend Image Locally and Push to Docker Hub (Recommended if you have Docker Hub account)**

From your local Windows machine (PowerShell):
```powershell
# Navigate to project directory
cd C:\Users\ChaitanyaMalle\Slack2teams-2-confident-chatbot

# Navigate to frontend directory
cd frontend

# Build frontend Docker image
docker build -f Dockerfile.frontend -t laxman006/slack2teams-frontend:ai --build-arg NEXT_PUBLIC_API_URL=https://ai.cloudfuze.com .

# Login to Docker Hub (if not already logged in)
docker login

# Push frontend image to Docker Hub
docker push laxman006/slack2teams-frontend:ai
```

Then on the server:
```bash
# SSH into server
ssh root@159.89.164.11
cd /opt/chatbot

# Pull frontend image
docker pull laxman006/slack2teams-frontend:ai
```

**Option B: Build Frontend Image Directly on Server (If you don't have Docker Hub)**

```bash
# On the server
ssh root@159.89.164.11
cd /opt/chatbot

# Build frontend image directly on server
cd frontend
docker build -f Dockerfile.frontend -t slack2teams-frontend-ai:latest --build-arg NEXT_PUBLIC_API_URL=https://ai.cloudfuze.com .
cd ..
```

### Step 7: Deploy All Services
```bash
# Still on the server, in /opt/chatbot directory

# Stop any running containers
docker-compose -f docker-compose.ai.yml down

# Build backend image
docker-compose -f docker-compose.ai.yml build backend

# Start all services with environment file
docker-compose -f docker-compose.ai.yml --env-file .env.ai up -d

# Wait for services to start
echo "Waiting for services to start..."
sleep 30

# Check service status
docker-compose -f docker-compose.ai.yml ps

# Check backend health
curl http://localhost:8002/health

# View logs
docker-compose -f docker-compose.ai.yml logs --tail=50
```

### Step 8: Verify Deployment
```bash
# Check all containers are running
docker-compose -f docker-compose.ai.yml ps

# Check individual service logs
docker logs slack2teams-backend-ai --tail=50
docker logs slack2teams-frontend-ai --tail=50
docker logs slack2teams-nginx-ai --tail=50

# Test backend health endpoint
curl http://localhost:8002/health

# Test frontend (should return HTML)
curl http://localhost:3000

# Test nginx (should proxy to frontend)
curl http://localhost/health
```

### Step 9: Test Application from Browser
Open your browser and test:
- **Frontend:** http://159.89.164.11
- **Backend Health:** http://159.89.164.11/health
- **API Health:** http://159.89.164.11/api/health

### Step 10: Setup SSL Certificate (After DNS is Configured)
Once `ai.cloudfuze.com` DNS is pointing to `159.89.164.11`:

```bash
# SSH into server
ssh root@159.89.164.11
cd /opt/chatbot

# Install certbot if not already installed
apt-get install -y certbot python3-certbot-nginx

# Stop nginx temporarily to get certificate
docker stop slack2teams-nginx-ai

# Get SSL certificate
certbot certonly --standalone -d ai.cloudfuze.com --agree-tos --non-interactive --email admin@cloudfuze.com

# Start nginx again
docker start slack2teams-nginx-ai

# Verify SSL certificate
ls -la /etc/letsencrypt/live/ai.cloudfuze.com/
```

**Note:** The nginx config already has HTTPS configured. Once the certificate is obtained, HTTPS will work automatically.

### Step 11: Sync Data Folder (If needed)
If you have a local `data` folder to sync:

```powershell
# From your local Windows machine
# Using PowerShell with SSH
cd C:\Users\ChaitanyaMalle\Slack2teams-2-confident-chatbot

# Backup existing data on server first
ssh root@159.89.164.11 "cd /opt/chatbot && tar -czf data_backup_$(date +%Y%m%d_%H%M%S).tar.gz data/ 2>/dev/null || true"

# Sync data folder using scp (if you have data folder locally)
scp -r ./data root@159.89.164.11:/opt/chatbot/

# OR using rsync (if available on Windows)
# rsync -avz --progress ./data/ root@159.89.164.11:/opt/chatbot/data/
```

---

## Quick Reference Commands

### Connect to Server
```powershell
# From Windows PowerShell
ssh root@159.89.164.11
# Password: 2026@Cloudfuze
```

### Check Service Status
```bash
# From server
cd /opt/chatbot
docker-compose -f docker-compose.ai.yml ps

# Or from local machine
ssh root@159.89.164.11 "cd /opt/chatbot && docker-compose -f docker-compose.ai.yml ps"
```

### View Logs
```bash
# All services (from server)
cd /opt/chatbot
docker-compose -f docker-compose.ai.yml logs -f

# Backend only
docker logs slack2teams-backend-ai -f

# Frontend only
docker logs slack2teams-frontend-ai -f

# Nginx only
docker logs slack2teams-nginx-ai -f

# Last 100 lines of backend logs
docker logs slack2teams-backend-ai --tail=100
```

### Restart Services
```bash
# Restart all services
cd /opt/chatbot
docker-compose -f docker-compose.ai.yml restart

# Restart specific service
docker restart slack2teams-backend-ai
docker restart slack2teams-frontend-ai
docker restart slack2teams-nginx-ai
```

### Stop Services
```bash
cd /opt/chatbot
docker-compose -f docker-compose.ai.yml down
```

### Start Services
```bash
cd /opt/chatbot
docker-compose -f docker-compose.ai.yml --env-file .env.ai up -d
```

### Update Code and Redeploy
```bash
# SSH into server
ssh root@159.89.164.11
cd /opt/chatbot

# Pull latest code
git pull origin before-agentic-rag

# Rebuild backend (if code changed)
docker-compose -f docker-compose.ai.yml build backend

# Restart services
docker-compose -f docker-compose.ai.yml --env-file .env.ai up -d

# Check status
docker-compose -f docker-compose.ai.yml ps
```

### Check Disk Space
```bash
df -h
du -sh /opt/chatbot/*
```

### Check Docker Resources
```bash
docker system df
docker stats --no-stream
```

---

## Troubleshooting

### SSH Connection Issues
```bash
# Test SSH connection
ssh -v root@159.89.164.11

# If connection refused, check:
# 1. Server is running in Digital Ocean dashboard
# 2. Firewall allows port 22
# 3. Try: ssh -o PreferredAuthentications=password root@159.89.164.11
```

### If Deployment Fails
```bash
# 1. Check SSH connection
ssh root@159.89.164.11

# 2. Verify Docker is running
docker ps
systemctl status docker

# 3. Check disk space
df -h

# 4. Check logs
cd /opt/chatbot
docker-compose -f docker-compose.ai.yml logs

# 5. Check if ports are in use
netstat -tulpn | grep -E ':(80|443|3000|8002)'
```

### If Services Won't Start
```bash
# Check environment file exists and has correct permissions
ls -la /opt/chatbot/.env.ai

# Check backend logs for errors
docker logs slack2teams-backend-ai --tail=100

# Check frontend logs
docker logs slack2teams-frontend-ai --tail=100

# Check if containers are running
docker ps -a

# Try rebuilding containers
cd /opt/chatbot
docker-compose -f docker-compose.ai.yml down
docker-compose -f docker-compose.ai.yml build --no-cache
docker-compose -f docker-compose.ai.yml --env-file .env.ai up -d
```

### If Backend Health Check Fails
```bash
# Check backend container status
docker ps | grep backend

# Check backend logs
docker logs slack2teams-backend-ai --tail=200

# Test backend directly
docker exec slack2teams-backend-ai curl http://localhost:8002/health

# Check if port 8002 is accessible
curl http://localhost:8002/health
```

### If Frontend Won't Load
```bash
# Check frontend container status
docker ps | grep frontend

# Check frontend logs
docker logs slack2teams-frontend-ai --tail=200

# Test frontend directly
docker exec slack2teams-frontend-ai wget -O- http://localhost:3000

# Check nginx logs
docker logs slack2teams-nginx-ai --tail=100

# Test nginx configuration
docker exec slack2teams-nginx-ai nginx -t
```

### If SSL Certificate Fails
```bash
# Ensure DNS is pointing to the server
nslookup ai.cloudfuze.com
dig ai.cloudfuze.com

# Ensure ports 80 and 443 are open
# Check Digital Ocean firewall settings

# Check if certbot is installed
which certbot

# Try getting certificate again
certbot certonly --standalone -d ai.cloudfuze.com --agree-tos --non-interactive --email admin@cloudfuze.com

# Check certificate files
ls -la /etc/letsencrypt/live/ai.cloudfuze.com/
```

### Common Issues and Solutions

**Issue: "Permission denied" errors**
```bash
# Fix Docker permissions
sudo usermod -aG docker $USER
# Then logout and login again
```

**Issue: "Port already in use"**
```bash
# Find what's using the port
lsof -i :80
lsof -i :443
lsof -i :3000
lsof -i :8002

# Stop conflicting services
systemctl stop apache2  # if Apache is running
systemctl stop nginx    # if system nginx is running
```

**Issue: "Out of disk space"**
```bash
# Clean up Docker
docker system prune -a

# Remove old images
docker image prune -a

# Check disk usage
du -sh /opt/chatbot/*
```

**Issue: "Container keeps restarting"**
```bash
# Check logs for errors
docker logs slack2teams-backend-ai --tail=200

# Check environment variables
docker exec slack2teams-backend-ai env | grep -E '(OPENAI|MICROSOFT|MONGODB)'

# Verify .env.ai file is correct
cat /opt/chatbot/.env.ai
```

---

## Deployment Summary

**Server IP:** 159.89.164.11  
**Username:** root  
**Password:** 2026@Cloudfuze  
**Project Directory:** /opt/chatbot  
**Domain:** ai.cloudfuze.com (to be mapped)  
**Branch:** before-agentic-rag  
**Docker Compose File:** docker-compose.ai.yml  
**Environment File:** .env.ai

---

## Complete Deployment Checklist

- [ ] SSH connection to server works
- [ ] Docker and Docker Compose installed on server
- [ ] Repository cloned to `/opt/chatbot`
- [ ] `.env.ai` file created with all required secrets
- [ ] Frontend Docker image built (locally or on server)
- [ ] Backend Docker image built on server
- [ ] All services started with `docker-compose up -d`
- [ ] Backend health check passes: `curl http://localhost:8002/health`
- [ ] Frontend accessible: `curl http://localhost:3000`
- [ ] Nginx proxy working: `curl http://localhost/health`
- [ ] Application accessible via IP: `http://159.89.164.11`
- [ ] DNS configured (if using domain)
- [ ] SSL certificate obtained (if using domain)
- [ ] HTTPS working (if using domain)

---

## Important Notes

1. **Password Security:** The password `2026@Cloudfuze` should be changed after initial setup for security. Consider setting up SSH keys instead of password authentication.

2. **Firewall Configuration:** Ensure these ports are open in Digital Ocean firewall:
   - Port 22 (SSH)
   - Port 80 (HTTP)
   - Port 443 (HTTPS)

3. **Data Backup:** Always backup the `/opt/chatbot/data` folder before major updates:
   ```bash
   cd /opt/chatbot
   tar -czf data_backup_$(date +%Y%m%d_%H%M%S).tar.gz data/
   ```

4. **Environment Variables:** Never commit `.env.ai` to git. It contains sensitive information.

5. **Monitoring:** Set up monitoring for:
   - Container health
   - Disk space
   - Memory usage
   - Application logs

---

## Support Commands

### Quick Health Check
```bash
ssh root@159.89.164.11 "cd /opt/chatbot && docker-compose -f docker-compose.ai.yml ps && curl -s http://localhost:8002/health"
```

### View All Logs (Last 50 lines)
```bash
ssh root@159.89.164.11 "cd /opt/chatbot && docker-compose -f docker-compose.ai.yml logs --tail=50"
```

### Restart Everything
```bash
ssh root@159.89.164.11 "cd /opt/chatbot && docker-compose -f docker-compose.ai.yml restart"
```
