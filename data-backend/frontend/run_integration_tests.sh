#!/bin/bash
#
# Integration Test Runner Script
# 
# Runs Playwright integration tests that test the full stack from the frontend.
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Integration Test Runner${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Parse command line arguments
UI=false
DEBUG=false
HEADED=false
SPECIFIC_TEST=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --ui)
            UI=true
            shift
            ;;
        --debug)
            DEBUG=true
            shift
            ;;
        --headed)
            HEADED=true
            shift
            ;;
        --test|-t)
            SPECIFIC_TEST="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: ./run_integration_tests.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --ui               Open Playwright UI"
            echo "  --debug            Run in debug mode"
            echo "  --headed           Run in headed mode (show browser)"
            echo "  -t, --test FILE    Run specific test file"
            echo "  -h, --help         Show this help message"
            echo ""
            echo "Examples:"
            echo "  ./run_integration_tests.sh                    # Run all tests"
            echo "  ./run_integration_tests.sh --ui               # Open UI"
            echo "  ./run_integration_tests.sh --headed           # Show browser"
            echo "  ./run_integration_tests.sh --test 01-entity   # Run specific test"
            echo ""
            echo "Prerequisites:"
            echo "  - Backend must be running on http://localhost:8000"
            echo "  - Frontend dev server will start automatically"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Check if we're in the right directory
if [ ! -f "package.json" ]; then
    echo -e "${RED}Error: package.json not found. Please run this script from the frontend directory.${NC}"
    exit 1
fi

# Check if backend is running
echo -e "${YELLOW}Checking if backend is running...${NC}"
if ! curl -s http://localhost:8000/api/ > /dev/null 2>&1; then
    echo -e "${RED}Error: Backend is not running on http://localhost:8000${NC}"
    echo -e "${YELLOW}Please start the backend first:${NC}"
    echo -e "  cd /home/ubuntu/monorepo/data-backend"
    echo -e "  docker-compose -f docker-compose.local.yml up"
    exit 1
fi
echo -e "${GREEN}✓ Backend is running${NC}"
echo ""

# Check if frontend dev server is running
echo -e "${YELLOW}Checking if frontend dev server is running...${NC}"
if ! curl -s http://localhost:5173 > /dev/null 2>&1; then
    echo -e "${YELLOW}Frontend dev server is not running. Starting it...${NC}"
    
    # Start dev server in background
    npm run dev > /tmp/vite-dev-server.log 2>&1 &
    DEV_SERVER_PID=$!
    
    # Wait for it to be ready (max 30 seconds)
    echo -e "${YELLOW}Waiting for dev server to start...${NC}"
    for i in {1..30}; do
        if curl -s http://localhost:5173 > /dev/null 2>&1; then
            echo -e "${GREEN}✓ Frontend dev server is running (PID: $DEV_SERVER_PID)${NC}"
            break
        fi
        if [ $i -eq 30 ]; then
            echo -e "${RED}Error: Frontend dev server failed to start${NC}"
            echo -e "${YELLOW}Check logs: tail /tmp/vite-dev-server.log${NC}"
            kill $DEV_SERVER_PID 2>/dev/null
            exit 1
        fi
        sleep 1
    done
    
    # Save PID for cleanup
    echo $DEV_SERVER_PID > /tmp/playwright-dev-server.pid
    STARTED_DEV_SERVER=true
else
    echo -e "${GREEN}✓ Frontend dev server is already running${NC}"
    STARTED_DEV_SERVER=false
fi
echo ""

# Build test command
if [ "$UI" = true ]; then
    echo -e "${YELLOW}Opening Playwright UI...${NC}"
    npx playwright test --ui
    exit 0
fi

TEST_CMD="npx playwright test"

if [ -n "$SPECIFIC_TEST" ]; then
    TEST_CMD="$TEST_CMD tests/integration/$SPECIFIC_TEST"
fi

if [ "$DEBUG" = true ]; then
    TEST_CMD="$TEST_CMD --debug"
fi

if [ "$HEADED" = true ]; then
    TEST_CMD="$TEST_CMD --headed"
fi

echo -e "${YELLOW}Running integration tests...${NC}"
echo -e "${YELLOW}Command: $TEST_CMD${NC}"
echo ""

eval $TEST_CMD
TEST_EXIT_CODE=$?

# Cleanup: Kill dev server if we started it
if [ "$STARTED_DEV_SERVER" = true ] && [ -f /tmp/playwright-dev-server.pid ]; then
    DEV_SERVER_PID=$(cat /tmp/playwright-dev-server.pid)
    echo ""
    echo -e "${YELLOW}Stopping dev server (PID: $DEV_SERVER_PID)...${NC}"
    kill $DEV_SERVER_PID 2>/dev/null
    rm /tmp/playwright-dev-server.pid
fi

# Check exit code
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  All integration tests passed! ✓${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "${BLUE}View detailed report:${NC}"
    echo -e "  npx playwright show-report"
else
    echo ""
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}  Some integration tests failed! ✗${NC}"
    echo -e "${RED}========================================${NC}"
    echo ""
    echo -e "${YELLOW}View detailed report:${NC}"
    echo -e "  npx playwright show-report"
    echo ""
    echo -e "${YELLOW}Debug failed tests:${NC}"
    echo -e "  ./run_integration_tests.sh --debug"
    echo -e "  ./run_integration_tests.sh --headed"
    exit 1
fi
