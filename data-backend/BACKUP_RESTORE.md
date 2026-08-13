# Backup and Restore Guide

This document describes the current backup and restore behavior for the bldrdojo production stack.

The backup scripts in `data-backend/scripts/` protect the main Django application data and media. They do **not** back up every service volume directly. The separate `devenkalra-app` SQLite service is backed up with monorepo `scripts/backup-devenkalra.sh`.

## Current Architecture Scope

### Covered by these scripts

- PostgreSQL data for the main Django stack
- Media files under `data-backend/media/` when present locally
- Sanitized configuration snapshots
- Optional Django JSON export for inspection

### Rebuilt during restore

- Neo4j graph data, via `python manage.py sync_neo4j`
- MeiliSearch index data, via `python manage.py reindex_meilisearch --clear-first`

### Not currently covered by these scripts

- Raw Docker named volumes for Redis, Neo4j, or MeiliSearch

`devenkalra.com` SQLite and media: run `./scripts/backup-devenkalra.sh` from the monorepo root (cron-safe; default keep 14 days).

## Quick Reference

```bash
# Full backup (PostgreSQL + media + config + optional Django export)
./scripts/backup.sh [name] --full

# Incremental backup (PostgreSQL only, faster - run daily)
./scripts/backup.sh [name] --incremental

# Restore
./scripts/restore.sh <backup-name>
```

## Backup Types

| Type | Contents | When to Run |
|------|----------|-------------|
| **Full** | PostgreSQL, media files, config snapshot, optional Django export | Weekly or before major changes |
| **Incremental** | PostgreSQL only | Daily or more frequently |

Both produce restorable backups for the main Django application. Neo4j and MeiliSearch are **not** backed up directly because they are derived from PostgreSQL and rebuilt on restore.

## Can I Restore All My Data from PostgreSQL?

**Yes, for the main bldrdojo Django stack.** The PostgreSQL backup includes:

- **People app**: Entities, notes, relations, tags, users
- **Food app**: Food spots, foods, media, reviews, lists
- **CAD app**: Models, parameters, scenes
- **Django**: Auth users, sessions, migrations state

After restore, the script runs:
1. Database migrations
2. **sync_neo4j** — rebuilds the graph from PostgreSQL
3. **reindex_meilisearch** (with `--clear-first` to avoid duplicates)

Media files are restored from the backup archive (full backups only).

This does **not** restore the separate `devenkalra.com` SQLite app. Use `scripts/backup-devenkalra.sh` backups for that.

## Usage

### Backup

```bash
cd data-backend

# Full backup (default)
./scripts/backup.sh
./scripts/backup.sh weekly_backup --full

# Incremental (PostgreSQL only)
./scripts/backup.sh daily_backup --incremental
```

### Restore

```bash
cd data-backend

# Dry run first
./scripts/restore.sh backup_20250215_120000 --dry-run

# Full restore
./scripts/restore.sh backup_20250215_120000

# Database only (e.g. incremental backup)
./scripts/restore.sh daily_backup --db-only

```

### Reindexing (No Duplicates)

After restore, MeiliSearch is reindexed with `--clear-first`, which:
1. Deletes all documents from the search index
2. Rebuilds the index from PostgreSQL

This ensures no duplicate or stale search results.

## Rsync to Dreamhost (optional)

To sync backups and media to Dreamhost after each run, set:

```bash
export DREAMHOST_RSYNC_DEST="kalramedia@pdx1-shared-a1-40.dreamhost.com:/home/kalramedia/testb/"
export DREAMHOST_SSH_KEY="$HOME/.ssh/dreamhost.pem"  # optional, defaults to ~/.ssh/dreamhost.pem
export DREAMHOST_MEDIA_SOURCE="/var/lib/bldrdojo/media"  # optional, defaults to /var/lib/bldrdojo/media
```

- **Backup** (postgres, config, etc.) → `$DREAMHOST_RSYNC_DEST/db/$BACKUP_NAME/`
- **Media** → `$DREAMHOST_RSYNC_DEST/media/`

## Production

Production runs from the monorepo root with the root-level compose file:

- Compose file: `/home/deploy/docker-compose.production.yml`
- Backend env file: `/home/deploy/data-backend/.env`
- Main stack includes PostgreSQL, Redis, Neo4j, MeiliSearch, backend, celery-worker, and frontend
- The same production compose file also includes `devenkalra-app`; back that up with `scripts/backup-devenkalra.sh`

Set environment variables before running:

```bash
export COMPOSE_FILE=/path/to/docker-compose.production.yml
export BACKUP_ROOT=/home/deploy/backups/data-backend
export POSTGRES_DB=entitydb  # or your DB name
```

Recommended production usage:

```bash
cd /home/deploy
COMPOSE_FILE=/home/deploy/docker-compose.production.yml \
BACKUP_ROOT=/home/deploy/backups/data-backend \
./data-backend/scripts/backup.sh weekly_$(date +%Y%m%d) --full
```

For restore:

```bash
cd /home/deploy/data-backend
COMPOSE_FILE=/home/deploy/docker-compose.production.yml \
BACKUP_ROOT=/home/deploy/backups/data-backend \
./scripts/restore.sh backup_full_YYYYMMDD_HHMMSS
```

Important production note: the backup script reads media from `data-backend/media/`. If production media lives elsewhere on the host, confirm the directory is mounted or copied into that path before relying on the archive.

## Cron Examples

To schedule backups, run `crontab -e` and add:

```bash
# Full backup once a week (Sunday 2am)
0 2 * * 0 cd /home/deploy && COMPOSE_FILE=/home/deploy/docker-compose.production.yml BACKUP_ROOT=/home/deploy/backups/data-backend ./data-backend/scripts/backup.sh weekly_$(date +\%Y\%m\%d) --full

# Full backup daily (Mon–Sat 2am)
0 2 * * 1-6 cd /home/deploy && COMPOSE_FILE=/home/deploy/docker-compose.production.yml BACKUP_ROOT=/home/deploy/backups/data-backend ./data-backend/scripts/backup.sh daily_$(date +\%Y\%m\%d) --full

# Incremental backup every 4 hours
0 */4 * * * cd /home/deploy && COMPOSE_FILE=/home/deploy/docker-compose.production.yml BACKUP_ROOT=/home/deploy/backups/data-backend ./data-backend/scripts/backup.sh incremental_$(date +\%Y\%m\%d_\%H) --incremental
```

Adjust `/home/deploy` if your production root differs.

For Dreamhost rsync, add these at the top of your crontab (before the cron lines):
```
DREAMHOST_RSYNC_DEST=user@host:/path/
DREAMHOST_SSH_KEY=/home/you/.ssh/dreamhost.pem
```

## Backup Location

Default: `$HOME/backups/data-backend/<backup-name>/`

Override with `BACKUP_ROOT`:
```bash
BACKUP_ROOT=/mnt/backups ./scripts/backup.sh
```

## Operational Warnings

- Do not assume a full backup contains Neo4j or MeiliSearch volume snapshots. It does not.
- `devenkalra.com` content is covered by `scripts/backup-devenkalra.sh`, not by these data-backend scripts.
- Test restore regularly with `--dry-run` and periodic full non-production restores.
