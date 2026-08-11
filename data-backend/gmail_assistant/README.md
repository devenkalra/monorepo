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

## Scheduled summarize

Create schedules in the UI (**Schedules**) or via `POST /api/gmail/schedules/`. Each schedule stores the same filter fields as search (`prompt`, `days`, `keyword`, dates) plus `interval_hours` (1–168).

Requires **Celery Beat** (`celery -A config beat`) in addition to the worker. Beat polls every 15 minutes and enqueues due schedules.

```bash
# local example
docker compose -f docker-compose.local.yml up -d celery-beat celery-worker
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
4. **Rebuild** backend + Celery worker/beat and frontend (embeds `/gmail-app/`):
   ```bash
   # preferred
   ./scripts/deploy_app.sh --app bldrdojo
   # or manually:
   docker compose -p <project> -f <prod-compose> up -d --build --force-recreate \
     --no-deps backend celery-worker celery-beat frontend
   ```
5. **Migrate**:
   ```bash
   docker compose ... exec backend python manage.py migrate gmail_assistant
   ```
6. Confirm worker lists `gmail_assistant.tasks.summarize_emails_task` and beat is running (`celery-beat` container).
7. Smoke test: `https://bldrdojo.com/gmail-app/` → login → Connect Gmail → search → summarize → Schedules.

Design overview: [`docs/mailmanager.md`](../../docs/mailmanager.md).

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
8. Enrich links → fetches web pages / images / YouTube transcripts, then summarizes
9. Toggle ZK on → summarize again (no content fields persisted)
10. Set context size 8192–64000 in Prefs

## Enrich links

`POST /api/gmail/enrich-links/` with `{gmail_ids, account_id?}`.

Pipeline (deterministic, not LLM-driven for discovery):

1. Extract `http(s)` URLs from body text + HTML `href`/`src` (HTML entities unescaped)
2. Classify:
   - YouTube → transcript
   - Instagram / Facebook / LinkedIn / X(Twitter) / TikTok → Apify scrape
   - image URL → download + vision describe
   - else → fetch page text
3. LLM summarizes email + linked content (LocalAI then OpenAI)

Requires worker deps: `beautifulsoup4`, `youtube-transcript-api`.  
Social scrapes need `APIFY_TOKEN`. Defaults:

| Source | Actor env | Default actor |
|--------|-----------|---------------|
| Instagram | `APIFY_INSTAGRAM_ACTOR` | `apify/instagram-scraper` |
| Facebook | `APIFY_FACEBOOK_ACTOR` | `apify/facebook-posts-scraper` |
| LinkedIn | `APIFY_LINKEDIN_ACTOR` | `simpleapi/linkedin-post-scraper` |
| X/Twitter | `APIFY_TWITTER_ACTOR` | `apidojo/tweet-scraper` |
| TikTok | `APIFY_TIKTOK_ACTOR` | `clockworks/tiktok-scraper` |

**Transcripts** (appended into enrich content for summarization):

| Source | Env | Default actor |
|--------|-----|---------------|
| YouTube | `APIFY_YOUTUBE_TRANSCRIPT_ACTOR` | `automation-lab/youtube-transcript` (fallback: `youtube-transcript-api`) |
| Instagram reels/posts | `APIFY_INSTAGRAM_TRANSCRIPT_ACTOR` | `khadinakbar/instagram-transcript-scraper` |
| TikTok | `APIFY_TIKTOK_TRANSCRIPT_ACTOR` | `clockworks/tiktok-transcript-extractor` |

LinkedIn group/private posts that 404 anonymously also need `LINKEDIN_LI_AT` (browser `li_at` cookie while logged in).
