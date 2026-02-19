# Blue-Green Deployment

Deploy a new version to staging, test it, then switch production to the new version—without downtime for testing.

## Flow

```
1. ./deploy_production.sh --staging   → New version runs on ports 8080/8443
2. Test at https://bldrdojo.com:8443
3. ./deploy_production.sh --promote   → Production switches to new version
```

## Commands

| Command | Description |
|---------|-------------|
| `./deploy_production.sh --staging` | Deploy new version to staging (ports 8080, 8443) |
| `./deploy_production.sh --promote` | Switch production to the staged version |
| `./deploy_production.sh` | Direct deploy to production (no staging) |

## Setup

### 1. Firewall

Allow HTTPS on the staging port:

```bash
sudo ufw allow 8443/tcp
sudo ufw reload
```

### 2. Directories

- **Production:** `/home/deploy` (or `PROD_DIR`)
- **Staging:** `/home/deploy-staging` (or `STAGING_DIR`)

On first `--staging` deploy, the script:
- Creates `STAGING_DIR` if needed
- Copies `.env` from production if staging has none
- Symlinks `ssl/` from production (shared certs)

### 3. Shared Resources

Staging uses the **same database, Redis, MeiliSearch, Neo4j** as production. Both stacks connect to the same data. Migrations run on staging deploy; promote only swaps the app containers.

## Promote Details

`--promote` does:

1. Stop production containers
2. Stop staging containers
3. Sync staging files → production (code, config)
4. Start production with the new code
5. Run migrations, collectstatic, setup_google_oauth

Production `.env`, `ssl/`, `backups/` are **not** overwritten.

## Rollback

If the new version has issues after promote:

1. Fix and redeploy: `./deploy_production.sh --staging` then `--promote`
2. Or restore from backup and redeploy the previous commit
