#!/bin/bash
#
# Production Deployment Script
#
# This script automates the deployment process
#
# Usage:
#   ./scripts/deploy_production.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Production Deployment${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}Error: Do not run this script as root${NC}"
    exit 1
fi

# Check if .env.production exists
if [ ! -f ".env.production" ]; then
    echo -e "${RED}Error: .env.production not found${NC}"
    echo "Please create .env.production with your production settings"
    exit 1
fi

# Confirmation
echo -e "${YELLOW}This will deploy the application to production.${NC}"
echo -e "${YELLOW}Make sure you have:${NC}"
echo "  - Configured .env.production"
echo "  - Set up domain DNS"
echo "  - Configured Nginx"
echo "  - Obtained SSL certificate"
echo ""
read -p "Continue? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Deployment cancelled"
    exit 0
fi
echo ""

# Pull latest code
echo -e "${YELLOW}Pulling latest code...${NC}"
git pull origin main || echo "Git pull skipped"
echo -e "${GREEN}✓ Code updated${NC}"
echo ""

# Build Docker images
echo -e "${YELLOW}Building Docker images...${NC}"
docker-compose -f docker-compose.production.yml build
echo -e "${GREEN}✓ Images built${NC}"
echo ""

# Stop existing containers
echo -e "${YELLOW}Stopping existing containers...${NC}"
docker-compose -f docker-compose.production.yml down
echo -e "${GREEN}✓ Containers stopped${NC}"
echo ""

# Start new containers
echo -e "${YELLOW}Starting new containers...${NC}"
docker-compose -f docker-compose.production.yml up -d
echo -e "${GREEN}✓ Containers started${NC}"
echo ""

# Wait for services to be ready
echo -e "${YELLOW}Waiting for services to be ready...${NC}"
sleep 10

# Run migrations
echo -e "${YELLOW}Running database migrations...${NC}"
docker-compose -f docker-compose.production.yml exec -T backend python manage.py migrate --noinput
echo -e "${GREEN}✓ Migrations complete${NC}"
echo ""

# Collect static files
echo -e "${YELLOW}Collecting static files...${NC}"
docker-compose -f docker-compose.production.yml exec -T backend python manage.py collectstatic --noinput
echo -e "${GREEN}✓ Static files collected${NC}"
echo ""

# Check service health
echo -e "${YELLOW}Checking service health...${NC}"
BACKEND_HEALTH=$(docker-compose -f docker-compose.production.yml exec -T backend curl -sf http://localhost:8000/api/ && echo "OK" || echo "FAIL")
if [ "$BACKEND_HEALTH" = "OK" ]; then
    echo -e "${GREEN}✓ Backend is healthy${NC}"
else
    echo -e "${RED}✗ Backend health check failed${NC}"
fi
echo ""

# Show running containers
echo -e "${YELLOW}Running containers:${NC}"
docker-compose -f docker-compose.production.yml ps
echo ""

# Create backup
echo -e "${YELLOW}Creating post-deployment backup...${NC}"
./scripts/backup.sh "post_deploy_$(date +%Y%m%d_%H%M%S)" || echo "Backup skipped"
echo ""

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Deployment Complete! ✓${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "  1. Test the application: https://your-domain.com"
echo "  2. Check logs: docker-compose -f docker-compose.production.yml logs -f"
echo "  3. Monitor services: docker-compose -f docker-compose.production.yml ps"
echo ""
echo -e "${YELLOW}Useful commands:${NC}"
echo "  View logs: docker-compose -f docker-compose.production.yml logs -f [service]"
echo "  Restart: docker-compose -f docker-compose.production.yml restart [service]"
echo "  Shell: docker-compose -f docker-compose.production.yml exec backend python manage.py shell"
echo ""
