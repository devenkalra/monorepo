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
#   food-frontend/
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
STAGING_DIR="${STAGING_DIR:-/home/deploy-staging}"
TEMP_DIR="${TEMP_DIR:-/tmp/bldrdojo-deploy-$$}"
REPO_URL="${REPO_URL:-}"  # Set via env or leave empty to use existing clone
BRANCH="${BRANCH:-main}"
DRY_RUN=false
MODE="production"  # production | staging | promote

# Parse args
for arg in "$@"; do
    case "$arg" in
        --dry-run|-n) DRY_RUN=true ;;
        --staging|-s) MODE="staging" ;;
        --promote|-p) MODE="promote" ;;
        --help|-h)
            echo "Usage: $0 [--dry-run] [--staging] [--promote]"
            echo ""
            echo "  --dry-run, -n    Show what would be copied, do not modify files"
            echo "  --staging, -s   Deploy to staging (ports 8080/8443). Test before promoting."
            echo "  --promote, -p   Switch production to the staged version (after testing)"
            echo ""
            echo "Blue-green flow:"
            echo "  1. ./deploy_production.sh --staging   # Deploy new version to staging"
            echo "  2. Test at https://bldrdojo.com:8443"
            echo "  3. ./deploy_production.sh --promote  # Switch production to new version"
            echo ""
            echo "Environment:"
            echo "  PROD_DIR        Production root (default: /home/deploy)"
            echo "  STAGING_DIR     Staging root (default: /home/deploy-staging)"
            echo "  REPO_URL        Git repo URL (required if PROD_DIR has no .git)"
            echo "  BRANCH          Branch to deploy (default: main)"
            exit 0
            ;;
    esac
done

# Target directory based on mode
if [[ "$MODE" == "staging" ]]; then
    DEPLOY_DIR="$STAGING_DIR"
    COMPOSE_FILE="docker-compose.staging.yml"
else
    DEPLOY_DIR="$PROD_DIR"
    COMPOSE_FILE="docker-compose.production.yml"
fi

# Directories/files to sync (relative to repo root). Excludes are applied per-path.
SYNC_PATHS=(
    "data-backend/config"
    "data-backend/people"
    "data-backend/cad"
    "data-backend/food"
    "data-backend/static"
    "data-backend/requirements.txt"
    "data-backend/Dockerfile"
    "data-backend/manage.py"
    "data-backend/docker-compose.yml"
    "frontend"
    "people-frontend"
    "cad-frontend"
    "food-frontend"
    "docker-compose.production.yml"
    "docker-compose.staging.yml"
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

# --- Promote mode: switch prod to staged version ---
if [[ "$MODE" == "promote" ]]; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  BldrDojo Promote (staging → production)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    if [[ ! -d "$STAGING_DIR" ]]; then
        print_error "Staging directory not found: $STAGING_DIR"
        print_info "Run with --staging first to deploy a new version."
        exit 1
    fi
    if [[ "$DRY_RUN" == true ]]; then
        print_info "Would stop production, sync staging→prod, start production"
        exit 0
    fi
    print_info "Stopping production..."
    cd "$PROD_DIR" && docker compose -f docker-compose.production.yml down
    print_info "Stopping staging..."
    cd "$STAGING_DIR" && docker compose -f docker-compose.staging.yml down 2>/dev/null || true
    print_info "Syncing staging → production..."
    rsync -a --delete \
        --exclude='.env' --exclude='.env.*' --exclude='ssl' --exclude='backups' \
        --exclude='logs' --exclude='logs-staging' --exclude='node_modules' \
        --exclude='__pycache__' --exclude='.git' --exclude='media' --exclude='staticfiles' \
        "$STAGING_DIR/" "$PROD_DIR/"
    print_info "Starting production with new version..."
    cd "$PROD_DIR"
    docker compose -f docker-compose.production.yml up -d
    sleep 5
    docker compose -f docker-compose.production.yml exec -T backend python manage.py migrate --noinput
    docker compose -f docker-compose.production.yml exec -T backend python manage.py collectstatic --noinput 2>/dev/null || true
    docker compose -f docker-compose.production.yml exec -T backend python manage.py setup_google_oauth --domain="bldrdojo.com" || true
    echo ""
    print_success "Promotion complete! Production is now running the new version."
    docker compose -f docker-compose.production.yml ps
    echo ""
    exit 0
fi

# --- Main (production or staging deploy) ---
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ "$MODE" == "staging" ]]; then
    echo "  BldrDojo Staging Deployment"
    echo "  (Test at https://bldrdojo.com:8443)"
else
    echo "  BldrDojo Production Deployment"
fi
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

# Verify deploy dir structure (.env can be in prod or staging)
ENV_SOURCE="$PROD_DIR/data-backend/.env"
[[ "$MODE" == "staging" ]] && [[ -f "$STAGING_DIR/data-backend/.env" ]] && ENV_SOURCE="$STAGING_DIR/data-backend/.env"
[[ "$MODE" == "staging" ]] && [[ ! -f "$STAGING_DIR/data-backend/.env" ]] && ENV_SOURCE="$PROD_DIR/data-backend/.env"
if [[ "$DRY_RUN" == false ]]; then
    if [[ ! -f "$PROD_DIR/data-backend/.env" ]] && [[ ! -f "$STAGING_DIR/data-backend/.env" ]]; then
        print_error ".env not found at $PROD_DIR/data-backend/.env"
        print_info "Create it before deploying. See DEPLOYMENT.md"
        [[ "$CLEANUP_TEMP" == true ]] && rm -rf "$TEMP_DIR"
        exit 1
    fi
    if [[ "$MODE" == "staging" ]] && [[ ! -f "$STAGING_DIR/data-backend/.env" ]]; then
        print_info "Copying .env from production to staging..."
        mkdir -p "$STAGING_DIR/data-backend"
        cp "$PROD_DIR/data-backend/.env" "$STAGING_DIR/data-backend/.env"
    fi
    if [[ "$MODE" == "staging" ]] && [[ ! -e "$STAGING_DIR/ssl" ]]; then
        print_info "Linking ssl from production to staging..."
        mkdir -p "$STAGING_DIR"
        ln -sfn "$(cd "$PROD_DIR" && pwd)/ssl" "$STAGING_DIR/ssl"
    fi
fi

# Copy files
print_info "Syncing files from git to $DEPLOY_DIR..."
COPIED=0
for path in "${SYNC_PATHS[@]}"; do
    src="$SRC_DIR/$path"
    dst="$DEPLOY_DIR/$path"
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
cd "$DEPLOY_DIR"
docker compose -f "$COMPOSE_FILE" build --no-cache backend celery-worker frontend

print_info "Restarting services..."
docker compose -f "$COMPOSE_FILE" up -d

print_info "Running migrations..."
sleep 5
docker compose -f "$COMPOSE_FILE" exec -T backend python manage.py migrate --noinput

print_info "Collecting static files..."
docker compose -f "$COMPOSE_FILE" exec -T backend python manage.py collectstatic --noinput 2>/dev/null || true

print_info "Configuring Google OAuth (Site + SocialApp for bldrdojo.com)..."
docker compose -f "$COMPOSE_FILE" exec -T backend python manage.py setup_google_oauth --domain="bldrdojo.com" || true

echo ""
print_success "Deployment complete!"
if [[ "$MODE" == "staging" ]]; then
    echo ""
    print_info "Test at: https://bldrdojo.com:8443"
    print_info "When ready, run: $0 --promote"
fi
docker compose -f "$COMPOSE_FILE" ps
echo ""
