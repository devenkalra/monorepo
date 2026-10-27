# Product Requirements Document: Email Processor

**Product:** Intelligent Email Processor  
**Surface:** `devenkalra.com` page slug `email-processor` → `EmailProcessorApp`  
**Backend:** Django app `email_processor` (`/api/email/…`)  
**Audience:** Single superuser operator (personal mailbox automation)  
**Status:** Implemented (local + deployable); stack uses SQLite job/session store + in-process worker (not Celery/Redis)

---

## 1. Problem & vision

### Problem
Inbox traffic mixes high-value signals (writing ideas, images, actionable mail) with noise (newsletters, automated notifications). Manual triage is slow; bulk cleanup is error-prone; useful content is not captured into downstream systems (ClickUp, Static Files).

### Vision
Turn one Gmail inbox into a **proactive automation engine**:

1. **Ingest** mail in near-real time (Pub/Sub + history reconcile).
2. **Classify** with an LLM (or alias bypass) into structured intents.
3. **Act** automatically when confidence and risk rules allow; otherwise **human-in-the-loop**.
4. **Command** the inbox conversationally and with checkbox selection for bulk ops and AI summaries.

The mailbox becomes a structured input channel, not only a message silo.

---

## 2. Goals & non-goals

### Goals
- Keep the operator’s INBOX clean without losing important mail.
- Capture writing ideas into ClickUp with summary + URLs + sender metadata.
- Ingest usable images into the site Static Files library with AI descriptions.
- Auto-archive safe noise (newsletters / ignore) after labeling as Processed.
- Provide a review queue for ambiguous or sensitive classifications.
- Provide a Command Center for NL search, selection actions, saved prompts, and AI summarization of selected messages.

### Non-goals
- Multi-tenant / multi-mailbox product (single active mailbox only).
- Permanent Gmail delete (Trash only; never auto-delete).
- Full email client (compose, reply, folders UI).
- Autonomous handling of receipts, unknown intent, or personal/financial risk mail.
- Celery/Redis as a hard requirement (current design uses SQLite + in-process worker).

---

## 3. Users & access

| Role | Access |
|------|--------|
| Site **superuser** | Full UI + API |
| Other authenticated users | Denied |
| Anonymous | OAuth callback + Pub/Sub webhook only (constrained) |

- UI: sign-in required; gate on `role === 'superuser'` (or staff equivalent in SPA).
- API: Django Token auth + `IsSuperuserRole`.
- CMS page seeded with `roles_with_access: superuser`.

---

## 4. Product pillars

### Pillar A — Event ingest & sync
Gmail `users.watch` on INBOX publishes to a GCP Pub/Sub topic. Push hits `/api/email/pubsub/`, which enqueues a **reconcile** job (coalesced so bursts do not stampede). Reconcile uses stored `historyId` → `history.list` (`messageAdded`); on failure/missing history, falls back to recent INBOX listing. New message IDs become **fetch → classify → workflow** jobs. Periodic reconcile (≈60 min) covers missed pushes. Watch renew when expiration is within ~1 day.

### Pillar B — Intelligent router
Each message is classified into a structured intent with confidence, summary, extracted fields, suggested actions, and risk flags. High-confidence safe intents auto-run workflows; everything else goes to **Needs Review**. Alias To-addresses (e.g. `writing_idea@…`) can bypass the LLM and force an intent at confidence 1.0.

### Pillar C — Workflows
Specialized runners convert classified mail into ClickUp tasks, Static File assets, or archive-only outcomes, then apply Gmail **Processed** + remove INBOX/UNREAD.

### Pillar D — Command Center
Natural-language Prompt-to-Select over live Gmail, checkbox/selection bulk actions, persisted labeled saved searches, and ephemeral AI summaries of selected message bodies.

---

## 5. Functional requirements

### 5.1 Mailbox connection
- Operator connects Gmail via OAuth (`gmail.modify`), offline refresh token required.
- On connect: ensure labels `Processed` and `Needs-Review`; register watch; enqueue initial reconcile.
- Only one `MailboxAccount` is active at a time.
- UI actions: Connect, Sync now, Renew watch, Refresh status.

### 5.2 Classification
**Intents:** `writing_idea` | `image_ingest` | `newsletter` | `receipt` | `ignore` | `unknown`

**Auto-run when all are true:**
- Confidence ≥ `EMAIL_CONFIDENCE_AUTO` (default **0.85**)
- Intent ∈ `{writing_idea, image_ingest, newsletter, ignore}`
- No risk flags `possible_personal` or `possible_financial`
- Intent is never `receipt` or `unknown` for auto-run

**Otherwise:** status `needs_review`, Gmail label `Needs-Review` (mail stays in INBOX).

**Alias bypass:** configured `EMAIL_ALIAS_ROUTES` (e.g. `writing_idea@kalra.com:writing_idea`) match recipient headers and skip LLM.

### 5.3 Workflows

| Intent / action | Behavior |
|-----------------|----------|
| `writing_idea` | Create ClickUp task (`markdown_content` = summary + URLs); optional “original sender” custom field |
| `image_ingest` | Extract MIME + HTML remote images; skip &lt;10KB or &lt;100×100; OpenAI describe; save `StaticFile` |
| `newsletter` / `ignore` | Archive-only (no external task); then Processed + archive |
| `receipt` / `unknown` | Never auto-run; review queue only |

After any successful workflow: apply **Processed**, remove **INBOX** + **UNREAD**. Auto path **never** deletes mail.

### 5.4 Needs Review queue
- List messages in `needs_review` with classification summary and Gmail link.
- Per-message: Approve (run classified intent), force Idea / Images / Ignore.
- Bulk: approve, dismiss, archive, trash (**confirm**), assign label, mark processed.
- Selection: select-all + Shift+range checkboxes.

### 5.5 Command Center (Prompt-to-Select)

**Search**
- Operator enters NL prompt (e.g. “Find newsletters from today”).
- System produces a Gmail query (LLM plan, with heuristic fallback) and lists up to N metadata rows.
- Active list stored in `CommandSession` (SQLite, TTL, e.g. 1 hour)—not Redis.
- Force search option ignores “treat as action on current list.”

**NL follow-up actions** (on numbered list)
- archive, trash (**confirm**), mark_read / mark_unread, label_processed
- Permanent delete is unsupported

**Deterministic selection bar**
- Checkbox / select-all / Shift+range on list rows
- Actions by `thread_ids` / `gmail_ids`: archive, trash (confirm), mark_read/unread, label, label_processed
- **Summarize** (max **10** messages): fetch full bodies; return ephemeral structured summary:
  - Brief Summary
  - Key Points
  - Detailed Summary
- Summarize does not mutate Gmail

**Saved searches**
- Persist prompt + optional Gmail query + **label** per user (`SavedSearch`)
- Cross-device / cross-session via API
- Save from active search; rename label; remove; click loads prompt into the box (does not auto-run)
- Soft cap ~40 per user

**UI chrome**
- Searching-for line, confirm banner, AI summary panel, example chips, recent prompt log, mailbox meta, recent classifications, recent workflow runs

---

## 6. User journeys

### J1 — Connect & idle automation
1. Superuser opens Email Processor → Connect Gmail → OAuth consent.  
2. Watch + reconcile start; new mail arrives via Pub/Sub.  
3. High-confidence newsletter → Processed + archived.  
4. High-confidence writing idea → ClickUp task + archived.  
5. Ambiguous mail → Needs Review.

### J2 — Review triage
1. Operator opens Needs Review.  
2. Approves idea / forces Images / dismisses as ignore.  
3. Or bulk-archives / labels / trash (with confirm).

### J3 — Command Center cleanup
1. “Find email from Smithsonian, Borowitz, InfoQ…” → numbered list.  
2. Select subset → Archive / Label / Delete (confirm).  
3. Or Summarize → Brief / Key Points / Detailed panel.  
4. Save search with label “Newsletters” for later reuse.

---

## 7. System architecture (as built)

```
Gmail INBOX ──watch──► GCP Pub/Sub ──push──► /api/email/pubsub/
                                              │
                                              ▼
                                    EmailJob (SQLite queue)
                                              │
                         in-process worker (EMAIL_WORKER_ENABLED)
                                              │
                    reconcile → fetch_message → classify → run_workflow
                                              │
                         ┌────────────────────┼────────────────────┐
                         ▼                    ▼                    ▼
                      ClickUp            StaticFile            Archive
                         │                    │                    │
                         └────────── Processed + leave INBOX ──────┘

SPA EmailProcessorApp
  ├─ Mailbox controls
  ├─ Command Center (NL + selection + summarize + saved searches)
  ├─ Needs Review
  └─ Recent classifications / runs
```

| Concern | Choice |
|---------|--------|
| App | Django + DRF |
| UI | React SPA page |
| Jobs | `EmailJob` + daemon thread |
| Command session | `CommandSession` JSON + TTL |
| LLM | OpenAI (`EMAIL_OPENAI_*`) |
| Gmail | OAuth user mailbox, `gmail.modify` |
| Persistence | Site DB (SQLite locally; Postgres-capable in other envs) |

---

## 8. Data model (logical)

| Entity | Purpose |
|--------|---------|
| `MailboxAccount` | OAuth tokens, `historyId`, watch expiry, sync health |
| `EmailMessage` | Synced message metadata + processing status |
| `Classification` | Intent JSON, confidence, extracted fields, bypass flag |
| `WorkflowRun` | Outcome of ClickUp / image / archive runs |
| `EmailJob` | Async work units with retries |
| `CommandSession` | Active Prompt-to-Select list for a user |
| `SavedSearch` | Labeled saved NL prompts / queries |

Message statuses (conceptual): `new` → `processing` → `processed` | `needs_review` | `failed` | `ignored`.

---

## 9. API surface (summary)

Base path: `/api/email/`

| Area | Endpoints |
|------|-----------|
| OAuth | `GET oauth/start/`, `GET oauth/callback/` |
| Push | `POST pubsub/` |
| Mailbox | `GET mailbox/`, `GET mailbox/status/`, `POST mailbox/sync_now/`, `POST mailbox/renew_watch/` |
| Messages | `GET messages/`, `GET messages/{id}/`, `POST …/approve/`, `POST …/dismiss/`, `POST messages/bulk/` |
| Runs | `GET runs/` |
| Command | `GET/POST/DELETE command/`, `POST command/selection/` |
| Saved | `GET/POST/PATCH/DELETE saved-searches/` |

---

## 10. Configuration

| Variable | Role |
|----------|------|
| `EMAIL_WORKER_ENABLED` | Start in-process job worker |
| `EMAIL_GMAIL_CLIENT_ID` / `SECRET` | Gmail OAuth (fallback: site Google OAuth) |
| `EMAIL_OAUTH_REDIRECT_URI` | Public callback URL |
| `EMAIL_PUBSUB_TOPIC` | Gmail watch topic |
| `EMAIL_PUBSUB_VERIFICATION_TOKEN` | Optional push auth |
| `EMAIL_OPENAI_API_KEY` / `EMAIL_OPENAI_MODEL` | Classify, command NL, summarize, image describe |
| `EMAIL_ALIAS_ROUTES` | Direct-to-intent recipient map |
| `EMAIL_CLICKUP_LIST_ID` / `EMAIL_CLICKUP_SENDER_FIELD_ID` | Writing-idea workflow |
| `EMAIL_CONFIDENCE_AUTO` | Auto-run threshold (default 0.85) |
| `EMAIL_COMMAND_SESSION_TTL` | Command session TTL seconds |
| `FRONTEND_URL` | Post-OAuth redirect host |
| `CLICKUP_API_TOKEN` | Shared ClickUp auth |

---

## 11. Safety, privacy & reliability

### Safety
- Auto pipeline **never** deletes mail.
- Trash only via explicit Command Center / review bulk with **confirm**.
- Classifier must not recommend deleting personal/financial mail; only bulk-safe noise for archive automation.
- Auto-run blocked for receipts, unknown intent, and personal/financial risk flags.
- Summarize capped at 10 messages; result is ephemeral (not a new durable model).

### Reliability
- Job retries with backoff (bounded attempts).
- Reconcile coalescing under Pub/Sub bursts.
- Periodic sync fallback if pushes are missed.
- Watch renewal before expiry.
- Command sessions expire via TTL; single active list per user.

### Access
- Superuser-only product surface.
- Pub/Sub endpoint may use shared verification token.
- OAuth callback is public but exchanges one-time Google code only.

---

## 12. Success metrics (product)

| Metric | Intent |
|--------|--------|
| % of new mail auto-processed without review | Automation leverage |
| Needs-review queue age / depth | HITL load |
| False auto-archives (operator undo / complaints) | Safety |
| Writing ideas created / week | Downstream value |
| Images ingested / week | Asset pipeline value |
| Command Center actions / session | Interactive usefulness |
| Summarize usage + time-to-decision | Reading-assist value |

---

## 13. Out of scope / future candidates

Not required for current PRD completion; candidates only:

- Multi-mailbox / shared team access  
- Receipt → expense / spreadsheet workflows  
- Reply / draft generation  
- Celery/Redis migration if volume demands it  
- Durable summary history  
- Explicit 1 notification/sec hard rate limiter (beyond reconcile coalesce)  
- Dedicated cron service (vs worker maintenance) for watch renew  

---

## 14. Acceptance criteria (MVP complete when)

1. Superuser can connect one Gmail mailbox and see sync status.  
2. New INBOX mail is fetched, classified, and either auto-workflowed or queued for review.  
3. Writing-idea and image-ingest workflows produce ClickUp / StaticFile outcomes and archive Processed mail.  
4. Newsletter/ignore auto-archive without delete.  
5. Needs Review supports approve / dismiss / bulk archive-label-trash (trash confirmed).  
6. Command Center can search via NL, act via NL or checkboxes, save labeled searches, and summarize selected mail as Brief Summary / Key Points / Detailed Summary.  
7. Auto path never deletes; trash always requires confirm.  

---

## 15. Related docs & code

| Artifact | Location |
|----------|----------|
| This PRD | `devenkalra.com/emailhandler.md` |
| Architecture notes | `devenkalra.com/DESIGN.md` §3.9 |
| Backend | `devenkalra.com/backend/email_processor/` |
| SPA | `devenkalra.com/frontend/src/components/EmailProcessorApp.jsx` |
| Page seed | `devenkalra.com/backend/add_email_processor_page.py` |
| Env template | `devenkalra.com/backend/.env.template` |
