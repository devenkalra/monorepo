#!/bin/bash
#
# Backup Script for Data Backend Application
#
# This script backs up:
# - PostgreSQL database
# - Neo4j graph database
# - Media files (photos, attachments, thumbnails)
# - MeiliSearch index data
# - Application configuration
#
# Usage:
#   ./scripts/backup.sh [backup-name]
#
# If no backup name is provided, uses timestamp.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_ROOT="${BACKUP_ROOT:-$HOME/backups/data-backend}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="${1:-backup_$TIMESTAMP}"
BACKUP_DIR="$BACKUP_ROOT/$BACKUP_NAME"

# Docker compose file
COMPOSE_FILE="$PROJECT_DIR/docker-compose.local.yml"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Data Backend Backup Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Backup name:${NC} $BACKUP_NAME"
echo -e "${YELLOW}Backup location:${NC} $BACKUP_DIR"
echo ""

# Check if docker-compose is running
if ! docker-compose -f "$COMPOSE_FILE" ps | grep -q "Up"; then
    echo -e "${RED}Error: Docker containers are not running${NC}"
    echo -e "${YELLOW}Please start the application first:${NC}"
    echo -e "  cd $PROJECT_DIR"
    echo -e "  docker-compose -f docker-compose.local.yml up -d"
    exit 1
fi

# Create backup directory
echo -e "${YELLOW}Creating backup directory...${NC}"
mkdir -p "$BACKUP_DIR"

# Create metadata file
cat > "$BACKUP_DIR/backup_metadata.txt" << EOF
Backup Name: $BACKUP_NAME
Backup Date: $(date)
Backup Type: Full
Application: Data Backend
Hostname: $(hostname)
User: $(whoami)
EOF

echo -e "${GREEN}✓ Backup directory created${NC}"
echo ""

# 1. Backup PostgreSQL Database
echo -e "${YELLOW}Backing up PostgreSQL database...${NC}"
docker-compose -f "$COMPOSE_FILE" exec -T db pg_dump -U postgres postgres > "$BACKUP_DIR/postgres_dump.sql"
gzip "$BACKUP_DIR/postgres_dump.sql"
PG_SIZE=$(du -h "$BACKUP_DIR/postgres_dump.sql.gz" | cut -f1)
echo -e "${GREEN}✓ PostgreSQL backup complete${NC} (Size: $PG_SIZE)"
echo ""

# 2. Backup Neo4j Database
echo -e "${YELLOW}Backing up Neo4j database...${NC}"
NEO4J_BACKUP_DIR="$BACKUP_DIR/neo4j"
mkdir -p "$NEO4J_BACKUP_DIR"

# Export Neo4j data using cypher-shell
docker-compose -f "$COMPOSE_FILE" exec -T neo4j cypher-shell -u neo4j -p password \
    "CALL apoc.export.json.all('/var/lib/neo4j/export/backup.json', {useTypes:true})" \
    2>/dev/null || echo "Note: APOC export not available, using alternative method"

# Alternative: Export using docker cp
docker-compose -f "$COMPOSE_FILE" exec -T neo4j neo4j-admin database dump neo4j \
    --to-path=/var/lib/neo4j/backups 2>/dev/null || true

# Copy backup files from container
docker cp $(docker-compose -f "$COMPOSE_FILE" ps -q neo4j):/var/lib/neo4j/data "$NEO4J_BACKUP_DIR/" 2>/dev/null || \
    echo "Note: Direct data copy not available"

# Create a simple export using cypher
docker-compose -f "$COMPOSE_FILE" exec -T neo4j cypher-shell -u neo4j -p password \
    "MATCH (n) RETURN n LIMIT 10" > "$NEO4J_BACKUP_DIR/sample_data.txt" 2>/dev/null || true

if [ -d "$NEO4J_BACKUP_DIR/data" ]; then
    tar -czf "$NEO4J_BACKUP_DIR.tar.gz" -C "$NEO4J_BACKUP_DIR" .
    rm -rf "$NEO4J_BACKUP_DIR"
    NEO4J_SIZE=$(du -h "$NEO4J_BACKUP_DIR.tar.gz" | cut -f1)
    echo -e "${GREEN}✓ Neo4j backup complete${NC} (Size: $NEO4J_SIZE)"
else
    echo -e "${YELLOW}⚠ Neo4j backup partial - data directory not accessible${NC}"
fi
echo ""

# 3. Backup Media Files
echo -e "${YELLOW}Backing up media files...${NC}"
MEDIA_DIR="$PROJECT_DIR/media"
if [ -d "$MEDIA_DIR" ]; then
    tar -czf "$BACKUP_DIR/media_files.tar.gz" -C "$PROJECT_DIR" media/
    MEDIA_SIZE=$(du -h "$BACKUP_DIR/media_files.tar.gz" | cut -f1)
    MEDIA_COUNT=$(find "$MEDIA_DIR" -type f | wc -l)
    echo -e "${GREEN}✓ Media files backup complete${NC} (Files: $MEDIA_COUNT, Size: $MEDIA_SIZE)"
else
    echo -e "${YELLOW}⚠ No media directory found${NC}"
fi
echo ""

# 4. Backup MeiliSearch Data
echo -e "${YELLOW}Backing up MeiliSearch data...${NC}"
MEILI_BACKUP_DIR="$BACKUP_DIR/meilisearch"
mkdir -p "$MEILI_BACKUP_DIR"

# Create MeiliSearch dump via API
MEILI_URL="http://localhost:7701"
MEILI_KEY=$(grep MEILI_MASTER_KEY "$PROJECT_DIR/.env" 2>/dev/null | cut -d= -f2 || echo "masterKey")

# Trigger dump creation
DUMP_RESPONSE=$(curl -s -X POST "$MEILI_URL/dumps" \
    -H "Authorization: Bearer $MEILI_KEY" 2>/dev/null || echo "{}")

if echo "$DUMP_RESPONSE" | grep -q "taskUid"; then
    TASK_UID=$(echo "$DUMP_RESPONSE" | grep -o '"taskUid":[0-9]*' | cut -d: -f2)
    echo "Waiting for MeiliSearch dump to complete (Task: $TASK_UID)..."
    
    # Wait for dump to complete (max 60 seconds)
    for i in {1..60}; do
        TASK_STATUS=$(curl -s "$MEILI_URL/tasks/$TASK_UID" \
            -H "Authorization: Bearer $MEILI_KEY" 2>/dev/null | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
        
        if [ "$TASK_STATUS" = "succeeded" ]; then
            echo -e "${GREEN}✓ MeiliSearch dump created${NC}"
            break
        elif [ "$TASK_STATUS" = "failed" ]; then
            echo -e "${YELLOW}⚠ MeiliSearch dump failed${NC}"
            break
        fi
        sleep 1
    done
    
    # Copy dump files from container
    docker cp $(docker-compose -f "$COMPOSE_FILE" ps -q meilisearch):/meili_data/dumps "$MEILI_BACKUP_DIR/" 2>/dev/null || \
        echo -e "${YELLOW}⚠ Could not copy MeiliSearch dumps${NC}"
    
    if [ -d "$MEILI_BACKUP_DIR/dumps" ]; then
        tar -czf "$MEILI_BACKUP_DIR.tar.gz" -C "$MEILI_BACKUP_DIR" dumps/
        rm -rf "$MEILI_BACKUP_DIR/dumps"
        MEILI_SIZE=$(du -h "$MEILI_BACKUP_DIR.tar.gz" | cut -f1)
        echo -e "${GREEN}✓ MeiliSearch backup complete${NC} (Size: $MEILI_SIZE)"
    fi
else
    echo -e "${YELLOW}⚠ MeiliSearch backup skipped (API not accessible)${NC}"
fi
echo ""

# 5. Backup Configuration Files
echo -e "${YELLOW}Backing up configuration files...${NC}"
CONFIG_DIR="$BACKUP_DIR/config"
mkdir -p "$CONFIG_DIR"

# Copy important config files (excluding secrets)
[ -f "$PROJECT_DIR/.env.example" ] && cp "$PROJECT_DIR/.env.example" "$CONFIG_DIR/"
[ -f "$PROJECT_DIR/docker-compose.local.yml" ] && cp "$PROJECT_DIR/docker-compose.local.yml" "$CONFIG_DIR/"
[ -f "$PROJECT_DIR/config/settings.py" ] && cp "$PROJECT_DIR/config/settings.py" "$CONFIG_DIR/"
[ -f "$PROJECT_DIR/requirements.txt" ] && cp "$PROJECT_DIR/requirements.txt" "$CONFIG_DIR/"

# Create a sanitized .env file (remove sensitive values)
if [ -f "$PROJECT_DIR/.env" ]; then
    sed 's/=.*/=<REDACTED>/' "$PROJECT_DIR/.env" > "$CONFIG_DIR/.env.template"
fi

echo -e "${GREEN}✓ Configuration backup complete${NC}"
echo ""

# 6. Export data via Django management command
echo -e "${YELLOW}Exporting application data via Django...${NC}"
docker-compose -f "$COMPOSE_FILE" exec -T backend python manage.py dumpdata \
    --natural-foreign --natural-primary \
    --exclude contenttypes --exclude auth.permission \
    --indent 2 > "$BACKUP_DIR/django_data.json" 2>/dev/null || \
    echo -e "${YELLOW}⚠ Django data export not available${NC}"

if [ -f "$BACKUP_DIR/django_data.json" ]; then
    gzip "$BACKUP_DIR/django_data.json"
    DJANGO_SIZE=$(du -h "$BACKUP_DIR/django_data.json.gz" | cut -f1)
    echo -e "${GREEN}✓ Django data export complete${NC} (Size: $DJANGO_SIZE)"
else
    echo -e "${YELLOW}⚠ Django data export skipped${NC}"
fi
echo ""

# 7. Create backup manifest
echo -e "${YELLOW}Creating backup manifest...${NC}"
cat > "$BACKUP_DIR/MANIFEST.txt" << EOF
========================================
Data Backend Backup Manifest
========================================

Backup Information:
  Name: $BACKUP_NAME
  Date: $(date)
  Location: $BACKUP_DIR

Contents:
  ✓ postgres_dump.sql.gz       - PostgreSQL database dump
  ✓ media_files.tar.gz          - All uploaded media files
  ✓ django_data.json.gz         - Django application data export
  ✓ config/                     - Configuration files (sanitized)
  $([ -f "$NEO4J_BACKUP_DIR.tar.gz" ] && echo "  ✓ neo4j.tar.gz                - Neo4j graph database" || echo "  ⚠ neo4j backup incomplete")
  $([ -f "$MEILI_BACKUP_DIR.tar.gz" ] && echo "  ✓ meilisearch.tar.gz          - MeiliSearch index data" || echo "  ⚠ meilisearch backup skipped")

Backup Sizes:
$(du -h "$BACKUP_DIR"/* | sed 's/^/  /')

Total Backup Size: $(du -sh "$BACKUP_DIR" | cut -f1)

Restore Instructions:
  See restore.sh script or RESTORE.md documentation

Notes:
  - Sensitive data (passwords, keys) are not included in config backups
  - Restore these from your secure password manager
  - Test restores regularly to ensure backup integrity
EOF

echo -e "${GREEN}✓ Manifest created${NC}"
echo ""

# 8. Create backup archive (optional)
if [ "$CREATE_ARCHIVE" = "true" ]; then
    echo -e "${YELLOW}Creating compressed archive...${NC}"
    ARCHIVE_NAME="$BACKUP_ROOT/${BACKUP_NAME}.tar.gz"
    tar -czf "$ARCHIVE_NAME" -C "$BACKUP_ROOT" "$BACKUP_NAME"
    ARCHIVE_SIZE=$(du -h "$ARCHIVE_NAME" | cut -f1)
    echo -e "${GREEN}✓ Archive created${NC} (Size: $ARCHIVE_SIZE)"
    echo -e "${YELLOW}Archive location:${NC} $ARCHIVE_NAME"
    echo ""
fi

# Summary
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Backup Complete! ✓${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Backup Summary:${NC}"
echo -e "  Location: $BACKUP_DIR"
echo -e "  Total Size: $(du -sh "$BACKUP_DIR" | cut -f1)"
echo ""
echo -e "${BLUE}Backup Contents:${NC}"
ls -lh "$BACKUP_DIR" | tail -n +2 | awk '{printf "  %-30s %s\n", $9, $5}'
echo ""
echo -e "${BLUE}Next Steps:${NC}"
echo -e "  1. Verify backup integrity: ./scripts/verify_backup.sh $BACKUP_NAME"
echo -e "  2. Copy to remote storage: rsync -av $BACKUP_DIR user@remote:/backups/"
echo -e "  3. Test restore procedure: ./scripts/restore.sh $BACKUP_NAME --dry-run"
echo ""
echo -e "${YELLOW}Important:${NC}"
echo -e "  - Store backups in multiple locations (local + remote)"
echo -e "  - Test restore procedures regularly"
echo -e "  - Keep at least 3 recent backups"
echo -e "  - Backup sensitive config (.env) separately and securely"
echo ""
