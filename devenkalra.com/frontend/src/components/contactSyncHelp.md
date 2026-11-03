# Contact Sync guide [#top]

Contact Sync keeps the ClickUp **People** list up to date from Google Contacts, LinkedIn and WhatsApp, and can
export and import the People and Orgs lists. ClickUp already holds data you care about, so everything here is
built to add information without losing any.

**Jump to:** [Workflow](#workflow) · [Safety](#safety) · [Overview tab](#tab-overview) · [Sync tab](#tab-sync) ·
[Runs tab](#tab-runs) · [Review tab](#tab-review) · [People & Orgs](#tab-people-orgs) ·
[Google](#tab-google) · [Check & add](#tab-check-add) · [Export / Import](#tab-transfer) · [Questions](#faq)

## The workflow [#workflow]

Every change to ClickUp follows the same four steps:

1. **Preview.** Start a sync on the Sync tab. It reads the source and ClickUp and lists what *would* change,
   without writing anything.
2. **Check.** Open the preview on the Runs tab. Filter by action, search for names, read the warnings.
3. **Review (if needed).** Contacts that only *look like* someone already in ClickUp wait on the Review tab
   until you decide. You can apply without deciding; those contacts are simply skipped.
4. **Apply.** Click **Apply to ClickUp…** on the preview. A live run makes exactly the changes the preview
   listed, and logs every one.

If you decide anything in Review, run a **new preview** before applying, so the plan includes your decisions.

## How your data is protected [#safety]

- **Previews never write.** Only applying a finished preview changes ClickUp.
- **Nothing is cleared or removed.** Existing values are never blanked; emails, phones, Groups and Sources are
  only ever added to; a contact's Google ID, LinkedIn URL or WhatsApp number is never replaced by a different
  one; merged contacts stay merged; last-message dates only move forward.
- **Write budget.** A live run may make at most the preview's writes + 20% + 10. If it needs more, it stops
  immediately.
- **Snapshot and change log.** Before a live sync writes, the whole list is saved as a snapshot. Every write is
  recorded with its before and after value (see *Show change log* on a live run).
- **Server switch.** Live writes only happen when the server has `CONTACTS_CLICKUP_WRITES_ENABLED=1`. Otherwise
  the app runs in preview-only mode and says so at the top.
- **Fresh plans only.** A preview can't be applied if it's over 24 hours old, if another live run finished
  since, if Review decisions changed since, or if it was already applied.
- **One run at a time.** A new run can't start while another is queued or running.

## Overview tab [#tab-overview]

- **ClickUp Contacts list:** which list the sync uses and whether live writes are on. **Check list fields**
  reads the list's custom fields and reports anything the sync needs that's missing (required: Google ID,
  Google hash, LinkedIn URL, LinkedIn hash, Emails, Match status, Duplicate of). It only reads.
- **Google account:** connect the Google account whose contacts you sync. **Connect Google (read-only)** is
  enough for syncing. **Grant write access** is only needed for *Write the ClickUp task id back to Google*.
  *Next sync* says whether the next Google preview reads only changes (incremental) or everything (full).
- **Latest runs:** the last preview, last live run and pending review count for each source.

## Sync tab [#tab-sync]

Each card starts a **preview**; nothing is written until you apply it from the Runs tab.

### Google Contacts [#sync-google]

Reads contacts changed since the last applied Google run (the first run reads everything).

| Option | What it does |
| --- | --- |
| Full sync | Re-reads every contact, and marks ClickUp contacts whose Google contact was deleted as *deleted in google*. If more than 2% (minimum 10) seem deleted, it marks none and warns instead. |
| Check photos on every contact | Normally photos are checked only for contacts that changed. |
| Update values already set in ClickUp | On: Google's company, title, birthday, address and website replace ClickUp's. Off: only empty fields are filled. |
| Rename ClickUp tasks… | Renames the task when the name changes in Google. Off by default. |
| Write the ClickUp task id back to Google | Stores the task link on the Google contact. Needs write access. |
| Ignore Google labels | Labels (one per line, `*` wildcards allowed) that aren't copied into Groups. |

### LinkedIn [#sync-linkedin]

Upload `Connections.csv` from LinkedIn's *Settings → Data privacy → Get a copy of your data*. Optionally add
`messages.csv` from the same export to fill **Last LinkedIn message**. *Update company/title already set*
works like the Google option.

### WhatsApp [#sync-whatsapp]

Upload the contacts JSON from your WhatsApp export tool.

| Option | What it does |
| --- | --- |
| Don't create new contacts | Only link or update people already in ClickUp. |
| Only numbers saved in my address book | Skip numbers that aren't saved contacts on the phone. |
| Link exact, unique name matches without review | If exactly one ClickUp contact has the same name and no WhatsApp number yet, link it without asking. |

### How contacts are matched [#matching]

1. Already linked (same Google ID, LinkedIn URL or WhatsApp number): **update** that task.
2. Same email or phone as exactly one ClickUp contact: **link** to it automatically.
3. Similar name (with the same company, a little less similar is enough): goes to **Review**.
4. No match: **create** a new task.

## Runs tab [#tab-runs]

Every preview, live run, export and import appears here, newest first. Select one to see its progress,
counts, warnings and the list of actions. Click a count chip to filter by that action; tick *Show unchanged*
to include contacts with nothing to do.

| Action | Meaning |
| --- | --- |
| CREATE | A new task is created |
| UPDATE | A linked contact's values changed |
| LINK(email) / LINK(phone) | Linked to an existing task with the same email / phone |
| LINK(name) | Linked by an exact, unique name (WhatsApp option) |
| LINK(review) | Linked because you chose *Same person* in Review |
| PENDING | Waiting for your decision in Review; skipped for now |
| DELETED | Marked *deleted in google* (full Google sync) |
| PHOTO | Google photo added to the task |
| MESSAGE | Last LinkedIn / WhatsApp message date moved forward |
| UNCHANGED | Nothing to do |
| SKIP / INFO / WARN / ERROR | Skipped item, information, something to look at, a contact that failed |
| EXPORT / RELATION | A list read into an export / a link between tasks found by it |
| LINK / ARCHIVE | Import: links pointed at the new copies / task archived as in the export |

**Applying.** On a finished preview, **Apply to ClickUp…** shows the counts and the write budget and asks you to
confirm. If the button is missing, the line *Can't apply:* says why; usually the fix is a new preview.

**Cancelling.** **Cancel** stops a running run at the next safe point. Writes already made stay; the change log
shows them.

**Live runs** show *Writes made: N of a budget of M* and, after it finishes, **Show change log** with every
write's before and after value. If writes failed, they're listed as *not confirmed*; for Google, the next run
retries them automatically.

## Review tab [#tab-review]

Contacts from Google, LinkedIn or WhatsApp that look like someone already in ClickUp, but not certainly
(similar name, no shared email or phone). For each one:

- **Same person:** the next preview links the contact to that ClickUp task (LINK(review)).
- **Different person:** the next preview creates a new task for it.

Pick a source in the drop-down to see only its items. Decisions you've made are under **Decided**, where
**Undo** puts an item back. A *Same person* decision is never allowed to replace a link the task already has
to someone else: if that would happen, the item comes back to Review with a note explaining why.

Decisions are used by the **next** preview of that source, so run one after deciding.

## People & Orgs [#tab-people-orgs]

Browse and edit the People and Orgs lists, and the relationships between them.

**Bulk actions** (checkboxes): Add to group, Add relationship, **Fill PSalutation**, and **Mail merge**.
PSalutation uses the Google given name when the person is linked to Google (skips Google entries with no given
name, e.g. bill-pay labels); otherwise the first name parsed from the display name (titles and leading initials
dropped; “Kalra, Deven” → Deven). Empty values only unless *Overwrite* is on. Preview first, then Apply. Merged
and archived are skipped. CLI: `contacts_entity_action fill_psalutation` (dry-run; `--apply --max-writes N`,
`--overwrite`, `--ids`).

**Mail merge** carries the current selection into the [Mail merge](#tab-mail-merge) tab as the campaign
audience (names shown; no need to paste task IDs).

**The list** shows both lists together. Search by name, company, email or phone; filter by type, group,
source, match status, *Has relationships* and *Archived*; click a column heading to sort by it (click again
to reverse). The list is a copy read from ClickUp, so it opens instantly. **Refresh list** re-reads it
(about a minute, read-only). A banner tells you when a live sync has changed ClickUp since the last refresh.

**Click a row** to see that person or organization: relationships in short form (click a name to jump to it),
filled-in fields, notes, and the fields the sync manages. The first open reads ClickUp and caches the detail;
later opens reuse that cache until the person is edited here, a live sync writes them, or you **Refresh list**
/ **Reload**.

**New contact** opens a create form in the same panel (first name, last name, emails, phones, company, title,
birthday, address, website, groups). First and last name map to Google’s given/family name. It creates the
person in **Google Contacts first**, then a linked ClickUp People task with the Google ID set so the next sync
updates it instead of duplicating. Needs live ClickUp writes and Google **write** access (grant it from
Overview). Overlapping email or phone with someone already in the list is refused.

**Edit** turns the details into a form. Nothing is written until you press **Save**; **Cancel** discards your
changes, and you're asked before leaving a form with unsaved changes.

- **Grayed-out fields** are managed by the sync and can't be changed here (hover for the reason): source IDs,
  hashes and links, Sources, Match status, Duplicate of, Last synced, Connected on and the last-message dates.
  Company and Title are also locked for contacts linked to Google or LinkedIn, and Birthday, Address, City,
  Country and Website for contacts linked to Google, because every sync fills them in again. Change those in
  the source.
- **Emails, Phones and Groups** can be edited, but syncs only ever add to them: anything you remove that's
  still in Google, LinkedIn or WhatsApp comes back on the next sync.
- **Relationships:** stored in the **Relationship data** field (JSON), not in the description — so editing
  notes can’t corrupt them. Each row has a type, a person or organization and an optional note.
  **Introduced by** is also a relationship type here (no separate field). **+ Add relationships** adds
  several at once: pick or type the type and press **Next**, then search and tick everyone it applies to
  (ticks are kept as you change the search), optionally add a note for all of them, and press **Add**. A
  person can be linked to people and orgs; an org only to people. Saving also updates the other side:
  *Parent of* shows as *Child of* on the other person, *Works at* as *Employs* on the organization, and
  unknown types read the same both ways.

**Merging duplicates.** On a person, **Merge…** combines two records for the same person. Pick the other
record (a record with *Duplicate of* set offers its twin automatically, and shows a "Possibly a duplicate"
banner with a *Merge them…* link), choose which one to keep, and press **Preview merge**. The preview opens in
**Runs**; apply it there like any other. The kept record gains the other's emails, phones, groups and
sources, plus its LinkedIn/WhatsApp links, company, title and other details where it has none, and becomes
active; the other is marked *merged* and archived. Two records linked to different live Google contacts
can't be merged (merge them in Google first), but a record marked *deleted in google* can be folded into
the one that's still in Google; its dead Google ID is dropped.

## Mail merge [#tab-mail-merge]

Create a throttled Gmail campaign from People contacts.

1. **Grant Gmail access** on Overview if you haven’t already (reconnect if drafts don’t appear — needs
   readonly + compose + send).
2. In **Gmail**, write the rich email and leave it as a **draft**. Put tokens in the subject/body:
   `{{first_name}}`, `{{name}}`, `{{email}}`, `{{company}}`, `{{title}}`, `{{groups}}`, `{{outreach}}`,
   `{{PSalutation}}`, `{{FSalutation}}`.
3. On **People & Orgs**, filter and check recipients, then click **Mail merge**.
4. On the Mail merge tab, pick that Gmail draft, set **From** to a verified send-as people recognize
   (your Gmail default, usually a custom domain — not the raw `@gmail.com` login), set daily limit / pace,
   create the campaign, then **Start / Resume**.
5. Delivery defaults to **new Gmail drafts** (one per person) so you can spot-check; or choose **Send**.
   The worker pauses at the daily cap (`waiting_quota`) and resumes the next UTC day. Restarts keep
   remaining `pending` rows.

Merged, archived, org-only, and no-email contacts are skipped when the campaign is created.

## Google [#tab-google]

A small Google Contacts manager. Writes go to **Google only**; run a Google sync afterward if you want
ClickUp updated. Needs Google **write** access (Overview).

- **Search** by name/email and filter by label; **Show more** pages through results.
- **Select one** contact to edit first/last name, emails, phones, labels, city, state and country (emails and
  phones are comma-separated and replace the list; labels replace membership).
- **Select several** to bulk-add labels and/or set city, state and country in one apply (labels add-only;
  location overwrites when filled).
- **Add contacts** opens a grid (first/last name, email, phone, labels, city, state, country). Labels must
  already exist in Google (comma-separated). Max 50 creates / 100 updates per request.

Save is refused, with nothing written, if:

- the task changed in ClickUp after you opened it (press **Reload** and redo your edit),
- a live sync is running, or live writes are off on the server,
- you changed a grayed-out field, or
- notes can't be saved when leftover relationship text in the description is unreadable (run
  `contacts_migrate_relationships`, or edit notes in ClickUp); relationship edits still go to
  Relationship data.

Every save is logged with what it changed. Saving makes earlier sync previews stale, so run a new preview
before applying one.

## Check & add [#tab-check-add]

Checks whether people are already in ClickUp People and Google Contacts. Type one contact (name, email,
phone) or upload a CSV. The CSV needs a header row; recognized columns are **Name** (or **First name** /
**Last name**), **Email** and **Phone** (also Mobile, Cell, E-mail address…). A Google Contacts export works
as-is. Other columns are ignored and listed. Up to 1,000 rows per file.

**Refresh the ClickUp cache first.** ClickUp is read from the People & Orgs cache, not live, so anyone added
or changed in ClickUp since its last refresh isn't seen. Google is re-read automatically when its copy is over
10 minutes old (or press **Refresh Google**). Comparing never writes anything.

Matching: one record with the same email or phone is a match. Several records sharing them, or the email
pointing at one record and the phone at another, is a conflict. Without an email/phone match, a very similar
name or the same last 10 phone digits makes a *possible* match for you to review.

| Outcome | Meaning | Action you can run |
| --- | --- | --- |
| Exists | In ClickUp and Google, and linked | none |
| Exists, unlinked | In both, but the ClickUp task has no Google ID | **Link** (Google ID on the task, task id on the contact) |
| ClickUp only | In ClickUp, not in Google | **Create in Google & link** (from the ClickUp task's data) |
| Google only | In Google, not in ClickUp | **Import into ClickUp** (new linked People task) |
| Not found | In neither | **Create in Google & ClickUp** (from the row) |
| Needs review | Only possible matches | pick **Use this match** or **Not in …**, then the row is re-evaluated; or **Create … as new** to ignore the possible matches and create the row (only where it has no exact match, so nothing is duplicated) |
| Conflict | The data disagrees (different name, email or phone; duplicates; mismatched links) | none: fix it in ClickUp or Google, then **Re-check** |

Each action runs only when you click it, on that row alone (or on the rows you select, one after another).
Before writing, the row is re-evaluated; if its outcome changed it is refused, and you see the new state.
Every contact an action creates or changes gets the **SyncDriven** label in Google (created on first use) and
the **SyncDriven** group in ClickUp. The ClickUp option must already exist in the Groups field; if it doesn't,
the action still runs and warns that the task wasn't labeled.
Comparisons are saved, so you can come back, **Re-check** against refreshed data and **Download results**.
A **Link** stores no Google hash, so the next Google sync fills the task in from Google as for any new link.

## Export / Import [#tab-transfer]

### Export [#export]

**Export People and Orgs** saves both lists to one JSON file: every task's name, status, tags, priority,
dates, description and custom field values (archived tasks included), plus every relationship between tasks:
the **Relationships**, **Organizations** and **People** sections at the end of descriptions and task-link
fields like *Introduced by*. It only reads ClickUp. When it finishes, open it on the Runs tab and click
**Download export**.

Not included: attachments (such as photos), comments, assignees, and calculated fields.

### Import [#import]

Creates the tasks from an export in **new, empty lists** and points every relationship at the new copies.
It refuses any list that already has tasks, and the lists Contact Sync uses, so it can't change People or Orgs.

1. In ClickUp, duplicate **People** and **Orgs** *without their tasks* (keep custom fields). Turn automations
   off in the copies.
2. Note each new list's ID: open the list; it's the number after `/li/` in the address.
3. Here, choose the export file, enter the two list IDs and click **Preview import**.
4. Check the preview's warnings: fields, dropdown options or statuses missing in the new lists are listed. Add
   them in ClickUp and preview again, or accept that those values are left out.
5. Apply it. Large imports take a while because ClickUp limits request speed.

If an import is interrupted, preview and apply again with the same file and lists: tasks it already created
are skipped, not duplicated.

## Questions [#faq]

**It says "Preview-only mode".** The server has live writes off. Set `CONTACTS_CLICKUP_WRITES_ENABLED=1` and
restart it, then reload this page.

**The Apply button is missing.** Read the *Can't apply:* line under the preview. Most reasons are fixed by
running a new preview.

**Do I have to clear Review before applying?** No. Undecided contacts are skipped. Decide later and run a new
preview to pick them up.

**Google sign-in fails with redirect_uri_mismatch.** The redirect address shown in Google's error must be added
to the OAuth client's *Authorized redirect URIs* in Google Cloud Console.

**A run says "Stopped by a safety check".** The run tried something the protections forbid (for example more
writes than its budget, or clearing a value). Nothing past that point was written. The error says what
happened; the change log shows what was written before it.

**Something went wrong after a live run. Can I see what changed?** Yes: **Show change log** on the live run
lists every write with its old and new value, and the snapshot taken before the run is kept on the server.
