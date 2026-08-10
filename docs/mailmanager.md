# Gmail Assistant — Design (bldrdojo)

As-built design for the Gmail Inbox Assistant on **bldrdojo.com**.  
Operator/setup details: `data-backend/gmail_assistant/README.md`.

## Goal

First-class bldrdojo app for search → select → act on Gmail (labels, archive, trash, LLM summarize/process), with optional **scheduled summarize** jobs.

Distinct from:

| App | Mechanism | Purpose |
|-----|-----------|---------|
| **Gmail Assistant** (this) | Gmail API + OAuth | Live inbox ops + LLM |
| `mail_archive` + `email-frontend` | IMAP / app password | Archive import |
| devenkalra `email_processor` | Gmail API | Separate product on devenkalra.com |

## Architecture

```
Browser  /gmail-app/  (Vite SPA, JWT in localStorage)
    │
    ├─ /login/          Django static login.html (same JWT as other apps)
    └─ /api/gmail/      Django DRF (feature-flagged)
              │
              ├─ Gmail API (OAuth refresh tokens per user/account)
              ├─ Postgres (accounts, prefs, prompts, summaries, jobs, schedules)
              ├─ Celery worker  (summarize / process / run schedule)
              └─ Celery beat    (every 15m: enqueue due summarize schedules)
                        │
                        └─ LocalAI first → OpenAI fallback
```

| Layer | Path |
|-------|------|
| Frontend | `gmail-frontend/` → Vite base `/gmail-app/` |
| Backend | `data-backend/gmail_assistant/` |
| API mount | `/api/gmail/` when `ENABLE_GMAIL_ASSISTANT=True` |
| Auth | Existing bldrdojo JWT (`Authorization: Bearer`); no separate login |
| Wiring | Same pattern as food: `INSTALLED_APPS`, urls, nginx, `frontend/Dockerfile`, `npm run dev:gmail` |

## Product behavior

### Connect & accounts

- Google OAuth scopes: `gmail.modify`, `gmail.labels`
- Multiple Gmail accounts per bldrdojo user; one **active** at a time
- Tokens stored in Postgres (`GmailAccount.refresh_token`); refreshable
- Redirect URI env: `GMAIL_OAUTH_REDIRECT_URI`  
  - Local: `http://localhost:8000/api/gmail/oauth/callback/`  
  - Prod: `https://bldrdojo.com/api/gmail/oauth/callback/`  
- After OAuth, browser returns to SPA (`GMAIL_UI_ORIGIN` locally; empty in prod = same origin)

### Search

- Rule-based NL → Gmail `q=` (**no LLM** for query building): `nl_query.py`
- Qualifiers: start/end date, days (`newer_than`), keyword
- Live query preview; search with prompt and/or qualifiers
- Results: From, Subject, snippet, smart date, “Summarized” chip

### Selection & bulk actions

- Checkbox, select-all, **shift-click range**, row click focuses + selects
- Archive, Delete (toolbar confirms; detail **Delete & next** does not), Assign label, Move to (label + archive), Summarize, Process

### Detail pane

- Clicking a row loads full message via `GET /api/gmail/emails/<id>/`
- HTML body in a **sandboxed iframe** (formatting preserved); plain text fallback
- Summary fields shown above the body when present
- **Expand** → full-viewport view; **Next** / **Delete & next** walk search results
- Optional **Open in Gmail ↗** (thread URL); subject no longer navigates away by default

### Saved prompts

- Named NL prompts; load fills the box, does **not** auto-run

### Summarize (Celery)

- Selected emails only (or schedule-selected set)
- Skip if already summarized unless `force`
- Persist: brief summary, key points, details, category + confidence
- Categories: Marketing, Newsletter, Offer, Receipt, Important, Personal, Work, Social, Spam, Other
- Progress polled from Redis-backed task progress

### Process (Celery)

- Free-form prompt over selected emails
- Bodies packed into batches by configured context size (8192–64000)
- Result in detail pane; discarded from DB when zero-knowledge is on

### Scheduled summarize

- UI: **Schedules** — create from current search filters + `interval_hours` (1–168)
- Model: `SummarizeSchedule` (filter fields, account, enabled, force, last run/status)
- Beat task `run_due_summarize_schedules` every **15 minutes** → `run_summarize_schedule` → existing summarize task
- Requires `celery-beat` service (compose + `deploy_app.sh` for bldrdojo)

### Zero-knowledge (default off)

- Preference: do not persist email content / summary text
- Category + confidence OK; process result not stored; UI may show session-only chips

## Data model (Postgres)

| Model | Role |
|-------|------|
| `GmailAccount` | Per-user connected mailbox + refresh token |
| `UserPreference` | ZK flag, LLM context size |
| `SavedPrompt` | Named NL prompts |
| `EmailSummary` | Per-message summary / category |
| `LlmJob` | Summarize/process job + progress metadata |
| `SummarizeSchedule` | Repeatable filter + interval |

## LLM

- `LOCALAI_URL` + `LOCALAI_API_KEY` + `GMAIL_LOCALAI_MODEL` tried first
- Fallback: `OPENAI_API_KEY` + `GMAIL_OPENAI_MODEL` (default `gpt-4o-mini`)
- Celery worker must have these env vars (from `data-backend/.env`)

## Auth / local UX notes

- Login allowlist includes `/gmail-app/` (`data-backend/static/login.html`)
- Vite `:5177` proxies `/api`, `/login`, `/accounts`, `/static` to Django `:8000`
- Django `DEBUG`: `/gmail-app/` redirects to `http://localhost:5177/gmail-app/` (SPA not served by Django alone)
- Prod: nginx serves SPA from frontend image; login + API on same origin

## Deploy

```bash
# on server
bash ./scripts/deploy_app.sh --app bldrdojo
# rebuilds backend, frontend, celery-worker, celery-beat
```

Env on server `data-backend/.env` must include `ENABLE_GMAIL_ASSISTANT=True`, OAuth redirect, and LLM settings. Google Console must list the prod redirect URI on the **same** OAuth client as login.

If migrate reports table/index already exists from a partial apply, fake the conflicting migration then continue (`migrate gmail_assistant 0002 --fake`, etc.).

## API surface (JWT)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/gmail/status/` | Connection + prefs |
| GET/PATCH | `/api/gmail/preferences/` | ZK, context size |
| * | `/api/gmail/accounts/…` | List / activate / disconnect |
| GET | `/api/gmail/oauth/start/` | Begin Gmail OAuth |
| GET | `/api/gmail/oauth/callback/` | OAuth return |
| POST | `/api/gmail/query/preview/` | NL → q preview |
| POST | `/api/gmail/search/` | Search messages |
| GET | `/api/gmail/emails/<id>/` | Full message + summary for detail pane |
| POST | `/api/gmail/emails/bulk/` | archive / delete / labels / move |
| GET/POST | `/api/gmail/schedules/` | List / create schedules |
| PATCH/DELETE | `/api/gmail/schedules/<id>/` | Update / delete |
| POST | `/api/gmail/schedules/<id>/run/` | Run schedule now |
| POST | `/api/gmail/summarize/` | Summarize selected |
| POST | `/api/gmail/process/` | Process selected |
| GET | `/api/gmail/tasks/<id>/progress/` | Poll Celery progress |

## Out of scope

- Replacing IMAP `mail_archive`
- Auto-summarizing every new mail without a schedule/filter
- Embedding LocalAI itself in this compose stack
- Google app verification for unrestricted public OAuth (Testing + test users is enough for private use)

## Definition of done

A logged-in bldrdojo user can connect Gmail, search with NL + qualifiers, inspect full HTML mail in-pane, archive/delete/label/move, summarize/process via Celery, and create interval schedules that summarize matching mail — all under `/gmail-app/` with JWT auth on bldrdojo.com.
