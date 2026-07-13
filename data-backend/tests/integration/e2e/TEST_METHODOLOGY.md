# E2E Test Methodology and Logging Patterns

This document defines the required patterns for writing live HTTP E2E tests in this repository.

## Goals

- Keep test intent obvious (BDD-style behavior and expected outcomes).
- Keep API-call logs compact but complete.
- Make failures diagnosable from logs without rerunning with extra debug output.
- Keep test data realistic enough to catch serialization/search/import edge cases.

## Test Authoring Patterns

### 1) BDD header at file top

Each E2E test file should start with a concise BDD overview describing:

- Feature
- Scenarios
- Given/When/Then behavior

### 2) Per-test docstring metadata

Each test method should include docstring metadata lines consumed by the logger:

- `log_title:` short primary title used in log heading
- `id:` stable test ID (for example `C-01`)
- `feature:` subsystem or capability under test
- `scenario:` behavior under test
- `objective:` explicit validation goal

Example:

```text
log_title: Entity CRUD
id: C-01
feature: People Core CRUD
scenario: Create/retrieve/patch/delete for every entity type
objective: Validate typed endpoints and generic endpoint parity
```

### 3) Realistic payloads

Use realistic names/values and punctuation (apostrophes, commas, hyphens, symbols) to validate parsing/normalization and avoid toy-data blind spots.

### 4) CRUD matrix via subtests

For families of similar entities, use a matrix + `subTest(...)` loop:

- one payload matrix definition
- one shared flow (create/get/patch/delete)
- entity-specific assertions from matrix metadata

### 5) Explicit call-purpose context

Wrap each API call with `client.log_call_purpose(...)` so logs show why the call exists.

Use compact wording:

- `Create Person`
- `Get Person by ID`
- `Update profession`
- `Delete Person`
- `Confirm deleted (404)`

### 6) Compact subtest phrases

Set subtest phrase per loop iteration with short wording:

- `Person CRUD`
- `Note CRUD`

### 7) Deterministic cleanup

Track created entities/tags and delete them in reverse order, best-effort.

### 8) Stable assertions

Assert status code first, then response structure/fields.
Use stringified comparisons when backend formatting can vary (for example decimal vs float string form).

## Logging Methodology

## Run-level behavior

- Log file path can be controlled by `E2E_API_LOG_FILE`.
- A new timestamped file is created per run.
- All client instances in the same Python test run append to that same file.
- Sensitive request fields/tokens are masked.

## Entry format (compact, no loss of information)

Each call logs:

- Title (`log_title - subtest - action`)
- Test function name
- Metadata (`feature`, `scenario`, `objective`, `id`, plus `Sub`, `Action`)
- Request: call number, HTTP verb, path, URL, headers, body
- Response: status, body (truncated only for very large payloads)

Compact labels currently used:

- `Req`, `Res`
- `Call`, `Verb`, `Path`, `Url`
- `Sub`, `Action`

## Failure tagging in title

After each test method completes, all log entry titles for that method are post-processed:

- Failed test: title is prefixed with `[FAIL]`
- Passed test: no failure prefix

This guarantees that failures are visible in the title even for calls logged before the assertion failure.

## Required Conventions for New E2E Tests

- Include BDD file header.
- Include per-test metadata docstring fields.
- Use compact `log_title`, compact subtest phrases, and compact action phrases.
- Use `log_call_purpose(...)` for significant API calls.
- Ensure teardown marks outcome via `client.finalize_test_outcome(...)`.
- Prefer realistic payloads over synthetic placeholders.
