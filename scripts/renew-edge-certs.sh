#!/usr/bin/env bash
set -euo pipefail

# Renew Let's Encrypt certs for edge-nginx and reload the proxy.
#
# Intended for the production host. Stops edge-nginx so certbot standalone
# can bind port 80, copies the Let's Encrypt tree into ssl-edge/, then
# starts edge-nginx and reloads nginx.
#
# Usage (from anywhere):
#   ./scripts/renew-edge-certs.sh
#   ./scripts/renew-edge-certs.sh --force
#   ./scripts/renew-edge-certs.sh --dry-run
#
# Cron (as root, every 3 months on the 1st at 04:00):
#   0 4 1 */3 * /home/deploy/apps/monorepo/scripts/renew-edge-certs.sh >> /home/deploy/apps/monorepo/logs/edge-nginx/renew-certs.log 2>&1
#
# Prefer monthly if you can: certbot only renews when a cert is near expiry.
#   0 4 1 * * /home/deploy/apps/monorepo/scripts/renew-edge-certs.sh >> /home/deploy/apps/monorepo/logs/edge-nginx/renew-certs.log 2>&1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
EDGE_COMPOSE="$REPO_DIR/docker-compose.edge.yml"
EDGE_CONF="$REPO_DIR/scripts/nginx/multi-domain-edge-example.conf"
SSL_EDGE="$REPO_DIR/ssl-edge"
LOG_DIR="$REPO_DIR/logs/edge-nginx"
LE_SRC="/etc/letsencrypt"
EDGE_NETWORK="bldrdojo-local-backend-network"

FORCE=0
DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      echo "Usage: $0 [--force] [--dry-run]"
      echo "  --force    Renew even if certbot thinks the cert is still fresh"
      echo "  --dry-run  Ask certbot to rehearse; still stops edge-nginx for port 80"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      echo "Usage: $0 [--force] [--dry-run]" >&2
      exit 1
      ;;
  esac
done

log() {
  echo "[renew-edge-certs $(date -Is)] $*"
}

run_root() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

need docker
need rsync
if [[ "$(id -u)" -eq 0 ]]; then
  need certbot
else
  command -v sudo >/dev/null 2>&1 || {
    echo "Run as root, or install sudo so this script can call certbot." >&2
    exit 1
  }
fi

if [[ ! -f "$EDGE_COMPOSE" ]]; then
  echo "Missing $EDGE_COMPOSE" >&2
  exit 1
fi

mkdir -p "$LOG_DIR" "$SSL_EDGE"

edge_exists() {
  docker ps -a --format '{{.Names}}' | grep -qx edge-nginx
}

edge_running() {
  docker ps --format '{{.Names}}' | grep -qx edge-nginx
}

WAS_RUNNING=0
if edge_running; then
  WAS_RUNNING=1
  log "Stopping edge-nginx so certbot can bind :80"
  docker stop edge-nginx
fi

CERTBOT_ARGS=(renew)
if [[ "$FORCE" -eq 1 ]]; then
  CERTBOT_ARGS+=(--force-renewal)
fi
if [[ "$DRY_RUN" -eq 1 ]]; then
  CERTBOT_ARGS+=(--dry-run)
fi

log "Running certbot ${CERTBOT_ARGS[*]}"
set +e
run_root certbot "${CERTBOT_ARGS[@]}"
CERTBOT_RC=$?
set -e

if [[ "$CERTBOT_RC" -ne 0 ]]; then
  log "certbot failed (exit $CERTBOT_RC)"
else
  log "certbot finished"
fi

if [[ "$DRY_RUN" -eq 0 && -d "$LE_SRC/live" ]]; then
  log "Copying $LE_SRC into $SSL_EDGE"
  run_root rsync -a "$LE_SRC/live" "$LE_SRC/archive" "$LE_SRC/renewal" "$SSL_EDGE/"
  if [[ "$(id -u)" -eq 0 && -n "${SUDO_USER:-}" ]]; then
    chown -R "$SUDO_USER:" "$SSL_EDGE" || true
  elif [[ "$(id -u)" -eq 0 ]]; then
    chown -R deploy:deploy "$SSL_EDGE" 2>/dev/null || true
  fi
elif [[ "$DRY_RUN" -eq 1 ]]; then
  log "Dry run: skipped copying certs into ssl-edge"
fi

if ! docker network inspect "$EDGE_NETWORK" >/dev/null 2>&1; then
  log "Creating missing Docker network $EDGE_NETWORK"
  docker network create "$EDGE_NETWORK"
fi

if edge_exists; then
  log "Starting edge-nginx"
  docker start edge-nginx
else
  log "Creating edge-nginx"
  EDGE_NGINX_CONF="$EDGE_CONF" docker compose -p edge -f "$EDGE_COMPOSE" up -d edge-nginx
fi

# Give nginx a moment after start before reload.
sleep 2
if edge_running; then
  if docker exec edge-nginx nginx -t; then
    docker exec edge-nginx nginx -s reload
    log "Reloaded edge-nginx"
  else
    log "nginx -t failed; container is up but config/certs look wrong"
    exit 1
  fi
else
  log "edge-nginx is not running"
  docker logs --tail=80 edge-nginx || true
  exit 1
fi

if [[ "$CERTBOT_RC" -ne 0 ]]; then
  exit "$CERTBOT_RC"
fi

log "Done"
if [[ "$WAS_RUNNING" -eq 0 ]]; then
  log "edge-nginx was not running when this script started; it is running now"
fi
