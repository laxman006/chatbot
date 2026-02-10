#!/bin/bash
# Remote deployment script executed on the server
set -e

DEPLOY_PATH="${DEPLOY_PATH:-/opt/chatbot}"
BRANCH="${BRANCH:-langgraph-rag}"

echo "🚀 Starting deployment..."
echo "   Branch: $BRANCH"
echo "   Path: $DEPLOY_PATH"

# Navigate to deployment directory
cd "$DEPLOY_PATH" || {
  echo "❌ Directory $DEPLOY_PATH does not exist!"
  exit 1
}

# Stop existing containers
echo "📦 Stopping existing containers..."
docker-compose -f docker-compose.ai.yml down || true

# Checkout and pull latest code
echo "📥 Pulling latest code from branch: $BRANCH"
git fetch origin
git checkout "$BRANCH" || {
  echo "⚠️  Branch $BRANCH not found locally, creating..."
  git checkout -b "$BRANCH" "origin/$BRANCH"
}
git pull origin "$BRANCH"

# Verify .env.ai exists
if [ ! -f .env.ai ]; then
  echo "⚠️  Warning: .env.ai file not found!"
  echo "   Make sure .env.ai exists on the server before deployment."
fi

# Start containers
echo "🚀 Starting containers..."
docker-compose -f docker-compose.ai.yml --env-file .env.ai up -d --build

# Wait a moment for services to start
sleep 10

# Check container status
echo "📊 Container status:"
docker-compose -f docker-compose.ai.yml ps

# Health check
echo "🏥 Checking backend health..."
if curl -f http://localhost:8002/health > /dev/null 2>&1; then
  echo "✅ Backend is healthy!"
else
  echo "⚠️  Backend health check failed (may still be starting)"
fi

echo "✅ Deployment completed!"
