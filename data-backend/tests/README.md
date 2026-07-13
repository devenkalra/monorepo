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

### Backend API E2E (Live HTTP)
```bash
python tests/integration/run_e2e_health_security.py
python tests/integration/run_e2e_section_c_people_core.py
python tests/integration/run_e2e_suite_d_relations_graph.py
python tests/integration/run_e2e_suite_e_search_hybrid.py
python tests/integration/run_e2e_suite_f_import_export_sync.py
python tests/integration/run_e2e_suite_g_import_export_async.py
python tests/integration/seed_frontend_sample_data.py
```

Optional environment variables:
- `E2E_BASE_URL` (default: `http://localhost:8000`)
- `E2E_EMAIL` (default: `e2e@kalra.com`)
- `E2E_PASSWORD` (default: `TestPassword`)
- `E2E_API_LOG_FILE` (default base path: `tests/integration/e2e/e2e_api_calls.md`)
  - A timestamp is appended automatically per run, e.g. `e2e_api_calls_20260712_201530.md`.

See [Testing Documentation](../docs/testing/) for more details.

## E2E Authoring Standards

- E2E test-writing and logging conventions are documented in
  [integration/e2e/TEST_METHODOLOGY.md](integration/e2e/TEST_METHODOLOGY.md).
- Use this as the required baseline for new E2E tests.
