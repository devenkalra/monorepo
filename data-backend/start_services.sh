#!/bin/bash
#
# Start all services for the Entity Manager application
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                                                                   ║${NC}"
echo -e "${BLUE}║  Starting Entity Manager Services                                ║${NC}"
echo -e "${BLUE}║                                                                   ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Activate virtual environment
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    echo -e "${GREEN}✓${NC} Virtual environment activated"
else
    echo -e "${YELLOW}⚠${NC}  Virtual environment not found. Creating..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    echo -e "${GREEN}✓${NC} Virtual environment created and dependencies installed"
fi

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  Starting Services${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Start Vector Search Service
echo -e "${BLUE}1. Vector Search Service${NC}"
if pgrep -f "vector_service.py" > /dev/null; then
    echo -e "   ${YELLOW}⚠${NC}  Already running (PID: $(pgrep -f 'vector_service.py'))"
else
    python vector_service.py > /tmp/vector_service.log 2>&1 &
    VECTOR_PID=$!
    echo -e "   ${GREEN}✓${NC} Started (PID: $VECTOR_PID)"
    sleep 3
    
    # Check if it's healthy
    if curl -s http://localhost:8002/health > /dev/null 2>&1; then
        echo -e "   ${GREEN}✓${NC} Health check passed"
    else
        echo -e "   ${YELLOW}⚠${NC}  Health check failed (may still be starting)"
    fi
fi

echo ""

# Start Django
echo -e "${BLUE}2. Django Application${NC}"
if pgrep -f "manage.py runserver" > /dev/null; then
    echo -e "   ${YELLOW}⚠${NC}  Already running (PID: $(pgrep -f 'manage.py runserver'))"
else
    python manage.py runserver 8001 --noreload > /tmp/django.log 2>&1 &
    DJANGO_PID=$!
    echo -e "   ${GREEN}✓${NC} Started (PID: $DJANGO_PID)"
    sleep 5
    
    # Check if it's responding
    if curl -s http://localhost:8001/api/conversations/ > /dev/null 2>&1; then
        echo -e "   ${GREEN}✓${NC} Responding to requests"
    else
        echo -e "   ${YELLOW}⚠${NC}  Not responding yet (may still be starting)"
    fi
fi

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  Service URLs${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${GREEN}Vector Service:${NC}  http://localhost:8002"
echo -e "  ${GREEN}Django API:${NC}      http://localhost:8001"
echo -e "  ${GREEN}Frontend:${NC}        http://localhost:5173"
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  Logs${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${GREEN}Vector Service:${NC}  tail -f /tmp/vector_service.log"
echo -e "  ${GREEN}Django:${NC}          tail -f /tmp/django.log"
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  Stop Services${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  pkill -f vector_service.py"
echo -e "  pkill -f 'manage.py runserver'"
echo ""
echo -e "${GREEN}✓ All services started!${NC}"
echo ""
