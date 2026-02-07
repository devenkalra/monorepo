#!/bin/bash
#
# Test Runner Script for Data Backend
# 
# This script runs all backend tests with various options.
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Data Backend Test Runner${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Parse command line arguments
COVERAGE=false
VERBOSE=false
SPECIFIC_TEST=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --coverage|-c)
            COVERAGE=true
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
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
            echo "  -v, --verbose      Run tests in verbose mode"
            echo "  -t, --test FILE    Run specific test file"
            echo "  -h, --help         Show this help message"
            echo ""
            echo "Examples:"
            echo "  ./run_tests.sh                          # Run all tests"
            echo "  ./run_tests.sh --coverage               # Run with coverage"
            echo "  ./run_tests.sh --test test_api_entities # Run specific test"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Check if we're in the right directory
if [ ! -f "manage.py" ]; then
    echo -e "${RED}Error: manage.py not found. Please run this script from the data-backend directory.${NC}"
    exit 1
fi

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo -e "${YELLOW}Activating virtual environment...${NC}"
    source venv/bin/activate
fi

# Build test command
TEST_CMD="python manage.py test"

if [ -n "$SPECIFIC_TEST" ]; then
    TEST_CMD="$TEST_CMD people.tests.$SPECIFIC_TEST"
else
    TEST_CMD="$TEST_CMD people.tests"
fi

if [ "$VERBOSE" = true ]; then
    TEST_CMD="$TEST_CMD --verbosity=2"
fi

if [ "$COVERAGE" = true ]; then
    echo -e "${YELLOW}Running tests with coverage...${NC}"
    coverage run --source='people' manage.py test people.tests
    echo ""
    echo -e "${GREEN}Coverage Report:${NC}"
    coverage report -m
    echo ""
    echo -e "${YELLOW}Generating HTML coverage report...${NC}"
    coverage html
    echo -e "${GREEN}HTML coverage report generated in htmlcov/index.html${NC}"
else
    echo -e "${YELLOW}Running tests...${NC}"
    $TEST_CMD
fi

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
