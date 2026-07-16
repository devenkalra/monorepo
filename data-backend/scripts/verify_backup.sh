#!/bin/bash
#
# Backup Verification Script
#
# Verifies the integrity and completeness of a backup
#
# Usage:
#   ./scripts/verify_backup.sh <backup-name>

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

BACKUP_ROOT="${BACKUP_ROOT:-$HOME/backups/data-backend}"
BACKUP_NAME="$1"

if [ -z "$BACKUP_NAME" ]; then
    echo -e "${RED}Error: Backup name required${NC}"
    echo "Usage: ./scripts/verify_backup.sh <backup-name>"
    exit 1
fi

BACKUP_DIR="$BACKUP_ROOT/$BACKUP_NAME"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Backup Verification${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Verifying backup:${NC} $BACKUP_NAME"
echo ""

if [ ! -d "$BACKUP_DIR" ]; then
    echo -e "${RED}✗ Backup directory not found${NC}"
    exit 1
fi

ERRORS=0
WARNINGS=0

# Check required files
echo -e "${YELLOW}Checking required files...${NC}"

if [ -f "$BACKUP_DIR/postgres_dump.sql.gz" ]; then
    echo -e "${GREEN}✓${NC} postgres_dump.sql.gz found"
    
    # Verify gzip integrity
    if gunzip -t "$BACKUP_DIR/postgres_dump.sql.gz" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} PostgreSQL dump is valid gzip"
    else
        echo -e "${RED}✗${NC} PostgreSQL dump is corrupted"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo -e "${RED}✗${NC} postgres_dump.sql.gz missing"
    ERRORS=$((ERRORS + 1))
fi

if [ -f "$BACKUP_DIR/media_files.tar.gz" ]; then
    echo -e "${GREEN}✓${NC} media_files.tar.gz found"
    
    # Verify tar integrity
    if tar -tzf "$BACKUP_DIR/media_files.tar.gz" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Media archive is valid"
        FILE_COUNT=$(tar -tzf "$BACKUP_DIR/media_files.tar.gz" | wc -l)
        echo -e "  Files in archive: $FILE_COUNT"
    else
        echo -e "${RED}✗${NC} Media archive is corrupted"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo -e "${YELLOW}⚠${NC} media_files.tar.gz missing (may be empty)"
    WARNINGS=$((WARNINGS + 1))
fi

if [ -f "$BACKUP_DIR/MANIFEST.txt" ]; then
    echo -e "${GREEN}✓${NC} MANIFEST.txt found"
else
    echo -e "${YELLOW}⚠${NC} MANIFEST.txt missing"
    WARNINGS=$((WARNINGS + 1))
fi

echo ""

# Check backup size
echo -e "${YELLOW}Checking backup size...${NC}"
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
echo -e "  Total size: $TOTAL_SIZE"

# Warn if backup is suspiciously small
SIZE_BYTES=$(du -sb "$BACKUP_DIR" | cut -f1)
if [ "$SIZE_BYTES" -lt 1048576 ]; then  # Less than 1MB
    echo -e "${YELLOW}⚠${NC} Backup seems very small (< 1MB)"
    WARNINGS=$((WARNINGS + 1))
fi

echo ""

# Summary
echo -e "${BLUE}========================================${NC}"
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}  Backup Verification Passed ✓${NC}"
else
    echo -e "${RED}  Backup Verification Failed ✗${NC}"
fi
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "Errors: $ERRORS"
echo -e "Warnings: $WARNINGS"
echo ""

if [ $ERRORS -gt 0 ]; then
    echo -e "${RED}This backup may not be usable for restore!${NC}"
    exit 1
elif [ $WARNINGS -gt 0 ]; then
    echo -e "${YELLOW}This backup has warnings but should be usable.${NC}"
    exit 0
else
    echo -e "${GREEN}This backup appears to be complete and valid.${NC}"
    exit 0
fi
