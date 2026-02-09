#!/bin/bash
# Backup existing langchain/chromadb project before migrating to langgraph/weaviate
# Run this on the server BEFORE deploying new code
# Usage: ./scripts/backup_existing_project.sh [backup_name]

set -e

BACKUP_NAME="${1:-langchain_chromadb_backup_$(date +%Y%m%d_%H%M%S)}"
BACKUP_DIR="project_backups"
PROJECT_DIR="$(pwd)"

echo "========================================="
echo "Backup Existing Langchain/ChromaDB Project"
echo "========================================="
echo "Project directory: $PROJECT_DIR"
echo "Backup name: $BACKUP_NAME"
echo ""

# Create backup directory
mkdir -p "$BACKUP_DIR"

# What to backup from existing langchain/chromadb project
BACKUP_ITEMS=(
    "chroma"              # ChromaDB database (if exists)
    "chromadb"            # Alternative ChromaDB location
    "vectorstore"         # Vectorstore data
    "data"                # Application data
    ".env"                # Environment file (may be .env or .env.ai)
    ".env.ai"             # Environment file
    "docker-compose.yml"  # Docker compose config
    "docker-compose.ai.yml"  # Docker compose config
    "nginx.conf"          # Nginx config
    "nginx-ai.conf"       # Nginx config
    "images"              # Static images
)

echo "📦 Creating backup of existing project..."
echo ""

# Create temporary backup directory
TEMP_BACKUP="$BACKUP_DIR/$BACKUP_NAME"
mkdir -p "$TEMP_BACKUP"

# Backup each item
BACKED_UP=0
for item in "${BACKUP_ITEMS[@]}"; do
    if [ -e "$item" ] || [ -d "$item" ]; then
        echo "   ✓ Backing up: $item"
        cp -r "$item" "$TEMP_BACKUP/" 2>/dev/null || {
            echo "   ⚠️  Warning: Could not backup $item"
        }
        BACKED_UP=$((BACKED_UP + 1))
    else
        echo "   ⊘ Skipping (not found): $item"
    fi
done

# Backup Docker volumes (if containers are running)
if docker ps | grep -q slack2teams || docker ps | grep -q chatbot; then
    echo ""
    echo "📦 Backing up Docker volumes..."
    
    # List all volumes
    docker volume ls | grep -E "slack2teams|chatbot|chroma|vectorstore" | while read -r volume; do
        VOL_NAME=$(echo $volume | awk '{print $2}')
        if [ ! -z "$VOL_NAME" ]; then
            echo "   ✓ Backing up volume: $VOL_NAME"
            docker run --rm -v "$VOL_NAME:/data" -v "$(pwd)/$TEMP_BACKUP:/backup" \
                alpine tar czf "/backup/${VOL_NAME//\//_}.tar.gz" -C /data . 2>/dev/null || echo "   ⚠️  Volume backup skipped: $VOL_NAME"
        fi
    done
fi

# Backup running containers info
if docker ps | grep -q -E "slack2teams|chatbot"; then
    echo ""
    echo "📦 Saving container information..."
    docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" > "$TEMP_BACKUP/running_containers.txt" 2>/dev/null || true
    docker-compose ps > "$TEMP_BACKUP/docker_compose_ps.txt" 2>/dev/null || docker compose ps > "$TEMP_BACKUP/docker_compose_ps.txt" 2>/dev/null || true
fi

# Create git info file (if git repo exists)
if [ -d ".git" ]; then
    echo "📝 Saving git information..."
    git rev-parse HEAD > "$TEMP_BACKUP/git_commit.txt" 2>/dev/null || echo "unknown" > "$TEMP_BACKUP/git_commit.txt"
    git branch --show-current > "$TEMP_BACKUP/git_branch.txt" 2>/dev/null || echo "unknown" > "$TEMP_BACKUP/git_branch.txt"
    git log -1 --format="%H %s" > "$TEMP_BACKUP/git_last_commit.txt" 2>/dev/null || echo "unknown" > "$TEMP_BACKUP/git_last_commit.txt"
fi

# Create backup manifest
cat > "$TEMP_BACKUP/BACKUP_MANIFEST.txt" << EOF
Backup Information
==================
Date: $(date)
Backup Name: $BACKUP_NAME
Project Directory: $PROJECT_DIR
Project Type: Langchain/ChromaDB (OLD)
Git Commit: $(cat "$TEMP_BACKUP/git_commit.txt" 2>/dev/null || echo "unknown")
Git Branch: $(cat "$TEMP_BACKUP/git_branch.txt" 2>/dev/null || echo "unknown")

Backed Up Items:
$(ls -lh "$TEMP_BACKUP" | tail -n +2)

Disk Usage:
$(du -sh "$TEMP_BACKUP")

IMPORTANT: This is a backup of the OLD langchain/chromadb project.
After deploying the new langgraph/weaviate version, you can restore
this backup if needed using restore_full_project.sh
EOF

# Create tar.gz archive
echo ""
echo "📦 Creating compressed archive..."
cd "$BACKUP_DIR"
tar -czf "${BACKUP_NAME}.tar.gz" "$BACKUP_NAME"
cd "$PROJECT_DIR"

# Remove temporary directory
rm -rf "$TEMP_BACKUP"

# Show backup info
BACKUP_SIZE=$(du -h "$BACKUP_DIR/${BACKUP_NAME}.tar.gz" | cut -f1)
echo ""
echo "✅ Backup created successfully!"
echo "   File: $BACKUP_DIR/${BACKUP_NAME}.tar.gz"
echo "   Size: $BACKUP_SIZE"
echo "   Items backed up: $BACKED_UP"
echo ""

# List recent backups
echo "📋 Recent backups:"
ls -lht "$BACKUP_DIR"/*.tar.gz 2>/dev/null | head -5 || echo "   No backups found"

echo ""
echo "💡 Next steps:"
echo "   1. Deploy new langgraph/weaviate code"
echo "   2. If rollback needed: ./scripts/restore_full_project.sh $BACKUP_DIR/${BACKUP_NAME}.tar.gz"
