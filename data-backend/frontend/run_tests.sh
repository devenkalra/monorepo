#!/bin/bash
#
# Frontend Test Runner Script
# 
# This script runs all frontend tests with various options.
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Frontend Test Runner${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Parse command line arguments
COVERAGE=false
WATCH=false
UI=false
E2E=false
SPECIFIC_TEST=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --coverage|-c)
            COVERAGE=true
            shift
            ;;
        --watch|-w)
            WATCH=true
            shift
            ;;
        --ui)
            UI=true
            shift
            ;;
        --e2e)
            E2E=true
            shift
            ;;
        --test|-t)
            SPECIFIC_TEST="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: ./run_tests.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -c, --coverage     Run tests with coverage report"
            echo "  -w, --watch        Run tests in watch mode"
            echo "  --ui               Open Vitest UI"
            echo "  --e2e              Run E2E tests only"
            echo "  -t, --test FILE    Run specific test file"
            echo "  -h, --help         Show this help message"
            echo ""
            echo "Examples:"
            echo "  ./run_tests.sh                    # Run all tests"
            echo "  ./run_tests.sh --coverage         # Run with coverage"
            echo "  ./run_tests.sh --watch            # Run in watch mode"
            echo "  ./run_tests.sh --e2e              # Run E2E tests only"
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

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}node_modules not found. Installing dependencies...${NC}"
    npm install
fi

# Build test command
if [ "$UI" = true ]; then
    echo -e "${YELLOW}Opening Vitest UI...${NC}"
    npm run test:ui
    exit 0
fi

TEST_CMD="npm run test"

if [ "$E2E" = true ]; then
    TEST_CMD="$TEST_CMD -- src/tests/e2e"
elif [ -n "$SPECIFIC_TEST" ]; then
    TEST_CMD="$TEST_CMD -- $SPECIFIC_TEST"
fi

if [ "$COVERAGE" = true ]; then
    TEST_CMD="$TEST_CMD -- --coverage"
fi

if [ "$WATCH" = true ]; then
    TEST_CMD="$TEST_CMD -- --watch"
fi

echo -e "${YELLOW}Running tests...${NC}"
echo -e "${YELLOW}Command: $TEST_CMD${NC}"
echo ""

eval $TEST_CMD

# Check exit code
if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  All tests passed! ✓${NC}"
    echo -e "${GREEN}========================================${NC}"
else
    echo ""
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}  Some tests failed! ✗${NC}"
    echo -e "${RED}========================================${NC}"
    exit 1
fi
