#!/usr/bin/env bash
set -euo pipefail

# Backup devenkalra.com SQLite + media. Safe to run while the app is up.
#
# Usage (from monorepo root, or via absolute path from cron):
#   ./scripts/backup-devenkalra.sh
#   ./scripts/backup-devenkalra.sh nightly
#   KEEP_DAYS=30 ./scripts/backup-devenkalra.sh
#
# Cron (daily 3:15 AM on the production host):
#   15 3 * * * /path/to/monorepo/scripts/backup-devenkalra.sh >> /home/deven/backups/devenkalra/backup.log 2>&1
#
# Restore (stop the app first so SQLite is not rewritten):
#   docker compose -p data-backend -f docker-compose.production.yml stop devenkalra-app
#   gunzip -c "$BACKUP_DIR/db.sqlite3.gz" > devenkalra.com/backend/db.sqlite3
#   tar -xzf "$BACKUP_DIR/media.tar.gz" -C devenkalra.com/backend
#   docker compose -p data-backend -f docker-compose.production.yml start devenkalra-app

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DB_FILE="${DB_FILE:-$REPO_ROOT/devenkalra.com/backend/db.sqlite3}"
MEDIA_DIR="${MEDIA_DIR:-$REPO_ROOT/devenkalra.com/backend/media}"
BACKUP_ROOT="${BACKUP_ROOT:-$HOME/backups/devenkalra}"
KEEP_DAYS="${KEEP_DAYS:-14}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_NAME="${1:-backup_$TIMESTAMP}"
BACKUP_DIR="$BACKUP_ROOT/$BACKUP_NAME"

log() { echo "[backup-devenkalra] $*"; }
die() { echo "[backup-devenkalra] ERROR: $*" >&2; exit 1; }

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  sed -n '2,18p' "$0"
  exit 0
fi

cd "$REPO_ROOT"

if [[ ! -f "$DB_FILE" ]]; then
  die "SQLite file not found: $DB_FILE"
fi
if [[ -d "$DB_FILE" ]]; then
  die "SQLite path is a directory (broken bind mount): $DB_FILE"
fi

mkdir -p "$BACKUP_DIR"
log "Backup name: $BACKUP_NAME"
log "Location:    $BACKUP_DIR"

copy_sqlite() {
  local dest="$1"
  if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "$DB_FILE" ".backup '$dest'"
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    python3 - "$DB_FILE" "$dest" <<'PY'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1])
try:
    src.execute('PRAGMA busy_timeout=5000')
    dst = sqlite3.connect(sys.argv[2])
    with dst:
        src.backup(dst)
    dst.close()
finally:
    src.close()
PY
    return
  fi
  log "sqlite3/python3 not found; using cp (less safe if the DB is mid-write)"
  cp -a "$DB_FILE" "$dest"
  [[ -f "${DB_FILE}-wal" ]] && cp -a "${DB_FILE}-wal" "${dest}-wal"
  [[ -f "${DB_FILE}-shm" ]] && cp -a "${DB_FILE}-shm" "${dest}-shm"
}

log "Copying SQLite ($(du -h "$DB_FILE" | cut -f1))"
copy_sqlite "$BACKUP_DIR/db.sqlite3"
gzip -f "$BACKUP_DIR/db.sqlite3"
for extra in "$BACKUP_DIR/db.sqlite3-wal" "$BACKUP_DIR/db.sqlite3-shm"; do
  [[ -f "$extra" ]] && gzip -f "$extra"
done
if [[ ! -s "$BACKUP_DIR/db.sqlite3.gz" ]]; then
  die "SQLite backup is empty: $BACKUP_DIR/db.sqlite3.gz"
fi
log "SQLite: $(du -h "$BACKUP_DIR/db.sqlite3.gz" | cut -f1)"

if [[ -d "$MEDIA_DIR" ]]; then
  log "Archiving media"
  tar -czf "$BACKUP_DIR/media.tar.gz" -C "$(dirname "$MEDIA_DIR")" "$(basename "$MEDIA_DIR")"
  log "Media: $(du -h "$BACKUP_DIR/media.tar.gz" | cut -f1) ($(find "$MEDIA_DIR" -type f | wc -l) files)"
else
  log "No media directory at $MEDIA_DIR"
fi

cat > "$BACKUP_DIR/backup_metadata.txt" <<EOF
Backup Name: $BACKUP_NAME
Backup Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Hostname: $(hostname)
User: $(whoami)
Repo: $REPO_ROOT
SQLite: $DB_FILE
Media: $MEDIA_DIR
EOF

if [[ "${KEEP_DAYS}" =~ ^[0-9]+$ ]] && [[ "$KEEP_DAYS" -gt 0 ]]; then
  log "Pruning backups older than ${KEEP_DAYS} days"
  find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -name 'backup_*' -mtime "+${KEEP_DAYS}" -print -exec rm -rf {} +
fi

log "Done. Total: $(du -sh "$BACKUP_DIR" | cut -f1)"
log "Restore: gunzip -c $BACKUP_DIR/db.sqlite3.gz > $DB_FILE"
