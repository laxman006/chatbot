#!/bin/bash

# Server-Side Deployment Script
# Run this script directly on the server 159.89.164.11
# This script deploys the chatbot application from GitHub

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}Chatbot Deployment on Server${NC}"
echo -e "${GREEN}Server: 159.89.164.11${NC}"
echo -e "${GREEN}================================${NC}"
echo ""

# Configuration
DOMAIN="ai.cloudfuze.com"
PROJECT_DIR="/opt/chatbot"
BRANCH="before-agentic-rag"
REPO_URL="https://github.com/laxman006/chatbot.git"
FRONTEND_IMAGE="laxman006/slack2teams-frontend:ai"

# Step 1: Update system packages
echo -e "${YELLOW}Step 1: Updating system packages...${NC}"
apt-get update
apt-get install -y docker.io docker-compose git curl wget || true

# Ensure Docker is running
systemctl start docker || true
systemctl enable docker || true

# Verify Docker installation
echo ""
echo "Docker version:"
docker --version
docker-compose --version || docker compose version
echo ""

# Step 1.5: Configure firewall (UFW) - Open required ports
echo -e "${YELLOW}Step 1.5: Configuring firewall...${NC}"
# Check if UFW is active
if command -v ufw &> /dev/null; then
    echo "UFW firewall detected. Opening ports 80 and 443..."
    ufw allow 80/tcp
    ufw allow 443/tcp
    ufw --force enable || true
    echo -e "${GREEN}✓ Firewall configured - ports 80 and 443 opened${NC}"
else
    echo -e "${YELLOW}UFW not found, skipping firewall configuration${NC}"
fi
echo ""

# Step 2: Stop any existing services
echo -e "${YELLOW}Step 2: Stopping existing services...${NC}"
cd /opt/chatbot 2>/dev/null && docker-compose -f docker-compose.ai.yml down || true
cd /opt/slack2teams 2>/dev/null && docker-compose down || true
cd /opt/slack2teams-prod 2>/dev/null && docker-compose down || true
echo -e "${GREEN}✓ Existing services stopped${NC}"

# Step 3: Create project directory
echo -e "${YELLOW}Step 3: Creating project directory...${NC}"
mkdir -p ${PROJECT_DIR}
cd ${PROJECT_DIR}
echo -e "${GREEN}✓ Project directory created: ${PROJECT_DIR}${NC}"

# Step 4: Clone or update repository
echo -e "${YELLOW}Step 4: Setting up repository...${NC}"
if [ -d ".git" ]; then
    echo "Repository exists, pulling latest changes..."
    git fetch origin
    git checkout ${BRANCH}
    git pull origin ${BRANCH}
    echo -e "${GREEN}✓ Repository updated${NC}"
else
    echo "Cloning repository..."
    git clone -b ${BRANCH} ${REPO_URL} .
    echo -e "${GREEN}✓ Repository cloned${NC}"
fi

# Step 5: Check for environment file
echo -e "${YELLOW}Step 5: Checking environment configuration...${NC}"
if [ ! -f ".env.ai" ]; then
    echo -e "${RED}⚠️  .env.ai file not found!${NC}"
    echo -e "${YELLOW}Creating from template...${NC}"
    if [ -f "env.ai.example" ]; then
        cp env.ai.example .env.ai
        echo -e "${GREEN}✓ Created .env.ai from template${NC}"
        echo -e "${RED}IMPORTANT: Edit .env.ai with your production secrets before continuing!${NC}"
        echo ""
        read -p "Press Enter after you've edited .env.ai with production secrets..."
    else
        echo -e "${RED}ERROR: env.ai.example not found!${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✓ .env.ai file found${NC}"
fi

# Step 6: Pull frontend Docker image
echo -e "${YELLOW}Step 6: Pulling frontend Docker image...${NC}"
docker pull ${FRONTEND_IMAGE} || echo -e "${YELLOW}Warning: Could not pull frontend image. It may need to be built locally first.${NC}"
echo -e "${GREEN}✓ Frontend image ready${NC}"

# Step 7: Build backend Docker image
echo -e "${YELLOW}Step 7: Building backend Docker image...${NC}"
docker-compose -f docker-compose.ai.yml build backend
echo -e "${GREEN}✓ Backend image built${NC}"

# Step 8: Setup SSL Certificate (optional - only if domain is mapped)
echo -e "${YELLOW}Step 8: Setting up SSL certificate (optional)...${NC}"
if command -v certbot &> /dev/null; then
    echo "Certbot is installed"
else
    echo "Installing certbot..."
    apt-get install -y certbot python3-certbot-nginx || true
fi

# Try to get SSL certificate (will fail if domain not pointing here, that's OK)
certbot certonly --standalone -d ${DOMAIN} --agree-tos --non-interactive --email admin@cloudfuze.com 2>/dev/null || echo -e "${YELLOW}SSL certificate setup skipped - domain may not be pointing to this server yet${NC}"

# Step 9: Verify nginx config exists
echo -e "${YELLOW}Step 9: Verifying nginx configuration...${NC}"
if [ ! -f "nginx-ai.conf" ]; then
    echo -e "${RED}ERROR: nginx-ai.conf not found!${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Nginx configuration found${NC}"

# Step 10: Create data and logs directories
echo -e "${YELLOW}Step 10: Creating required directories...${NC}"
mkdir -p data logs
chmod -R 755 data logs
echo -e "${GREEN}✓ Directories created${NC}"

# Step 11: Deploy services
echo -e "${YELLOW}Step 11: Deploying services...${NC}"
docker-compose -f docker-compose.ai.yml --env-file .env.ai up -d

# Wait for services to start
echo "Waiting for services to start..."
sleep 30

# Step 12: Check service status
echo ""
echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}Service Status${NC}"
echo -e "${GREEN}================================${NC}"
docker-compose -f docker-compose.ai.yml ps

# Step 13: Health checks
echo ""
echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}Health Checks${NC}"
echo -e "${GREEN}================================${NC}"

echo ""
echo "Backend Health:"
curl -s http://localhost:8002/health || echo -e "${RED}Backend not ready yet${NC}"

echo ""
echo "Frontend Status:"
docker logs slack2teams-frontend-ai --tail 5 2>/dev/null || echo -e "${YELLOW}Frontend container not found${NC}"

echo ""
echo "Nginx Status:"
docker logs slack2teams-nginx-ai --tail 5 2>/dev/null || echo -e "${YELLOW}Nginx container not found${NC}"

# Step 14: Final summary
echo ""
echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${GREEN}================================${NC}"
echo ""
echo -e "Project Directory: ${PROJECT_DIR}"
echo -e "Domain: ${DOMAIN}"
echo -e "Branch: ${BRANCH}"
echo ""
echo -e "Access URLs:"
echo -e "  HTTP:  http://159.89.164.11"
echo -e "  HTTPS: https://${DOMAIN} (after DNS mapping and SSL setup)"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo -e "1. Map domain ${DOMAIN} to IP 159.89.164.11 in DNS"
echo -e "2. After DNS propagation, setup SSL:"
echo -e "   certbot certonly --standalone -d ${DOMAIN}"
echo -e "3. Enable HTTPS redirect in nginx-ai.conf"
echo -e "4. Restart nginx: docker restart slack2teams-nginx-ai"
echo ""
echo -e "${YELLOW}Useful Commands:${NC}"
echo -e "  View logs:    docker-compose -f docker-compose.ai.yml logs -f"
echo -e "  Restart:      docker-compose -f docker-compose.ai.yml restart"
echo -e "  Stop:         docker-compose -f docker-compose.ai.yml down"
echo -e "  Status:       docker-compose -f docker-compose.ai.yml ps"
echo ""
