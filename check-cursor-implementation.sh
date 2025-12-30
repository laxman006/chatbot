#!/bin/bash

# Commands to properly check cursor implementation on server

echo "=== Step 1: Verify Images Exist ==="
docker exec $(docker ps -q -f name=frontend) ls -lh /app/public/images/ | grep -i christmas

echo ""
echo "=== Step 2: Find CSS Files in Next.js Build ==="
docker exec $(docker ps -q -f name=frontend) find /app/.next -name "*.css" -type f | head -5

echo ""
echo "=== Step 3: Check CSS for Cursor Definitions ==="
docker exec $(docker ps -q -f name=frontend) sh -c 'find /app/.next -name "*.css" -exec grep -l "cursor-tree\|cursor-bulb" {} \; | head -3'

echo ""
echo "=== Step 4: View Cursor CSS Content ==="
docker exec $(docker ps -q -f name=frontend) sh -c 'find /app/.next -name "*.css" -exec grep -A 2 "cursor-tree\|cursor-bulb" {} \; | head -15'

echo ""
echo "=== Step 5: Check Source CSS File ==="
grep -A 3 "cursor-tree\|cursor-bulb" /opt/slack2teams-ai/frontend/src/app/globals.css | head -10

echo ""
echo "=== Step 6: Test Image Accessibility ==="
curl -I "https://ai.cloudfuze.com/images/Christmas%20Tree%20&%20Bulb%20Animated--cursor--SweezyCursors.png" 2>/dev/null | head -3
curl -I "https://ai.cloudfuze.com/images/Christmas%20Tree%20&%20Bulb%20Animated--pointer--SweezyCursors.png" 2>/dev/null | head -3

echo ""
echo "=== Step 7: Check Container Logs for Errors ==="
docker logs $(docker ps -q -f name=frontend) --tail 20 | grep -i error || echo "No errors found"

