#!/bin/bash

# Pre-Deployment Check Script
# Run this on the server BEFORE deploying to verify everything is ready

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}Pre-Deployment Check${NC}"
echo -e "${GREEN}================================${NC}"
echo ""

# Check 1: Docker Installation
echo -e "${YELLOW}1. Checking Docker installation...${NC}"
if command -v docker &> /dev/null; then
    echo -e "${GREEN}✓ Docker is installed${NC}"
    docker --version
else
    echo -e "${RED}✗ Docker is NOT installed${NC}"
    exit 1
fi

# Check 2: Docker Compose
echo ""
echo -e "${YELLOW}2. Checking Docker Compose...${NC}"
if command -v docker-compose &> /dev/null || docker compose version &> /dev/null; then
    echo -e "${GREEN}✓ Docker Compose is installed${NC}"
    docker-compose --version || docker compose version
else
    echo -e "${RED}✗ Docker Compose is NOT installed${NC}"
    exit 1
fi

# Check 3: Docker Service Status
echo ""
echo -e "${YELLOW}3. Checking Docker service status...${NC}"
if systemctl is-active --quiet docker; then
    echo -e "${GREEN}✓ Docker service is running${NC}"
else
    echo -e "${YELLOW}⚠ Docker service is not running, starting it...${NC}"
    systemctl start docker
    systemctl enable docker
    echo -e "${GREEN}✓ Docker service started${NC}"
fi

# Check 4: Firewall (UFW) Status
echo ""
echo -e "${YELLOW}4. Checking firewall configuration...${NC}"
if command -v ufw &> /dev/null; then
    UFW_STATUS=$(ufw status | head -n 1)
    echo "UFW Status: $UFW_STATUS"
    
    if echo "$UFW_STATUS" | grep -q "Status: active"; then
        echo -e "${YELLOW}UFW is active. Checking ports 80 and 443...${NC}"
        
        # Check if ports are open
        if ufw status | grep -q "80/tcp"; then
            echo -e "${GREEN}✓ Port 80 is open${NC}"
        else
            echo -e "${YELLOW}⚠ Port 80 is NOT open. Opening it...${NC}"
            ufw allow 80/tcp
        fi
        
        if ufw status | grep -q "443/tcp"; then
            echo -e "${GREEN}✓ Port 443 is open${NC}"
        else
            echo -e "${YELLOW}⚠ Port 443 is NOT open. Opening it...${NC}"
            ufw allow 443/tcp
        fi
        
        echo ""
        echo "Current UFW rules:"
        ufw status numbered
    else
        echo -e "${YELLOW}UFW is inactive${NC}"
    fi
else
    echo -e "${YELLOW}UFW not installed, skipping firewall check${NC}"
fi

# Check 5: Disk Space
echo ""
echo -e "${YELLOW}5. Checking disk space...${NC}"
df -h / | tail -n 1 | awk '{print "Disk usage: " $5 " used (" $3 " / " $2 ")"}'
DISK_USAGE=$(df / | tail -n 1 | awk '{print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -lt 80 ]; then
    echo -e "${GREEN}✓ Sufficient disk space available${NC}"
else
    echo -e "${RED}⚠ Warning: Disk usage is ${DISK_USAGE}%${NC}"
fi

# Check 6: Memory
echo ""
echo -e "${YELLOW}6. Checking memory...${NC}"
free -h | grep Mem | awk '{print "Memory: " $3 " / " $2 " used"}'

# Check 7: Network Connectivity
echo ""
echo -e "${YELLOW}7. Checking network connectivity...${NC}"
if ping -c 1 8.8.8.8 &> /dev/null; then
    echo -e "${GREEN}✓ Internet connectivity OK${NC}"
else
    echo -e "${RED}✗ No internet connectivity${NC}"
    exit 1
fi

# Check 8: Git Installation
echo ""
echo -e "${YELLOW}8. Checking Git installation...${NC}"
if command -v git &> /dev/null; then
    echo -e "${GREEN}✓ Git is installed${NC}"
    git --version
else
    echo -e "${YELLOW}⚠ Git is NOT installed. It will be installed during deployment.${NC}"
fi

# Check 9: Required Ports Availability
echo ""
echo -e "${YELLOW}9. Checking if required ports are available...${NC}"
PORTS=(80 443 3000 8002)
for port in "${PORTS[@]}"; do
    if netstat -tuln 2>/dev/null | grep -q ":$port "; then
        echo -e "${YELLOW}⚠ Port $port is already in use${NC}"
    else
        echo -e "${GREEN}✓ Port $port is available${NC}"
    fi
done

# Summary
echo ""
echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}Pre-Deployment Check Complete${NC}"
echo -e "${GREEN}================================${NC}"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo -e "1. Run the deployment script: ./deploy-on-server.sh"
echo -e "2. Or follow manual deployment steps"
echo ""
