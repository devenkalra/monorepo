# Server Setup Guide

Complete guide for setting up and maintaining the bldrdojo.com server. Covers architecture, deployment, backups, cron, and maintenance.

---

## Overview

- **App**: Django REST API + React frontends (People, CAD, Food apps)
- **Domain**: https://bldrdojo.com
- **Stack**: Docker Compose, PostgreSQL, Redis, MeiliSearch, Neo4j, Celery
- **Deploy user**: `deploy` (default)
- **Production root**: `/home/deploy` (or `PROD_DIR`)

---

## Architecture

### Services (Docker Compose)

| Service | Image | Purpose |
|---------|-------|---------|
| **backend** | Django + Gunicorn | REST API, migrations |
| **frontend** | Nginx + React | Serves apps, proxies API |
| **db** | PostgreSQL 15 | Primary database |
| **redis** | Redis 7 | Caching, Celery broker |
| **meilisearch** | MeiliSearch v1.5 | Full-text search |
| **neo4j** | Neo4j 5 | Graph (relations) |
| **celery-worker** | Django + Celery | Async tasks |

### Data Flow

- **PostgreSQL** = source of truth (entities, users, notes, etc.)
- **Neo4j** = derived from PostgreSQL (sync via `sync_neo4j`)
- **MeiliSearch** = derived from PostgreSQL (sync via `reindex_meilisearch`)
- **Media** = `/var/lib/bldrdojo/media` (host path, mounted into containers)

### Ports

- **80/443**: Production (frontend Nginx)
- **8080/8443**: Staging (when using blue-green deploy)
- Backend runs on internal port 8000 (proxied by Nginx)

---

## Server Requirements

- **OS**: Ubuntu 22.04 LTS or newer
- **RAM**: 4GB minimum, 8GB+ recommended
- **Storage**: 50GB+ SSD
- **CPU**: 2+ cores
- **Network**: Static IP, ports 80, 443 open (8443 for staging)

---

## Initial Setup

### 1. System Update

```bash
sudo apt update && sudo apt upgrade -y
```

### 2. Install Docker

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
```

Log out and back in for group changes.

### 3. Install Docker Compose

```bash
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### 4. Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw allow 8443/tcp   # For staging (blue-green)
sudo ufw enable
```

### 5. Create Deploy User (optional)

```bash
sudo adduser deploy
sudo usermod -aG docker deploy
```

---

## Directory Structure

### Production (`/home/deploy`)

```
/home/deploy/
├── data-backend/          # Django app
│   ├── .env               # Secrets (POSTGRES_*, REDIS_*, etc.)
│   ├── backups/           # Local backup dir (optional)
│   └── ...
├── frontend/              # React build output
├── people-frontend/
├── cad-frontend/
├── food-frontend/
├── ssl/                   # SSL certs (fullchain.pem, privkey.pem)
├── docker-compose.production.yml
└── scripts/
```

### Media Storage

- **Path**: `/var/lib/bldrdojo/media`
- **Owner**: Ensure `deploy` (or run user) can read/write
- **Backup**: Included in full backups; rsync'd to Dreamhost when configured

```bash
sudo mkdir -p /var/lib/bldrdojo/media
sudo chown deploy:deploy /var/lib/bldrdojo/media
```

---

## Configuration

### Environment (`.env`)

Create `data-backend/.env` with:

```bash
# Django
DEBUG=False
SECRET_KEY=<generate-with-django>
ALLOWED_HOSTS=bldrdojo.com,www.bldrdojo.com

# PostgreSQL
POSTGRES_DB=entitydb
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<strong-password>

# Redis
REDIS_PASSWORD=<strong-password>

# MeiliSearch
MEILI_MASTER_KEY=<strong-key>

# Neo4j
NEO4J_USER=neo4j
NEO4J_PASSWORD=<strong-password>

# Google OAuth
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

Generate `SECRET_KEY`:

```bash
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### SSL Certificates

Place in `ssl/` (or mount from host):

- `fullchain.pem`
- `privkey.pem`

Obtain via Let's Encrypt:

```bash
sudo certbot certonly --standalone -d bldrdojo.com -d www.bldrdojo.com
# Copy certs to ssl/ or symlink
```

---

## Deployment

### One-Time Clone

```bash
cd /home/deploy
git clone <repo-url> .
# Copy .env to data-backend/.env
# Copy or obtain ssl/ certs
```

**Note:** The deploy script syncs specific paths (config, people, frontend, etc.). It does not sync `data-backend/scripts/`. If you update backup or restore scripts, copy them manually or run `git pull` in the deploy directory.

### Deploy (from dev machine or CI)

```bash
# From monorepo root
./scripts/deploy_production.sh
```

Or with dry-run:

```bash
./scripts/deploy_production.sh --dry-run
```

### Blue-Green (Staging → Promote)

1. Deploy to staging (ports 8080/8443):
   ```bash
   ./scripts/deploy_production.sh --staging
   ```

2. Test at https://bldrdojo.com:8443

3. Promote to production:
   ```bash
   ./scripts/deploy_production.sh --promote
   ```

Staging shares the same DB, Redis, MeiliSearch, Neo4j as production.

### Environment Variables for Deploy

| Variable | Default | Description |
|----------|---------|-------------|
| `PROD_DIR` | `/home/deploy` | Production root |
| `STAGING_DIR` | `/home/deploy-staging` | Staging root |
| `REPO_URL` | (from .git) | Git clone URL |
| `BRANCH` | `main` | Branch to deploy |

---

## Backup & Restore

See `data-backend/BACKUP_RESTORE.md` for full details.

### Quick Reference

```bash
cd /home/deploy

# Full backup (PostgreSQL + media + config)
COMPOSE_FILE=/home/deploy/docker-compose.production.yml BACKUP_ROOT=/home/deploy/backups ./data-backend/scripts/backup.sh weekly_$(date +%Y%m%d) --full

# Incremental (PostgreSQL only)
COMPOSE_FILE=/home/deploy/docker-compose.production.yml BACKUP_ROOT=/home/deploy/backups ./data-backend/scripts/backup.sh incremental_$(date +%Y%m%d_%H) --incremental

# Restore
cd /home/deploy/data-backend
COMPOSE_FILE=/home/deploy/docker-compose.production.yml ./scripts/restore.sh <backup-name>
```

### Production Env for Backups

```bash
export COMPOSE_FILE=/home/deploy/docker-compose.production.yml
export BACKUP_ROOT=/home/deploy/backups
export POSTGRES_DB=entitydb
```

---

## Cron (Scheduled Backups)

### Create Crontab File

Create `crontab.txt` (run from repo root `/home/deploy`):

```
# Dreamhost rsync (optional - add at top)
DREAMHOST_RSYNC_DEST=user@host:/home/user/backups/
DREAMHOST_SSH_KEY=/home/deploy/.ssh/dreamhost.pem

# Full backup weekly (Sunday 2am)
0 2 * * 0 cd /home/deploy && COMPOSE_FILE=/home/deploy/docker-compose.production.yml BACKUP_ROOT=/home/deploy/backups ./data-backend/scripts/backup.sh weekly_$(date +\%Y\%m\%d) --full

# Full backup daily (Mon–Sat 2am)
0 2 * * 1-6 cd /home/deploy && COMPOSE_FILE=/home/deploy/docker-compose.production.yml BACKUP_ROOT=/home/deploy/backups ./data-backend/scripts/backup.sh daily_$(date +\%Y\%m\%d) --full

# Incremental every 4 hours
0 */4 * * * cd /home/deploy && COMPOSE_FILE=/home/deploy/docker-compose.production.yml BACKUP_ROOT=/home/deploy/backups ./data-backend/scripts/backup.sh incremental_$(date +\%Y\%m\%d_\%H) --incremental
```

### Install Crontab

```bash
crontab crontab.txt
# Or append to existing:
(crontab -l 2>/dev/null; cat crontab.txt) | crontab -
```

### Rsync Layout (Dreamhost)

When `DREAMHOST_RSYNC_DEST` is set:

- **Backup** → `$DREAMHOST_RSYNC_DEST/db/<backup-name>/`
- **Media** → `$DREAMHOST_RSYNC_DEST/media/`

---

## Maintenance Commands

### View Logs

```bash
cd /home/deploy
docker compose -f docker-compose.production.yml logs -f backend
docker compose -f docker-compose.production.yml logs -f frontend
```

### Restart Services

```bash
docker compose -f docker-compose.production.yml restart backend
docker compose -f docker-compose.production.yml restart celery-worker
```

### Run Migrations

```bash
docker compose -f docker-compose.production.yml exec backend python manage.py migrate
```

### Collect Static Files

```bash
docker compose -f docker-compose.production.yml exec backend python manage.py collectstatic --noinput
```

### Reindex MeiliSearch

```bash
docker compose -f docker-compose.production.yml exec backend python manage.py reindex_meilisearch --clear-first
```

### Sync Neo4j from PostgreSQL

```bash
docker compose -f docker-compose.production.yml exec backend python manage.py sync_neo4j
```

### Create Superuser

```bash
docker compose -f docker-compose.production.yml exec backend python manage.py createsuperuser
```

### Django Shell

```bash
docker compose -f docker-compose.production.yml exec backend python manage.py shell
```

### Database Shell

```bash
docker compose -f docker-compose.production.yml exec db psql -U postgres -d entitydb
```

---

## Volumes (Data Persistence)

| Volume | Purpose |
|--------|---------|
| `bldrdojo-postgres-data` | PostgreSQL data |
| `bldrdojo-redis-data` | Redis data |
| `bldrdojo-meilisearch-data` | Search index |
| `bldrdojo-neo4j-data` | Graph data |
| `bldrdojo-static` | Static files |
| Host `/var/lib/bldrdojo/media` | Uploaded media |

**Warning**: `docker compose down -v` removes volumes and deletes data.

---

## Troubleshooting

### 502 Bad Gateway

- Check backend: `docker compose ps backend`
- Check logs: `docker compose logs backend`
- Restart: `docker compose restart backend`

### Database Connection Failed

- Check db: `docker compose ps db`
- Verify `.env` has correct `POSTGRES_*` values
- Test: `docker compose exec backend python manage.py dbshell`

### Media Not Loading

- Verify `/var/lib/bldrdojo/media` exists and is readable
- Check volume mount in `data-backend/docker-compose.yml`: `/var/lib/bldrdojo/media:/app/media`

### SSL Certificate Expired

```bash
sudo certbot renew
# Copy new certs to ssl/ and restart frontend
docker compose restart frontend
```

### Out of Disk Space

```bash
# Clean old backups
ls -la ~/backups/data-backend/
rm -rf ~/backups/data-backend/old_backup_name

# Clean Docker
docker system prune -a
```

---

## Related Documentation

- `data-backend/BACKUP_RESTORE.md` — Backup/restore details
- `scripts/BLUE_GREEN_DEPLOYMENT.md` — Staging flow
- `data-backend/SYSTEM_CONTEXT.md` — Architecture and config notes
- `data-backend/docs/deployment/PRODUCTION_DEPLOYMENT.md` — Detailed production setup
