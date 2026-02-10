#!/bin/bash
# Push Weaviate folder from local to server
# Usage: ./scripts/push_weaviate_to_server.sh <server_user>@<server_ip> [remote_path]

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
echo "Push Weaviate Data to Server"
echo "========================================="
echo "Server: $SERVER"
echo "Remote path: $REMOTE_PATH"
echo "Local Weaviate: $WEAVIATE_DIR"
echo ""

# Check if weaviate directory exists locally
if [ ! -d "$WEAVIATE_DIR" ]; then
    echo "❌ Error: $WEAVIATE_DIR directory not found locally!"
    exit 1
fi

if [ ! "$(ls -A $WEAVIATE_DIR 2>/dev/null)" ]; then
    echo "⚠️  Warning: $WEAVIATE_DIR directory is empty"
    read -p "Continue anyway? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        exit 0
    fi
fi

# Show local size
LOCAL_SIZE=$(du -sh "$WEAVIATE_DIR" | cut -f1)
echo "📊 Local Weaviate data size: $LOCAL_SIZE"
echo ""

# Check remote server connection
echo "🔍 Checking server connection..."
if ! ssh -o ConnectTimeout=5 "$SERVER" "echo 'Connection OK'" > /dev/null 2>&1; then
    echo "❌ Error: Cannot connect to server $SERVER"
    echo "   Check SSH access: ssh $SERVER"
    exit 1
fi
echo "✅ Server connection OK"
echo ""

# Check if remote path exists
echo "🔍 Checking remote directory..."
if ! ssh "$SERVER" "test -d $REMOTE_PATH"; then
    echo "❌ Error: Remote directory $REMOTE_PATH does not exist!"
    echo "   Create it first or specify correct path"
    exit 1
fi
echo "✅ Remote directory exists"
echo ""

# Show remote Weaviate status
echo "📊 Remote Weaviate status:"
REMOTE_EXISTS=$(ssh "$SERVER" "test -d $REMOTE_PATH/weaviate && echo 'yes' || echo 'no'")
if [ "$REMOTE_EXISTS" == "yes" ]; then
    REMOTE_SIZE=$(ssh "$SERVER" "du -sh $REMOTE_PATH/weaviate 2>/dev/null | cut -f1" || echo "unknown")
    echo "   Remote Weaviate exists: Yes"
    echo "   Remote size: $REMOTE_SIZE"
else
    echo "   Remote Weaviate exists: No (will be created)"
fi
echo ""

# Confirm push
read -p "⚠️  This will sync Weaviate data to server (may overwrite existing data). Continue? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Push cancelled"
    exit 0
fi

# Stop Weaviate on server before sync
echo "🛑 Stopping Weaviate on server..."
ssh "$SERVER" "cd $REMOTE_PATH && docker-compose -f docker-compose.ai.yml stop weaviate 2>/dev/null || docker compose -f docker-compose.ai.yml stop weaviate 2>/dev/null || true"
sleep 2

# Create backup on server before overwriting
if [ "$REMOTE_EXISTS" == "yes" ]; then
    echo "📦 Creating backup on server before overwriting..."
    ssh "$SERVER" "cd $REMOTE_PATH && mkdir -p weaviate_backup && tar -czf weaviate_backup/pre_sync_backup_\$(date +%Y%m%d_%H%M%S).tar.gz -C weaviate . 2>/dev/null || true"
fi

# Sync using rsync (preferred) or scp
echo "📤 Syncing Weaviate data..."
if command -v rsync &> /dev/null; then
    echo "   Using rsync (faster, preserves permissions)..."
    rsync -avz --progress --delete "$WEAVIATE_DIR/" "$SERVER:$REMOTE_PATH/weaviate/"
    SYNC_METHOD="rsync"
else
    echo "   Using scp (rsync not available)..."
    echo "   ⚠️  This may take longer. Consider installing rsync for faster sync."
    ssh "$SERVER" "mkdir -p $REMOTE_PATH/weaviate"
    scp -r "$WEAVIATE_DIR"/* "$SERVER:$REMOTE_PATH/weaviate/"
    SYNC_METHOD="scp"
fi

# Set permissions on server
echo "🔧 Setting permissions on server..."
ssh "$SERVER" "chmod -R 755 $REMOTE_PATH/weaviate || true"

# Verify sync
echo "🔍 Verifying sync..."
REMOTE_COUNT=$(ssh "$SERVER" "find $REMOTE_PATH/weaviate -type f 2>/dev/null | wc -l" || echo "0")
LOCAL_COUNT=$(find "$WEAVIATE_DIR" -type f 2>/dev/null | wc -l || echo "0")
echo "   Local files: $LOCAL_COUNT"
echo "   Remote files: $REMOTE_COUNT"

# Start Weaviate on server
echo "▶️  Starting Weaviate on server..."
ssh "$SERVER" "cd $REMOTE_PATH && docker-compose -f docker-compose.ai.yml up -d weaviate || docker compose -f docker-compose.ai.yml up -d weaviate"

echo ""
echo "✅ Weaviate data pushed successfully!"
echo ""
echo "📋 Summary:"
echo "   Method: $SYNC_METHOD"
echo "   Local size: $LOCAL_SIZE"
echo "   Files synced: $LOCAL_COUNT → $REMOTE_COUNT"
echo ""
echo "⚠️  Next steps:"
echo "   1. Wait for Weaviate to be healthy:"
echo "      ssh $SERVER 'docker exec slack2teams-weaviate wget -q -O- http://localhost:8080/v1/.well-known/ready'"
echo "   2. Verify collections:"
echo "      ssh $SERVER 'cd $REMOTE_PATH && docker exec slack2teams-backend-ai python -c \"from app.weaviate_schema import list_collections; print(list_collections())\"'"
echo "   3. Check Weaviate logs:"
echo "      ssh $SERVER 'docker logs slack2teams-weaviate --tail=50'"
