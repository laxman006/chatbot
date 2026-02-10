#!/bin/bash
# Restore full project backup - Run on server
# Usage: ./scripts/restore_full_project.sh <backup_file.tar.gz>

set -e

BACKUP_FILE="$1"

if [ -z "$BACKUP_FILE" ]; then
    echo "❌ Error: Backup file not specified"
    echo "Usage: $0 <backup_file.tar.gz>"
    echo ""
    echo "Available backups:"
    ls -lh project_backups/*.tar.gz 2>/dev/null || echo "   No backups found"
    exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ Error: Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "========================================="
echo "Full Project Restore"
echo "========================================="
echo "Backup file: $BACKUP_FILE"
echo ""

# Show backup manifest if exists
if tar -tzf "$BACKUP_FILE" | grep -q "BACKUP_MANIFEST.txt"; then
    echo "📋 Backup Information:"
    tar -xzf "$BACKUP_FILE" --to-stdout */BACKUP_MANIFEST.txt 2>/dev/null | head -20
    echo ""
fi

# Confirm restore
read -p "⚠️  This will RESTORE files from backup. Continue? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Restore cancelled"
    exit 0
fi

# Stop services
echo "🛑 Stopping services..."
docker-compose -f docker-compose.ai.yml down || docker compose -f docker-compose.ai.yml down || true
sleep 3

# Extract backup
echo "📥 Extracting backup..."
TEMP_RESTORE="restore_temp_$(date +%s)"
mkdir -p "$TEMP_RESTORE"
tar -xzf "$BACKUP_FILE" -C "$TEMP_RESTORE"
RESTORE_DIR=$(find "$TEMP_RESTORE" -maxdepth 1 -type d ! -path "$TEMP_RESTORE" | head -1)

if [ -z "$RESTORE_DIR" ]; then
    echo "❌ Error: Could not find backup contents"
    rm -rf "$TEMP_RESTORE"
    exit 1
fi

# Restore files
echo "📤 Restoring files..."

# Restore Weaviate data
if [ -d "$RESTORE_DIR/weaviate" ]; then
    echo "   ✓ Restoring Weaviate data..."
    rm -rf weaviate
    cp -r "$RESTORE_DIR/weaviate" .
    chmod -R 755 weaviate
fi

# Restore data folder
if [ -d "$RESTORE_DIR/data" ]; then
    echo "   ✓ Restoring data folder..."
    rm -rf data
    cp -r "$RESTORE_DIR/data" .
fi

# Restore .env.ai (with confirmation)
if [ -f "$RESTORE_DIR/.env.ai" ]; then
    read -p "   Restore .env.ai file? (yes/no): " restore_env
    if [ "$restore_env" == "yes" ]; then
        echo "   ✓ Restoring .env.ai..."
        cp "$RESTORE_DIR/.env.ai" .env.ai
        chmod 600 .env.ai
    else
        echo "   ⊘ Skipping .env.ai (keeping current)"
    fi
fi

# Restore nginx configs
if [ -f "$RESTORE_DIR/nginx-ai.conf" ]; then
    echo "   ✓ Restoring nginx-ai.conf..."
    cp "$RESTORE_DIR/nginx-ai.conf" .
fi

if [ -f "$RESTORE_DIR/nginx.conf" ]; then
    echo "   ✓ Restoring nginx.conf..."
    cp "$RESTORE_DIR/nginx.conf" .
fi

# Restore images
if [ -d "$RESTORE_DIR/images" ]; then
    echo "   ✓ Restoring images..."
    rm -rf images
    cp -r "$RESTORE_DIR/images" .
fi

# Restore MongoDB volume (if exists)
if [ -f "$RESTORE_DIR/mongodb_data.tar.gz" ]; then
    read -p "   Restore MongoDB data? (yes/no): " restore_mongo
    if [ "$restore_mongo" == "yes" ]; then
        echo "   ✓ Restoring MongoDB data..."
        docker volume create slack2teams-chatbot_mongodb_data 2>/dev/null || true
        docker run --rm -v slack2teams-chatbot_mongodb_data:/data -v "$(pwd)/$RESTORE_DIR:/backup" \
            alpine sh -c "cd /data && rm -rf * && tar xzf /backup/mongodb_data.tar.gz" || echo "   ⚠️  MongoDB restore failed"
    fi
fi

# Cleanup
rm -rf "$TEMP_RESTORE"

echo ""
echo "✅ Restore completed!"
echo ""
echo "⚠️  Next steps:"
echo "   1. Review restored files"
echo "   2. Update .env.ai if needed"
echo "   3. Start services: docker-compose -f docker-compose.ai.yml --env-file .env.ai up -d"
