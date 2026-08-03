#!/usr/bin/env bash
# Sync vacation_list + asset_manager data from a lister SQLite DB into the
# devenkalra.com database WITHOUT replacing the whole prod db.sqlite3.
#
# Only clears/rewrites tables for vacation_list and asset_manager (plus
# copies asset photos into the mounted media volume). Pages, blog, notes,
# subscriptions, analytics, etc. are left untouched.
#
# Prerequisites:
#   - Code with vacation_list / asset_manager already deployed & migrated
#   - docker compose access to the devenkalra-app service
#
# Examples (run on the production host):
#   ./scripts/sync_devenkalra_lister_data.sh \
#       --source /tmp/lister/db.sqlite3 \
#       --media  /tmp/lister/media
#
# Examples (from your laptop; scp then import on server):
#   ./scripts/sync_devenkalra_lister_data.sh \
#       --source /m/code/lister/db.sqlite3 \
#       --media  /m/code/lister/media \
#       --ssh deploy@your-server
#
# Dry run (show plan only):
#   ./scripts/sync_devenkalra_lister_data.sh --source ... --media ... --dry-run

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

print_ok() { echo -e "${GREEN}[ok]${NC} $1"; }
print_info() { echo -e "${YELLOW}[info]${NC} $1"; }
print_step() { echo -e "${CYAN}[step]${NC} $1"; }
print_err() { echo -e "${RED}[error]${NC} $1"; }

REPO_DIR="${REPO_DIR:-/home/deploy/apps/monorepo}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.production.yml}"
PROJECT="${PROJECT:-data-backend}"
SERVICE="${SERVICE:-devenkalra-app}"
SOURCE=""
MEDIA=""
SSH_HOST=""
DRY_RUN=0
SKIP_CLEAR=0
SEED_PAGES=0

usage() {
  cat <<'EOF'
Usage:
  ./scripts/sync_devenkalra_lister_data.sh --source <lister.sqlite3> --media <lister-media-dir> [options]

Required:
  --source <path>     Path to lister db.sqlite3 (local path; scp'd if --ssh is set)
  --media <path>      Path to lister MEDIA_ROOT (directory that contains ass_photos/)

Options:
  --ssh <user@host>   Copy sources to the server over SSH, then run import there
  --repo-dir <path>   Repo on the server (default: /home/deploy/apps/monorepo)
  --compose-file <f>  Compose file (default: docker-compose.production.yml)
  --project <name>    Compose project name (default: data-backend)
  --service <name>    Service name (default: devenkalra-app)
  --no-clear          Do not wipe existing vac/asset rows (default clears those apps only)
  --seed-pages        Also run add_vacation_asset_pages.py after import
  --dry-run, -n       Print actions only
  --help, -h          Show help

What this does NOT do:
  - Replace devenkalra.com/backend/db.sqlite3
  - Touch core / blog / notes / auth / analytics tables
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source) SOURCE="$2"; shift 2 ;;
    --media) MEDIA="$2"; shift 2 ;;
    --ssh) SSH_HOST="$2"; shift 2 ;;
    --repo-dir) REPO_DIR="$2"; shift 2 ;;
    --compose-file) COMPOSE_FILE="$2"; shift 2 ;;
    --project) PROJECT="$2"; shift 2 ;;
    --service) SERVICE="$2"; shift 2 ;;
    --no-clear) SKIP_CLEAR=1; shift ;;
    --seed-pages) SEED_PAGES=1; shift ;;
    --dry-run|-n) DRY_RUN=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) print_err "Unknown arg: $1"; usage; exit 1 ;;
  esac
done

if [[ -z "$SOURCE" || -z "$MEDIA" ]]; then
  print_err "--source and --media are required"
  usage
  exit 1
fi

if [[ ! -f "$SOURCE" ]]; then
  print_err "Source DB not found: $SOURCE"
  exit 1
fi
if [[ ! -d "$MEDIA" ]]; then
  print_err "Media directory not found: $MEDIA"
  exit 1
fi

IMPORT_REL="devenkalra.com/backend/_import"
REMOTE_IMPORT="$REPO_DIR/$IMPORT_REL"
CLEAR_FLAG="--clear"
if [[ "$SKIP_CLEAR" -eq 1 ]]; then
  CLEAR_FLAG=""
fi

compose() {
  docker compose -f "$COMPOSE_FILE" -p "$PROJECT" "$@"
}

run_import_on_host() {
  local repo="$1"
  print_step "Staging import payload under $repo/$IMPORT_REL"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    print_info "Would mkdir and copy lister.sqlite3 + media → $repo/$IMPORT_REL"
  else
    mkdir -p "$repo/$IMPORT_REL/lister_media"
    cp -f "$SOURCE" "$repo/$IMPORT_REL/lister.sqlite3"
    rm -rf "$repo/$IMPORT_REL/lister_media"
    cp -a "$MEDIA" "$repo/$IMPORT_REL/lister_media"
  fi

  print_step "Copying payload into $SERVICE container"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    print_info "Would: compose cp _import → ${SERVICE}:/app/_import"
  else
    cd "$repo"
    compose exec -T "$SERVICE" mkdir -p /app/_import
    # Prefer compose cp when available; fall back to docker cp via container id
    if compose cp --help >/dev/null 2>&1; then
      compose cp "$IMPORT_REL/lister.sqlite3" "${SERVICE}:/app/_import/lister.sqlite3"
      compose cp "$IMPORT_REL/lister_media" "${SERVICE}:/app/_import/lister_media"
    else
      local cid
      cid="$(compose ps -q "$SERVICE")"
      docker cp "$IMPORT_REL/lister.sqlite3" "${cid}:/app/_import/lister.sqlite3"
      docker cp "$IMPORT_REL/lister_media" "${cid}:/app/_import/lister_media"
    fi
  fi

  print_step "Running scoped import (vacation_list + asset_manager only)"
  local cmd=(
    python scripts/import_lister_data.py
    --source /app/_import/lister.sqlite3
    --media-source /app/_import/lister_media
  )
  if [[ -n "$CLEAR_FLAG" ]]; then
    cmd+=("$CLEAR_FLAG")
  fi

  if [[ "$DRY_RUN" -eq 1 ]]; then
    print_info "Would: compose exec $SERVICE ${cmd[*]}"
  else
    cd "$repo"
    compose exec -T "$SERVICE" "${cmd[@]}"
    print_ok "Import finished"
  fi

  if [[ "$SEED_PAGES" -eq 1 ]]; then
    print_step "Seeding vacation-list / asset-manager CMS pages"
    if [[ "$DRY_RUN" -eq 1 ]]; then
      print_info "Would: compose exec $SERVICE python add_vacation_asset_pages.py"
    else
      cd "$repo"
      compose exec -T "$SERVICE" python add_vacation_asset_pages.py
      print_ok "Pages seeded"
    fi
  fi
}

if [[ -n "$SSH_HOST" ]]; then
  print_step "Uploading lister DB + media to $SSH_HOST:$REMOTE_IMPORT"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    print_info "Would scp $SOURCE and $MEDIA to $SSH_HOST"
    print_info "Would ssh $SSH_HOST and run import in $REPO_DIR"
  else
    ssh "$SSH_HOST" "mkdir -p '$REMOTE_IMPORT'"
    scp "$SOURCE" "$SSH_HOST:$REMOTE_IMPORT/lister.sqlite3"
    ssh "$SSH_HOST" "rm -rf '$REMOTE_IMPORT/lister_media'"
    scp -r "$MEDIA" "$SSH_HOST:$REMOTE_IMPORT/lister_media"

    # Re-run this script on the server using the staged copies
    remote_flags=(
      --source "$REMOTE_IMPORT/lister.sqlite3"
      --media "$REMOTE_IMPORT/lister_media"
      --repo-dir "$REPO_DIR"
      --compose-file "$COMPOSE_FILE"
      --project "$PROJECT"
      --service "$SERVICE"
    )
    if [[ "$SKIP_CLEAR" -eq 1 ]]; then
      remote_flags+=(--no-clear)
    fi
    if [[ "$SEED_PAGES" -eq 1 ]]; then
      remote_flags+=(--seed-pages)
    fi
    # shellcheck disable=SC2029
    ssh "$SSH_HOST" "cd '$REPO_DIR' && ./scripts/sync_devenkalra_lister_data.sh ${remote_flags[*]}"
  fi
  print_ok "Remote sync requested"
  exit 0
fi

# Local / on-server mode
if [[ ! -d "$REPO_DIR" ]]; then
  # Allow running from repo checkout when REPO_DIR default doesn't exist
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  CANDIDATE="$(cd "$SCRIPT_DIR/.." && pwd)"
  if [[ -f "$CANDIDATE/$COMPOSE_FILE" ]]; then
    REPO_DIR="$CANDIDATE"
    print_info "Using repo dir: $REPO_DIR"
  else
    print_err "Repo dir not found: $REPO_DIR (set --repo-dir)"
    exit 1
  fi
fi

run_import_on_host "$REPO_DIR"
print_ok "Prod DB updated for vacation_list + asset_manager only"
