# devenkalra.com — Design Doc

Last updated: 2026-08-03

## 1. Purpose

Personal website and CMS for Deven Kalra: professional background, personal interests (photography, writing, travel, music, cooking), workflow trackers, and small custom apps.

**Not** a multi-tenant product. One primary owner; limited access for other authenticated users via roles and optional email allowlists.

Product intent and content outline also live in [`spec.md`](./spec.md). This document describes the **implemented** architecture.

---

## 2. High-level architecture

```
Browser (React SPA)
        │
        ▼
  Django + Gunicorn  (:8000)
   ├── /api/*          REST (DRF)
   ├── /admin/         Django admin
   ├── /api/media/*    uploaded files
   ├── /api/docs/      OpenAPI (Swagger)
   └── /*              SPA from frontend_dist
```

| Layer | Stack | Location |
|-------|--------|----------|
| Frontend | React + Vite + React Router | `frontend/` |
| Backend | Django  + DRF + SQLite | `backend/` (app: `core`) |
| Packaging | Multi-stage Docker image | `devenkalra.com/Dockerfile` |
| Edge | Nginx host routing | monorepo `scripts/nginx/*`, compose edge |

**Local:** `docker-compose.local.yml` service `devenkalra-app` → host `8090:8000` (or `devenkalra.local` via edge).  
**Prod:** same image pattern in `docker-compose.production.yml`; public host `devenkalra.com`.

Volumes typically mounted: `db.sqlite3`, `media/`. Locally, admin templates may also be bind-mounted for live edit.

Changing backend/frontend code requires rebuilding `devenkalra-app` (only templates are live-mounted locally).

---

## 3. Content and navigation model

### 3.1 Pages

`Page` is the primary CMS unit:

- `title`, unique `slug`, optional `category`
- `content` — Markdown or HTML (`render_as_html`); **may be empty** (app shells)
- Access: `roles_with_access`, `allowed_emails`
- Literal `\n` sequences in pasted content are normalized to real newlines on save

Public/read URL key is **slug** (`GET /api/pages/<slug>/`). Site routes: `/p/<menuItemId>/<slug>`.

Superusers can edit page content from the SPA (breadcrumb pencil / Notes pencil) with `?page_edit=1` or `?edit=1` and debounced autosave (~10s).

### 3.2 Menu tree

`MenuItem` is a self-referential tree:

- Folder: `page=null` (optional `external_url`)
- Leaf: links a `Page` and/or external URL
- `order`, `show_in_menu`, `roles_with_access`
- `full_path` computed on save (`A -> B -> C`)

**Requirements preserved from original spec:**

1. Hierarchical dropdown menu  
2. Breadcrumbs from the menu tree  
3. Same page can appear under multiple menu branches  

Frontend: `Layout.jsx` (menu), `Breadcrumbs.jsx`, `PageView.jsx` (folder directory cards when no page).

The SPA refetches `GET /api/menu/` when auth/role changes so role-gated items (e.g. `roles_with_access=superuser`) appear or disappear after login/logout.

### 3.3 Blog / Articles

Separate content type: `BlogPost` (+ categories, tags, comments).

| Route | Notes |
|-------|--------|
| `/blog`, `/blog/:slug` | Primary |
| `/articles`, `/articles/:slug` | Legacy aliases |

Publishing uses `is_published` / `publish_date`; preview via `preview_token`. Admin supports Substack import.

**Subscribe UI** lives near the top of the blog catalog (`BlogCatalog.jsx`):

- Logged out → social login, then opt in  
- Logged in → toggle prefs via `/api/me/preferences/`  
- Intent survives OAuth redirect via `sessionStorage` (`pendingBlogSubscribe`)

### 3.4 Notes (Notebook → Notes)

Internal organizational tree **independent of the site menu**:

| Model | Role |
|-------|------|
| `NoteNode` | Folder (`page=null`) or link to a selected `Page` |

UI: `NotesApp` on page slug `notes` — collapsible left tree (folders first, then A–Z), right preview, create/link/edit pages. Selection and sidebar collapse are stored in query params (`node`, `doc`, `sidebar`, `new`, `edit`) for bookmarks and history.

Seed/repair menu: `backend/add_notes_menu.py`.

### 3.5 Subscription / contact preferences

`Subscription` is the email-keyed **contact preferences** record (not Django `User` profile fields):

| Field | Purpose |
|-------|---------|
| `email` (unique) | Stable identity for social + staff |
| `user` (nullable FK) | Linked Django/token user when known |
| `name`, `provider` | Display / last auth provider |
| `is_active` | Master switch — inactive contacts excluded from outreach |
| `blog_subscribed` | Opted in to the blog list |
| `notify_on_article` | Email when a new article is published |
| `subscribed_at`, `updated_at` | Audit |

**Opt-in rules:**

- Social login **creates/updates** the contact row (name, provider, user link) but does **not** set `blog_subscribed` / `notify_on_article`.
- Subscribe on `/blog` sets both true; unsubscribe clears both; notify can be toggled while subscribed.
- Existing active contacts were grandfathered into blog + notify prefs by migration `0025`.

Article email sending on publish is **not** wired yet; `notify_on_article` is the flag for that later job.

### 3.6 First-party analytics (`SiteEvent`)

Append-only page-view log for **any SPA route** (not blog-only):

| Field | Notes |
|-------|--------|
| `event` | Currently `page_view` |
| `path` | Pathname (query ignored to avoid Notes UI spam) |
| `page` / `post` | Optional FKs when path resolves to `Page` or `BlogPost` |
| `ip`, `country` | From `CF-Connecting-IP` / `CF-IPCountry` when present |
| `user_agent`, `referrer`, `session_key` | Client / request metadata |
| `user`, `subscription` | Filled when Token (or matching email) is known |

- Ingest: `POST /api/analytics/events/` (`AllowAny`; Token optional)
- SPA: `Layout` → `trackPageView` on `location.pathname` change; tab-session dedupe
- Skips OAuth callbacks and obvious bot UAs; soft per-IP rate limit
- Browse in Django admin → **Site events**

Complements Cloudflare zone analytics; Cloudflare alone often only sees the SPA shell.

### 3.7 Vacation List (`vacation_list` app)

Ported from `lister` packing-list domain with **`Vac*` prefixes** (avoids colliding with blog/menu names):

| Model | Role |
|-------|------|
| `VacTag` / `VacCategory` | Catalog taxonomy |
| `VacItem` | Reusable packing catalog item (`name_group`, tags, category) |
| `VacList` | Trip list; `initial_tags` used to seed membership |
| `VacListItem` | Item on a list (`need` / `done`); FK `in_list` only (no redundant M2M) |

- API (Token required): `/api/vacation/tags|categories|items|lists|list-items/`
- List helpers: `GET …/lists/<id>/items/`, `POST …/lists/<id>/seed/`, `POST …/lists/<id>/bulk/`
- SPA: slug `vacation-list` → `VacationListApp`
- Seed pages/menu: `backend/add_vacation_asset_pages.py`
- Data import from legacy lister DB: `backend/scripts/import_lister_data.py` (scoped tables only)
- Prod sync wrapper (does **not** replace `db.sqlite3`): monorepo `scripts/sync_devenkalra_lister_data.sh`

### 3.8 Asset Manager (`asset_manager` app)

Ported from `lister` inventory domain:

| Model | Role |
|-------|------|
| `AssetPhoto` | GFK photos (`upload_to=ass_photos/`) |
| `AssetBase` | Abstract: name, description, category, tags, locator |
| `AssetCategory` / `AssetTag` | Unique taxonomy |
| `AssetArea` | Nested areas (`parent_area`) |
| `AssetBox` | Nested boxes; in parent box **xor** area |
| `AssetItem` | In box **xor** area (orphan allowed) |

- API (Token required): `/api/assets/categories|tags|areas|boxes|items/`
- Admin: full CRUD + photo inlines (richer workflows than the SPA v1)
- SPA: slug `asset-manager` → `AssetManagerApp` (search / quick-add)
- Requires **Pillow** for `ImageField`

### 3.9 Other structured content

| Model | Typical use |
|-------|-------------|
| `Project` | Nested projects (e.g. photography / video AI) |
| `WorkflowIdea` | Idea tracker |
| `BookReview`, `MusicTrack`, `Recipe` | Catalog UIs |
| `StaticFile` | Uploads or fetch-from-URL → `/api/media/` |
| `PageData` | JSON blob keyed by `page_slug` (e.g. exercise planner) |

---

## 4. Custom apps (slug mounts)

After rendering page content, `PageView.jsx` mounts React apps by **page slug**:

| Slug | App |
|------|-----|
| `time-keeper` | Clock / world clock / stopwatch / timer |
| `exercise-planner` | Workouts (`PageData`) |
| `notes` | Notes folder tree + editor |
| `vacation-list` | Packing lists (`vacation_list`) |
| `asset-manager` | Physical inventory (`asset_manager`) |
| `creative-projects` | ClickUp-backed projects |
| `contacts` | ClickUp-backed contacts |
| `book-reviews`, `indian-music`, `cooking-snacks`, `track-ideas` | Inline catalog UIs |
| photography / video internship slugs | Project trees |

**Convention for new apps:**

1. Create/ensure `Page` with chosen slug (content optional).  
2. Attach under desired `MenuItem`.  
3. Add `{activeSlug === '…' && <App />}` in `PageView.jsx`.  
4. Persist via dedicated models + API, `PageData`, or client-only storage.

---

## 5. Auth and access control

| Mechanism | Behavior |
|-----------|----------|
| Password login | Django user → DRF **Token** (+ session); FE stores `authToken` |
| Social Google | OAuth **authorization-code** redirect → `/login/google/callback` → backend exchanges `code` + `redirect_uri` (legacy GIS `id_token` still accepted) |
| Social GitHub | OAuth code → `/login/github/callback` |
| Role | `None` (logged out) \| `user` (any authenticated) \| `superuser` |
| Superuser | Django staff/superuser **or** email in `SOCIAL_SUPERUSERS` |
| `roles_with_access` | Comma-separated; blank = public; **`user`** = any logged-in person; superuser bypasses |
| `allowed_emails` | Optional extra allowlist on pages |

Display names prefer real name / email over internal usernames like `google_<sub>`.

Mutating Notes/page APIs use **Token** auth. Prefer `credentials: 'omit'` with `Authorization: Token …` for POSTs so session CSRF does not block the SPA.

Endpoints: `/api/auth/login|logout|status|csrf|config/`, `/api/auth/social/google|github/`, `/api/me/preferences/`.

---

## 6. API surface (summary)

Base: `/api/`. Interactive docs: `/api/docs/` (schema `/api/schema/`).

| Area | Paths |
|------|--------|
| Menu | `GET /menu/`; CRUD `/menu-items/` |
| Pages | CRUD `/pages/` (slug lookup) |
| Notes | CRUD `/note-nodes/`; `GET /note-nodes/tree/` |
| Preferences | `GET\|PATCH /me/preferences/` (Token; `blog_subscribed`, `notify_on_article`, …) |
| Analytics | `POST /analytics/events/` (page views; anonymous OK) |
| Vacation | `/vacation/tags|categories|items|lists|list-items/` (auth) |
| Assets | `/assets/categories|tags|areas|boxes|items/` (auth) |
| PageData | `GET\|POST /page-data/<slug>/` |
| Catalogs | `/projects/`, `/ideas/`, `/books/`, `/tracks/`, `/recipes/` |
| Blog | `/blog/categories|tags|posts/`, comments |
| ClickUp | `/clickup/tasks/`, `/clickup/contacts/` (auth) |
| Media | `/api/media/…` |

List/retrieve for pages and menu are generally public (retrieve still enforces page access). Create/update/destroy require authentication unless noted.

---

## 7. Admin and markdown editing

- **Page admin** (`admin/core/page/change_form.html`): split editor + live preview (Marked iframe for Markdown; HTML mode injects editorial styles). Matches site fonts (Newsreader / Source Sans 3) rather than GitHub Markdown CSS.
- **Blog admin**: similar preview + Substack import + preview URL.
- **Subscription admin**: contact prefs (`blog_subscribed`, `notify_on_article`, linked `user`).
- **Frontend Markdown**: `MarkdownBody` + `remark-gfm` + `rehype-raw`; heading anchors via `## Title [#id]` (`utils/markdown.js`).
- Cheat sheet seed: `backend/seed_data/markdown-cheat-sheet.md`.
- Editorial CSS for HTML iframes: `frontend/public/iframe-editorial.css` (keep in sync with `frontend/src/index.css` typography).

---

## 8. Frontend packaging and CSS workflow

- Production UI is **built into the Docker image** as `frontend_dist`. Changing `index.css` / React requires rebuilding `devenkalra-app`.
- Vite `npm run dev` is available for local hot reload against the API.
- Admin template changes apply when templates are mounted (local compose) or after image rebuild.

---

## 9. Environment (selected)

See `backend/.env.template` (and host `.env`):

- Django / DB / `ALLOWED_HOSTS`
- `FRONTEND_URL` (blog preview links)
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (OAuth redirect to `{origin}/login/google/callback`; register that exact URI in Google Cloud Console)
- `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET`
- `SOCIAL_SUPERUSERS`
- ClickUp tokens (projects / contacts apps)

---

## 10. Design principles

1. **Menu for navigation, models for domain data** — don’t overload the menu tree for app-internal structure (Notes uses `NoteNode`).  
2. **Slug is the stable app contract** — custom UIs mount by page slug.  
3. **Access is declarative** — roles + optional emails on pages/menu items; use `user` for “any logged-in person”.  
4. **Email-keyed prefs, not User columns** — contact/marketing flags live on `Subscription`; auth stays on Django `User` / token.  
5. **Explicit blog opt-in** — social login links identity; Subscribe sets prefs.  
6. **Markdown by default, HTML when needed** — `render_as_html` + shared editorial styles.  
7. **SPA + API in one deployable** — single container serves API, admin, media, and built frontend.  
8. **Bookmarkable app state** — Notes encodes selection/UI in the query string.

---

## 11. Related files

| Concern | Path |
|---------|------|
| Product brief | `spec.md` |
| Models | `backend/core/models.py` |
| API routes | `backend/core/urls.py`, `backend/backend/urls.py` |
| SPA shell | `frontend/src/App.jsx`, `views/PageView.jsx` |
| Auth | `frontend/src/context/AuthContext.jsx`, `utils/googleOAuth.js`, `views/GoogleCallback.jsx` |
| Blog catalog / subscribe | `frontend/src/views/BlogCatalog.jsx` |
| Page analytics | `frontend/src/utils/pageAnalytics.js` (hooked from `Layout.jsx`) |
| Notes UI | `frontend/src/components/NotesApp.jsx` |
| Vacation list | `backend/vacation_list/`, `frontend/src/components/VacationListApp.jsx` |
| Asset manager | `backend/asset_manager/`, `frontend/src/components/AssetManagerApp.jsx` |
| Vac/Asset page seed | `backend/add_vacation_asset_pages.py` |
| Dockerfile | `devenkalra.com/Dockerfile` |
| Local compose | monorepo `docker-compose.local.yml` (`devenkalra-app`) |
| Notes menu seed | `backend/add_notes_menu.py` |
| Targeted prod deploy | monorepo `scripts/deploy_app.sh` (FF-merges `origin/<branch>`, rebuilds selected services) |
| Devenkalra-only deploy | `scripts/deploy-devenkalra-prod.sh` (`git pull --ff-only` then rebuild) |
