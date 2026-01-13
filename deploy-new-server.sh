#!/bin/bash

# Deployment Script for ai.cloudfuze.com (159.89.164.11)
# This script deploys the before-agentic-rag branch with frontend and data folder sync
# Domain ai.cloudfuze.com will be mapped to this server after deployment

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}AI.CloudFuze.com Deployment${NC}"
echo -e "${GREEN}New Server: 159.89.164.11${NC}"
echo -e "${GREEN}================================${NC}"
echo ""

# Configuration
SERVER_IP="159.89.164.11"
SERVER_USER="root"
DOMAIN="ai.cloudfuze.com"
PROJECT_DIR="/opt/chatbot"
BRANCH="before-agentic-rag"
FRONTEND_IMAGE="laxman006/slack2teams-frontend:ai"
LOCAL_DATA_DIR="./data"  # Local data folder path (relative to script location)

# Step 0: Commit uncommitted changes (if any)
echo -e "${YELLOW}Step 0: Checking for uncommitted changes...${NC}"
if [ -n "$(git status --porcelain)" ]; then
    echo -e "${YELLOW}Found uncommitted changes. Committing them...${NC}"
    git add -A
    git commit -m "feat: Update deployment configuration for new server 159.89.164.11" || echo "No changes to commit or already committed"
    echo -e "${GREEN}✓ Changes committed${NC}"
    
    echo -e "${YELLOW}Pushing changes to remote...${NC}"
    git push origin ${BRANCH} || echo "Push failed or already up to date"
    echo -e "${GREEN}✓ Changes pushed${NC}"
else
    echo -e "${GREEN}✓ No uncommitted changes${NC}"
fi

# Step 1: Build and push frontend Docker image locally
echo -e "${YELLOW}Step 1: Building frontend Docker image...${NC}"
cd frontend
docker build -f Dockerfile.frontend -t ${FRONTEND_IMAGE} \
  --build-arg NEXT_PUBLIC_API_URL=https://${DOMAIN} .
echo -e "${GREEN}✓ Frontend image built${NC}"

echo -e "${YELLOW}Step 2: Pushing frontend image to Docker Hub...${NC}"
docker push ${FRONTEND_IMAGE}
echo -e "${GREEN}✓ Frontend image pushed${NC}"
cd ..

# Step 2: Prepare server
echo -e "${YELLOW}Step 3: Preparing server...${NC}"
ssh ${SERVER_USER}@${SERVER_IP} << 'ENDSSH'
# Stop old services
echo "Stopping old services..."
cd /opt/slack2teams 2>/dev/null && docker-compose down || true
cd /opt/slack2teams-prod 2>/dev/null && docker-compose down || true
cd /opt/chatbot 2>/dev/null && docker-compose -f docker-compose.ai.yml down || true

# Create project directory
echo "Creating project directory..."
mkdir -p /opt/chatbot
cd /opt/chatbot

# Update system packages
echo "Updating system packages..."
apt-get update
apt-get install -y docker.io docker-compose git curl wget || true

# Ensure Docker is running
systemctl start docker || true
systemctl enable docker || true

# Verify Docker installation
docker --version
docker-compose --version
ENDSSH
echo -e "${GREEN}✓ Server prepared${NC}"

# Step 3: Clone repository and setup
echo -e "${YELLOW}Step 4: Setting up repository on server...${NC}"
ssh ${SERVER_USER}@${SERVER_IP} << ENDSSH
cd /opt/chatbot

# Remove old repo if exists (but keep data folder)
if [ -d ".git" ]; then
    echo "Removing old repository..."
    rm -rf .git
fi

# Clone repository
echo "Cloning repository from branch ${BRANCH}..."
git clone -b ${BRANCH} https://github.com/laxman006/chatbot.git .

# Pull latest changes
git pull origin ${BRANCH}

echo "Repository setup complete!"
ENDSSH
echo -e "${GREEN}✓ Repository cloned${NC}"

# Step 3.5: Sync local data folder to server
echo -e "${YELLOW}Step 4.5: Syncing local data folder to server...${NC}"
if [ -d "${LOCAL_DATA_DIR}" ]; then
    echo -e "${YELLOW}Backing up existing server data folder...${NC}"
    ssh ${SERVER_USER}@${SERVER_IP} << ENDSSH
cd /opt/chatbot
if [ -d "data" ]; then
    echo "Backing up existing data folder..."
    tar -czf data_backup_\$(date +%Y%m%d_%H%M%S).tar.gz data/ || true
    echo "Backup created"
fi
ENDSSH
    
    echo -e "${YELLOW}Syncing data folder to server...${NC}"
    # Use rsync if available, otherwise use scp
    if command -v rsync &> /dev/null; then
        rsync -avz --progress --delete ${LOCAL_DATA_DIR}/ ${SERVER_USER}@${SERVER_IP}:${PROJECT_DIR}/data/
    else
        echo -e "${YELLOW}rsync not found, using scp...${NC}"
        scp -r ${LOCAL_DATA_DIR} ${SERVER_USER}@${SERVER_IP}:${PROJECT_DIR}/
    fi
    echo -e "${GREEN}✓ Data folder synced${NC}"
else
    echo -e "${RED}⚠️  Local data folder not found at ${LOCAL_DATA_DIR}${NC}"
    echo -e "${YELLOW}Skipping data folder sync. Using existing server data folder.${NC}"
fi

# Step 4: Copy environment file
echo -e "${YELLOW}Step 5: Setting up environment variables...${NC}"
echo -e "${RED}IMPORTANT: Copy env.ai.example to .env.ai on the server and fill in the secrets${NC}"
echo -e "${YELLOW}The file should contain all your production API keys and configs${NC}"
echo -e "${YELLOW}env.ai.example now ships with this repo as a reference template${NC}"
echo ""
read -p "Press Enter after you've created .env.ai on the server..."

# Step 5: Pull frontend image on server
echo -e "${YELLOW}Step 6: Pulling frontend image on server...${NC}"
ssh ${SERVER_USER}@${SERVER_IP} << ENDSSH
cd /opt/chatbot
docker pull ${FRONTEND_IMAGE}
ENDSSH
echo -e "${GREEN}✓ Frontend image pulled${NC}"

# Step 6: Setup SSL Certificate (Note: Domain must be pointing to this IP for SSL to work)
echo -e "${YELLOW}Step 7: Setting up SSL certificate...${NC}"
echo -e "${YELLOW}Note: Domain ${DOMAIN} must be pointing to ${SERVER_IP} for SSL certificate to work${NC}"
ssh ${SERVER_USER}@${SERVER_IP} << ENDSSH
# Install certbot if not present
if ! command -v certbot &> /dev/null; then
    apt-get install -y certbot python3-certbot-nginx
fi

# Get SSL certificate (will fail if domain not pointing here, but that's OK for now)
certbot certonly --standalone -d ${DOMAIN} --agree-tos --non-interactive --email admin@cloudfuze.com || echo "SSL certificate setup skipped - domain may not be pointing to this server yet"
ENDSSH
echo -e "${GREEN}✓ SSL certificate configured (or skipped if domain not mapped)${NC}"

# Step 7: Copy nginx config
echo -e "${YELLOW}Step 8: Copying nginx configuration...${NC}"
scp nginx-ai.conf ${SERVER_USER}@${SERVER_IP}:${PROJECT_DIR}/nginx-ai.conf
echo -e "${GREEN}✓ Nginx config copied${NC}"

# Step 8: Deploy services
echo -e "${YELLOW}Step 9: Deploying services...${NC}"
ssh ${SERVER_USER}@${SERVER_IP} << 'ENDSSH'
cd /opt/chatbot

# Stop any running containers
docker-compose -f docker-compose.ai.yml down 2>/dev/null || true

# Build backend image
echo "Building backend image..."
docker-compose -f docker-compose.ai.yml build backend

# Start services with environment file
docker-compose -f docker-compose.ai.yml --env-file .env.ai up -d

# Wait for services to start
echo "Waiting for services to start..."
sleep 30

# Check service status
echo ""
echo "Service Status:"
docker-compose -f docker-compose.ai.yml ps

# Check health
echo ""
echo "Backend Health:"
curl -s http://localhost:8002/health || echo "Backend not ready yet"

echo ""
echo "Frontend Status:"
docker logs slack2teams-frontend-ai --tail 10 || echo "Frontend not ready yet"

echo ""
echo "Nginx Status:"
docker logs slack2teams-nginx-ai --tail 10 || echo "Nginx not ready yet"
ENDSSH
echo -e "${GREEN}✓ Services deployed${NC}"

# Step 9: Final verification
echo ""
echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${GREEN}================================${NC}"
echo ""
echo -e "Server IP: ${SERVER_IP}"
echo -e "Domain: ${DOMAIN} (will be mapped to this server)"
echo ""
echo -e "URLs (after domain mapping):"
echo -e "  Frontend: https://${DOMAIN}/"
echo -e "  Backend Health: https://${DOMAIN}/health"
echo -e "  API Health: https://${DOMAIN}/api/health"
echo -e "  Auth Config: https://${DOMAIN}/auth/config"
echo ""
echo -e "URLs (using IP - temporary):"
echo -e "  Frontend: http://${SERVER_IP}/"
echo -e "  Backend Health: http://${SERVER_IP}/health"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo -e "1. Map domain ${DOMAIN} to IP ${SERVER_IP} in DNS"
echo -e "2. After DNS propagation, run SSL certificate setup:"
echo -e "   ssh ${SERVER_USER}@${SERVER_IP} 'cd ${PROJECT_DIR} && certbot certonly --standalone -d ${DOMAIN}'"
echo -e "3. Test the application: https://${DOMAIN} (after DNS mapping)"
echo -e "4. Verify data folder: ssh ${SERVER_USER}@${SERVER_IP} 'ls -lh ${PROJECT_DIR}/data'"
echo -e "5. Check backend logs: ssh ${SERVER_USER}@${SERVER_IP} 'cd ${PROJECT_DIR} && docker logs slack2teams-backend-ai --tail=100'"
echo -e "6. Monitor all logs: ssh ${SERVER_USER}@${SERVER_IP} 'cd ${PROJECT_DIR} && docker-compose -f docker-compose.ai.yml logs -f'"
echo ""
