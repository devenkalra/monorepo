# Local Full-System Startup Runbook (bldrdojo)

This document describes how to bring up the full local system from a cold start using Docker Compose.

## Scope

This runbook starts the full local stack defined in:

- `docker-compose.local.yml` (repo root)

Services included:

- db (Postgres)
- redis
- meilisearch
- neo4j
- backend (Django)
- celery-worker
- frontend (Nginx)
- email-frontend-dev (Vite)

## Prerequisites

1. Docker Desktop is installed and running.
2. Run commands from the monorepo root.
3. Required env file exists:
   - `data-backend/.env`
4. Required host ports are free:
   - 80 (frontend)
   - 8000 (backend)
   - 5432 (postgres)
   - 6380 (redis)
   - 7474, 7687 (neo4j)
   - 7701 (meilisearch)
   - 5176 (email frontend dev)

## 1) Start Everything

From repo root:

```powershell
docker compose -f docker-compose.local.yml up -d
```

## 2) Verify Service Status

```powershell
docker compose -f docker-compose.local.yml ps
```

Expected steady state:

- db, redis, meilisearch, neo4j, frontend, backend are healthy
- celery-worker may show health: starting briefly after startup
- email-frontend-dev is up

## 3) Verify Endpoints

```powershell
# Frontend (Nginx)
Invoke-WebRequest -UseBasicParsing http://localhost

# Backend health
Invoke-WebRequest -UseBasicParsing http://localhost:8000/api/health/
```

Expected:

- Frontend returns 200
- Backend health returns 200

## Common Startup Issues and Fixes

### A) Docker daemon not running

Symptom:

- compose fails with pipe/daemon connection errors

Fix:

1. Start Docker Desktop.
2. Retry startup command.

### B) Port already allocated

Symptom:

- compose fails with bind errors (for example 5432 or 8000)

Fix:

1. Identify conflicts:

```powershell
docker ps --format "table {{.Names}}\t{{.Ports}}"
Get-NetTCPConnection -State Listen -LocalPort 8000,5432,7474,7687,80,5176,6380,7701 |
  Select-Object LocalAddress,LocalPort,OwningProcess
```

2. Stop conflicting containers/processes.

Examples seen locally:

- `zk_postgres` using 5432
- `zk_neo4j` using 7474/7687
- local python process using 8000

### C) Frontend returns 502 after startup

Symptom:

- `http://localhost` returns 502 while backend is starting/restarting

Fix:

```powershell
docker compose -f docker-compose.local.yml restart frontend
```

Then retry:

```powershell
Invoke-WebRequest -UseBasicParsing http://localhost
```

### D) Service exits or keeps restarting

Check logs:

```powershell
docker compose -f docker-compose.local.yml logs <service> --tail 200
```

Examples:

```powershell
docker compose -f docker-compose.local.yml logs backend --tail 200
docker compose -f docker-compose.local.yml logs neo4j --tail 200
```

## Clean Restart (without deleting data)

Use this if network attachments or dependency ordering look broken.

```powershell
docker compose -f docker-compose.local.yml down
docker compose -f docker-compose.local.yml up -d
```

## Full Reset (deletes local data volumes)

Use only when you intentionally want a clean data state.

```powershell
docker compose -f docker-compose.local.yml down -v
docker compose -f docker-compose.local.yml up -d
```

## Useful Operational Commands

```powershell
# Follow all logs
docker compose -f docker-compose.local.yml logs -f

# Follow one service
docker compose -f docker-compose.local.yml logs -f backend

# Restart one service
docker compose -f docker-compose.local.yml restart backend

# Stop all
docker compose -f docker-compose.local.yml stop
```

## Quick Success Checklist

1. `docker compose -f docker-compose.local.yml ps` shows all expected services up.
2. `http://localhost` returns 200.
3. `http://localhost:8000/api/health/` returns 200.
4. Neo4j service reports healthy in `docker compose ps`.
