#!/bin/bash

# ============================================
# VERIFICATION SCRIPT FOR CURSOR IMPLEMENTATION
# Server: 64.227.160.206 (ai.cloudfuze.com)
# ============================================

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

SERVER_IP="64.227.160.206"
SERVER_USER="root"
PROJECT_DIR="/opt/slack2teams-ai"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Cursor Implementation Verification${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to run command on server
run_on_server() {
    ssh ${SERVER_USER}@${SERVER_IP} "$1"
}

echo -e "${YELLOW}Step 1: Checking if cursor image files exist...${NC}"
echo ""

# Check cursor images in Docker container
echo -e "${BLUE}Checking cursor images in frontend container:${NC}"
run_on_server "docker exec \$(docker ps -q -f name=frontend) ls -lh /app/public/images/ | grep -i 'christmas\|cursor\|pointer' || echo 'Container not found, checking filesystem...'"

echo ""
echo -e "${BLUE}Checking cursor images on filesystem:${NC}"
run_on_server "ls -lh ${PROJECT_DIR}/frontend/public/images/ | grep -i 'christmas\|cursor\|pointer' || echo 'Files not found'"

echo ""
echo -e "${YELLOW}Step 2: Checking image file sizes...${NC}"
run_on_server "docker exec \$(docker ps -q -f name=frontend) sh -c 'file /app/public/images/Christmas*.png 2>/dev/null || echo \"Checking filesystem...\"; ls -lh ${PROJECT_DIR}/frontend/public/images/Christmas*.png 2>/dev/null || echo \"Files not found\"'"

echo ""
echo -e "${YELLOW}Step 3: Checking CSS file for cursor definitions...${NC}"
run_on_server "docker exec \$(docker ps -q -f name=frontend) grep -A 2 '--cursor-tree\|--cursor-bulb' /app/.next/static/css/*.css 2>/dev/null | head -10 || echo 'Checking source files...'; grep -A 2 '--cursor-tree\|--cursor-bulb' ${PROJECT_DIR}/frontend/src/app/globals.css 2>/dev/null | head -10 || echo 'CSS file not found'"

echo ""
echo -e "${YELLOW}Step 4: Checking if images are accessible via HTTP...${NC}"
echo -e "${BLUE}Testing cursor image URLs:${NC}"
echo ""
echo "Tree cursor:"
curl -I "https://ai.cloudfuze.com/images/Christmas%20Tree%20&%20Bulb%20Animated--cursor--SweezyCursors.png" 2>/dev/null | head -5 || echo "Failed to fetch"
echo ""
echo "Bulb cursor:"
curl -I "https://ai.cloudfuze.com/images/Christmas%20Tree%20&%20Bulb%20Animated--pointer--SweezyCursors.png" 2>/dev/null | head -5 || echo "Failed to fetch"

echo ""
echo -e "${YELLOW}Step 5: Checking Docker container status...${NC}"
run_on_server "docker ps | grep frontend || echo 'Frontend container not running'"

echo ""
echo -e "${YELLOW}Step 6: Checking frontend container logs (last 20 lines)...${NC}"
run_on_server "docker logs \$(docker ps -q -f name=frontend) --tail 20 2>&1 | tail -20"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Verification Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Manual Testing Steps:${NC}"
echo "1. Open browser: https://ai.cloudfuze.com"
echo "2. Open Developer Tools (F12)"
echo "3. Check Network tab for cursor images"
echo "4. Check Elements tab -> Computed styles for cursor property"
echo "5. Hover over clickable elements to see bulb cursor"
echo "6. Move mouse normally to see tree cursor"
echo ""

