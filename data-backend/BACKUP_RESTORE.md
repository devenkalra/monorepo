# Backup and Restore Guide

Backup and restore scripts for catastrophic data loss recovery. All data stored in PostgreSQL can be restored.

## Quick Reference

```bash
# Full backup (PostgreSQL + Neo4j + Media + MeiliSearch + config)
./scripts/backup.sh [name] --full

# Incremental backup (PostgreSQL only, faster - run daily)
./scripts/backup.sh [name] --incremental

# Restore
./scripts/restore.sh <backup-name>
```

## Backup Types

| Type | Contents | When to Run |
|------|----------|-------------|
| **Full** | PostgreSQL, Media files, config | Weekly or before major changes |
| **Incremental** | PostgreSQL only | Daily or more frequently |

Both produce restorable backups. Neo4j and MeiliSearch are **not** backed up—they are derived from PostgreSQL and are rebuilt on restore.

## Can I Restore All My Data from PostgreSQL?

**Yes.** The PostgreSQL backup includes:

- **People app**: Entities, notes, relations, tags, users
- **Food app**: Food spots, foods, media, reviews, lists
- **CAD app**: Models, parameters, scenes
- **Django**: Auth users, sessions, migrations state

After restore, the script runs:
1. Database migrations
2. **sync_neo4j** — rebuilds the graph from PostgreSQL
3. **reindex_meilisearch** (with `--clear-first` to avoid duplicates)

Media files are restored from the backup archive (full backups only).

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

Set environment variables before running:

```bash
export COMPOSE_FILE=/path/to/docker-compose.production.yml
export BACKUP_ROOT=/home/deploy/backups/data-backend
export POSTGRES_DB=entitydb  # or your DB name
```

For production media (often at `/var/lib/bldrdojo/media`), ensure the backup script can access it or set `MEDIA_DIR` if your backup script supports it.

## Cron Examples

To schedule backups, run `crontab -e` and add:

```bash
# Full backup once a week (Sunday 2am)
0 2 * * 0 cd /path/to/data-backend && ./scripts/backup.sh weekly_$(date +\%Y\%m\%d) --full

# Full backup daily (Mon–Sat 2am)
0 2 * * 1-6 cd /path/to/data-backend && ./scripts/backup.sh daily_$(date +\%Y\%m\%d) --full

# Incremental backup every 4 hours
0 */4 * * * cd /path/to/data-backend && ./scripts/backup.sh incremental_$(date +\%Y\%m\%d_\%H) --incremental
```

Replace `/path/to/data-backend` with your project path (e.g. `/home/ubuntu/monorepo/data-backend`).

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
