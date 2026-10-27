## Markdown Cheat Sheet [#markdown-cheat-sheet]

Here is a quick-reference guide for basic and extended Markdown syntax (including GitHub-flavored Markdown used on this site).

## Table of Contents [#table-of-contents]

- [Headings](#headings)
- [Text Formatting](#text-formatting)
- [Lists](#lists)
- [Links & Images](#links-images)
- [Code & Quotes](#code-quotes)
- [Tables](#tables)
- [Horizontal Rules](#horizontal-rules)
- [Footnotes](#footnotes)
- [Definition Lists](#definition-lists)
- [HTML & Escaping](#html-escaping)
- [Miscellaneous](#miscellaneous)
- [Local Environment Shell Commands](#local-environment-shell-commands)
- [Production Environment Shell Commands](#production-environment-shell-commands)
- [Site-Specific Notes](#site-specific-notes)

## Headings [#headings]

```
# Heading 1
## Heading 2
### Heading 3
#### Heading 4
##### Heading 5
###### Heading 6
```

On this site you can set an explicit jump target with `[#id]` after the title:

```
## My Section [#my-section]
```

That renders as a heading you can link to with `[Jump](#my-section)`.

## Text Formatting [#text-formatting]

```
**Bold text**
*Italic text*
***Bold and italic***
__Bold__ and _italic_ (underscore form)
~~Strikethrough~~
==Highlight== (not always supported)
H~2~O and x^2^ (subscript / superscript — limited support)
```

Line breaks:

```
Hard break: end a line with two spaces  
Or use a blank line between paragraphs.
```

## Lists [#lists]

Unordered:

```
- Item 1
- Item 2
  - Nested item
  - Nested item
* Also works with asterisks
+ Or plus signs
```

Ordered:

```
1. First
2. Second
   1. Nested ordered
   2. Nested ordered
3. Third
```

Task lists (GFM):

```
- [ ] Unchecked task
- [x] Checked task
- [X] Also checked
```

## Links & Images [#links-images]

```
[Google](https://google.com)
[Local page path](/p/73/articles)
[Same-page jump](#headings)
[Link with title](https://example.com "Tooltip title")

![Alt text](https://example.com/image.jpg)
![Alt text](https://example.com/image.jpg "Image title")

<!-- Reference-style links -->
[Reference link][ref-id]
[ref-id]: https://example.com
```

Autolinks:

```
https://devenkalra.com
<https://devenkalra.com>
```

## Code & Quotes [#code-quotes]

Inline and fenced code:

````
`inline code`

```
plain code block
```

```python
def hello(name):
    print(f"Hello, {name}")
```
````

Blockquotes:

```
> Single-line quote
>
> > Nested quote
>
> Quote with **formatting** and a [link](#links-images)
```

## Tables [#tables]

```
| Header 1 | Header 2 | Header 3 |
| -------- | -------- | -------- |
| Cell 1   | Cell 2   | Cell 3   |
| Left     | Center   | Right    |
```

Alignment:

```
| Left     | Center   | Right    |
| :------- | :------: | -------: |
| left     | center   | right    |
| aaa      | bbb      | ccc      |
```

Tips:

- Put a blank line before and after the table
- Use real line breaks between rows (not literal `\n` text)
- Cells can contain `**bold**`, `*italic*`, and `` `code` ``

## Horizontal Rules [#horizontal-rules]

```
---
***
___
```

## Footnotes [#footnotes]

```
Here is a statement with a footnote.[^1]

[^1]: Footnote contents go here.
```

(Support depends on the renderer; GFM/common pipelines vary.)

## Definition Lists [#definition-lists]

Some processors support:

```
Term
: Definition of the term

Another term
: First definition
: Second definition
```

If unsupported, use a bullet list or bold labels instead:

```
**Term** — definition of the term
```

## HTML & Escaping [#html-escaping]

Raw HTML (allowed on this site when using markdown + raw HTML):

```
<details>
<summary>Click to expand</summary>

Hidden details go here.

</details>

<br>
<a id="custom-anchor"></a>
```

Escape Markdown special characters with a backslash:

```
\*not italic\*
\# not a heading
\[not a link\](url)
```

## Miscellaneous [#miscellaneous]

Emoji shortcodes (renderer-dependent):

```
:rocket: :white_check_mark: :warning:
```

Comments (HTML comments are ignored in output):

```
<!-- This will not appear on the page -->
```

Math (renderer-dependent; not guaranteed here):

```
Inline: \( x^2 + y^2 = z^2 \)
Block:
$$
\int_0^1 x^2 \, dx
$$
```

Keyboard / sample UI text:

```
Press `Ctrl+S` to save.
Use **Save** then **Publish**.
```

## Local Environment Shell Commands [#local-environment-shell-commands]

Day-to-day commands to **build, start, stop, and debug** the local Docker environment. Run from the **monorepo root**.

### Build and start

```bash
# Build images and start the full local stack (detached)
docker compose -f docker-compose.local.yml up -d --build

# Start without rebuilding (containers already built)
docker compose -f docker-compose.local.yml up -d

# Build + start in the foreground (Ctrl+C stops; good for first-run debug)
docker compose -f docker-compose.local.yml up --build

# Build only (do not start)
docker compose -f docker-compose.local.yml build

# Build / start a single service
docker compose -f docker-compose.local.yml up -d --build --no-deps backend
docker compose -f docker-compose.local.yml up -d --build --no-deps celery-worker
docker compose -f docker-compose.local.yml up -d --build --no-deps celery-beat
docker compose -f docker-compose.local.yml up -d --build --no-deps frontend
docker compose -f docker-compose.local.yml up -d --build --no-deps devenkalra-app

# Edge nginx (separate project name)
docker compose -p edge -f docker-compose.edge.yml up -d --build
```

**Local ports after start**

- API: `http://localhost:8000`
- Baked SPA: `http://localhost:8080`
- devenkalra.com app: `http://localhost:8090`
- Edge: `http://localhost/` (needs edge compose)

### Stop and clean up

```bash
# Stop containers (keep them for a quick restart)
docker compose -f docker-compose.local.yml stop

# Start again after stop
docker compose -f docker-compose.local.yml start

# Restart running services
docker compose -f docker-compose.local.yml restart
docker compose -f docker-compose.local.yml restart backend celery-worker

# Remove containers (named volumes kept — DB data survives)
docker compose -f docker-compose.local.yml down

# Remove containers + anonymous leftovers; still keeps named volumes
docker compose -f docker-compose.local.yml down --remove-orphans

# Nuclear: also delete named volumes (wipes local DB / media volumes)
docker compose -f docker-compose.local.yml down -v

# Edge down
docker compose -p edge -f docker-compose.edge.yml down
```

### Reload after code or `.env` changes

```bash
# Python code is volume-mounted → usually just restart the process
docker compose -f docker-compose.local.yml restart backend celery-worker celery-beat

# data-backend/.env changed → recreate so env vars reload
docker compose -f docker-compose.local.yml up -d --force-recreate --no-deps \
  backend celery-worker celery-beat

# requirements.txt / Dockerfile changed → rebuild
docker compose -f docker-compose.local.yml up -d --build --no-deps backend celery-worker

# Frontend UI change on :8080 → rebuild baked image
docker compose -f docker-compose.local.yml up -d --build --no-deps frontend
```

### Debug: status

```bash
docker compose -f docker-compose.local.yml ps
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
docker inspect bldrdojo-local-backend --format "{{json .State.Health}}"
```

### Logs for each container

Compose service name on the left; follow with `-f`, limit with `--tail=N`.

```bash
# All local stack services
docker compose -f docker-compose.local.yml logs -f

# --- App / workers ---
docker compose -f docker-compose.local.yml logs -f backend
docker compose -f docker-compose.local.yml logs -f celery-worker
docker compose -f docker-compose.local.yml logs -f celery-beat
docker compose -f docker-compose.local.yml logs -f frontend
docker compose -f docker-compose.local.yml logs -f email-frontend-dev
docker compose -f docker-compose.local.yml logs -f devenkalra-app

# --- Data stores / infra ---
docker compose -f docker-compose.local.yml logs -f db
docker compose -f docker-compose.local.yml logs -f redis
docker compose -f docker-compose.local.yml logs -f meilisearch
docker compose -f docker-compose.local.yml logs -f neo4j
docker compose -f docker-compose.local.yml logs -f vector-service

# --- Edge proxy (separate compose project) ---
docker compose -p edge -f docker-compose.edge.yml logs -f edge-nginx

# Useful variants
docker compose -f docker-compose.local.yml logs --tail=200 -f backend
docker compose -f docker-compose.local.yml logs --tail=200 -f celery-worker
docker compose -f docker-compose.local.yml logs --since=10m backend celery-worker
docker compose -f docker-compose.local.yml logs --timestamps backend

# By container name (same logs if you prefer docker CLI)
docker logs -f bldrdojo-local-backend
docker logs -f bldrdojo-local-celery-worker
docker logs -f bldrdojo-local-celery-beat
docker logs -f bldrdojo-local-frontend
docker logs -f devenkalra-local-app
docker logs -f bldrdojo-local-vector
docker logs -f edge-nginx
```

**When to look where**

| Symptom | Start with |
|---------|------------|
| API 500 / auth / migrate | `backend` |
| Summarize / Enrich links / Apify stuck | `celery-worker` |
| Schedules not firing | `celery-beat` then `celery-worker` |
| SPA blank / old UI on `:8080` | `frontend` |
| devenkalra.com local pages | `devenkalra-app` |
| Proxy / host routing | `edge-nginx` |
| DB connection refused | `db` + `backend` |
| Celery “cannot connect to broker” | `redis` + `celery-worker` |

### Debug: shells into containers

```bash
docker compose -f docker-compose.local.yml exec backend bash
docker compose -f docker-compose.local.yml exec celery-worker bash
docker compose -f docker-compose.local.yml exec db bash
docker compose -f docker-compose.local.yml exec redis sh
docker compose -f docker-compose.local.yml exec backend env | sort
docker compose -f docker-compose.local.yml exec backend curl -sS http://localhost:8000/api/health/
```

### Debug: Celery queue & workers

Local broker is Redis (`REDIS_URL=redis://:localredispass@redis:6379/0`).

```bash
# Worker alive?
docker compose -f docker-compose.local.yml exec celery-worker \
  celery -A config inspect ping

# Which tasks does this worker know about? (look for gmail_assistant.tasks.*)
docker compose -f docker-compose.local.yml exec celery-worker \
  celery -A config inspect registered

# What’s running right now?
docker compose -f docker-compose.local.yml exec celery-worker \
  celery -A config inspect active

# Reserved / scheduled / revoked
docker compose -f docker-compose.local.yml exec celery-worker \
  celery -A config inspect reserved
docker compose -f docker-compose.local.yml exec celery-worker \
  celery -A config inspect scheduled
docker compose -f docker-compose.local.yml exec celery-worker \
  celery -A config inspect revoked

# Worker stats (concurrency, pool)
docker compose -f docker-compose.local.yml exec celery-worker \
  celery -A config inspect stats

# Active queues this worker consumes
docker compose -f docker-compose.local.yml exec celery-worker \
  celery -A config inspect active_queues

# Beat schedule (what periodic jobs exist)
docker compose -f docker-compose.local.yml exec celery-beat \
  celery -A config inspect conf
# Or from worker (shows app config including beat schedule when configured):
docker compose -f docker-compose.local.yml exec celery-worker \
  celery -A config report

# Purge all waiting tasks from the default queue (destructive)
docker compose -f docker-compose.local.yml exec celery-worker \
  celery -A config purge -f
```

### Debug: Redis broker (queue depth)

```bash
# Redis CLI (password from local compose)
docker compose -f docker-compose.local.yml exec redis \
  redis-cli -a localredispass

# One-liners without interactive shell:
docker compose -f docker-compose.local.yml exec redis \
  redis-cli -a localredispass ping

# List keys (Celery uses several; filter if noisy)
docker compose -f docker-compose.local.yml exec redis \
  redis-cli -a localredispass keys '*'

# Approximate length of the default Celery queue
docker compose -f docker-compose.local.yml exec redis \
  redis-cli -a localredispass llen celery

# Peek at queued messages (0 = oldest)
docker compose -f docker-compose.local.yml exec redis \
  redis-cli -a localredispass lrange celery 0 5

# How many clients / memory
docker compose -f docker-compose.local.yml exec redis \
  redis-cli -a localredispass info clients
docker compose -f docker-compose.local.yml exec redis \
  redis-cli -a localredispass info memory
```

### Debug: Django task progress / Gmail jobs

```bash
# Django shell — inspect recent LlmJob rows (summarize / process / enrich_links)
docker compose -f docker-compose.local.yml exec backend python manage.py shell -c "
from gmail_assistant.models import LlmJob
for j in LlmJob.objects.order_by('-created_at')[:10]:
    print(j.id, j.kind, j.status, j.celery_task_id, (j.errors or '')[:120])
"

# Cache progress key used by the UI poller (task_progress_<celery_id>)
docker compose -f docker-compose.local.yml exec backend python manage.py shell -c "
from django.core.cache import cache
from gmail_assistant.models import LlmJob
j = LlmJob.objects.order_by('-created_at').first()
print(j and cache.get(f'task_progress_{j.celery_task_id}'))
"
```

### Debug: Django / DB

```bash
docker compose -f docker-compose.local.yml exec backend python manage.py shell
docker compose -f docker-compose.local.yml exec backend python manage.py showmigrations
docker compose -f docker-compose.local.yml exec backend python manage.py migrate

docker compose -f docker-compose.local.yml run --rm --no-deps backend \
  python manage.py test -v2

docker compose -f docker-compose.local.yml exec db \
  psql -U postgres -d entitydb
```

### Debug: HTTP checks from the host

```bash
curl -sS http://localhost:8000/api/health/
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8080/
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8090/
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost/health

# Verbose response headers (auth / redirect issues)
curl -sSI http://localhost:8000/api/health/
curl -sSI http://localhost:8080/gmail-app/
```

### Debug: frontend hot reload (no Docker rebuild)

```bash
npm run dev:gmail    # http://localhost:5177/gmail-app/
npm run dev:people
npm run dev:cad
npm run dev:food
```

Use Vite when iterating on UI; use `frontend` rebuild when testing the baked `:8080` image / edge proxy.

### Debug: common “it’s broken” checklist

```bash
# 1) Are containers up and healthy?
docker compose -f docker-compose.local.yml ps

# 2) Backend error log
docker compose -f docker-compose.local.yml logs --tail=100 backend

# 3) Worker errors (summarize / enrich-links / Apify)
docker compose -f docker-compose.local.yml logs --tail=100 celery-worker

# 4) Did .env fail to load? Recreate:
docker compose -f docker-compose.local.yml up -d --force-recreate --no-deps \
  backend celery-worker

# 5) Port already in use?
# Windows PowerShell:
netstat -ano | findstr ":8000"
netstat -ano | findstr ":8080"
# macOS / Linux:
# lsof -i :8000
```

## Production Environment Shell Commands [#production-environment-shell-commands]

Commands for the **production** server. Run from the **monorepo root** on the host (SSH). Defaults match `scripts/deploy_app.sh`:

- Compose file: `docker-compose.production.yml`
- Compose project: `data-backend` (`-p data-backend`)
- Edge project: `edge` (`docker-compose.edge.yml`)

Set these once per shell session:

```bash
cd /path/to/monorepo   # e.g. /home/ubuntu/monorepo
export COMPOSE_FILE=docker-compose.production.yml
export PROJECT=data-backend
# Shorthand used below:
#   dc  = docker compose -p "$PROJECT" -f "$COMPOSE_FILE"
alias dc='docker compose -p data-backend -f docker-compose.production.yml'
alias dce='docker compose -p edge -f docker-compose.edge.yml'
```

**Caution:** Prefer `deploy_app.sh` for routine deploys. Avoid `down -v` and Celery `purge` unless you intend to drop queues / volumes.

### Deploy / build / recreate

```bash
# Preferred: targeted app deploy (pull + build + recreate + migrate for bldrdojo)
bash ./scripts/deploy_app.sh --app bldrdojo
bash ./scripts/deploy_app.sh --app devenkalra
bash ./scripts/deploy_app.sh --app bldrdojo --app devenkalra

# Dry-run (show actions only)
bash ./scripts/deploy_app.sh --app bldrdojo --dry-run

# Manual: rebuild specific services (same services deploy_app uses for bldrdojo)
dc up -d --build --force-recreate --no-deps backend frontend celery-worker celery-beat

# devenkalra.com only
dc up -d --build --force-recreate --no-deps devenkalra-app

# Edge nginx (production TLS conf usually via EDGE_NGINX_CONF)
EDGE_NGINX_CONF=./scripts/nginx/multi-domain-edge-example.conf \
  dce up -d --force-recreate --no-deps edge-nginx

# After data-backend/.env change (no image rebuild)
dc up -d --force-recreate --no-deps backend celery-worker celery-beat

# Restart only (code not volume-mounted in prod the same way as local — prefer recreate/rebuild)
dc restart backend celery-worker celery-beat
```

### Status

```bash
dc ps
dce ps
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
docker inspect bldrdojo-backend --format "{{json .State.Health}}"
```

### Logs for each production container

```bash
# All project services
dc logs -f

# --- App / workers ---
dc logs -f backend
dc logs -f celery-worker
dc logs -f celery-beat
dc logs -f frontend
dc logs -f devenkalra-app

# --- Data stores / infra ---
dc logs -f db
dc logs -f redis
dc logs -f meilisearch
dc logs -f neo4j

# --- Edge ---
dce logs -f edge-nginx

# Tail / time window
dc logs --tail=200 -f backend
dc logs --tail=200 -f celery-worker
dc logs --since=30m backend celery-worker
dc logs --timestamps backend

# By container name
docker logs -f bldrdojo-backend
docker logs -f bldrdojo-celery-worker
docker logs -f bldrdojo-celery-beat
docker logs -f bldrdojo-frontend
docker logs -f bldrdojo-db
docker logs -f bldrdojo-redis
docker logs -f bldrdojo-meilisearch
docker logs -f bldrdojo-neo4j
docker logs -f edge-nginx
# devenkalra-app name depends on compose project; prefer:
dc logs -f devenkalra-app
```

**When to look where (prod)**

| Symptom | Start with |
|---------|------------|
| bldrdojo.com API / login | `backend` |
| Summarize / Enrich links / Apify | `celery-worker` |
| Gmail schedules | `celery-beat` → `celery-worker` |
| Static SPA /g\* apps | `frontend` |
| devenkalra.com | `devenkalra-app` + `edge-nginx` |
| TLS / host routing | `edge-nginx` |
| Broker / queue stuck | `redis` + `celery-worker` |

### Shells (production)

```bash
dc exec backend bash
dc exec celery-worker bash
dc exec db bash
dc exec redis sh

dc exec backend env | sort
dc exec backend curl -sS http://localhost:8000/api/health/
```

### Celery queue & workers (production)

```bash
dc exec celery-worker celery -A config inspect ping
dc exec celery-worker celery -A config inspect registered
dc exec celery-worker celery -A config inspect active
dc exec celery-worker celery -A config inspect reserved
dc exec celery-worker celery -A config inspect scheduled
dc exec celery-worker celery -A config inspect stats
dc exec celery-worker celery -A config inspect active_queues

# Destructive — clears waiting tasks on the default queue
# dc exec celery-worker celery -A config purge -f
```

### Redis broker (production)

Password comes from `data-backend/.env` (`REDIS_PASSWORD`). Do not hardcode it in docs/scripts you commit.

```bash
# Interactive (enter password when prompted, or pass -a from env on the host)
dc exec redis redis-cli -a "$REDIS_PASSWORD" ping

# Queue depth / peek (default Celery list key is often "celery")
dc exec redis redis-cli -a "$REDIS_PASSWORD" llen celery
dc exec redis redis-cli -a "$REDIS_PASSWORD" lrange celery 0 5
dc exec redis redis-cli -a "$REDIS_PASSWORD" info memory
```

If `$REDIS_PASSWORD` is not set in your SSH session, load it from the env file first:

```bash
set -a; source data-backend/.env; set +a
```

### Django / Gmail jobs / DB (production)

```bash
dc exec backend python manage.py showmigrations
dc exec backend python manage.py migrate --noinput
dc exec backend python manage.py collectstatic --noinput

# Recent Gmail LLM jobs
dc exec backend python manage.py shell -c "
from gmail_assistant.models import LlmJob
for j in LlmJob.objects.order_by('-created_at')[:10]:
    print(j.id, j.kind, j.status, j.celery_task_id, (j.errors or '')[:120])
"

# Latest task progress blob (UI poller)
dc exec backend python manage.py shell -c "
from django.core.cache import cache
from gmail_assistant.models import LlmJob
j = LlmJob.objects.order_by('-created_at').first()
print(j and cache.get(f'task_progress_{j.celery_task_id}'))
"

# Postgres
dc exec db psql -U postgres -d entitydb
# Or via Django:
# dc exec backend python manage.py dbshell
```

### HTTP checks (from prod host or laptop)

```bash
curl -sS https://bldrdojo.com/api/health/
curl -sSI https://bldrdojo.com/gmail-app/
curl -sSI https://devenkalra.com/
curl -sS -o /dev/null -w "%{http_code}\n" https://bldrdojo.com/
```

### Production “it’s broken” checklist

```bash
dc ps
dc logs --tail=100 backend
dc logs --tail=100 celery-worker
dce logs --tail=100 edge-nginx

# Worker registered Gmail tasks?
dc exec celery-worker celery -A config inspect registered | grep -i gmail || true

# Queue backing up?
set -a; source data-backend/.env; set +a
dc exec redis redis-cli -a "$REDIS_PASSWORD" llen celery
```

## Site-Specific Notes [#site-specific-notes]

- Prefer GitHub-flavored tables, task lists, and strikethrough — they are supported in page render.
- Use `## Title [#anchor-id]` for stable in-page anchors; TOC links should use `(#anchor-id)`.
- Literal `\n` sequences pasted from JSON/Swagger are converted to real line breaks when you save a page in admin.
- Keep a blank line around headings, lists, code fences, and tables so the preview parses cleanly.
