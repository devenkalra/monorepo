#!/bin/bash
# Production deployment script for bldrdojo.com
# 1. Clones repo into temp directory (fresh from git, no local changes)
# 2. Copies changed/new files into prod folder
# 3. Rebuilds and restarts services
#
# Usage:
#   ./scripts/deploy_production.sh              # Deploy
#   ./scripts/deploy_production.sh --dry-run    # Show what would be copied
#
# Expected PROD_DIR structure (default /home/deploy):
#   data-backend/   (with .env, ssl/)
#   frontend/
#   people-frontend/
#   cad-frontend/
#   docker-compose.production.yml

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_error()   { echo -e "${RED}✗ $1${NC}"; }
print_info()    { echo -e "${YELLOW}ℹ $1${NC}"; }
print_action()  { echo -e "${CYAN}→ $1${NC}"; }

# Configuration
PROD_DIR="${PROD_DIR:-/home/deploy}"
TEMP_DIR="${TEMP_DIR:-/tmp/bldrdojo-deploy-$$}"
REPO_URL="${REPO_URL:-}"  # Set via env or leave empty to use existing clone
BRANCH="${BRANCH:-main}"
DRY_RUN=false

# Parse args
for arg in "$@"; do
    case "$arg" in
        --dry-run|-n) DRY_RUN=true ;;
        --help|-h)
            echo "Usage: $0 [--dry-run]"
            echo ""
            echo "  --dry-run, -n    Show what would be copied, do not modify files"
            echo ""
            echo "Environment:"
            echo "  PROD_DIR        Production root (default: /home/deploy)"
            echo "  TEMP_DIR        Temp clone dir (default: /tmp/bldrdojo-deploy-$$)"
            echo "  REPO_URL        Git repo URL (required if PROD_DIR has no .git)"
            echo "  BRANCH          Branch to deploy (default: main)"
            exit 0
            ;;
    esac
done

# Directories/files to sync (relative to repo root). Excludes are applied per-path.
SYNC_PATHS=(
    "data-backend/config"
    "data-backend/people"
    "data-backend/cad"
    "data-backend/static"
    "data-backend/requirements.txt"
    "data-backend/Dockerfile"
    "data-backend/manage.py"
    "data-backend/docker-compose.yml"
    "frontend"
    "people-frontend"
    "cad-frontend"
    "docker-compose.production.yml"
    "scripts"
)

# Patterns to exclude from copy (relative to each sync path)
EXCLUDE_PATTERNS=(
    ".env"
    ".env.*"
    "node_modules"
    "__pycache__"
    "*.pyc"
    ".git"
    "ssl"
    "backups"
    "logs"
    "*.log"
    "media"
    "staticfiles"
    ".pytest_cache"
    "htmlcov"
    ".coverage"
    "playwright-report"
    "test-results"
    ".cache"
)

# Build rsync exclude args
RSYNC_EXCLUDES=()
for p in "${EXCLUDE_PATTERNS[@]}"; do
    RSYNC_EXCLUDES+=(--exclude="$p")
done

copy_or_dry() {
    local src="$1"
    local dst="$2"
    if [[ "$DRY_RUN" == true ]]; then
        if [[ -d "$src" ]]; then
            print_action "Would sync: $src/ -> $dst/"
            rsync -avn "${RSYNC_EXCLUDES[@]}" "$src/" "$dst" 2>/dev/null | tail -n +2 || true
        else
            print_action "Would copy: $src -> $dst"
        fi
    else
        mkdir -p "$(dirname "$dst")"
        if [[ -d "$src" ]]; then
            mkdir -p "$dst"
            rsync -a "${RSYNC_EXCLUDES[@]}" "$src/" "$dst"
        else
            cp -a "$src" "$dst"
        fi
    fi
}

# --- Main ---
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  BldrDojo Production Deployment"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [[ "$DRY_RUN" == true ]]; then
    print_info "DRY RUN - no files will be modified"
    echo ""
fi

# Resolve source: clone fresh or use existing
SRC_DIR=""
if [[ -n "$REPO_URL" ]]; then
    print_info "Cloning $REPO_URL ($BRANCH) into $TEMP_DIR..."
    rm -rf "$TEMP_DIR"
    git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$TEMP_DIR"
    SRC_DIR="$TEMP_DIR"
    CLEANUP_TEMP=true
elif [[ -d "$PROD_DIR/.git" ]]; then
    REPO_URL=$(cd "$PROD_DIR" && git remote get-url origin 2>/dev/null || true)
    if [[ -z "$REPO_URL" ]]; then
        print_error "No remote URL in $PROD_DIR/.git. Set REPO_URL."
        exit 1
    fi
    print_info "Cloning $REPO_URL ($BRANCH) into $TEMP_DIR (clean copy, no local changes)..."
    rm -rf "$TEMP_DIR"
    git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$TEMP_DIR"
    SRC_DIR="$TEMP_DIR"
    CLEANUP_TEMP=true
else
    print_error "No REPO_URL and no .git in $PROD_DIR. Set REPO_URL or ensure prod is a git clone."
    exit 1
fi

if [[ ! -d "$SRC_DIR" ]]; then
    print_error "Source directory not found: $SRC_DIR"
    exit 1
fi

# Verify prod dir structure
if [[ "$DRY_RUN" == false ]] && [[ ! -f "$PROD_DIR/data-backend/.env" ]]; then
    print_error ".env not found at $PROD_DIR/data-backend/.env"
    print_info "Create it before deploying. See DEPLOYMENT.md"
    [[ "$CLEANUP_TEMP" == true ]] && rm -rf "$TEMP_DIR"
    exit 1
fi

# Copy files
print_info "Syncing files from git to $PROD_DIR..."
COPIED=0
for path in "${SYNC_PATHS[@]}"; do
    src="$SRC_DIR/$path"
    dst="$PROD_DIR/$path"
    if [[ -e "$src" ]]; then
        copy_or_dry "$src" "$dst"
        ((COPIED++)) || true
    else
        print_info "Skip (not in repo): $path"
    fi
done

# Cleanup temp
[[ "$CLEANUP_TEMP" == true ]] && rm -rf "$TEMP_DIR"

if [[ "$DRY_RUN" == true ]]; then
    echo ""
    print_info "Dry run complete. Run without --dry-run to deploy."
    exit 0
fi

# Build and restart
echo ""
print_info "Building Docker images..."
cd "$PROD_DIR"
docker compose -f docker-compose.production.yml build --no-cache backend frontend

print_info "Restarting services..."
docker compose -f docker-compose.production.yml up -d

print_info "Running migrations..."
sleep 5
docker compose -f docker-compose.production.yml exec -T backend python manage.py migrate --noinput 2>/dev/null || true

print_info "Collecting static files..."
docker compose -f docker-compose.production.yml exec -T backend python manage.py collectstatic --noinput 2>/dev/null || true

print_info "Configuring Google OAuth (Site + SocialApp for bldrdojo.com)..."
docker compose -f docker-compose.production.yml exec -T backend python manage.py setup_google_oauth --domain="bldrdojo.com" || true

echo ""
print_success "Deployment complete!"
docker compose -f docker-compose.production.yml ps
echo ""
