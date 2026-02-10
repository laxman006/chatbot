#!/bin/bash
# Restore Weaviate data from backup
# Usage: ./scripts/restore_weaviate.sh <backup_file.tar.gz>

set -e

BACKUP_FILE="$1"
WEAVIATE_DIR="weaviate"

if [ -z "$BACKUP_FILE" ]; then
    echo "❌ Error: Backup file not specified"
    echo "Usage: $0 <backup_file.tar.gz>"
    echo ""
    echo "Available backups:"
    ls -lh weaviate_backup/*.tar.gz 2>/dev/null || echo "   No backups found"
    exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ Error: Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "========================================="
echo "Weaviate Data Restore"
echo "========================================="
echo "Backup file: $BACKUP_FILE"
echo ""

# Confirm restore
read -p "⚠️  This will REPLACE existing Weaviate data. Continue? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Restore cancelled"
    exit 0
fi

# Stop Weaviate container
echo "🛑 Stopping Weaviate container..."
docker stop slack2teams-weaviate || true
sleep 2

# Backup existing data (if exists)
if [ -d "$WEAVIATE_DIR" ] && [ "$(ls -A $WEAVIATE_DIR 2>/dev/null)" ]; then
    BACKUP_EXISTING="weaviate_backup/existing_before_restore_$(date +%Y%m%d_%H%M%S).tar.gz"
    echo "📦 Backing up existing data to: $BACKUP_EXISTING"
    mkdir -p weaviate_backup
    tar -czf "$BACKUP_EXISTING" -C "$WEAVIATE_DIR" .
fi

# Remove existing weaviate data
echo "🗑️  Removing existing Weaviate data..."
rm -rf "$WEAVIATE_DIR"/*

# Restore from backup
echo "📥 Restoring from backup..."
mkdir -p "$WEAVIATE_DIR"
tar -xzf "$BACKUP_FILE" -C "$WEAVIATE_DIR"

# Set permissions
chmod -R 755 "$WEAVIATE_DIR" || true

# Restart Weaviate
echo "▶️  Starting Weaviate container..."
docker start slack2teams-weaviate || docker-compose -f docker-compose.ai.yml up -d weaviate

echo ""
echo "✅ Restore completed!"
echo "   Weaviate data restored from: $BACKUP_FILE"
echo ""
echo "⚠️  Note: Wait for Weaviate to be healthy before using:"
echo "   docker exec slack2teams-weaviate wget -q -O- http://localhost:8080/v1/.well-known/ready"
