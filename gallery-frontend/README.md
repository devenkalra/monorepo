# Gallery frontend

Manage and view galleries on bldrdojo.

| URL | Purpose |
|-----|---------|
| `/app/gallery/` | Authenticated management SPA |
| `/{public_username}/gallery/{slug}` | Public / share viewer (same SPA bundle) |

## Local

```bash
npm run dev:gallery
# http://localhost:5178/app/gallery/
```

API proxies to Django on `:8000`. Ensure migrations are applied:

```bash
docker compose -f docker-compose.local.yml exec backend python manage.py migrate
```

## Notes

- Each user gets a URL-safe `public_username` (auto-created from email local-part) used in share links.
- Restricted galleries require login as the invited email **and** that invite’s share password (session unlock).
