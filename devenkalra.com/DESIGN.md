# devenkalra.com — Design Doc

Last updated: 2026-08-01

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

---

## 3. Content and navigation model

### 3.1 Pages

`Page` is the primary CMS unit:

- `title`, unique `slug`, optional `category`
- `content` — Markdown or HTML (`render_as_html`); **may be empty** (app shells)
- Access: `roles_with_access`, `allowed_emails`
- Literal `\n` sequences in pasted content are normalized to real newlines on save

Public/read URL key is **slug** (`GET /api/pages/<slug>/`). Site routes: `/p/<menuItemId>/<slug>`.

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

### 3.3 Blog / Articles

Separate content type: `BlogPost` (+ categories, tags, comments). Routes `/articles`, `/articles/:slug`. Publishing uses `is_published` / `publish_date`; preview via `preview_token`. Admin supports Substack import.

### 3.4 Notes (Notebook → Notes)

Internal organizational tree **independent of the site menu**:

| Model | Role |
|-------|------|
| `NoteNode` | Folder (`page=null`) or link to a selected `Page` |

UI: `NotesApp` on page slug `notes` — collapsible left tree, right preview, create/link pages into the current folder. Selection and sidebar collapse are stored in query params (`node`, `doc`, `sidebar`, `new`) for bookmarks and history.

Seed/repair menu: `backend/add_notes_menu.py`.

### 3.5 Other structured content

| Model | Typical use |
|-------|-------------|
| `Project` | Nested projects (e.g. photography / video AI) |
| `WorkflowIdea` | Idea tracker |
| `BookReview`, `MusicTrack`, `Recipe` | Catalog UIs |
| `StaticFile` | Uploads or fetch-from-URL → `/api/media/` |
| `PageData` | JSON blob keyed by `page_slug` (e.g. exercise planner) |
| `Subscription` | Newsletter / social subscribers |

---

## 4. Custom apps (slug mounts)

After rendering page content, `PageView.jsx` mounts React apps by **page slug**:

| Slug | App |
|------|-----|
| `time-keeper` | Clock / world clock / stopwatch / timer |
| `exercise-planner` | Workouts (`PageData`) |
| `notes` | Notes folder tree + editor |
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
| Social | Google ID token / GitHub OAuth → token + session `social_user` |
| Role | `None` \| `user` \| `superuser` (`get_user_role`) |
| Superuser | Django staff/superuser **or** email in `SOCIAL_SUPERUSERS` |
| `roles_with_access` | Comma-separated; blank = public; superuser bypasses |
| `allowed_emails` | Optional extra allowlist on pages |

Mutating Notes/page APIs use **Token** auth. Prefer `credentials: 'omit'` with `Authorization: Token …` for POSTs so session CSRF does not block the SPA.

Endpoints: `/api/auth/login|logout|status|csrf|config/`, `/api/auth/social/google|github/`.

---

## 6. API surface (summary)

Base: `/api/`. Interactive docs: `/api/docs/` (schema `/api/schema/`).

| Area | Paths |
|------|--------|
| Menu | `GET /menu/`; CRUD `/menu-items/` |
| Pages | CRUD `/pages/` (slug lookup) |
| Notes | CRUD `/note-nodes/`; `GET /note-nodes/tree/` |
| PageData | `GET\|POST /page-data/<slug>/` |
| Catalogs | `/projects/`, `/ideas/`, `/books/`, `/tracks/`, `/recipes/` |
| Blog | `/blog/categories|tags|posts/`, comments |
| ClickUp | `/clickup/tasks/`, `/clickup/contacts/` (auth) |
| Media | `/api/media/…` |

List/retrieve for pages and menu are generally public (retrieve still enforces page access). Create/update/destroy require authentication unless noted.

---

## 7. Admin and markdown editing

- **Page admin** (`admin/core/page/change_form.html`): split editor + live preview (Marked iframe for Markdown; HTML mode injects editorial styles). Matches site fonts (Inter / Lora) rather than GitHub Markdown CSS.
- **Blog admin**: similar preview + Substack import + preview URL.
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
- `GOOGLE_CLIENT_ID`, `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET`
- `SOCIAL_SUPERUSERS`
- ClickUp tokens (projects / contacts apps)

---

## 10. Design principles

1. **Menu for navigation, models for domain data** — don’t overload the menu tree for app-internal structure (Notes uses `NoteNode`).  
2. **Slug is the stable app contract** — custom UIs mount by page slug.  
3. **Access is declarative** — roles + optional emails on pages/menu items.  
4. **Markdown by default, HTML when needed** — `render_as_html` + shared editorial styles.  
5. **SPA + API in one deployable** — single container serves API, admin, media, and built frontend.  
6. **Bookmarkable app state** — Notes encodes selection/UI in the query string.

---

## 11. Related files

| Concern | Path |
|---------|------|
| Product brief | `spec.md` |
| Models | `backend/core/models.py` |
| API routes | `backend/core/urls.py`, `backend/backend/urls.py` |
| SPA shell | `frontend/src/App.jsx`, `views/PageView.jsx` |
| Notes UI | `frontend/src/components/NotesApp.jsx` |
| Dockerfile | `devenkalra.com/Dockerfile` |
| Local compose | monorepo `docker-compose.local.yml` (`devenkalra-app`) |
| Notes menu seed | `backend/add_notes_menu.py` |
