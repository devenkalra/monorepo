#!/usr/bin/env bash
#
# Local Testing Script for bldrdojo.com
# Automated testing and verification
#

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

COMPOSE_FILE="docker-compose.local.yml"

echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                                                                   ║${NC}"
echo -e "${BLUE}║  Bldrdojo.com - Local Testing Suite                              ║${NC}"
echo -e "${BLUE}║                                                                   ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════════╝${NC}"
echo

# Check Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not running${NC}"
    exit 1
fi

echo -e "${BLUE}Starting local environment...${NC}"
docker-compose -f $COMPOSE_FILE up -d

echo
echo -e "${BLUE}Waiting for services to be healthy...${NC}"
sleep 15

# Function to check service health
check_service() {
    local service=$1
    local max_attempts=30
    local attempt=0
    
    echo -n "  Checking $service... "
    
    while [ $attempt -lt $max_attempts ]; do
        if docker-compose -f $COMPOSE_FILE ps $service | grep -q "healthy\|running"; then
            echo -e "${GREEN}✓${NC}"
            return 0
        fi
        sleep 2
        ((attempt++))
    done
    
    echo -e "${RED}✗ (timeout)${NC}"
    return 1
}

# Check all services
SERVICES="db redis meilisearch neo4j vector-service backend"
ALL_HEALTHY=true

for service in $SERVICES; do
    if ! check_service $service; then
        ALL_HEALTHY=false
    fi
done

if [ "$ALL_HEALTHY" = false ]; then
    echo
    echo -e "${RED}Some services failed to start. Check logs:${NC}"
    echo -e "${YELLOW}docker-compose -f $COMPOSE_FILE logs${NC}"
    exit 1
fi

echo
echo -e "${BLUE}Running tests...${NC}"
echo

# Test 1: Health Check
echo -n "  Testing backend health endpoint... "
if curl -sf http://localhost:8001/api/health/ > /dev/null; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗${NC}"
    ALL_HEALTHY=false
fi

# Test 2: Admin Access
echo -n "  Testing admin panel access... "
if curl -sf http://localhost:8001/admin/ | grep -q "Django"; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗${NC}"
    ALL_HEALTHY=false
fi

# Test 3: Database Connection
echo -n "  Testing database connection... "
if docker-compose -f $COMPOSE_FILE exec -T backend python manage.py dbshell <<< "SELECT 1;" > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗${NC}"
    ALL_HEALTHY=false
fi

# Test 4: Redis Connection
echo -n "  Testing Redis connection... "
if docker-compose -f $COMPOSE_FILE exec -T redis redis-cli -a localredispass ping | grep -q "PONG"; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗${NC}"
    ALL_HEALTHY=false
fi

# Test 5: MeiliSearch
echo -n "  Testing MeiliSearch... "
if curl -sf http://localhost:7700/health | grep -q "available"; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗${NC}"
    ALL_HEALTHY=false
fi

# Test 6: Neo4j
echo -n "  Testing Neo4j connection... "
if curl -sf http://localhost:7474/ > /dev/null; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗${NC}"
    ALL_HEALTHY=false
fi

# Test 7: Vector Service
echo -n "  Testing vector service... "
if curl -sf http://localhost:5000/health > /dev/null; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗${NC}"
    ALL_HEALTHY=false
fi

# Test 8: API Registration
echo -n "  Testing user registration... "
REGISTER_RESPONSE=$(curl -sf -X POST http://localhost:8001/api/auth/registration/ \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"testuser_$$\",\"email\":\"test$$@example.com\",\"password1\":\"testpass123\",\"password2\":\"testpass123\"}")

if echo "$REGISTER_RESPONSE" | grep -q "access\|key"; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗${NC}"
    ALL_HEALTHY=false
fi

echo
if [ "$ALL_HEALTHY" = true ]; then
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                                                                   ║${NC}"
    echo -e "${GREEN}║  ✅ All Tests Passed!                                             ║${NC}"
    echo -e "${GREEN}║                                                                   ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════════╝${NC}"
else
    echo -e "${RED}╔═══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║                                                                   ║${NC}"
    echo -e "${RED}║  ❌ Some Tests Failed                                             ║${NC}"
    echo -e "${RED}║                                                                   ║${NC}"
    echo -e "${RED}╚═══════════════════════════════════════════════════════════════════╝${NC}"
fi

echo
echo -e "${BLUE}Application URLs:${NC}"
echo -e "  Frontend:     ${GREEN}http://localhost:5174${NC}"
echo -e "  Backend API:  ${GREEN}http://localhost:8001/api/${NC}"
echo -e "  Admin Panel:  ${GREEN}http://localhost:8001/admin/${NC}"
echo -e "  PostgreSQL:   ${GREEN}localhost:5432${NC}"
echo -e "  Redis:        ${GREEN}localhost:6379${NC}"
echo -e "  MeiliSearch:  ${GREEN}http://localhost:7700${NC}"
echo -e "  Neo4j:        ${GREEN}http://localhost:7474${NC}"
echo -e "  Vector:       ${GREEN}http://localhost:5000${NC}"
echo
echo -e "${BLUE}Useful Commands:${NC}"
echo -e "  View logs:    ${YELLOW}docker-compose -f $COMPOSE_FILE logs -f${NC}"
echo -e "  Stop:         ${YELLOW}docker-compose -f $COMPOSE_FILE down${NC}"
echo -e "  Restart:      ${YELLOW}docker-compose -f $COMPOSE_FILE restart${NC}"
echo -e "  Shell:        ${YELLOW}docker-compose -f $COMPOSE_FILE exec backend bash${NC}"
echo

if [ "$ALL_HEALTHY" = true ]; then
    exit 0
else
    exit 1
fi
