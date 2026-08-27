#!/usr/bin/env bash
set -euo pipefail

# Deploy only the devenkalra.com app in production from monorepo root.
#
# Usage:
#   ./scripts/deploy-devenkalra-prod.sh
#   ./scripts/deploy-devenkalra-prod.sh --with-edge
#   ./scripts/deploy-devenkalra-prod.sh --index-audio
#
# Notes:
# - Run this on the production server from the monorepo root.
# - --with-edge also recreates edge-nginx using the multi-domain config.
# - Audio indexing walks the NAS mount and can take several minutes. It is
#   opt-in; pass --index-audio only when tracks may have changed.

WITH_EDGE=0
INDEX_AUDIO=0
for arg in "$@"; do
  case "$arg" in
    --with-edge) WITH_EDGE=1 ;;
    --index-audio) INDEX_AUDIO=1 ;;
    -h|--help)
      echo "Usage: $0 [--with-edge] [--index-audio]"
      echo "  --with-edge     Recreate edge-nginx with the multi-domain config"
      echo "  --index-audio   Reindex the NAS audio library (slow; skip on frontend deploys)"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      echo "Usage: $0 [--with-edge] [--index-audio]" >&2
      exit 1
      ;;
  esac
done

PROD_COMPOSE_FILE="docker-compose.production.yml"
EDGE_COMPOSE_FILE="docker-compose.edge.yml"
EDGE_CONF="./scripts/nginx/multi-domain-edge-example.conf"

if [[ ! -f "$PROD_COMPOSE_FILE" ]]; then
  echo "Missing $PROD_COMPOSE_FILE. Run from monorepo root." >&2
  exit 1
fi

if [[ ! -f "devenkalra.com/Dockerfile" ]]; then
  echo "Missing devenkalra.com/Dockerfile. Ensure repo is up to date." >&2
  exit 1
fi

echo "[deploy] Pulling latest changes"
git pull --ff-only

DB_FILE="devenkalra.com/backend/db.sqlite3"
if [[ ! -f "$DB_FILE" ]]; then
  echo "[deploy] REFUSING TO DEPLOY: $DB_FILE is missing or not a file." >&2
  echo "[deploy] Compose would create an empty database. Restore sqlite first." >&2
  exit 1
fi
if [[ -d "$DB_FILE" ]]; then
  echo "[deploy] REFUSING TO DEPLOY: $DB_FILE is a directory (broken bind mount)." >&2
  exit 1
fi
STAMP=$(date +%Y%m%d%H%M%S)
BACKUP_FILE="${DB_FILE}.bak-${STAMP}"
echo "[deploy] Backing up SQLite ($(du -h "$DB_FILE" | cut -f1)) to $BACKUP_FILE"
cp -a "$DB_FILE" "$BACKUP_FILE"

COMPOSE_FILES=(-f "$PROD_COMPOSE_FILE")
if [[ -f docker-compose.audio.yml ]] && grep -q '^NAS_SMB_USER=.\+' .env 2>/dev/null && grep -q '^NAS_SMB_PASSWORD=.\+' .env 2>/dev/null; then
  COMPOSE_FILES+=(-f docker-compose.audio.yml)
  echo "[deploy] Including docker-compose.audio.yml for the NAS audio mount"
else
  echo "[deploy] NAS_SMB_USER/PASSWORD not set in .env; skipping CIFS overlay"
fi

echo "[deploy] Building and recreating devenkalra-app"
docker compose -p data-backend "${COMPOSE_FILES[@]}" up -d --build --force-recreate --no-deps devenkalra-app

echo "[deploy] Current devenkalra-app status"
docker compose -p data-backend "${COMPOSE_FILES[@]}" ps devenkalra-app

echo "[deploy] Seeding Music Library page"
docker compose -p data-backend "${COMPOSE_FILES[@]}" exec -T devenkalra-app python manage.py ensure_music_library_page

if [[ "$INDEX_AUDIO" -eq 1 ]]; then
  if [[ "${COMPOSE_FILES[*]}" == *docker-compose.audio.yml* ]]; then
    echo "[deploy] Indexing audio library"
    docker compose -p data-backend "${COMPOSE_FILES[@]}" exec -T devenkalra-app python manage.py index_audio_library
  else
    echo "[deploy] --index-audio requested but NAS CIFS overlay is not enabled; skipping" >&2
  fi
else
  echo "[deploy] Skipping audio index (pass --index-audio to reindex the NAS library)"
fi

if [[ "$WITH_EDGE" -eq 1 ]]; then
  if [[ ! -f "$EDGE_COMPOSE_FILE" ]]; then
    echo "Missing $EDGE_COMPOSE_FILE. Skipping edge update." >&2
    exit 1
  fi

  echo "[deploy] Recreating edge-nginx with production config"
  EDGE_NGINX_CONF="$EDGE_CONF" docker compose -p edge -f "$EDGE_COMPOSE_FILE" up -d --force-recreate --no-deps edge-nginx

  echo "[deploy] Current edge-nginx status"
  docker compose -p edge -f "$EDGE_COMPOSE_FILE" ps edge-nginx
fi

echo "[deploy] Done"
