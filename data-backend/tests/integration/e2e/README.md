# Backend API E2E Tests

This folder contains live API end-to-end tests that hit the running backend over HTTP.

## Current Section
- Health and Security tests

## Preconditions
- Backend stack is running (including auth backend).
- Test account exists:
  - email: e2e@kalra.com
  - password: TestPassword

## Run
From `data-backend`:

```bash
python tests/integration/run_e2e_health_security.py
python tests/integration/run_e2e_suite_d_relations_graph.py
python tests/integration/run_e2e_suite_e_search_hybrid.py
python tests/integration/run_e2e_suite_f_import_export_sync.py
python tests/integration/run_e2e_suite_g_import_export_async.py
```

## Seed Frontend Demo Data (API-only)

Populate the backend with realistic sample entities (people, notes, orgs, assets, etc.) plus uploaded media,
attachments, locations, and relations for interactive frontend testing.

From `data-backend`:

```bash
python tests/integration/seed_frontend_sample_data.py
```

Optional arguments:

```bash
python tests/integration/seed_frontend_sample_data.py --tag FD01
python tests/integration/seed_frontend_sample_data.py --no-relations
python tests/integration/seed_frontend_sample_data.py --base-url http://localhost:8000 --email e2e@kalra.com --password TestPassword
```

Notes:
- If `--tag` is omitted, the script auto-picks a compact tag (`FD01`, `FD02`, ...).
- Seeded entity display names are clean and do not include the dataset tag.
- Before seeding, the script deletes all existing tags via `/api/tags/` cleanup.
- Seeded media now includes themed titles like `The Godfather`, `Shakespeare in Love`, and `Game of Thrones`, with richer cross-entity relations.

## Optional Environment Variables
- `E2E_BASE_URL` (default: `http://localhost:8000`)
- `E2E_EMAIL` (default: `e2e@kalra.com`)
- `E2E_PASSWORD` (default: `TestPassword`)
- `E2E_TIMEOUT_SECONDS` (default: `20`)
- `E2E_API_LOG_FILE` (default base path: `tests/integration/e2e/e2e_api_calls.md`)
  - A timestamp is appended automatically per run, e.g. `e2e_api_calls_20260712_201530.md`.

## Notes
- Tests validate public health endpoints, auth-required protection for private APIs,
  login success/failure, authenticated user endpoint, CSRF endpoint, and token refresh when available.
- This suite intentionally performs real HTTP calls and does not mock backend services.

## Methodology and Patterns
- Follow the required patterns in [TEST_METHODOLOGY.md](TEST_METHODOLOGY.md).
- New tests should use compact metadata titles, compact subtest/action phrases,
  and explicit per-call purpose logging.
- Log titles are automatically marked with `[FAIL]` when a test fails.
