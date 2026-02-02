#!/usr/bin/env bash
#
# Run all test suites with coverage reporting
#
# Usage:
#   ./run_all_tests.sh              # Run all tests
#   ./run_all_tests.sh --coverage   # Run with coverage report
#   ./run_all_tests.sh --verbose    # Run with verbose output

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
RUN_COVERAGE=false
VERBOSE=""

for arg in "$@"; do
    case $arg in
        --coverage)
            RUN_COVERAGE=true
            ;;
        --verbose)
            VERBOSE="-v"
            ;;
    esac
done

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Running Media Management Test Suite${NC}"
echo -e "${BLUE}========================================${NC}"
echo

# Check if coverage is installed
if [ "$RUN_COVERAGE" = true ]; then
    if ! python3 -c "import coverage" 2>/dev/null; then
        echo -e "${YELLOW}Warning: coverage not installed. Installing...${NC}"
        pip3 install coverage
    fi
fi

# Test files
TEST_FILES=(
    "tests/test_index_media.py"
    "tests/test_apply_exif.py"
    "tests/test_move_media.py"
    "tests/test_locate_in_db.py"
    "tests/test_show_exif.py"
    "tests/test_media_utils.py"
    "tests/test_location_utils.py"
)

# Set PYTHONPATH to include current directory
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# Run tests
FAILED_TESTS=()
PASSED_TESTS=()

for test_file in "${TEST_FILES[@]}"; do
    if [ -f "$test_file" ]; then
        echo -e "${BLUE}Running: $test_file${NC}"
        
        # Extract module path from file path
        module_path=$(echo "$test_file" | sed 's|/|.|g' | sed 's|\.py$||')
        
        if [ "$RUN_COVERAGE" = true ]; then
            if python3 -m coverage run --source=. -a -m unittest "$module_path" $VERBOSE; then
                echo -e "${GREEN}✓ PASSED${NC}"
                PASSED_TESTS+=("$test_file")
            else
                echo -e "${RED}✗ FAILED${NC}"
                FAILED_TESTS+=("$test_file")
            fi
        else
            if python3 -m unittest "$module_path" $VERBOSE; then
                echo -e "${GREEN}✓ PASSED${NC}"
                PASSED_TESTS+=("$test_file")
            else
                echo -e "${RED}✗ FAILED${NC}"
                FAILED_TESTS+=("$test_file")
            fi
        fi
        echo
    else
        echo -e "${YELLOW}Skipping: $test_file (not found)${NC}"
        echo
    fi
done

# Summary
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Test Summary${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Passed: ${#PASSED_TESTS[@]}${NC}"
echo -e "${RED}Failed: ${#FAILED_TESTS[@]}${NC}"
echo

if [ ${#FAILED_TESTS[@]} -gt 0 ]; then
    echo -e "${RED}Failed tests:${NC}"
    for test in "${FAILED_TESTS[@]}"; do
        echo -e "  ${RED}✗${NC} $test"
    done
    echo
fi

# Coverage report
if [ "$RUN_COVERAGE" = true ]; then
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}Coverage Report${NC}"
    echo -e "${BLUE}========================================${NC}"
    python3 -m coverage report -m
    echo
    
    echo -e "${BLUE}Generating HTML coverage report...${NC}"
    python3 -m coverage html
    echo -e "${GREEN}HTML report generated: htmlcov/index.html${NC}"
    echo
fi

# Exit with error if any tests failed
if [ ${#FAILED_TESTS[@]} -gt 0 ]; then
    exit 1
fi

echo -e "${GREEN}All tests passed!${NC}"
exit 0
