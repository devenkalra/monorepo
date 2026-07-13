# Backend E2E Test Plan

## Purpose
Define an exhaustive end-to-end API test suite for the backend only (no frontend), using real datastore writes and reads.

Primary goals:
- Validate all API operations across enabled backend apps.
- Validate cross-store side effects (PostgreSQL, MeiliSearch, Neo4j, Redis/Celery where applicable).
- Validate authentication, authorization, filtering, pagination, sorting, import/export, async tasks, and failure paths.

## Test Account And Execution Model
- Primary test user: e2e@kalra.com
- Password: TestPassword
- Tests will authenticate through API endpoints and use real access tokens/cookies.
- Tests will run against a live backend stack and write real records.

Recommended execution mode:
- Use a dedicated E2E test marker/tag and deterministic naming convention with a run id, for example: E2E-RUN-<timestamp>.
- All created entities/tags/lists/etc. include this marker in display/tags so cleanup can be deterministic.
- Cleanup is mandatory at suite start and suite end.

## Scope
In scope:
- API namespaces under:
  - /api/auth
  - /api/auth/registration
  - /api/health
  - /api (people app)
  - /api/cad
  - /api/food
  - /api/mail
  - /api/wa-assistant

Out of scope for this phase:
- Frontend rendering/UX behavior.
- Browser-based OAuth UI flows (server-side callback endpoint behavior remains testable with API-level requests).

## Environment Prerequisites
- Running services: backend, db, redis, meilisearch, neo4j, celery worker.
- Seed account exists: e2e@kalra.com / TestPassword.
- Meili index ready and writable.
- Neo4j reachable for relation lookups.
- For async tests: celery worker and redis healthy.

## Datastores And Assertions
For each relevant scenario, assert in one or more stores:
- PostgreSQL:
  - API-visible record state and ownership boundaries.
- MeiliSearch:
  - Searchability for created/updated/deleted entities.
  - Hybrid behavior for partial and semantic-like queries.
- Neo4j:
  - Relation-based query behavior through API endpoints that depend on graph lookups.
- Redis/Celery:
  - Task progress and cancellation behavior for async imports/exports/reindex.

## Test Suite Structure
- Suite A: Platform and Auth
- Suite B: Health and Security
- Suite C: People Domain Core CRUD
- Suite D: Relations and Graph-dependent Queries
- Suite E: Search and Hybrid Ranking
- Suite F: Import/Export Sync
- Suite G: Import/Export Async and Task Lifecycle
- Suite H: Uploads and Media Attachments
- Suite I: CAD API
- Suite J: Food API
- Suite K: Mail Archive API
- Suite L: WhatsApp Webhook API
- Suite M: Cross-user Authorization and Isolation
- Suite N: Cleanup and Idempotency

## Exhaustive Operation Matrix

### A. Platform And Auth
Endpoints:
- POST /api/auth/login/
- POST /api/auth/logout/
- GET /api/auth/user/
- POST /api/auth/password/change/
- POST /api/auth/password/reset/
- POST /api/auth/password/reset/confirm/
- POST /api/auth/registration/
- POST /api/auth/token/refresh/
- GET /api/auth/csrf/

Coverage:
- Valid login, invalid login, missing credentials.
- Authenticated user profile fetch.
- Token refresh happy path and expired/invalid token path.
- Logout and token invalidation behavior.
- Registration conflict scenarios.

Assertions:
- Correct status codes and payload shapes.
- Session/token behavior across requests.

### B. Health And Security
Endpoints:
- GET /api/health/
- GET /api/health/detailed/

Coverage:
- Service health shape and required fields.
- Unauthorized access behavior on protected endpoints.

### C. People Domain Core CRUD
Viewsets/endpoints:
- /api/entities/
- /api/people/
- /api/notes/
- /api/locations/
- /api/movies/
- /api/books/
- /api/containers/
- /api/assets/
- /api/orgs/
- /api/tags/
- /api/entities/recent/

Coverage for each type:
- Create, retrieve, list, update, partial_update, delete.
- Filter/search fields defined for each viewset.
- Pagination and sorting behavior where supported.
- Serializer shape checks for required fields.

Entity-specific actions:
- GET /api/entities/{id}/relations/
- GET /api/entities/{id}/llm_context/

Tag behavior:
- CRUD by name-based lookup.
- Deleting a tag removes tag from user entities and updates counts.

Recent endpoint:
- limit mode.
- page/page_size mode.
- sort_by variants.

### D. Relations And Graph-dependent Queries
Endpoints:
- /api/relations/
- relation-filtered search/count/delete_all via /api/search

Coverage:
- Create/update/delete relations between owned entities.
- Reject relation creation when one or both entities are not owned by caller.
- Verify relation-filter query paths that rely on graph lookups.

Assertions:
- API result correctness.
- Graph-dependent query behavior through API output.

### E. Search And Hybrid Ranking
Endpoints:
- GET /api/search/
- GET /api/search/count/
- POST /api/search/delete_all/

Coverage:
- Text queries (full and partial, case-insensitive).
- Semantic-like query behavior under hybrid settings.
- Filters: type, tags (hierarchical), display, first_name, last_name, gender.
- Relation filters: relation_entity + relation_type.
- Sorting and pagination combinations.

Assertions:
- Result set correctness.
- Count consistency with list filters.
- delete_all removes exactly filtered records.
- Meili reflects create/update/delete lifecycle.

### F. Import/Export Sync
Endpoints:
- POST /api/entities/import_data/
- GET /api/entities/export/
- POST /api/entities/export-selected/

Coverage:
- Valid legacy export import.
- Valid v2 import operations.
- Re-import idempotency expectations.
- Schema validation failures and user mismatch failures.
- export-selected with max_hops variations.

Assertions:
- Stats payload correctness.
- No unintended duplication on repeated imports.
- Export payload shape, ownership correctness, relation closure correctness.

### G. Import/Export Async And Task Lifecycle
Endpoints:
- POST /api/entities/import-async/
- POST /api/entities/export-async/
- POST /api/entities/export-selected-async/
- GET /api/entities/tasks/{task_id}/progress/
- GET /api/entities/tasks/{task_id}/download/
- POST /api/entities/tasks/{task_id}/cancel/
- POST /api/entities/reindex/

Coverage:
- Task creation and progress polling.
- Success, failure, pending, and cancellation states.
- Download flow and expiry/not-found behavior.
- Reindex flow and post-index search verification.

Assertions:
- Task status transitions.
- Output artifacts available when expected.

### H. Uploads And Media Attachments
Endpoints:
- POST /api/upload/
- POST /api/upload/ with entity_id

Coverage:
- Upload without file error path.
- Upload with supported files.
- Entity-scoped file behavior when entity_id is supplied.

Assertions:
- Response metadata includes stored path/urls as applicable.
- Entity retrieval returns expected attachment/photo/url structures after updates.

### I. CAD API
Endpoints:
- /api/cad/models/
- POST /api/cad/models/{id}/render
- GET /api/cad/models/{id}/meta
- GET /api/cad/models/{id}/geometry
- GET /api/cad/models/{id}/export/stl
- GET /api/cad/models/{id}/geometry-part/{index}
- /api/cad/scenes/
- GET /api/cad/textures/{filename}
- GET /api/cad/env/{filename}

Coverage:
- CAD model CRUD with script validation.
- Render happy path and render failure path.
- Geometry fetch before and after render.
- Scene config CRUD behavior.
- Auth-protected static asset serving.

### J. Food API
Endpoints:
- /api/food/spots/
- /api/food/foods/
- /api/food/spot-lists/
- /api/food/food-lists/
- /api/food/media/
- /api/food/reviews/
- /api/food/food-spot-ratings/

Coverage:
- CRUD for each viewset.
- Ownership and private/public visibility rules.
- Search/filter/order behavior on spots/foods.
- Rating upsert semantics.

### K. Mail Archive API
Endpoints:
- /api/mail/accounts/
- POST /api/mail/accounts/{id}/test_connection/
- /api/mail/configs/
- POST /api/mail/configs/{id}/import_now/
- /api/mail/emails/
- GET /api/mail/emails/task_progress/?task_id=...
- POST /api/mail/emails/cancel_task/

Coverage:
- Account/config CRUD and ownership boundaries.
- test_connection success/failure paths.
- import_now task kickoff constraints (inactive account/config).
- email listing filters, sorting, pagination.
- task progress and cancellation behavior.

### L. WhatsApp Webhook API
Endpoint:
- GET/POST /api/wa-assistant/webhook/

Coverage:
- GET verification success with valid token.
- GET verification failure with invalid token.
- POST invalid JSON, non-whatsapp object, valid message payload.
- Duplicate message id deduplication behavior.

### M. Cross-user Authorization And Isolation
Coverage across all protected resources:
- User A cannot read/update/delete User B resources.
- Relation creation blocked across mixed ownership.
- Search/export results never leak other user data.
- Task endpoints scoped to caller where applicable.

### N. Cleanup And Idempotency
Coverage:
- Start-of-suite cleanup for prior E2E_RUN markers.
- End-of-suite cleanup for created records.
- Repeatability: suite can run multiple times without manual intervention.

## Data Strategy
- Use deterministic fixtures for core entity graph:
  - Person, Note, Location, Movie, Book, Container, Asset, Org
  - Rich relation network and hierarchical tags.
- Use import fixtures:
  - Legacy export payload.
  - v2 operation payload (create/update/replace/delete).
- Use dedicated marker tag on all generated records.

## Proposed Execution Order
1. Auth and health baseline.
2. Core people CRUD and relations.
3. Search/count/delete_all with Meili verification.
4. Import/export sync flows.
5. Async task flows and reindex.
6. Upload/media flows.
7. CAD, food, mail, whatsapp namespaces.
8. Cross-user isolation checks.
9. Cleanup and rerun smoke to confirm idempotency.

## Reporting
Each suite should report:
- Endpoint coverage count.
- Passed/failed test count.
- Store-level verification results (DB, Meili, graph/task where applicable).
- Artifacts for failures: request/response payloads, task ids, and relevant IDs.

## Deliverables After This Plan
- E2E test harness and shared API client utilities.
- Fixture factory for deterministic entities and relations.
- Full backend E2E suite implementation matching this matrix.
- CI job that can run targeted suites and full exhaustive run.
