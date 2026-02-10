#!/bin/bash
# Full project backup script - Run on server before deployment
# Usage: ./scripts/backup_full_project.sh [backup_name]

set -e

BACKUP_NAME="${1:-project_backup_$(date +%Y%m%d_%H%M%S)}"
BACKUP_DIR="project_backups"
PROJECT_DIR="$(pwd)"

echo "========================================="
echo "Full Project Backup"
echo "========================================="
echo "Project directory: $PROJECT_DIR"
echo "Backup name: $BACKUP_NAME"
echo ""

# Create backup directory
mkdir -p "$BACKUP_DIR"

# What to backup
BACKUP_ITEMS=(
    "weaviate"           # Weaviate vector database
    "data"               # Application data
    ".env.ai"            # Environment file
    "docker-compose.ai.yml"  # Docker compose config
    "nginx-ai.conf"      # Nginx config
    "nginx.conf"         # Nginx config (if exists)
    "images"             # Static images
    "*.log"              # Log files (if any)
)

echo "📦 Creating backup..."
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
if docker ps | grep -q slack2teams; then
    echo ""
    echo "📦 Backing up Docker volumes..."
    
    # Backup MongoDB data
    if docker ps | grep -q mongodb; then
        echo "   ✓ Backing up MongoDB volume..."
        docker run --rm -v slack2teams-chatbot_mongodb_data:/data -v "$(pwd)/$TEMP_BACKUP:/backup" \
            alpine tar czf /backup/mongodb_data.tar.gz -C /data . 2>/dev/null || echo "   ⚠️  MongoDB backup skipped"
    fi
fi

# Create git info file
echo "📝 Saving git information..."
git rev-parse HEAD > "$TEMP_BACKUP/git_commit.txt" 2>/dev/null || echo "unknown" > "$TEMP_BACKUP/git_commit.txt"
git branch --show-current > "$TEMP_BACKUP/git_branch.txt" 2>/dev/null || echo "unknown" > "$TEMP_BACKUP/git_branch.txt"
git log -1 --format="%H %s" > "$TEMP_BACKUP/git_last_commit.txt" 2>/dev/null || echo "unknown" > "$TEMP_BACKUP/git_last_commit.txt"

# Create backup manifest
cat > "$TEMP_BACKUP/BACKUP_MANIFEST.txt" << EOF
Backup Information
==================
Date: $(date)
Backup Name: $BACKUP_NAME
Project Directory: $PROJECT_DIR
Git Commit: $(cat "$TEMP_BACKUP/git_commit.txt")
Git Branch: $(cat "$TEMP_BACKUP/git_branch.txt")
Last Commit: $(cat "$TEMP_BACKUP/git_last_commit.txt")

Backed Up Items:
$(ls -lh "$TEMP_BACKUP" | tail -n +2)

Disk Usage:
$(du -sh "$TEMP_BACKUP")
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
echo "💡 To restore this backup:"
echo "   ./scripts/restore_full_project.sh $BACKUP_DIR/${BACKUP_NAME}.tar.gz"
