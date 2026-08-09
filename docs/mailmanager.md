# Port: Gmail Inbox Assistant app for bldrdojo.com

## Goal
Recreate the Gmail parsing / inbox-assistant UX from the local AI gateway project as a first-class **bldrdojo app**:
- Frontend: new sibling Vite React SPA (or extend `email-frontend` if that’s clearly better)
- Backend: new Django + DRF module under `data-backend/` (or extend `mail_archive` only if Gmail API OAuth fits cleanly there)
- Mount like other apps: `/gmail-app/` (or `/email-app/` if extending email) + `/api/gmail/` (or `/api/mail/…`)
- Auth: use existing bldrdojo JWT (`AuthContext`, Bearer token) — do **not** invent a separate login
- Follow wiring pattern of **`food` + `food-frontend`** (INSTALLED_APPS, urls, nginx, Dockerfile, package.json scripts)
- Model UI/API behavior on the reference implementation below — do **not** reinvent product behavior

## Reference implementation (source of truth for behavior)
Local path (read these files; port behavior, don’t copy FastAPI/SQLite literally):
- `c:\code\aiserver\ui\gmail.html`
- `c:\code\aiserver\ui\gmail.js`
- `c:\code\aiserver\ui\gmail.css`
- `c:\code\aiserver\workflows\gmail\routes.py`
- `c:\code\aiserver\workflows\gmail\nl_query.py`
- `c:\code\aiserver\workflows\gmail\search.py`
- `c:\code\aiserver\workflows\gmail\workflow.py`
- `c:\code\aiserver\workflows\gmail\client.py`
- `c:\code\aiserver\workflows\gmail\oauth.py`
- `c:\code\aiserver\workflows\gmail\db.py`

Also check existing monorepo email work so we don’t duplicate the wrong thing:
- bldrdojo IMAP archive: `data-backend/mail_archive/` + `email-frontend/` (IMAP/app-password — **not** this product)
- devenkalra Gmail API processor: `devenkalra.com/backend/email_processor/` + EmailProcessorApp (reuse OAuth/Gmail API ideas if helpful, but ship as a **bldrdojo** app)

## Product (must match)
An inbox-style Gmail assistant:

1. **Connect Gmail** via Google OAuth with scopes allowing read + modify labels/archive/trash  
   (`gmail.modify`, `gmail.labels` in the reference). Store tokens per bldrdojo user (Postgres), refreshable.

2. **Natural-language search** (rule-based, **no LLM** for query building) → Gmail `q=` operators.
   - Freeform prompt examples:
     - `find email from smithsonian, borowitz, infoq in inbox`
     - `Get emails from the last day in inbox`
     - raw escape: `q:in:inbox newer_than:2d`
   - Live query preview under the prompt.
   - **Qualifiers** (UI fields, merged into the Gmail query):
     - Start date → `after:YYYY/MM/DD`
     - End date → `before:YYYY/MM/DD`
     - Days → `newer_than:Nd` (overrides NL time window when set)
     - Keyword → subject/body term (quote if multi-word)
   - Search allowed with prompt and/or qualifiers.

3. **Results list** like Gmail: checkbox, From, Subject, short snippet, smart date  
   (today → time; this year → Mon D; older → yy/mm/dd).  
   Chip when already summarized.

4. **Selection**: checkboxes, select-all, **shift-click range select**, row click focuses + selects.

5. **Bulk actions on selected**:
   - Archive (remove INBOX)
   - Delete (trash, confirm)
   - Assign label (add labels; keep in inbox)
   - **Move to** = assign label(s) **and** archive (remove INBOX) — same dialog pattern as Assign label
   - Summarize
   - Process

6. **Saved prompts**: save labeled NL prompts; selecting one fills the prompt box but does **not** auto-run; delete supported.

7. **Summarize** (LLM, per email):
   - Only selected emails
   - Skip if already summarized (unless force)
   - Persist: brief summary, key points, details, category + confidence
   - Categories roughly: Marketing, Newsletter, Offer, Receipt, Important, Personal, Work, Social, Spam, Other
   - Stream progress to the UI

8. **Process** (LLM, free-form prompt on selected emails):
   - Dialog: user prompt like “extract the books mentioned in these emails”
   - Combine email bodies; **pack into as few batches as fit model context**; run prompt per batch; merge answers when possible
   - Stream progress; show result in detail pane (need not persist unless easy)

9. **UX details to preserve**:
   - Subject is a link to open the thread in Gmail (`mail.google.com/.../#all/{threadId}`) in a new tab; clicking the link must not toggle row selection
   - Autolink `http(s)://` and `www.` URLs in snippets, summaries, key points, details, process result
   - Archive / delete / move remove rows from the current result list

## Technical constraints for bldrdojo
- Postgres models instead of SQLite; associate Gmail connection + saved prompts + summaries with the logged-in user
- LLM calls: use whatever LLM/gateway pattern bldrdojo already has (or a clear env-configured OpenAI-compatible endpoint). Do not hardcode LocalAI from aiserver unless that’s already how bldrdojo talks to models
- Prefer Celery for long summarize/process jobs if that matches existing patterns; otherwise streaming SSE/websocket consistent with the stack
- Feature-flag if other optional apps do (`ENABLE_…`)
- Wire nginx + frontend Dockerfile + root package scripts like food/email
- Document env vars: Google OAuth client for **Gmail API** (separate from login-only Google OAuth if needed), redirect URI, LLM base URL/model

## Implementation plan
1. Explore `food`/`food-frontend` and `mail_archive`/`email-frontend` wiring; skim devenkalra `email_processor` for Gmail OAuth patterns
2. Propose short design (app name, URL paths, models, OAuth storage) — then implement
3. Port NL query logic from `nl_query.py` (keep deterministic)
4. Build API + SPA matching the reference UX
5. End-to-end: Connect → Search with qualifiers → Select → Move/Label → Summarize → Process

## Out of scope
- Replacing the IMAP `mail_archive` importer
- Auto-processing every email on sync (this app is search → select → act)
- LocalAI-specific Docker from aiserver

## Definition of done
Logged-in bldrdojo user can connect Gmail, search with NL + date/days/keyword qualifiers, select messages, archive/delete/label/move, summarize selected mail into Postgres, and run a custom Process prompt with context-aware batching — all from a mounted SPA under bldrdojo.com with JWT auth.