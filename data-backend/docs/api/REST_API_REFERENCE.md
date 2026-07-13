# bldrdojo Data Backend REST API Reference

This document inventories the REST APIs exposed by the Django backend in `data-backend`.
It is intended as the starting point for building an MCP server in front of this backend.

## Base URL and Conventions

- Local base URL: `http://localhost:8000`
- API root prefix: `/api/`
- Most endpoints use trailing slashes (DRF `DefaultRouter` behavior).
- Auth model: JWT/Bearer for protected endpoints.
- Unless noted otherwise, API endpoints require authentication.

## Authentication and Session Endpoints

### Health

- `GET /api/health/`
- `GET /api/health/detailed/`

### CSRF helper for SPA flows

- `GET /api/auth/csrf/`

### dj-rest-auth endpoints (mounted at `/api/auth/`)

Mounted via `include('dj_rest_auth.urls')` and `include('dj_rest_auth.registration.urls')`.
Common endpoints available in this setup:

- `POST /api/auth/login/`
- `POST /api/auth/logout/`
- `GET /api/auth/user/`
- `POST /api/auth/password/change/`
- `POST /api/auth/password/reset/`
- `POST /api/auth/password/reset/confirm/`
- `POST /api/auth/registration/`

Token refresh:

- `POST /api/auth/token/refresh/`

### Google OAuth

- `POST /api/auth/google/`
- `GET /api/auth/google/url/`
- `POST /api/auth/google/callback/`

## People Domain APIs (`/api/`)

## Standard CRUD Resources

The following are DRF router resources. Unless noted, they provide:

- `GET /<resource>/`
- `POST /<resource>/`
- `GET /<resource>/{id}/`
- `PUT /<resource>/{id}/`
- `PATCH /<resource>/{id}/`
- `DELETE /<resource>/{id}/`

Resources:

- `/api/entities/`
- `/api/people/`
- `/api/notes/`
- `/api/locations/`
- `/api/movies/`
- `/api/books/`
- `/api/containers/`
- `/api/assets/`
- `/api/orgs/`
- `/api/relations/`
- `/api/tags/` (lookup field is tag name)

Additional non-router people endpoints:

- `GET /api/entities/recent/`
- `GET /api/geocode/forward/`
- `GET /api/geocode/reverse/`

## Custom Actions in People API

### Entity custom actions

- `GET /api/entities/{id}/relations/`
- `POST /api/entities/import_data/`
- `GET /api/entities/export/`
- `POST /api/entities/import-async/`
- `POST /api/entities/export-async/`
- `POST /api/entities/export-selected-async/`
- `POST /api/entities/export-selected/`
- `GET /api/entities/tasks/{task_id}/download/`
- `GET /api/entities/tasks/{task_id}/progress/`
- `POST /api/entities/tasks/{task_id}/cancel/`
- `POST /api/entities/reindex/`

### Note custom actions

- `POST /api/notes/import_file/`

### Org custom actions

- `POST /api/orgs/import_file/`
- `POST /api/orgs/semantic_search/`

### Search endpoints

`SearchViewSet` exposes list plus custom actions:

- `GET /api/search/` (search + filters + pagination)
- `GET /api/search/count/`
- `POST /api/search/delete_all/`

## CAD APIs (`/api/cad/`)

## Router resources

- `/api/cad/models/` (CRUD)
- `/api/cad/scenes/` (list/retrieve/create/update/delete)

## CAD model custom actions

- `POST /api/cad/models/{id}/render/`
- `POST /api/cad/models/{id}/render` (explicit no-trailing-slash route)
- `GET /api/cad/models/{id}/meta/`
- `GET /api/cad/models/{id}/geometry/`
- `GET /api/cad/models/{id}/export/stl/`
- `GET /api/cad/models/{id}/geometry-part/{index}/`

## CAD static asset endpoints (auth protected)

- `GET /api/cad/textures/{filename}`
- `GET /api/cad/env/{filename}`

## Food APIs (`/api/food/`)

Router resources:

- `/api/food/spots/`
- `/api/food/foods/`
- `/api/food/spot-lists/`
- `/api/food/food-lists/`
- `/api/food/media/`
- `/api/food/reviews/`
- `/api/food/food-spot-ratings/`

These are standard ModelViewSet endpoints (`list/create/retrieve/update/partial_update/destroy`).
Filtering/search/ordering is implemented on several resources (notably spots and foods).

## Mail Archive APIs (`/api/mail/`)

Router resources:

- `/api/mail/accounts/`
- `/api/mail/configs/`
- `/api/mail/emails/` (read-only model viewset)

Custom actions:

- `POST /api/mail/accounts/{id}/test_connection/`
- `POST /api/mail/configs/{id}/import_now/`
- `GET /api/mail/emails/task_progress/?task_id={task_id}`
- `POST /api/mail/emails/cancel_task/`

`/api/mail/emails/` supports query filters such as:

- `account`
- `from`
- `to`
- `subject`
- `q`
- `has_attachments`
- `date_from`
- `date_to`
- `sort_by`
- `page`, `page_size`

## WhatsApp Assistant API (`/api/wa-assistant/`)

- `GET /api/wa-assistant/webhook/` (Meta webhook verification)
- `POST /api/wa-assistant/webhook/` (incoming message/events)

## Non-API Pages (for completeness)

- `GET /` (login page)
- `GET /login/`
- `GET /api-tester/`

## Notes for MCP Server Design

1. Resource ownership is user-scoped for most models. MCP tools should always provide auth context.
2. Async workflows are task-based (`task_id`, progress polling, cancel endpoints).
3. A few endpoints intentionally return file payloads (exports, CAD geometry/STL).
4. The most useful MCP abstractions are likely:
   - entity search/list/count/delete
   - entity import/export (sync + async)
   - relation inspection
   - CAD render and geometry retrieval
   - mail import orchestration + task polling

## Source of Truth

URL definitions are implemented in:

- `config/urls.py`
- `people/urls.py`
- `cad/urls.py`
- `food/urls.py`
- `mail_archive/urls.py`
- `wa_assistant/urls.py`
