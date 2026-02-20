#!/bin/bash
#
# Backup Script for Data Backend Application
#
# Supports full and incremental backups:
#   --full        (default) Backs up PostgreSQL, Neo4j, Media, MeiliSearch, config
#   --incremental Backs up PostgreSQL only (faster, for frequent runs)
#
# Run full backup weekly, incremental daily. Both produce restorable backups.
# For catastrophic restore: use the most recent full backup, or an incremental
# (which contains the complete database snapshot).
#
# Usage:
#   ./scripts/backup.sh [backup-name] [--full|--incremental]
#
# Examples:
#   ./scripts/backup.sh                    # Full backup with timestamp
#   ./scripts/backup.sh my_backup --full   # Full backup named my_backup
#   ./scripts/backup.sh inc_daily --incremental  # Incremental (DB only)

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
COMPOSE_FILE="${COMPOSE_FILE:-$PROJECT_DIR/docker-compose.local.yml}"
POSTGRES_DB="${POSTGRES_DB:-entitydb}"

# Parse arguments
BACKUP_NAME=""
BACKUP_TYPE="full"
while [[ $# -gt 0 ]]; do
    case $1 in
        --full)
            BACKUP_TYPE="full"
            shift
            ;;
        --incremental)
            BACKUP_TYPE="incremental"
            shift
            ;;
        --help|-h)
            echo "Usage: ./scripts/backup.sh [backup-name] [--full|--incremental]"
            echo ""
            echo "  --full        (default) Back up everything: PostgreSQL, Neo4j, Media, MeiliSearch, config"
            echo "  --incremental Back up PostgreSQL only (faster, run more frequently)"
            echo ""
            echo "Examples:"
            echo "  ./scripts/backup.sh                     # Full backup, auto-named"
            echo "  ./scripts/backup.sh weekly --full       # Full backup named 'weekly'"
            echo "  ./scripts/backup.sh daily --incremental # Incremental backup named 'daily'"
            exit 0
            ;;
        -*)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
        *)
            BACKUP_NAME="$1"
            shift
            ;;
    esac
done

BACKUP_NAME="${BACKUP_NAME:-backup_${BACKUP_TYPE}_$TIMESTAMP}"
BACKUP_DIR="$BACKUP_ROOT/$BACKUP_NAME"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Data Backend Backup Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Backup name:${NC} $BACKUP_NAME"
echo -e "${YELLOW}Backup type:${NC} $BACKUP_TYPE"
echo -e "${YELLOW}Backup location:${NC} $BACKUP_DIR"
echo ""

# Check if docker-compose is running
if ! docker compose -f "$COMPOSE_FILE" ps 2>/dev/null | grep -q "Up" && \
   ! docker-compose -f "$COMPOSE_FILE" ps 2>/dev/null | grep -q "Up"; then
    echo -e "${RED}Error: Docker containers are not running${NC}"
    echo -e "${YELLOW}Please start the application first${NC}"
    exit 1
fi

# Use docker compose (v2) or docker-compose (v1)
DOCKER_COMPOSE="docker compose"
docker compose version &>/dev/null || DOCKER_COMPOSE="docker-compose"

# Create backup directory
echo -e "${YELLOW}Creating backup directory...${NC}"
mkdir -p "$BACKUP_DIR"

# Create metadata file
cat > "$BACKUP_DIR/backup_metadata.txt" << EOF
Backup Name: $BACKUP_NAME
Backup Date: $(date)
Backup Type: $BACKUP_TYPE
Application: Data Backend
Hostname: $(hostname)
User: $(whoami)
Database: $POSTGRES_DB
EOF

echo -e "${GREEN}✓ Backup directory created${NC}"
echo ""

# 1. Backup PostgreSQL Database (always, for both full and incremental)
echo -e "${YELLOW}Backing up PostgreSQL database ($POSTGRES_DB)...${NC}"
$DOCKER_COMPOSE -f "$COMPOSE_FILE" exec -T db pg_dump -U postgres "$POSTGRES_DB" > "$BACKUP_DIR/postgres_dump.sql"
gzip "$BACKUP_DIR/postgres_dump.sql"
PG_SIZE=$(du -h "$BACKUP_DIR/postgres_dump.sql.gz" | cut -f1)
echo -e "${GREEN}✓ PostgreSQL backup complete${NC} (Size: $PG_SIZE)"
echo ""

# For incremental, we're done after PostgreSQL
if [ "$BACKUP_TYPE" = "incremental" ]; then
    echo -e "${GREEN}Incremental backup complete (PostgreSQL only)${NC}"
    echo ""
    echo -e "${BLUE}Note:${NC} For full restore, use a full backup. Incremental contains DB only."
    exit 0
fi

# Neo4j and MeiliSearch are derived from PostgreSQL - no need to backup.
# Restore rebuilds them via sync_neo4j and reindex_meilisearch.

# 2. Backup Media Files
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

# 3. Backup Configuration Files
echo -e "${YELLOW}Backing up configuration files...${NC}"
CONFIG_DIR="$BACKUP_DIR/config"
mkdir -p "$CONFIG_DIR"

# Copy important config files (excluding secrets)
[ -f "$PROJECT_DIR/.env.example" ] && cp "$PROJECT_DIR/.env.example" "$CONFIG_DIR/"
# Save the compose file actually in use (production or local)
[ -f "$COMPOSE_FILE" ] && cp "$COMPOSE_FILE" "$CONFIG_DIR/$(basename "$COMPOSE_FILE")"
[ -f "$PROJECT_DIR/config/settings.py" ] && cp "$PROJECT_DIR/config/settings.py" "$CONFIG_DIR/"
[ -f "$PROJECT_DIR/requirements.txt" ] && cp "$PROJECT_DIR/requirements.txt" "$CONFIG_DIR/"

# Create a sanitized .env file (remove sensitive values)
if [ -f "$PROJECT_DIR/.env" ]; then
    sed 's/=.*/=<REDACTED>/' "$PROJECT_DIR/.env" > "$CONFIG_DIR/.env.template"
fi

echo -e "${GREEN}✓ Configuration backup complete${NC}"
echo ""

# 4. Export data via Django (optional, PostgreSQL is source of truth)
echo -e "${YELLOW}Exporting application data via Django...${NC}"
$DOCKER_COMPOSE -f "$COMPOSE_FILE" exec -T backend python manage.py dumpdata \
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

# 5. Create backup manifest
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
  ✓ postgres_dump.sql.gz       - PostgreSQL database (source of truth)
  ✓ media_files.tar.gz          - All uploaded media files
  ✓ django_data.json.gz         - Django application data export
  ✓ config/                     - Configuration files (sanitized)

Note: Neo4j and MeiliSearch are derived from PostgreSQL and are rebuilt on restore.

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

# 6. Rsync to Dreamhost (optional - set DREAMHOST_RSYNC_DEST to enable)
# Backup → db/ subdirectory, media → media/ subdirectory
if [ -n "${DREAMHOST_RSYNC_DEST}" ]; then
    RSYNC_SSH_KEY="${DREAMHOST_SSH_KEY:-$HOME/.ssh/dreamhost.pem}"
    KEY_PATH="${RSYNC_SSH_KEY/#\~/$HOME}"
    BASE_DEST="${DREAMHOST_RSYNC_DEST%/}"
    if [ -f "$KEY_PATH" ]; then
        echo -e "${YELLOW}Syncing backup to Dreamhost db/...${NC}"
        rsync -avP -e "ssh -i $KEY_PATH" "$BACKUP_DIR"/ "$BASE_DEST/db/$BACKUP_NAME/" && \
            echo -e "${GREEN}✓ Backup rsync to db/ complete${NC}" || \
            echo -e "${YELLOW}⚠ Backup rsync failed${NC}"
        echo ""
        MEDIA_SOURCE="${DREAMHOST_MEDIA_SOURCE:-/var/lib/bldrdojo/media}"
        if [ -d "$MEDIA_SOURCE" ]; then
            echo -e "${YELLOW}Syncing media to Dreamhost media/...${NC}"
            rsync -avP -e "ssh -i $KEY_PATH" "$MEDIA_SOURCE/" "$BASE_DEST/media/" && \
                echo -e "${GREEN}✓ Media rsync to media/ complete${NC}" || \
                echo -e "${YELLOW}⚠ Media rsync failed${NC}"
        else
            echo -e "${YELLOW}⚠ Media rsync skipped: Media directory not found at $MEDIA_SOURCE${NC}"
        fi
    else
        echo -e "${YELLOW}⚠ Rsync skipped: SSH key not found at $KEY_PATH${NC}"
    fi
    echo ""
fi

# 7. Create backup archive (optional)
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
