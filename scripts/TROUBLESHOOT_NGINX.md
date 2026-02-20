# Troubleshooting Nginx "Page Unavailable" Error

The message *"Sorry, the page you are looking for is currently unavailable"* is nginx's default 502/503 error. It usually means nginx cannot reach the backend.

## Quick checks (run from your production directory, e.g. `/home/deploy`)

### 1. Are all containers running?

```bash
docker compose -f docker-compose.production.yml ps
```

All services should show "Up". If `backend` is "Exited" or "Restarting", that's the cause.

### 2. Backend logs

```bash
docker compose -f docker-compose.production.yml logs backend --tail 100
```

Look for Python tracebacks, migration errors, or "Address already in use".

### 3. Frontend/nginx logs

```bash
docker compose -f docker-compose.production.yml logs frontend --tail 50
```

### 4. Nginx error log (inside container)

```bash
docker compose -f docker-compose.production.yml exec frontend cat /var/log/nginx/error.log
```

Look for "upstream timed out", "connection refused", or "no live upstreams".

### 5. Can frontend reach backend?

```bash
docker compose -f docker-compose.production.yml exec frontend wget -qO- http://backend:8000/api/health/ || echo "FAILED"
```

If this fails, the frontend cannot reach the backend (network or backend down).

### 6. SSL certificates

Nginx needs SSL certs for HTTPS. Verify they exist:

```bash
ls -la data-backend/ssl/
# Should show: fullchain.pem, privkey.pem
```

If missing, nginx may fail to start or reject HTTPS connections.

### 7. Restart services

```bash
docker compose -f docker-compose.production.yml restart backend frontend
```

### 8. Full restart (if backend crashed during migrate)

```bash
docker compose -f docker-compose.production.yml down
docker compose -f docker-compose.production.yml up -d
```

## Celery worker restarting

If `celery-worker` keeps restarting, check its logs:

```bash
docker compose -f docker-compose.production.yml logs celery-worker --tail 200
```

Common causes:

| Cause | Fix |
|-------|-----|
| Redis connection failed | Verify `REDIS_URL` in `.env` – format `redis://:PASSWORD@redis:6379/0`. If password has `@` or `:`, URL-encode it. |
| OOM (out of memory) | Reduce concurrency: in docker-compose, change command to `celery -A config worker --loglevel=info --concurrency=1` |
| Django/model import error | Same as backend – migration or model mismatch. Run migrations, restart. |
| Redis not ready | Add `restart: on-failure` and a short `healthcheck` delay, or increase `depends_on` wait. |

**Temporary workaround** – run without celery to get the site up (async tasks like import/export won’t work):

```bash
docker compose -f docker-compose.production.yml up -d
docker compose -f docker-compose.production.yml stop celery-worker
```

## Common causes

| Cause | Fix |
|-------|-----|
| Backend crashed (e.g. migration error) | Check backend logs, fix migration, restart |
| Backend not on same network as frontend | Ensure both use `frontend-network` |
| Missing .env or wrong DB credentials | Verify `data-backend/.env` |
| SSL certs missing | Add `fullchain.pem` and `privkey.pem` to `data-backend/ssl/` |
| Database not ready | Wait for db healthcheck, then `docker compose up -d` |
