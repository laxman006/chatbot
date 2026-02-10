#!/bin/bash
# Backup Weaviate data folder
# Usage: ./scripts/backup_weaviate.sh [backup_name]

set -e

BACKUP_NAME="${1:-weaviate_backup_$(date +%Y%m%d_%H%M%S)}"
BACKUP_DIR="weaviate_backup"
WEAVIATE_DIR="weaviate"

echo "========================================="
echo "Weaviate Data Backup"
echo "========================================="

# Check if weaviate directory exists
if [ ! -d "$WEAVIATE_DIR" ]; then
    echo "❌ Error: $WEAVIATE_DIR directory not found!"
    exit 1
fi

# Check if weaviate directory has data
if [ ! "$(ls -A $WEAVIATE_DIR 2>/dev/null)" ]; then
    echo "⚠️  Warning: $WEAVIATE_DIR directory is empty"
    echo "   Nothing to backup"
    exit 0
fi

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Create backup
echo "📦 Creating backup: $BACKUP_NAME"
echo "   Source: $WEAVIATE_DIR"
echo "   Destination: $BACKUP_DIR/$BACKUP_NAME.tar.gz"

# Stop Weaviate container if running (to ensure data consistency)
if docker ps | grep -q slack2teams-weaviate; then
    echo "🛑 Stopping Weaviate container for consistent backup..."
    docker stop slack2teams-weaviate || true
    sleep 2
fi

# Create tar.gz backup
tar -czf "$BACKUP_DIR/$BACKUP_NAME.tar.gz" -C "$WEAVIATE_DIR" .

# Restart Weaviate if it was running
if docker ps -a | grep -q slack2teams-weaviate; then
    echo "▶️  Restarting Weaviate container..."
    docker start slack2teams-weaviate || true
fi

# Show backup size
BACKUP_SIZE=$(du -h "$BACKUP_DIR/$BACKUP_NAME.tar.gz" | cut -f1)
echo ""
echo "✅ Backup created successfully!"
echo "   File: $BACKUP_DIR/$BACKUP_NAME.tar.gz"
echo "   Size: $BACKUP_SIZE"

# List all backups
echo ""
echo "📋 Available backups:"
ls -lh "$BACKUP_DIR"/*.tar.gz 2>/dev/null | tail -5 || echo "   No backups found"
