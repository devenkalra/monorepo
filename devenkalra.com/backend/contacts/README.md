# Contact Sync

Syncs Google Contacts, LinkedIn and WhatsApp into the ClickUp **People** list, and exports/imports the People
and Orgs lists with the relationships between them. It replaces the scripts in `contacts_mgmt/` and shares one
engine between the web app (page `/p/contact-sync`, superusers only) and the CLI.

The user guide lives in the app (the **Help** button), sourced from
`frontend/src/components/contactSyncHelp.md`. This file covers setup and how the code fits together.

## Setup

Settings, read from the environment (`backend/.env` locally):

| Variable | Purpose |
| --- | --- |
| `CLICKUP_API_TOKEN` (or `CONTACTS_CLICKUP_TOKEN`) | ClickUp personal token |
| `CONTACTS_CLICKUP_LIST_ID` | The People list the sync reads and writes |
| `CONTACTS_CLICKUP_ORGS_LIST_ID` | The Orgs list (export only) |
| `CONTACTS_CLICKUP_WRITES_ENABLED` | `1` allows live writes; anything else is preview-only |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth web client (or `CONTACTS_GOOGLE_CLIENT_ID` / `_SECRET` to use a separate one) |
| `CONTACTS_OAUTH_REDIRECT_URI` | Pin the OAuth callback; defaults to `<request host>/api/contacts/oauth/callback/` |
| `CONTACTS_PLAN_MAX_AGE_HOURS` | How old a preview may be and still be applied (default 24) |
| `CONTACTS_WORKER_ENABLED` | Run queued runs in a background thread of the web process (default on) |
| `CONTACTS_DATA_DIR` | Uploads, exports and snapshots (default `backend/contacts_data/`, git-ignored) |

Google Cloud: enable the **People API**, and add the callback (for example
`http://localhost:8090/api/contacts/oauth/callback/` locally and
`https://devenkalra.com/api/contacts/oauth/callback/` in production) to the OAuth client's
*Authorized redirect URIs*.

ClickUp: the People list needs the custom fields in `engine/fields.py`. `python manage.py contacts_sync check`
(or *Check list fields* in the app) reports what's missing. Required: Google ID, Google hash, LinkedIn URL,
LinkedIn hash, Emails, Match status (options: active, possible duplicate, deleted in google, merged),
Duplicate of. Field types are read from the list, so a field can be text or date and the engine sends the
matching value.

Locally the app runs in the `devenkalra-local-app` container. `contacts/` is baked into the image, so rebuild
after backend changes (`docker compose -p data-backend -f docker-compose.local.yml up -d --build devenkalra-app`
from the monorepo root; it migrates on start) and run `npm run build` in `frontend/` after frontend changes.
The page itself is created by `python manage.py ensure_contact_sync_page`, which never overwrites an
existing page.

## CLI

Every command is a dry run unless it has `--apply --max-writes N`. Runs from the CLI appear in the app's
Runs tab and share its single-run lock.

```
python manage.py contacts_sync check
python manage.py contacts_sync google [--full] [--photos] [--writeback] [--rename-tasks] [--ignore-label PATTERN]
python manage.py contacts_sync linkedin Connections.csv [--messages messages.csv]
python manage.py contacts_sync whatsapp export.json [--no-create] [--only-saved] [--trust-exact-names]
python manage.py contacts_sync merge SURVIVOR_TASK_ID LOSER_TASK_ID
python manage.py contacts_sync export [--out contacts.json]
python manage.py contacts_sync import contacts.json --people-list ID [--orgs-list ID]
python manage.py contacts_import_cli ...   # one-time import of the old scripts' sync token, labels and review CSVs
```

## How it fits together

```
contacts/
  engine/            framework-free; no Django imports
    fields.py        ClickUp field names, required fields, status vocabulary
    guard.py         WriteGuard + check_field_changes: the single gate for every write
    clickup.py       ClickUp API client; reads, value encoding, guarded writes
    index.py         in-memory index of the list (by id, email, phone, name tokens, source keys)
    sync.py          matching and upsert/create/update/merge
    sources/         google.py, linkedin.py, whatsapp.py
    transfer.py      export/import of People + Orgs and their relationships
    relations.py     relationship sections in task descriptions; inverse labels
  entities.py        People & Orgs editor: list cache, detail, field locks, save
  runner.py          executes SyncRuns: progress, change journal, snapshots, review items, apply rules
  worker.py          background thread that claims queued runs
  views.py           DRF API under /api/contacts/ (IsSuperuserRole)
  models.py          SyncRun, ChangeLog, ReviewItem, SourceFile, GoogleAccount, ContactsState, ImportedTask,
                     EntityCache, EntityEdit
```

A **SyncRun** is either a dry run (preview) or a live run. The API only creates dry runs; a live run is created
by applying a finished dry run, which sets its write budget to `ceil(planned × 1.2) + 10`
(`runner.plan_budget`). `runner.apply_refusal` lists everything that blocks applying.

### Safety layers

All in the engine, so the CLI gets them too:

1. Dry runs count writes in `WriteGuard.begin` and never send them; `ClickUp._req` refuses any non-GET in a dry
   run as a second check.
2. Live writes need `CONTACTS_CLICKUP_WRITES_ENABLED` and a budget; exceeding the budget raises
   `WriteBudgetExceeded`.
3. `check_field_changes` refuses clearing values, dropping emails/phones/labels, replacing a source key,
   un-merging, and moving last-message dates backwards.
4. Every live write is journaled to `ChangeLog` before it is sent and marked ok/failed after. Live syncs save a
   gzipped snapshot of the whole list first (`contacts_data/snapshots/`).
5. Task creation is never retried on 5xx (it may have succeeded).

Anything that is a `SafetyStop` aborts the whole run; per-contact error handling must re-raise it.

### Matching and review

`sync.find_existing`: an exact source key updates the linked task; a unique email or phone match links
automatically; a similar name (`NAME_STRONG`, or `NAME_WITH_COMPANY` with the same company) becomes a
`ReviewItem` for all three sources. Decisions feed the next preview through `runner._decisions`. Google syncs
are incremental, so `sources/google.run_google` re-fetches decided contacts that aren't linked yet.

### Export and import

`transfer.export_lists` reads both lists (archived tasks included) and derives relationships from the managed
description sections (`**Relationships**`, `**Organizations**`, `**People**`, written by the old
`create_relation.py` / `link_org.py`) and from task-link custom fields. `transfer.import_lists` refuses
non-empty targets, maps fields by name and type and options by name, creates every task, then rewrites
description links and task-link fields to the new IDs. `ImportedTask` rows make an interrupted import
resumable.

### People & Orgs editor

`entities.py` backs `/api/contacts/entities/` (list from the `EntityCache` copy; POST re-reads both lists) and
`/api/contacts/entities/<task_id>/` (GET reads the task live; PUT saves). `engine/relations.py` parses and
renders the managed description sections and holds the inverse labels (`Parent of` ↔ `Child of`,
`Works at` → `Employs`).

A save is refused unless writes are enabled and no live run is active, and refused if the task's
`date_updated` differs from the one the editor loaded. Fields in `entities.SYNC_OWNED` are always locked, and
`FROM_SOURCE` fields are locked when the contact has that source's key; the server rejects changes to locked
fields, not just the UI. Relationship changes are mirrored on the other task with the inverse label. A
description whose managed sections contain text `relations.parse` doesn't understand is never rewritten.
Writes go through a `WriteGuard` and are recorded in `EntityEdit`; any edit makes earlier previews
unappliable (`runner.apply_refusal`).

## Tests

```
python manage.py test contacts
```

`tests/fakes.py` and `tests/test_transfer.py` hold in-memory stand-ins for the ClickUp and People APIs. The
fake ClickUp rejects numbers in text fields the way the real API does.
