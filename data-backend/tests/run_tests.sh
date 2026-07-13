#!/bin/bash
#
# Test Runner Script for Data Backend
# 
# This script runs integration tests in Docker environment.
# For the original integration test runner, use ../run_integration_tests.sh
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
VERBOSE=false
SPECIFIC_TEST=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --test|-t)
            SPECIFIC_TEST="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: ./tests/run_tests.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -v, --verbose      Run tests in verbose mode (verbosity=2)"
            echo "  -t, --test CLASS   Run specific test class"
            echo "  -h, --help         Show this help message"
            echo ""
            echo "Examples:"
            echo "  ./tests/run_tests.sh                                    # Run all integration tests"
            echo "  ./tests/run_tests.sh --verbose                          # Run with verbose output"
            echo "  ./tests/run_tests.sh --test AllEntityTypesCRUDTest      # Run specific test class"
            echo "  ./tests/run_tests.sh --test FileUploadTest              # Run file upload tests"
            echo ""
            echo "Available test classes:"
            echo "  - FullStackIntegrationTest (21 tests)"
            echo "  - CrossUserImportExportTest (1 test)"
            echo "  - AllEntityTypesCRUDTest (9 tests)"
            echo "  - FileUploadTest (6 tests)"
            echo "  - MeiliSearchStressTest (1 test)"
            echo ""
            echo "Note: This runs tests in Docker. Services must be running:"
            echo "  docker compose -f docker-compose.local.yml up -d"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Get the project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# Check if services are running
echo -e "${YELLOW}Checking if Docker services are running...${NC}"
if ! docker compose -f docker-compose.local.yml ps | grep -q "Up"; then
    echo -e "${RED}ERROR: Services are not running!${NC}"
    echo "Start them with: docker compose -f docker-compose.local.yml up -d"
    exit 1
fi

echo -e "${GREEN}✓ Services are running${NC}"
echo ""

# Clean up any existing test database
echo -e "${YELLOW}Cleaning up test database...${NC}"
docker compose -f docker-compose.local.yml exec -T db psql -U postgres -c "DROP DATABASE IF EXISTS test_entitydb;" > /dev/null 2>&1 || true
echo -e "${GREEN}✓ Test database cleaned${NC}"
echo ""

# Build test command
TEST_CMD="python manage.py test"

if [ -n "$SPECIFIC_TEST" ]; then
    TEST_CMD="$TEST_CMD people.tests.test_integration_full_stack.$SPECIFIC_TEST"
else
    TEST_CMD="$TEST_CMD people.tests.test_integration_full_stack"
fi

if [ "$VERBOSE" = true ]; then
    TEST_CMD="$TEST_CMD --verbosity=2"
else
    TEST_CMD="$TEST_CMD --verbosity=1"
fi

# Run the tests
echo -e "${YELLOW}Running tests in Docker...${NC}"
echo -e "${YELLOW}Command: $TEST_CMD${NC}"
echo ""

docker compose -f docker-compose.local.yml exec -T backend $TEST_CMD

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
