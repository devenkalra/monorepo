# Tests

This directory contains all test files and testing utilities.

## Directory Structure

- **integration/** - Integration tests (symlink to people/tests/)
- **unit/** - Unit tests (future)
- **scripts/** - Standalone test scripts
- **fixtures/** - Test data and fixtures

## Running Tests

### All Integration Tests
```bash
cd /home/ubuntu/monorepo/data-backend
./tests/run_tests.sh
```

### Specific Test Class
```bash
docker compose -f docker-compose.local.yml exec backend \
  python manage.py test people.tests.test_integration_full_stack.AllEntityTypesCRUDTest
```

### Individual Test Scripts
```bash
python tests/scripts/test_search.py
```

See [Testing Documentation](../docs/testing/) for more details.
