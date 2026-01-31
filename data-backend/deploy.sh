#!/usr/bin/env bash
#
# Production Deployment Script for bldrdojo.com
# Quick deployment automation
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                                                                   ║${NC}"
echo -e "${BLUE}║  Bldrdojo.com - Production Deployment                            ║${NC}"
echo -e "${BLUE}║                                                                   ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════════╝${NC}"
echo

# Check if .env exists
if [ ! -f .env ]; then
    echo -e "${RED}Error: .env file not found!${NC}"
    echo -e "${YELLOW}Please copy .env.example to .env and configure it.${NC}"
    echo -e "${YELLOW}Run: cp .env.example .env${NC}"
    exit 1
fi

# Check for placeholder values
if grep -q "change-this" .env; then
    echo -e "${RED}Error: .env file contains placeholder values!${NC}"
    echo -e "${YELLOW}Please update all 'change-this' values in .env${NC}"
    exit 1
fi

# Check SSL certificates
if [ ! -f ssl/fullchain.pem ] || [ ! -f ssl/privkey.pem ]; then
    echo -e "${YELLOW}Warning: SSL certificates not found in ssl/ directory${NC}"
    echo -e "${YELLOW}HTTPS will not work without certificates.${NC}"
    echo -e "${YELLOW}See DEPLOYMENT.md for SSL setup instructions.${NC}"
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo -e "${BLUE}Building Docker images...${NC}"
docker-compose build || {
    echo -e "${RED}Build failed!${NC}"
    exit 1
}

echo
echo -e "${BLUE}Starting services...${NC}"
docker-compose up -d || {
    echo -e "${RED}Failed to start services!${NC}"
    exit 1
}

echo
echo -e "${BLUE}Waiting for services to be healthy...${NC}"
sleep 10

# Check service health
echo -e "${BLUE}Checking service health...${NC}"
SERVICES="db redis meilisearch neo4j"
for service in $SERVICES; do
    echo -n "  Checking $service... "
    for i in {1..30}; do
        if docker-compose ps $service | grep -q "healthy"; then
            echo -e "${GREEN}✓${NC}"
            break
        elif [ $i -eq 30 ]; then
            echo -e "${RED}✗ (timeout)${NC}"
            echo -e "${YELLOW}Check logs with: docker-compose logs $service${NC}"
        fi
        sleep 2
    done
done

echo
echo -e "${BLUE}Running database migrations...${NC}"
docker-compose exec -T backend python manage.py migrate || {
    echo -e "${RED}Migration failed!${NC}"
    exit 1
}

echo
echo -e "${BLUE}Collecting static files...${NC}"
docker-compose exec -T backend python manage.py collectstatic --noinput || {
    echo -e "${RED}Static file collection failed!${NC}"
    exit 1
}

echo
echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                                                                   ║${NC}"
echo -e "${GREEN}║  ✅ Deployment Complete!                                          ║${NC}"
echo -e "${GREEN}║                                                                   ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════════╝${NC}"
echo
echo -e "${BLUE}Services Status:${NC}"
docker-compose ps
echo
echo -e "${BLUE}Application URLs:${NC}"
echo -e "  Frontend:     ${GREEN}https://bldrdojo.com${NC}"
echo -e "  API:          ${GREEN}https://bldrdojo.com/api/${NC}"
echo -e "  Admin:        ${GREEN}https://bldrdojo.com/admin/${NC}"
echo
echo -e "${BLUE}Useful Commands:${NC}"
echo -e "  View logs:           ${YELLOW}docker-compose logs -f${NC}"
echo -e "  View backend logs:   ${YELLOW}docker-compose logs -f backend${NC}"
echo -e "  Restart services:    ${YELLOW}docker-compose restart${NC}"
echo -e "  Stop services:       ${YELLOW}docker-compose down${NC}"
echo -e "  Create superuser:    ${YELLOW}docker-compose exec backend python manage.py createsuperuser${NC}"
echo
echo -e "${BLUE}Next Steps:${NC}"
echo -e "  1. Create a superuser account (see command above)"
echo -e "  2. Configure Google OAuth in Django admin"
echo -e "  3. Test the application"
echo -e "  4. Set up automated backups (see DEPLOYMENT.md)"
echo
