#!/bin/bash
# Deployment script for bldrdojo.com
# Run this on your Linode server as the deploy user

set -e  # Exit on error

echo "🚀 Starting deployment for bldrdojo.com..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
APP_DIR="/home/deploy/data-backend"
BACKUP_DIR="$APP_DIR/backups"

# Function to print colored output
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

# Check if running as deploy user
if [ "$USER" != "deploy" ]; then
    print_error "This script should be run as the 'deploy' user"
    exit 1
fi

# Check if .env file exists
if [ ! -f "$APP_DIR/.env" ]; then
    print_error ".env file not found at $APP_DIR/.env"
    print_info "Please create .env file first. See DEPLOYMENT.md for details."
    exit 1
fi

# Check if SSL certificates exist
if [ ! -f "$APP_DIR/ssl/fullchain.pem" ] || [ ! -f "$APP_DIR/ssl/privkey.pem" ]; then
    print_error "SSL certificates not found at $APP_DIR/ssl/"
    print_info "Please setup SSL certificates first. See DEPLOYMENT.md for details."
    exit 1
fi

# Navigate to app directory
cd "$APP_DIR"

# Create backup before deployment
print_info "Creating backup..."
BACKUP_DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

if docker compose ps | grep -q "Up"; then
    docker compose exec -T db pg_dump -U postgres entitydb | gzip > "$BACKUP_DIR/pre_deploy_$BACKUP_DATE.sql.gz"
    print_success "Database backup created: pre_deploy_$BACKUP_DATE.sql.gz"
else
    print_info "Database not running, skipping backup"
fi

# Pull latest code (if using git)
if [ -d ".git" ]; then
    print_info "Pulling latest code from git..."
    git pull origin main || git pull origin master
    print_success "Code updated"
fi

# Build Docker images
print_info "Building Docker images..."
docker compose build --no-cache
print_success "Docker images built"

# Stop services
print_info "Stopping services..."
docker compose down
print_success "Services stopped"

# Start services
print_info "Starting services..."
docker compose up -d
print_success "Services started"

# Wait for services to be healthy
print_info "Waiting for services to be healthy..."
sleep 10

# Check service health
RETRIES=30
HEALTHY=false

for i in $(seq 1 $RETRIES); do
    if docker compose ps | grep -q "unhealthy"; then
        print_info "Waiting for services to be healthy... ($i/$RETRIES)"
        sleep 5
    else
        HEALTHY=true
        break
    fi
done

if [ "$HEALTHY" = false ]; then
    print_error "Services failed to become healthy"
    print_info "Check logs with: docker compose logs"
    exit 1
fi

# Run migrations
print_info "Running database migrations..."
docker compose exec -T backend python manage.py migrate --noinput
print_success "Migrations completed"

# Collect static files
print_info "Collecting static files..."
docker compose exec -T backend python manage.py collectstatic --noinput
print_success "Static files collected"

# Sync MeiliSearch (optional, can be slow)
read -p "Do you want to sync MeiliSearch index? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_info "Syncing MeiliSearch..."
    docker compose exec -T backend python manage.py sync_meilisearch
    print_success "MeiliSearch synced"
fi

# Show service status
print_info "Service Status:"
docker compose ps

# Test endpoints
print_info "Testing endpoints..."

# Test backend health
if curl -f -s https://bldrdojo.com/api/health/ > /dev/null; then
    print_success "Backend API is responding"
else
    print_error "Backend API is not responding"
fi

# Test frontend
if curl -f -s https://bldrdojo.com/ > /dev/null; then
    print_success "Frontend is responding"
else
    print_error "Frontend is not responding"
fi

# Print summary
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
print_success "Deployment completed successfully!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
print_info "Application URL: https://bldrdojo.com"
print_info "Admin Panel: https://bldrdojo.com/admin/"
echo ""
print_info "Useful commands:"
echo "  View logs:        docker compose logs -f"
echo "  Restart services: docker compose restart"
echo "  Stop services:    docker compose down"
echo "  Service status:   docker compose ps"
echo ""
print_info "Backup created at: $BACKUP_DIR/pre_deploy_$BACKUP_DATE.sql.gz"
echo ""
