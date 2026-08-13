#!/usr/bin/env bash
set -euo pipefail

# Deploy only the devenkalra.com app in production from monorepo root.
#
# Usage:
#   ./scripts/deploy-devenkalra-prod.sh
#   ./scripts/deploy-devenkalra-prod.sh --with-edge
#
# Notes:
# - Run this on the production server from the monorepo root.
# - --with-edge also recreates edge-nginx using the multi-domain config.

WITH_EDGE=0
if [[ "${1:-}" == "--with-edge" ]]; then
  WITH_EDGE=1
fi

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

echo "[deploy] Building and recreating devenkalra-app"
docker compose -p data-backend -f "$PROD_COMPOSE_FILE" up -d --build --force-recreate --no-deps devenkalra-app

echo "[deploy] Current devenkalra-app status"
docker compose -p data-backend -f "$PROD_COMPOSE_FILE" ps devenkalra-app

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
