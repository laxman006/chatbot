#!/bin/bash
# Manual backup script for existing langchain/chromadb project
# Run this on the server BEFORE deploying new langgraph/weaviate code
# This script works even if backup scripts don't exist yet

set -e

BACKUP_NAME="langchain_chromadb_backup_$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="project_backups"
PROJECT_DIR="$(pwd)"

echo "========================================="
echo "Manual Backup: Langchain/ChromaDB Project"
echo "========================================="
echo "Project directory: $PROJECT_DIR"
echo "Backup name: $BACKUP_NAME"
echo ""

# Create backup directory
mkdir -p "$BACKUP_DIR/$BACKUP_NAME"
TEMP_BACKUP="$BACKUP_DIR/$BACKUP_NAME"

echo "📦 Backing up existing project files..."
echo ""

# Backup ChromaDB/vectorstore data
if [ -d "chroma" ]; then
    echo "   ✓ Backing up: chroma/"
    cp -r chroma "$TEMP_BACKUP/" 2>/dev/null || echo "   ⚠️  Failed to backup chroma/"
fi

if [ -d "chromadb" ]; then
    echo "   ✓ Backing up: chromadb/"
    cp -r chromadb "$TEMP_BACKUP/" 2>/dev/null || echo "   ⚠️  Failed to backup chromadb/"
fi

if [ -d "vectorstore" ]; then
    echo "   ✓ Backing up: vectorstore/"
    cp -r vectorstore "$TEMP_BACKUP/" 2>/dev/null || echo "   ⚠️  Failed to backup vectorstore/"
fi

# Backup application data
if [ -d "data" ]; then
    echo "   ✓ Backing up: data/"
    cp -r data "$TEMP_BACKUP/" 2>/dev/null || echo "   ⚠️  Failed to backup data/"
fi

# Backup environment files
if [ -f ".env" ]; then
    echo "   ✓ Backing up: .env"
    cp .env "$TEMP_BACKUP/" 2>/dev/null || echo "   ⚠️  Failed to backup .env"
fi

if [ -f ".env.ai" ]; then
    echo "   ✓ Backing up: .env.ai"
    cp .env.ai "$TEMP_BACKUP/" 2>/dev/null || echo "   ⚠️  Failed to backup .env.ai"
fi

# Backup Docker configs
if [ -f "docker-compose.yml" ]; then
    echo "   ✓ Backing up: docker-compose.yml"
    cp docker-compose.yml "$TEMP_BACKUP/" 2>/dev/null || echo "   ⚠️  Failed to backup docker-compose.yml"
fi

if [ -f "docker-compose.ai.yml" ]; then
    echo "   ✓ Backing up: docker-compose.ai.yml"
    cp docker-compose.ai.yml "$TEMP_BACKUP/" 2>/dev/null || echo "   ⚠️  Failed to backup docker-compose.ai.yml"
fi

# Backup nginx configs
for nginx_file in nginx.conf nginx-ai.conf nginx-prod.conf; do
    if [ -f "$nginx_file" ]; then
        echo "   ✓ Backing up: $nginx_file"
        cp "$nginx_file" "$TEMP_BACKUP/" 2>/dev/null || echo "   ⚠️  Failed to backup $nginx_file"
    fi
done

# Backup images
if [ -d "images" ]; then
    echo "   ✓ Backing up: images/"
    cp -r images "$TEMP_BACKUP/" 2>/dev/null || echo "   ⚠️  Failed to backup images/"
fi

# Backup Docker container info
if command -v docker &> /dev/null; then
    echo ""
    echo "📦 Saving Docker container information..."
    docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" > "$TEMP_BACKUP/running_containers.txt" 2>/dev/null || true
    
    if command -v docker-compose &> /dev/null; then
        docker-compose ps > "$TEMP_BACKUP/docker_compose_ps.txt" 2>/dev/null || true
    elif command -v docker &> /dev/null && docker compose version &> /dev/null; then
        docker compose ps > "$TEMP_BACKUP/docker_compose_ps.txt" 2>/dev/null || true
    fi
fi

# Create backup manifest
cat > "$TEMP_BACKUP/BACKUP_MANIFEST.txt" << EOF
Backup Information
==================
Date: $(date)
Backup Name: $BACKUP_NAME
Project Directory: $PROJECT_DIR
Project Type: Langchain/ChromaDB (OLD PROJECT)

Backed Up Items:
$(ls -lh "$TEMP_BACKUP" | tail -n +2)

Disk Usage:
$(du -sh "$TEMP_BACKUP" 2>/dev/null || echo "unknown")

IMPORTANT: This is a backup of the OLD langchain/chromadb project.
After deploying the new langgraph/weaviate version, you can restore
this backup if needed.
EOF

# Create compressed archive
echo ""
echo "📦 Creating compressed archive..."
cd "$BACKUP_DIR"
tar -czf "${BACKUP_NAME}.tar.gz" "$BACKUP_NAME"
cd "$PROJECT_DIR"

# Remove temporary directory
rm -rf "$TEMP_BACKUP"

# Show backup info
BACKUP_SIZE=$(du -h "$BACKUP_DIR/${BACKUP_NAME}.tar.gz" 2>/dev/null | cut -f1 || echo "unknown")
echo ""
echo "✅ Backup created successfully!"
echo "   File: $BACKUP_DIR/${BACKUP_NAME}.tar.gz"
echo "   Size: $BACKUP_SIZE"
echo ""

# List recent backups
echo "📋 Recent backups:"
ls -lht "$BACKUP_DIR"/*.tar.gz 2>/dev/null | head -5 || echo "   No backups found"

echo ""
echo "💡 Next steps:"
echo "   1. Deploy new langgraph/weaviate code"
echo "   2. If rollback needed: tar -xzf $BACKUP_DIR/${BACKUP_NAME}.tar.gz"
