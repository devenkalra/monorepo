# Gmail Assistant

Inbox-style Gmail manager for bldrdojo: NL search, bulk actions, summarize/process via Celery.

## Enable

```env
ENABLE_GMAIL_ASSISTANT=True
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GMAIL_OAUTH_REDIRECT_URI=http://localhost:8000/api/gmail/oauth/callback/
GMAIL_UI_ORIGIN=http://localhost:5177
LOCALAI_URL=http://100.x.x.x:8180
LOCALAI_API_KEY=...
OPENAI_API_KEY=...   # fallback
GMAIL_LOCALAI_MODEL=qwen3-32b
GMAIL_OPENAI_MODEL=gpt-4o-mini
```

Register the redirect URI on the same Google Cloud OAuth client used for login. Add Gmail scopes usage in the consent screen (`gmail.modify`).

## Migrate

```bash
cd data-backend
python manage.py migrate gmail_assistant
```

## Frontend

```bash
npm run dev:gmail   # http://localhost:5177/gmail-app/
```

Production path: `/gmail-app/` (nginx + frontend Dockerfile).

## Production install

1. **Pull / deploy** the monorepo revision that includes `gmail_assistant` + `gmail-frontend`.
2. **Env** (`data-backend/.env` on the server):
   ```env
   ENABLE_GMAIL_ASSISTANT=True
   GOOGLE_CLIENT_ID=...
   GOOGLE_CLIENT_SECRET=...
   GMAIL_OAUTH_REDIRECT_URI=https://bldrdojo.com/api/gmail/oauth/callback/
   # Leave empty in prod so OAuth returns to same-origin /gmail-app/
   GMAIL_UI_ORIGIN=
   LOCALAI_URL=https://your-localai-host:8180
   LOCALAI_API_KEY=...
   OPENAI_API_KEY=...
   GMAIL_LOCALAI_MODEL=qwen3-32b
   GMAIL_OPENAI_MODEL=gpt-4o-mini
   ```
3. **Google Cloud Console** (same OAuth client as login):
   - Enable **Gmail API**
   - Add redirect URI: `https://bldrdojo.com/api/gmail/oauth/callback/`
   - Consent screen scopes: `gmail.modify`, `gmail.labels`
   - If app is in Testing, add production test users
4. **Rebuild** backend + Celery (new Python deps) and frontend (embeds `/gmail-app/`):
   ```bash
   docker compose -p <project> -f <prod-compose> build backend celery-worker frontend
   docker compose -p <project> -f <prod-compose> up -d --force-recreate backend celery-worker frontend
   ```
5. **Migrate**:
   ```bash
   docker compose ... exec backend python manage.py migrate gmail_assistant
   ```
6. Confirm Celery can reach Redis and that `gmail_assistant.tasks.summarize_emails_task` is listed in worker logs.
7. Smoke test: `https://bldrdojo.com/gmail-app/` → login → Connect Gmail → search → summarize.

## API

Mounted at `/api/gmail/` when the flag is on. JWT required.

## Zero-knowledge

User preference (default **off**). When on: no subject/from/snippet/summary text stored; category + confidence OK; process result discarded after poll; summarize chips are session-only on the client.

## E2E checklist

1. Login → open `/gmail-app/`
2. Connect Gmail (and a second account); switch active
3. Search with NL + days/keyword/dates; confirm query preview
4. Select (shift-range); Archive / Delete / Assign label / Move to
5. Save / load prompt (no auto-run)
6. Summarize selected → progress poll → chip
7. Process selected → result in detail pane
8. Toggle ZK on → summarize again (no content fields persisted)
9. Set context size 8192–64000 in Prefs
