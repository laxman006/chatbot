# Server-Side Deployment Guide

## Quick Start - Deploy on Server

### Option 1: Run Script Directly on Server

1. **SSH into the server:**
```bash
ssh root@159.89.164.11
```

2. **Download and run the deployment script:**
```bash
# Download the script
curl -o deploy-on-server.sh https://raw.githubusercontent.com/laxman006/chatbot/before-agentic-rag/deploy-on-server.sh

# Make it executable
chmod +x deploy-on-server.sh

# Run it
./deploy-on-server.sh
```

### Option 2: Manual Deployment Steps

If you prefer to run commands manually:

#### Step 1: SSH into Server
```bash
ssh root@159.89.164.11
```

#### Step 2: Update System and Install Dependencies
```bash
apt-get update
apt-get install -y docker.io docker-compose git curl wget
systemctl start docker
systemctl enable docker
```

#### Step 3: Create Project Directory
```bash
mkdir -p /opt/chatbot
cd /opt/chatbot
```

#### Step 4: Clone Repository
```bash
git clone -b before-agentic-rag https://github.com/laxman006/chatbot.git .
```

#### Step 5: Create Environment File
```bash
cp env.ai.example .env.ai
nano .env.ai
# Fill in all your production secrets
# Save: Ctrl+X, Y, Enter
```

#### Step 6: Pull Frontend Image
```bash
docker pull laxman006/slack2teams-frontend:ai
```

#### Step 7: Build Backend Image
```bash
docker-compose -f docker-compose.ai.yml build backend
```

#### Step 8: Create Required Directories
```bash
mkdir -p data logs
chmod -R 755 data logs
```

#### Step 9: Deploy Services
```bash
docker-compose -f docker-compose.ai.yml --env-file .env.ai up -d
```

#### Step 10: Verify Deployment
```bash
# Check status
docker-compose -f docker-compose.ai.yml ps

# Check health
curl http://localhost:8002/health

# View logs
docker-compose -f docker-compose.ai.yml logs -f
```

## Complete Command Sequence (Copy & Paste)

```bash
# SSH into server
ssh root@159.89.164.11

# Run these commands on the server:
apt-get update && \
apt-get install -y docker.io docker-compose git curl wget && \
systemctl start docker && \
systemctl enable docker && \
mkdir -p /opt/chatbot && \
cd /opt/chatbot && \
git clone -b before-agentic-rag https://github.com/laxman006/chatbot.git . && \
cp env.ai.example .env.ai && \
echo "Now edit .env.ai with your secrets: nano .env.ai" && \
echo "After editing, run: docker pull laxman006/slack2teams-frontend:ai && docker-compose -f docker-compose.ai.yml build backend && mkdir -p data logs && chmod -R 755 data logs && docker-compose -f docker-compose.ai.yml --env-file .env.ai up -d"
```

## After Deployment - Management Commands

### View Logs
```bash
# All services
docker-compose -f docker-compose.ai.yml logs -f

# Specific service
docker logs slack2teams-backend-ai -f
docker logs slack2teams-frontend-ai -f
docker logs slack2teams-nginx-ai -f
```

### Restart Services
```bash
docker-compose -f docker-compose.ai.yml restart
```

### Stop Services
```bash
docker-compose -f docker-compose.ai.yml down
```

### Update Code
```bash
cd /opt/chatbot
git pull origin before-agentic-rag
docker-compose -f docker-compose.ai.yml build backend
docker-compose -f docker-compose.ai.yml --env-file .env.ai up -d
```

### Check Status
```bash
docker-compose -f docker-compose.ai.yml ps
docker ps
```

## SSL Setup (After DNS Mapping)

```bash
# Install certbot
apt-get install -y certbot python3-certbot-nginx

# Get SSL certificate
cd /opt/chatbot
certbot certonly --standalone -d ai.cloudfuze.com --agree-tos --non-interactive --email admin@cloudfuze.com

# Enable HTTPS redirect in nginx
nano nginx-ai.conf
# Uncomment: return 301 https://$host$request_uri;

# Restart nginx
docker restart slack2teams-nginx-ai
```

## Troubleshooting

### Check if services are running
```bash
docker ps
docker-compose -f docker-compose.ai.yml ps
```

### Check logs for errors
```bash
docker-compose -f docker-compose.ai.yml logs --tail=100
```

### Check disk space
```bash
df -h
```

### Check Docker status
```bash
systemctl status docker
docker info
```

### Restart Docker service
```bash
systemctl restart docker
```
