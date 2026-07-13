# bldrdojo MCP Tool Spec

Version: 0.1.0
Status: Draft (implementation-ready)
Source API inventory: `data-backend/docs/api/REST_API_REFERENCE.md`

## Purpose

Define a Model Context Protocol (MCP) server surface in front of the bldrdojo Django backend so LLM clients can safely and consistently perform authenticated operations.

## Scope

This spec focuses on high-value tools for:

- auth bootstrap and identity
- entity CRUD and retrieval
- relation lookups
- search and bulk operations
- async job orchestration
- CAD rendering workflows
- mail import workflows
- health checks

## MCP Server Assumptions

- Transport: stdio or streamable HTTP (implementation choice).
- All tool calls execute with a user auth context.
- Backend base URL is server-configured (default local: `http://localhost:8000`).
- MCP server stores auth tokens per session/user context (not in tool args unless explicitly noted).

## Common Error Model

All tools should return errors in a normalized shape:

```json
{
  "ok": false,
  "error": {
    "code": "AUTH_REQUIRED|VALIDATION_ERROR|NOT_FOUND|CONFLICT|UPSTREAM_ERROR|TIMEOUT|INTERNAL",
    "message": "Human-readable message",
    "status": 401,
    "details": {}
  }
}
```

Success shape:

```json
{
  "ok": true,
  "data": {}
}
```

## Authentication Strategy

Preferred login flow for MCP:

1. `auth.login` -> `POST /api/auth/login/`
2. Persist access + refresh in MCP session store.
3. Auto-refresh via `POST /api/auth/token/refresh/` on 401/token expiry.

## Tool Catalog

## 1) Health and Session

### `system.health`

- Purpose: verify backend availability.
- Backend: `GET /api/health/`
- Input schema:

```json
{ "type": "object", "properties": {}, "additionalProperties": false }
```

- Output data:

```json
{
  "status": "healthy",
  "service": "bldrdojo-backend"
}
```

### `system.health_detailed`

- Backend: `GET /api/health/detailed/`
- Input: none
- Output data includes dependency checks:

```json
{
  "status": "healthy|unhealthy",
  "service": "bldrdojo-backend",
  "checks": {
    "database": "healthy|unhealthy",
    "cache": "healthy|unhealthy"
  }
}
```

### `auth.login`

- Backend: `POST /api/auth/login/`
- Input schema:

```json
{
  "type": "object",
  "required": ["email", "password"],
  "properties": {
    "email": { "type": "string", "format": "email" },
    "password": { "type": "string" }
  },
  "additionalProperties": false
}
```

- Output data:

```json
{
  "access": "jwt",
  "refresh": "jwt",
  "user": {}
}
```

### `auth.logout`

- Backend: `POST /api/auth/logout/`
- Input: none
- Output: `{ "logged_out": true }`

### `auth.current_user`

- Backend: `GET /api/auth/user/`
- Input: none
- Output: backend user payload.

### `auth.refresh`

- Backend: `POST /api/auth/token/refresh/`
- Input schema:

```json
{
  "type": "object",
  "required": ["refresh"],
  "properties": {
    "refresh": { "type": "string" }
  },
  "additionalProperties": false
}
```

- Output: `{ "access": "jwt" }`

## 2) Entity Tools

### `entities.list`

- Backend: `GET /api/entities/`
- Input schema:

```json
{
  "type": "object",
  "properties": {
    "search": { "type": "string", "description": "Maps to ?search=" },
    "type": { "type": "string" },
    "display": { "type": "string" },
    "ordering": { "type": "string" },
    "page": { "type": "integer", "minimum": 1 },
    "page_size": { "type": "integer", "minimum": 1, "maximum": 100 }
  },
  "additionalProperties": false
}
```

- Output: paginated entity list (server-normalized).

### `entities.get`

- Backend: `GET /api/entities/{id}/`
- Input:

```json
{
  "type": "object",
  "required": ["id"],
  "properties": {
    "id": { "type": "string", "format": "uuid" }
  },
  "additionalProperties": false
}
```

### `entities.create`

- Backend: `POST /api/entities/`
- Input:

```json
{
  "type": "object",
  "required": ["payload"],
  "properties": {
    "payload": { "type": "object" }
  },
  "additionalProperties": false
}
```

### `entities.update`

- Backend: `PATCH /api/entities/{id}/`
- Input:

```json
{
  "type": "object",
  "required": ["id", "payload"],
  "properties": {
    "id": { "type": "string", "format": "uuid" },
    "payload": { "type": "object" }
  },
  "additionalProperties": false
}
```

### `entities.delete`

- Backend: `DELETE /api/entities/{id}/`
- Input: `{ "id": "uuid" }`
- Output: `{ "deleted": true }`

### `entities.recent`

- Backend: `GET /api/entities/recent/`
- Input supports `limit`, `page`, `page_size`, `sort_by`.

### `entities.relations`

- Backend: `GET /api/entities/{id}/relations/`
- Input: `{ "id": "uuid" }`
- Output: outgoing/incoming relation arrays.

## 3) Search and Bulk Tools

### `search.query`

- Backend: `GET /api/search/`
- Input schema:

```json
{
  "type": "object",
  "properties": {
    "q": { "type": "string" },
    "type": { "type": "string", "description": "comma-separated types" },
    "tags": { "type": "string", "description": "comma-separated tags" },
    "display": { "type": "string" },
    "sort_by": { "type": "string" },
    "relation_entity": { "type": "string", "format": "uuid" },
    "relation_type": { "type": "string" },
    "page": { "type": "integer", "minimum": 1 },
    "page_size": { "type": "integer", "minimum": 1, "maximum": 100 }
  },
  "additionalProperties": false
}
```

### `search.count`

- Backend: `GET /api/search/count/`
- Input: same filter params as `search.query` (without pagination).
- Output: `{ "count": 123 }`

### `search.delete_all`

- Backend: `POST /api/search/delete_all/` with query params.
- Input: same filter params.
- Output: `{ "deleted": 42 }`

## 4) Import/Export and Async Tasks

### `entities.import_sync`

- Backend: `POST /api/entities/import_data/` (multipart file upload)
- Input schema:

```json
{
  "type": "object",
  "required": ["file_path"],
  "properties": {
    "file_path": { "type": "string", "description": "Path on MCP host" }
  },
  "additionalProperties": false
}
```

### `entities.export_sync`

- Backend: `GET /api/entities/export/`
- Input:

```json
{
  "type": "object",
  "properties": {
    "save_to": { "type": "string", "description": "Optional file path" }
  },
  "additionalProperties": false
}
```

- Output: either raw JSON object or `{file_path, bytes}` depending on MCP implementation mode.

### `entities.export_selected_sync`

- Backend: `POST /api/entities/export-selected/`
- Input:

```json
{
  "type": "object",
  "required": ["entity_ids"],
  "properties": {
    "entity_ids": {
      "type": "array",
      "items": { "type": "string", "format": "uuid" },
      "minItems": 1
    },
    "max_hops": { "type": "integer", "minimum": 0, "default": 1 },
    "save_to": { "type": "string" }
  },
  "additionalProperties": false
}
```

### `entities.import_async`

- Backend: `POST /api/entities/import-async/`
- Input: `{ "file_path": "..." }`
- Output: `{ "task_id": "...", "message": "..." }`

### `entities.export_async`

- Backend: `POST /api/entities/export-async/`
- Input: none
- Output: `{ "task_id": "..." }`

### `entities.export_selected_async`

- Backend: `POST /api/entities/export-selected-async/`
- Input: `{ "entity_ids": ["..."], "max_hops": 1 }`

### `tasks.progress`

- Backend: `GET /api/entities/tasks/{task_id}/progress/`
- Input: `{ "task_id": "string" }`

### `tasks.cancel`

- Backend: `POST /api/entities/tasks/{task_id}/cancel/`
- Input: `{ "task_id": "string" }`

### `tasks.download_export`

- Backend: `GET /api/entities/tasks/{task_id}/download/`
- Input: `{ "task_id": "string", "save_to": "optional path" }`

### `entities.reindex`

- Backend: `POST /api/entities/reindex/`
- Input: none
- Output: `{ "task_id": "..." }`

## 5) CAD Tools

### `cad.models.list`

- Backend: `GET /api/cad/models/`

### `cad.models.get`

- Backend: `GET /api/cad/models/{id}/`

### `cad.models.create`

- Backend: `POST /api/cad/models/`
- Input includes script + metadata payload.

### `cad.models.update`

- Backend: `PATCH /api/cad/models/{id}/`

### `cad.models.delete`

- Backend: `DELETE /api/cad/models/{id}/`

### `cad.render`

- Backend: `POST /api/cad/models/{id}/render/`
- Input schema:

```json
{
  "type": "object",
  "required": ["id"],
  "properties": {
    "id": { "type": "integer" },
    "parameters": { "type": "object", "default": {} },
    "debug": { "type": "boolean", "default": false }
  },
  "additionalProperties": false
}
```

### `cad.geometry`

- Backend: `GET /api/cad/models/{id}/geometry/`
- Output: file stream or saved file path.

### `cad.meta`

- Backend: `GET /api/cad/models/{id}/meta/`

### `cad.export_stl`

- Backend: `GET /api/cad/models/{id}/export/stl/`

### `cad.geometry_part`

- Backend: `GET /api/cad/models/{id}/geometry-part/{index}/`

### `cad.scenes.list|get|create|update|delete`

- Backends:
  - `GET /api/cad/scenes/`
  - `GET /api/cad/scenes/{id}/`
  - `POST /api/cad/scenes/`
  - `PUT/PATCH /api/cad/scenes/{id}/`
  - `DELETE /api/cad/scenes/{id}/`

## 6) Mail Archive Tools

### `mail.accounts.list|create|update|delete|get`

- Backend resource: `/api/mail/accounts/`

### `mail.accounts.test_connection`

- Backend: `POST /api/mail/accounts/{id}/test_connection/`

### `mail.configs.list|create|update|delete|get`

- Backend resource: `/api/mail/configs/`

### `mail.configs.import_now`

- Backend: `POST /api/mail/configs/{id}/import_now/`

### `mail.emails.list`

- Backend: `GET /api/mail/emails/`
- Supports filters: `account`, `from`, `to`, `subject`, `q`, `has_attachments`, `date_from`, `date_to`, `sort_by`, `page`, `page_size`.

### `mail.emails.get`

- Backend: `GET /api/mail/emails/{id}/`

### `mail.tasks.progress`

- Backend: `GET /api/mail/emails/task_progress/?task_id=...`

### `mail.tasks.cancel`

- Backend: `POST /api/mail/emails/cancel_task/`
- Input: `{ "task_id": "string" }`

## 7) WhatsApp Webhook Ops Tools (Optional/Admin)

These are typically for server integration tests rather than end-user chat tools.

### `wa.webhook.verify_probe`

- Backend: `GET /api/wa-assistant/webhook/`
- Input: passthrough query params (`hub.mode`, `hub.verify_token`, `hub.challenge`).

### `wa.webhook.inject_event`

- Backend: `POST /api/wa-assistant/webhook/`
- Input: raw Meta-like event payload.

## Recommended MVP Tool Set

Implement first:

1. `system.health`
2. `auth.login`
3. `auth.current_user`
4. `search.query`
5. `search.count`
6. `entities.get`
7. `entities.list`
8. `entities.create`
9. `entities.update`
10. `entities.delete`
11. `entities.relations`
12. `entities.export_selected_sync`
13. `tasks.progress`
14. `cad.render`
15. `cad.geometry`
16. `mail.emails.list`

## Security and Guardrails

- Always enforce user-scoped auth context at MCP layer.
- Redact tokens and secrets from tool outputs/logs.
- For destructive tools (`entities.delete`, `search.delete_all`), add optional confirmation guard in MCP server config.
- Validate file paths for import/export tools to prevent path traversal.

## Implementation Notes

- Build one shared HTTP client with:
  - auth header injection
  - token refresh retry once on 401
  - standard timeout and retry policy for idempotent GETs
- Normalize backend response shapes into `{ok, data}` for all tools.
- Preserve backend `task_id` contract exactly for async orchestration.

## Next Step

After this spec, generate `tools.json` (machine-readable MCP manifest) directly from the catalog above and scaffold handlers.

## Generated Artifacts

The initial artifacts referenced by this spec now exist:

- `data-backend/docs/api/tools.json` (machine-readable MVP manifest)
- `data-backend/mcp_server/server.py` (transport-agnostic execution scaffold)
- `data-backend/mcp_server/README.md` (usage and next steps)
- `data-backend/mcp_server/transport_stdio.py` (MCP-style stdio JSON-RPC transport)
- `data-backend/mcp_server/__main__.py` (module entrypoint; run with `python -m mcp_server`)
