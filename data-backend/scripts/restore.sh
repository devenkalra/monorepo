#!/bin/bash
#
# Restore Script for Data Backend Application
#
# This script restores:
# - PostgreSQL database
# - Neo4j graph database
# - Media files (photos, attachments, thumbnails)
# - MeiliSearch index data
#
# Usage:
#   ./scripts/restore.sh <backup-name> [options]
#
# Options:
#   --dry-run          Show what would be restored without doing it
#   --db-only          Restore only the database
#   --media-only       Restore only media files
#   --skip-neo4j       Skip Neo4j restoration
#   --skip-meilisearch Skip MeiliSearch restoration

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
COMPOSE_FILE="$PROJECT_DIR/docker-compose.local.yml"

# Parse arguments
BACKUP_NAME="$1"
DRY_RUN=false
DB_ONLY=false
MEDIA_ONLY=false
SKIP_NEO4J=false
SKIP_MEILISEARCH=false

shift || true
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --db-only)
            DB_ONLY=true
            shift
            ;;
        --media-only)
            MEDIA_ONLY=true
            shift
            ;;
        --skip-neo4j)
            SKIP_NEO4J=true
            shift
            ;;
        --skip-meilisearch)
            SKIP_MEILISEARCH=true
            shift
            ;;
        --help|-h)
            echo "Usage: ./scripts/restore.sh <backup-name> [options]"
            echo ""
            echo "Options:"
            echo "  --dry-run          Show what would be restored without doing it"
            echo "  --db-only          Restore only the database"
            echo "  --media-only       Restore only media files"
            echo "  --skip-neo4j       Skip Neo4j restoration"
            echo "  --skip-meilisearch Skip MeiliSearch restoration"
            echo "  -h, --help         Show this help message"
            echo ""
            echo "Examples:"
            echo "  ./scripts/restore.sh backup_20260201_120000"
            echo "  ./scripts/restore.sh backup_20260201_120000 --dry-run"
            echo "  ./scripts/restore.sh backup_20260201_120000 --db-only"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

if [ -z "$BACKUP_NAME" ]; then
    echo -e "${RED}Error: Backup name required${NC}"
    echo "Usage: ./scripts/restore.sh <backup-name>"
    echo ""
    echo "Available backups:"
    ls -1 "$BACKUP_ROOT" 2>/dev/null | grep -v ".tar.gz" || echo "  (none found)"
    exit 1
fi

BACKUP_DIR="$BACKUP_ROOT/$BACKUP_NAME"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Data Backend Restore Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Backup name:${NC} $BACKUP_NAME"
echo -e "${YELLOW}Backup location:${NC} $BACKUP_DIR"
if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}Mode:${NC} DRY RUN (no changes will be made)"
fi
echo ""

# Check if backup exists
if [ ! -d "$BACKUP_DIR" ]; then
    echo -e "${RED}Error: Backup directory not found: $BACKUP_DIR${NC}"
    echo ""
    echo "Available backups:"
    ls -1 "$BACKUP_ROOT" 2>/dev/null | grep -v ".tar.gz" || echo "  (none found)"
    exit 1
fi

# Show backup contents
echo -e "${YELLOW}Backup contents:${NC}"
ls -lh "$BACKUP_DIR" | tail -n +2 | awk '{printf "  %-30s %s\n", $9, $5}'
echo ""

# Show manifest if available
if [ -f "$BACKUP_DIR/MANIFEST.txt" ]; then
    echo -e "${YELLOW}Backup manifest:${NC}"
    head -20 "$BACKUP_DIR/MANIFEST.txt" | sed 's/^/  /'
    echo ""
fi

# Confirmation prompt
if [ "$DRY_RUN" = false ]; then
    echo -e "${RED}WARNING: This will overwrite existing data!${NC}"
    echo -e "${YELLOW}Make sure you have a current backup before proceeding.${NC}"
    echo ""
    read -p "Are you sure you want to restore from this backup? (yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        echo "Restore cancelled."
        exit 0
    fi
    echo ""
fi

# Check if docker-compose is running
if ! docker-compose -f "$COMPOSE_FILE" ps | grep -q "Up"; then
    echo -e "${YELLOW}Docker containers are not running. Starting them...${NC}"
    if [ "$DRY_RUN" = false ]; then
        docker-compose -f "$COMPOSE_FILE" up -d
        echo "Waiting for services to be ready..."
        sleep 10
    fi
    echo -e "${GREEN}✓ Services started${NC}"
    echo ""
fi

# 1. Restore PostgreSQL Database
if [ "$MEDIA_ONLY" = false ] && [ -f "$BACKUP_DIR/postgres_dump.sql.gz" ]; then
    echo -e "${YELLOW}Restoring PostgreSQL database...${NC}"
    
    if [ "$DRY_RUN" = true ]; then
        echo "  [DRY RUN] Would restore postgres_dump.sql.gz"
    else
        # Drop existing connections
        docker-compose -f "$COMPOSE_FILE" exec -T db psql -U postgres -c \
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='postgres' AND pid <> pg_backend_pid();" \
            2>/dev/null || true
        
        # Drop and recreate database
        docker-compose -f "$COMPOSE_FILE" exec -T db psql -U postgres -c "DROP DATABASE IF EXISTS postgres_backup;" 2>/dev/null || true
        docker-compose -f "$COMPOSE_FILE" exec -T db psql -U postgres -c "CREATE DATABASE postgres_backup;" 2>/dev/null || true
        
        # Restore from backup
        gunzip -c "$BACKUP_DIR/postgres_dump.sql.gz" | \
            docker-compose -f "$COMPOSE_FILE" exec -T db psql -U postgres postgres_backup
        
        # Swap databases
        docker-compose -f "$COMPOSE_FILE" exec -T db psql -U postgres -c \
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='postgres' AND pid <> pg_backend_pid();" \
            2>/dev/null || true
        docker-compose -f "$COMPOSE_FILE" exec -T db psql -U postgres -c "DROP DATABASE postgres;" 2>/dev/null || true
        docker-compose -f "$COMPOSE_FILE" exec -T db psql -U postgres -c "ALTER DATABASE postgres_backup RENAME TO postgres;" 2>/dev/null || true
        
        echo -e "${GREEN}✓ PostgreSQL database restored${NC}"
    fi
    echo ""
fi

# 2. Restore Neo4j Database
if [ "$MEDIA_ONLY" = false ] && [ "$SKIP_NEO4J" = false ] && [ -f "$BACKUP_DIR/neo4j.tar.gz" ]; then
    echo -e "${YELLOW}Restoring Neo4j database...${NC}"
    
    if [ "$DRY_RUN" = true ]; then
        echo "  [DRY RUN] Would restore neo4j.tar.gz"
    else
        # Stop Neo4j
        docker-compose -f "$COMPOSE_FILE" stop neo4j
        
        # Extract backup
        NEO4J_TMP="/tmp/neo4j_restore_$$"
        mkdir -p "$NEO4J_TMP"
        tar -xzf "$BACKUP_DIR/neo4j.tar.gz" -C "$NEO4J_TMP"
        
        # Copy to container
        NEO4J_CONTAINER=$(docker-compose -f "$COMPOSE_FILE" ps -q neo4j)
        if [ -n "$NEO4J_CONTAINER" ]; then
            docker cp "$NEO4J_TMP/data" "$NEO4J_CONTAINER:/var/lib/neo4j/"
            echo -e "${GREEN}✓ Neo4j data copied${NC}"
        fi
        
        # Cleanup
        rm -rf "$NEO4J_TMP"
        
        # Restart Neo4j
        docker-compose -f "$COMPOSE_FILE" start neo4j
        echo "Waiting for Neo4j to start..."
        sleep 10
        
        echo -e "${GREEN}✓ Neo4j database restored${NC}"
    fi
    echo ""
fi

# 3. Restore Media Files
if [ "$DB_ONLY" = false ] && [ -f "$BACKUP_DIR/media_files.tar.gz" ]; then
    echo -e "${YELLOW}Restoring media files...${NC}"
    
    if [ "$DRY_RUN" = true ]; then
        echo "  [DRY RUN] Would restore media_files.tar.gz"
        tar -tzf "$BACKUP_DIR/media_files.tar.gz" | head -10 | sed 's/^/    /'
        FILE_COUNT=$(tar -tzf "$BACKUP_DIR/media_files.tar.gz" | wc -l)
        echo "    ... and $(($FILE_COUNT - 10)) more files"
    else
        # Backup existing media
        if [ -d "$PROJECT_DIR/media" ]; then
            MEDIA_BACKUP="$PROJECT_DIR/media.backup.$(date +%Y%m%d_%H%M%S)"
            mv "$PROJECT_DIR/media" "$MEDIA_BACKUP"
            echo "  Existing media backed up to: $MEDIA_BACKUP"
        fi
        
        # Extract media files
        tar -xzf "$BACKUP_DIR/media_files.tar.gz" -C "$PROJECT_DIR"
        
        FILE_COUNT=$(find "$PROJECT_DIR/media" -type f | wc -l)
        echo -e "${GREEN}✓ Media files restored${NC} ($FILE_COUNT files)"
    fi
    echo ""
fi

# 4. Restore MeiliSearch Data
if [ "$MEDIA_ONLY" = false ] && [ "$SKIP_MEILISEARCH" = false ] && [ -f "$BACKUP_DIR/meilisearch.tar.gz" ]; then
    echo -e "${YELLOW}Restoring MeiliSearch data...${NC}"
    
    if [ "$DRY_RUN" = true ]; then
        echo "  [DRY RUN] Would restore meilisearch.tar.gz"
    else
        # Extract dump
        MEILI_TMP="/tmp/meili_restore_$$"
        mkdir -p "$MEILI_TMP"
        tar -xzf "$BACKUP_DIR/meilisearch.tar.gz" -C "$MEILI_TMP"
        
        # Copy to container
        MEILI_CONTAINER=$(docker-compose -f "$COMPOSE_FILE" ps -q meilisearch)
        if [ -n "$MEILI_CONTAINER" ] && [ -d "$MEILI_TMP/dumps" ]; then
            docker cp "$MEILI_TMP/dumps" "$MEILI_CONTAINER:/meili_data/"
            
            # Get the latest dump file
            DUMP_FILE=$(ls -t "$MEILI_TMP/dumps"/*.dump 2>/dev/null | head -1 | xargs basename)
            
            if [ -n "$DUMP_FILE" ]; then
                # Import via API
                MEILI_URL="http://localhost:7701"
                MEILI_KEY=$(grep MEILI_MASTER_KEY "$PROJECT_DIR/.env" 2>/dev/null | cut -d= -f2 || echo "masterKey")
                
                curl -X POST "$MEILI_URL/dumps/$DUMP_FILE/restore" \
                    -H "Authorization: Bearer $MEILI_KEY" 2>/dev/null || true
                
                echo -e "${GREEN}✓ MeiliSearch data restored${NC}"
            fi
        fi
        
        # Cleanup
        rm -rf "$MEILI_TMP"
    fi
    echo ""
fi

# 5. Restore Django Data (alternative method)
if [ "$MEDIA_ONLY" = false ] && [ -f "$BACKUP_DIR/django_data.json.gz" ]; then
    echo -e "${YELLOW}Django data export available (django_data.json.gz)${NC}"
    echo "  To restore Django data, run:"
    echo "    gunzip -c $BACKUP_DIR/django_data.json.gz | \\"
    echo "      docker-compose -f $COMPOSE_FILE exec -T backend python manage.py loaddata --format=json -"
    echo ""
fi

# 6. Run migrations and sync
if [ "$DRY_RUN" = false ] && [ "$MEDIA_ONLY" = false ]; then
    echo -e "${YELLOW}Running database migrations...${NC}"
    docker-compose -f "$COMPOSE_FILE" exec -T backend python manage.py migrate --noinput 2>/dev/null || \
        echo -e "${YELLOW}⚠ Could not run migrations (run manually if needed)${NC}"
    echo ""
    
    echo -e "${YELLOW}Reindexing MeiliSearch...${NC}"
    docker-compose -f "$COMPOSE_FILE" exec -T backend python manage.py shell << 'EOF' 2>/dev/null || true
from people.sync import sync_all_to_meilisearch
sync_all_to_meilisearch()
print("Reindexing complete")
EOF
    echo -e "${GREEN}✓ Reindexing complete${NC}"
    echo ""
fi

# Summary
if [ "$DRY_RUN" = true ]; then
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  Dry Run Complete${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    echo -e "${YELLOW}No changes were made. Run without --dry-run to perform actual restore.${NC}"
else
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  Restore Complete! ✓${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "${BLUE}Restored from:${NC} $BACKUP_DIR"
    echo ""
    echo -e "${BLUE}Next Steps:${NC}"
    echo -e "  1. Verify application is working: http://localhost:5173"
    echo -e "  2. Check data integrity: ./scripts/verify_data.sh"
    echo -e "  3. Review logs: docker-compose -f $COMPOSE_FILE logs"
    echo ""
    echo -e "${YELLOW}Important:${NC}"
    echo -e "  - Restore sensitive config (.env) manually from secure storage"
    echo -e "  - Update any environment-specific settings"
    echo -e "  - Test critical functionality before using in production"
fi
echo ""
