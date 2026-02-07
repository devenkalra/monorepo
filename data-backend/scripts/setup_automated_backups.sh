#!/bin/bash
#
# Setup Automated Backups
#
# This script sets up automated backups using cron
#
# Usage:
#   ./scripts/setup_automated_backups.sh [schedule]
#
# Schedule options:
#   daily    - Run backup daily at 2 AM
#   hourly   - Run backup every hour
#   custom   - Specify custom cron schedule

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SCRIPT="$SCRIPT_DIR/backup.sh"
SCHEDULE="${1:-daily}"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Setup Automated Backups${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if backup script exists
if [ ! -f "$BACKUP_SCRIPT" ]; then
    echo -e "${RED}Error: Backup script not found: $BACKUP_SCRIPT${NC}"
    exit 1
fi

# Make backup script executable
chmod +x "$BACKUP_SCRIPT"

# Determine cron schedule
case $SCHEDULE in
    daily)
        CRON_SCHEDULE="0 2 * * *"
        DESCRIPTION="Daily at 2:00 AM"
        ;;
    hourly)
        CRON_SCHEDULE="0 * * * *"
        DESCRIPTION="Every hour"
        ;;
    custom)
        echo "Enter custom cron schedule (e.g., '0 2 * * *' for daily at 2 AM):"
        read CRON_SCHEDULE
        DESCRIPTION="Custom: $CRON_SCHEDULE"
        ;;
    *)
        echo -e "${RED}Error: Invalid schedule: $SCHEDULE${NC}"
        echo "Valid options: daily, hourly, custom"
        exit 1
        ;;
esac

# Create cron job
CRON_JOB="$CRON_SCHEDULE $BACKUP_SCRIPT >> $HOME/backups/backup.log 2>&1"
CRON_COMMENT="# Data Backend Automated Backup - $DESCRIPTION"

echo -e "${YELLOW}Setting up cron job...${NC}"
echo -e "  Schedule: $DESCRIPTION"
echo -e "  Command: $BACKUP_SCRIPT"
echo ""

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "$BACKUP_SCRIPT"; then
    echo -e "${YELLOW}Cron job already exists. Updating...${NC}"
    # Remove old job
    crontab -l 2>/dev/null | grep -v "$BACKUP_SCRIPT" | crontab -
fi

# Add new job
(crontab -l 2>/dev/null; echo "$CRON_COMMENT"; echo "$CRON_JOB") | crontab -

echo -e "${GREEN}✓ Automated backup scheduled${NC}"
echo ""

# Show current cron jobs
echo -e "${YELLOW}Current cron jobs:${NC}"
crontab -l | grep -A1 "Data Backend" || echo "  (none)"
echo ""

# Create backup retention script
RETENTION_SCRIPT="$SCRIPT_DIR/cleanup_old_backups.sh"
cat > "$RETENTION_SCRIPT" << 'EOF'
#!/bin/bash
# Cleanup old backups - keep last 7 daily, 4 weekly, 3 monthly

BACKUP_ROOT="${BACKUP_ROOT:-$HOME/backups/data-backend}"
KEEP_DAILY=7
KEEP_WEEKLY=4
KEEP_MONTHLY=3

# Remove backups older than 90 days
find "$BACKUP_ROOT" -maxdepth 1 -type d -name "backup_*" -mtime +90 -exec rm -rf {} \;

# Keep only recent backups
cd "$BACKUP_ROOT" || exit
ls -t | grep "^backup_" | tail -n +$((KEEP_DAILY + 1)) | xargs -r rm -rf

echo "Backup cleanup complete"
EOF

chmod +x "$RETENTION_SCRIPT"

# Add retention to cron (weekly)
RETENTION_CRON="0 3 * * 0 $RETENTION_SCRIPT >> $HOME/backups/cleanup.log 2>&1"
RETENTION_COMMENT="# Data Backend Backup Cleanup - Weekly"

if ! crontab -l 2>/dev/null | grep -q "$RETENTION_SCRIPT"; then
    (crontab -l 2>/dev/null; echo "$RETENTION_COMMENT"; echo "$RETENTION_CRON") | crontab -
    echo -e "${GREEN}✓ Backup cleanup scheduled (weekly)${NC}"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Setup Complete! ✓${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Automated backups configured:${NC}"
echo -e "  Schedule: $DESCRIPTION"
echo -e "  Backup script: $BACKUP_SCRIPT"
echo -e "  Log file: $HOME/backups/backup.log"
echo ""
echo -e "${BLUE}Backup retention:${NC}"
echo -e "  Daily backups: Keep last $KEEP_DAILY"
echo -e "  Cleanup: Weekly on Sunday at 3 AM"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo -e "  1. Test backup manually: $BACKUP_SCRIPT"
echo -e "  2. Monitor logs: tail -f $HOME/backups/backup.log"
echo -e "  3. Set up remote backup sync (see BACKUP.md)"
echo ""
