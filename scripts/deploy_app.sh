#!/usr/bin/env bash
# Targeted production deployment for monorepo apps.
#
# This script fetches origin/<branch>, fast-forwards HEAD when the selected
# app has remote changes, and recreates only the corresponding Docker services.
#
# (Older versions used `git restore --worktree` without moving HEAD, which left
# the restored files looking "modified" and forced a stash before every deploy.)
#
# Examples:
#   ./scripts/deploy_app.sh --app bldrdojo
#   ./scripts/deploy_app.sh --app devenkalra
#   ./scripts/deploy_app.sh --app bldrdojo --app devenkalra
#   ./scripts/deploy_app.sh --app all --dry-run
#   ./scripts/deploy_app.sh --app devenkalra --with-edge
#
# Expected:
# - Repo exists on server (default: /home/deploy/apps/monorepo)
# - Run from anywhere; script will cd into REPO_DIR
# - docker compose + git installed

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

usage() {
  cat <<'EOF'
Usage:
  ./scripts/deploy_app.sh --app <name> [--app <name> ...] [options]

Apps:
  bldrdojo
  devenkalra
  all

Options:
  --app <name>         App to deploy (repeatable). Use 'all' for all apps.
  --branch <name>      Git branch to deploy (default: main)
  --repo-dir <path>    Repo path on server (default: /home/deploy/apps/monorepo)
  --compose-file <f>   Compose file relative to repo root (default: docker-compose.production.yml)
  --project <name>     Compose project name (default: data-backend)
  --with-edge          Recreate edge-nginx (devenkalra only)
  --edge-compose <f>   Edge compose file (default: docker-compose.edge.yml)
  --edge-conf <path>   Edge nginx conf passed via EDGE_NGINX_CONF
  --discard-local      Discard local changes in app paths that would be
                       overwritten by this deploy (default: on for those files)
  --keep-local         Refuse to deploy if app-path files have local changes
  --dry-run, -n        Show actions, do not change files/containers
  --help, -h           Show help

Environment:
  REPO_DIR             Same as --repo-dir
  BRANCH               Same as --branch

How to add a new app:
  Edit app_paths() and app_services() in this script, then add any post-deploy steps
  in deploy_one_app().
EOF
}

contains() {
  local needle="$1"
  shift
  local item
  for item in "$@"; do
    [[ "$item" == "$needle" ]] && return 0
  done
  return 1
}

append_unique() {
  local value="$1"
  shift
  local -n arr_ref=$1
  local x
  for x in "${arr_ref[@]}"; do
    [[ "$x" == "$value" ]] && return 0
  done
  arr_ref+=("$value")
}

ensure_local_git_excludes() {
  local exclude_file=".git/info/exclude"
  local pattern
  local patterns=(
    ".bash_history"
    ".bash_logout"
    ".bashrc"
    ".docker/"
    ".lesshst"
    ".node_repl_history"
    ".npm/"
    ".profile"
    ".ssh/"
    ".sudo_as_admin_successful"
    ".viminfo"
    "deploy_production.sh"
    "logs/"
    "ssl-edge/"
  )

  [[ -d .git ]] || return 0
  mkdir -p .git/info

  for pattern in "${patterns[@]}"; do
    if ! grep -Fxq "$pattern" "$exclude_file" 2>/dev/null; then
      printf '%s\n' "$pattern" >> "$exclude_file"
    fi
  done
}

app_paths() {
  local app="$1"
  case "$app" in
    bldrdojo)
      cat <<'EOF'
docker-compose.production.yml
data-backend/config
data-backend/people
data-backend/cad
data-backend/food
data-backend/wa_assistant
data-backend/mail_archive
data-backend/gmail_assistant
data-backend/static
data-backend/requirements.txt
data-backend/Dockerfile
data-backend/manage.py
data-backend/docker-compose.yml
frontend
people-frontend
cad-frontend
food-frontend
gmail-frontend
scripts/deploy_app.sh
EOF
      ;;
    devenkalra)
      cat <<'EOF'
docker-compose.production.yml
devenkalra.com
scripts/deploy-devenkalra-prod.sh
scripts/nginx/multi-domain-edge-example.conf
EOF
      ;;
    *)
      return 1
      ;;
  esac
}

app_services() {
  local app="$1"
  case "$app" in
    bldrdojo)
      echo "backend frontend celery-worker celery-beat"
      ;;
    devenkalra)
      echo "devenkalra-app"
      ;;
    *)
      return 1
      ;;
  esac
}

run_cmd() {
  if [[ "$DRY_RUN" == true ]]; then
    echo "[dry-run] $*"
  else
    "$@"
  fi
}

run_shell() {
  local cmd="$1"
  if [[ "$DRY_RUN" == true ]]; then
    echo "[dry-run] $cmd"
  else
    bash -lc "$cmd"
  fi
}

ensure_repo_clean_enough() {
  local status
  status=$(git status --porcelain || true)
  if [[ -n "$status" ]]; then
    print_info "Working tree has local changes outside this deploy. The script will refuse to overwrite changed files inside the selected app paths."
  fi
}

paths_have_local_changes() {
  git diff --quiet -- "${@}" || return 0
  git diff --cached --quiet -- "${@}" || return 0
  return 1
}

list_dirty_paths() {
  # Unique dirty paths (worktree + index) under the given pathspecs.
  {
    git diff --name-only -- "$@" || true
    git diff --cached --name-only -- "$@" || true
  } | awk 'NF && !seen[$0]++'
}

force_reset_paths_to_head() {
  local f
  for f in "$@"; do
    [[ -n "$f" ]] || continue
    git update-index --no-skip-worktree -- "$f" 2>/dev/null || true
    git update-index --no-assume-unchanged -- "$f" 2>/dev/null || true
    if git cat-file -e "HEAD:$f" 2>/dev/null; then
      # Rewrite via object DB — survives sticky worktree / filter oddities better
      # than restore alone on some hosts.
      git cat-file -p "HEAD:$f" >"$f"
      git add -- "$f"
      git reset -q HEAD -- "$f"
    else
      rm -f -- "$f"
      git rm -f --ignore-unmatch -- "$f" >/dev/null 2>&1 || true
    fi
  done
}

discard_overwritten_local_changes() {
  local app="$1"
  shift
  local -a paths=("$@")
  local diff_out="$DIFF_OUT_FOR_DISCARD"
  local -a dirty=()
  local -a to_reset=()
  local f

  while IFS= read -r f; do
    [[ -n "$f" ]] && dirty+=("$f")
  done < <(list_dirty_paths "${paths[@]}")

  if [[ "${#dirty[@]}" -eq 0 ]]; then
    return 0
  fi

  for f in "${dirty[@]}"; do
    if grep -Fxq -- "$f" <<<"$diff_out"; then
      to_reset+=("$f")
    fi
  done

  local -a leftover=()
  for f in "${dirty[@]}"; do
    if ! grep -Fxq -- "$f" <<<"$diff_out"; then
      leftover+=("$f")
    fi
  done

  if [[ "${#to_reset[@]}" -gt 0 ]]; then
    if [[ "$DISCARD_LOCAL" == true ]]; then
      print_info "[$app] Discarding local changes that would be overwritten by deploy:"
      printf '  - %s\n' "${to_reset[@]}"
      if [[ "$DRY_RUN" == true ]]; then
        echo "[dry-run] reset ${#to_reset[@]} path(s) to HEAD"
      else
        force_reset_paths_to_head "${to_reset[@]}"
        if paths_have_local_changes "${to_reset[@]}"; then
          print_info "[$app] Hard reset failed; stashing overwrite candidates instead"
          git stash push -m "deploy_app auto-discard $(date +%Y%m%d%H%M%S)" -- "${to_reset[@]}" || true
        fi
      fi
    else
      print_err "[$app] Local changes exist in files this deploy would overwrite. Re-run with --discard-local, or stash/discard them."
      printf '  - %s\n' "${to_reset[@]}"
      git status --short -- "${to_reset[@]}" || true
      exit 1
    fi
  fi

  if [[ "${#leftover[@]}" -gt 0 ]]; then
    print_err "[$app] Local changes exist in targeted paths (not in incoming revision). Commit, stash, or discard them before deploying."
    printf '  - %s\n' "${leftover[@]}"
    git status --short -- "${leftover[@]}" || true
    print_info "Tip: git stash push -u -m pre-deploy -- <paths>   OR   re-run with only overwrite-safe dirties"
    exit 1
  fi
}

deploy_one_app() {
  local app="$1"
  local paths=()
  local p
  while IFS= read -r p; do
    [[ -n "$p" ]] && paths+=("$p")
  done < <(app_paths "$app")

  if [[ "${#paths[@]}" -eq 0 ]]; then
    print_err "No paths configured for app: $app"
    exit 1
  fi

  local services
  services=$(app_services "$app")
  if [[ -z "$services" ]]; then
    print_err "No services configured for app: $app"
    exit 1
  fi

  print_step "[$app] Checking incoming changes on origin/$BRANCH"
  local diff_out
  diff_out=$(git diff --name-only "HEAD..origin/$BRANCH" -- "${paths[@]}" || true)

  if [[ -z "$diff_out" ]]; then
    print_info "[$app] No remote changes in configured paths; skipping deploy."
    return 0
  fi

  print_info "[$app] Files to update:"
  echo "$diff_out" | sed 's/^/  - /'

  DIFF_OUT_FOR_DISCARD="$diff_out"
  discard_overwritten_local_changes "$app" "${paths[@]}"

  if paths_have_local_changes "${paths[@]}"; then
    print_err "[$app] Local changes still exist in targeted paths after cleanup."
    git status --short -- "${paths[@]}" || true
    print_info "Nuclear option: git stash push -u -m pre-deploy && re-run deploy"
    exit 1
  fi

  # Advance HEAD with a fast-forward merge. Using only
  # `git restore --source origin/<branch> --worktree` leaves HEAD behind origin,
  # so the restored files show as "modified" forever and force a stash before
  # the next deploy. FF-merge keeps the tree clean while we still rebuild only
  # this app's services below.
  print_step "[$app] Fast-forwarding HEAD to origin/$BRANCH (keeps git status clean)"
  if ! run_cmd git merge --ff-only "origin/$BRANCH"; then
    print_err "[$app] Could not fast-forward to origin/$BRANCH."
    print_info "Resolve/commit/stash unrelated local changes, then retry. Avoid stashing the restored app files — that undoes the deploy checkout."
    exit 1
  fi

  if [[ "$app" == "devenkalra" ]]; then
    local db_file="devenkalra.com/backend/db.sqlite3"
    if [[ ! -f "$db_file" ]]; then
      print_err "[$app] REFUSING TO DEPLOY: $db_file is missing or not a file."
      print_info "Compose would create an empty database. Restore sqlite first."
      exit 1
    fi
    local backup_file="${db_file}.bak-$(date +%Y%m%d%H%M%S)"
    print_step "[$app] Backing up SQLite to $backup_file"
    run_cmd cp -a "$db_file" "$backup_file"
  fi

  print_step "[$app] Rebuilding and recreating services: $services"
  run_shell "docker compose -p \"$PROJECT\" -f \"$COMPOSE_FILE\" up -d --build --force-recreate --no-deps $services"

  if [[ "$app" == "bldrdojo" ]]; then
    print_step "[$app] Running migrations"
    run_shell "docker compose -p \"$PROJECT\" -f \"$COMPOSE_FILE\" exec -T backend python manage.py migrate --noinput"

    print_step "[$app] Collecting static"
    run_shell "docker compose -p \"$PROJECT\" -f \"$COMPOSE_FILE\" exec -T backend python manage.py collectstatic --noinput"

    print_step "[$app] Refreshing Google OAuth config"
    run_shell "docker compose -p \"$PROJECT\" -f \"$COMPOSE_FILE\" exec -T backend python manage.py setup_google_oauth --domain=\"bldrdojo.com\" || true"
  fi

  if [[ "$app" == "devenkalra" && "$WITH_EDGE" == true ]]; then
    print_step "[$app] Recreating edge-nginx"
    run_shell "EDGE_NGINX_CONF=\"$EDGE_CONF\" docker compose -p edge -f \"$EDGE_COMPOSE\" up -d --force-recreate --no-deps edge-nginx"
  fi

  print_ok "[$app] Deploy complete"
}

REPO_DIR="${REPO_DIR:-/home/deploy/apps/monorepo}"
BRANCH="${BRANCH:-main}"
COMPOSE_FILE="docker-compose.production.yml"
PROJECT="data-backend"
EDGE_COMPOSE="docker-compose.edge.yml"
EDGE_CONF="./scripts/nginx/multi-domain-edge-example.conf"
DRY_RUN=false
WITH_EDGE=false
DISCARD_LOCAL=true
DIFF_OUT_FOR_DISCARD=""

APPS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app)
      [[ $# -lt 2 ]] && { print_err "--app requires a value"; usage; exit 1; }
      APPS+=("$2")
      shift 2
      ;;
    --branch)
      [[ $# -lt 2 ]] && { print_err "--branch requires a value"; usage; exit 1; }
      BRANCH="$2"
      shift 2
      ;;
    --repo-dir)
      [[ $# -lt 2 ]] && { print_err "--repo-dir requires a value"; usage; exit 1; }
      REPO_DIR="$2"
      shift 2
      ;;
    --compose-file)
      [[ $# -lt 2 ]] && { print_err "--compose-file requires a value"; usage; exit 1; }
      COMPOSE_FILE="$2"
      shift 2
      ;;
    --project)
      [[ $# -lt 2 ]] && { print_err "--project requires a value"; usage; exit 1; }
      PROJECT="$2"
      shift 2
      ;;
    --with-edge)
      WITH_EDGE=true
      shift
      ;;
    --edge-compose)
      [[ $# -lt 2 ]] && { print_err "--edge-compose requires a value"; usage; exit 1; }
      EDGE_COMPOSE="$2"
      shift 2
      ;;
    --edge-conf)
      [[ $# -lt 2 ]] && { print_err "--edge-conf requires a value"; usage; exit 1; }
      EDGE_CONF="$2"
      shift 2
      ;;
    --discard-local)
      DISCARD_LOCAL=true
      shift
      ;;
    --keep-local)
      DISCARD_LOCAL=false
      shift
      ;;
    --dry-run|-n)
      DRY_RUN=true
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      print_err "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ "${#APPS[@]}" -eq 0 ]]; then
  print_err "At least one --app is required."
  usage
  exit 1
fi

VALID_APPS=("bldrdojo" "devenkalra")
TARGET_APPS=()

for app in "${APPS[@]}"; do
  if [[ "$app" == "all" ]]; then
    TARGET_APPS=("${VALID_APPS[@]}")
    break
  fi
  if ! contains "$app" "${VALID_APPS[@]}"; then
    print_err "Unknown app: $app"
    print_info "Valid apps: ${VALID_APPS[*]} all"
    exit 1
  fi
  append_unique "$app" TARGET_APPS
done

if [[ ! -d "$REPO_DIR/.git" ]]; then
  print_err "No git repo at $REPO_DIR"
  print_info "Clone your monorepo there first, then run this script."
  exit 1
fi

cd "$REPO_DIR"

ensure_local_git_excludes

if [[ ! -f "$COMPOSE_FILE" ]]; then
  print_err "Missing compose file: $COMPOSE_FILE"
  exit 1
fi

if [[ "$WITH_EDGE" == true && ! -f "$EDGE_COMPOSE" ]]; then
  print_err "Missing edge compose file: $EDGE_COMPOSE"
  exit 1
fi

echo ""
echo "========================================"
echo " Targeted Monorepo Production Deployment"
echo "========================================"
echo " Repo:     $REPO_DIR"
echo " Branch:   $BRANCH"
echo " Apps:     ${TARGET_APPS[*]}"
echo " Compose:  $COMPOSE_FILE (project: $PROJECT)"
if [[ "$WITH_EDGE" == true ]]; then
  echo " Edge:     enabled ($EDGE_COMPOSE)"
fi
if [[ "$DRY_RUN" == true ]]; then
  echo " Mode:     DRY RUN"
fi
echo ""

print_step "Fetching origin/$BRANCH"
run_cmd git fetch origin "$BRANCH"

ensure_repo_clean_enough

for app in "${TARGET_APPS[@]}"; do
  deploy_one_app "$app"
done

echo ""
print_ok "All requested app deployments completed."
if [[ "$DRY_RUN" == false ]]; then
  print_step "Current service status"
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" ps
fi
