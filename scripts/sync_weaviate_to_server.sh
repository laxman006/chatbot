#!/bin/bash
# Sync Weaviate data folder to server
# Usage: ./scripts/sync_weaviate_to_server.sh <server_user>@<server_ip> [remote_path]

set -e

if [ -z "$1" ]; then
    echo "❌ Error: Server address not specified"
    echo "Usage: $0 <server_user>@<server_ip> [remote_path]"
    echo "Example: $0 laxman006@159.89.164.11 /opt/chatbot"
    exit 1
fi

SERVER="$1"
REMOTE_PATH="${2:-/opt/chatbot}"
WEAVIATE_DIR="weaviate"

echo "========================================="
echo "Sync Weaviate Data to Server"
echo "========================================="
echo "Server: $SERVER"
echo "Remote path: $REMOTE_PATH"
echo ""

# Check if weaviate directory exists locally
if [ ! -d "$WEAVIATE_DIR" ]; then
    echo "❌ Error: $WEAVIATE_DIR directory not found locally!"
    exit 1
fi

if [ ! "$(ls -A $WEAVIATE_DIR 2>/dev/null)" ]; then
    echo "⚠️  Warning: $WEAVIATE_DIR directory is empty"
    echo "   Nothing to sync"
    exit 0
fi

# Show local size
LOCAL_SIZE=$(du -sh "$WEAVIATE_DIR" | cut -f1)
echo "📊 Local Weaviate data size: $LOCAL_SIZE"
echo ""

# Confirm sync
read -p "⚠️  This will sync Weaviate data to server (may overwrite existing data). Continue? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Sync cancelled"
    exit 0
fi

# Stop Weaviate on server before sync
echo "🛑 Stopping Weaviate on server..."
ssh "$SERVER" "cd $REMOTE_PATH && docker-compose -f docker-compose.ai.yml stop weaviate || docker compose -f docker-compose.ai.yml stop weaviate || true"

# Sync using rsync (preferred) or scp
echo "📤 Syncing Weaviate data..."
if command -v rsync &> /dev/null; then
    echo "   Using rsync..."
    rsync -avz --progress --delete "$WEAVIATE_DIR/" "$SERVER:$REMOTE_PATH/weaviate/"
else
    echo "   Using scp (rsync not available)..."
    echo "   ⚠️  This may take longer. Consider installing rsync for faster sync."
    scp -r "$WEAVIATE_DIR" "$SERVER:$REMOTE_PATH/"
fi

# Set permissions on server
echo "🔧 Setting permissions on server..."
ssh "$SERVER" "chmod -R 755 $REMOTE_PATH/weaviate || true"

# Start Weaviate on server
echo "▶️  Starting Weaviate on server..."
ssh "$SERVER" "cd $REMOTE_PATH && docker-compose -f docker-compose.ai.yml up -d weaviate || docker compose -f docker-compose.ai.yml up -d weaviate"

echo ""
echo "✅ Sync completed!"
echo ""
echo "⚠️  Note: Wait for Weaviate to be healthy on server before using:"
echo "   ssh $SERVER 'docker exec slack2teams-weaviate wget -q -O- http://localhost:8080/v1/.well-known/ready'"
