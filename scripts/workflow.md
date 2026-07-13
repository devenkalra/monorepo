# Managing a Large Media Library

Most of us accumulate files faster than we organize them. Photos from phones, camera cards, old hard drives, NAS shares, email attachments, and documents pile up across folders and machines. The goal is not perfect order on day one — it is a **repeatable lifecycle**: catalog what you have, find things when you need them, fold in new material safely, and clean up without losing track of anything.

The tools in `scripts/` support that lifecycle with a SQLite **index** that sits beside your files. The index stores paths, hashes, metadata, and thumbnails. Your files stay where they are on disk until you deliberately move them. The index is the map; the filesystem is the territory.

For command syntax and options, see [MEDIA_INDEX_USER_MANUAL.md](MEDIA_INDEX_USER_MANUAL.md).

---

## The big picture

```

  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
  │   Catalog   │ ──> │   Search    │ ──> │   Act on    │
  │  (index)    │     │  & verify   │     │  the files  │
  └─────────────┘     └─────────────┘     └─────────────┘
         ▲                                        │
         │                                        │
         └──────────── re-index / update ─────────┘
```

Every workflow below follows the same rhythm: **index (or update the index) → search to understand what you have → take action on disk → re-index to stay in sync.**

---

## Phase 1: Establish your catalog

Before cleaning or reorganizing, you need a baseline. Trying to deduplicate or move tens of thousands of files by eye is slow and error-prone. Indexing once gives you a searchable record of everything on a volume.

### Register your library

Tell the system where your files live. A **volume** is a named library (e.g. `photo`) with a mount point on your machine (`P:\`, `/mnt/photo`, etc.). The database stores paths *relative* to that mount, so the same index works when you plug the drive into a different computer and mount it under a new letter.

→ `manage_volumes.py`

### Run the first full index

Walk the volume and record each file: name, dates, size, content hash, EXIF or other metadata, and a thumbnail. The first run on a large library takes time — that is normal. Let it finish; you only pay this cost once per untouched file.

→ `index_media.py`

### Spot-check the results

Search for a few files you know exist. Browse by date, location, camera, or filename. Open thumbnails in a grid. Confirm counts feel roughly right before you start moving or deleting anything.

→ `search_media.py` (or `show_thumbnails.py`)

**You now have a catalog.** Everything that follows is a variation on updating that catalog as your files change.

---

## Phase 2: Day-to-day — find and verify

Once indexed, the library is queryable without opening folders. This is the steady state most people live in.

| Need | Approach |
|------|----------|
| "Where is that photo from Christchurch?" | Search by metadata, date taken, or path pattern |
| "Do I already have this file?" | Look up by hash or filename |
| "What's on the NAS from last month?" | Filter by indexed or modified date |
| "Show me what this looks like" | Thumbnail grid in the browser |

→ `search_media.py`, `locate_in_db.py`

When you edit tags in place (keywords, location, captions), refresh the index for those files so search stays accurate.

→ `apply_exif.py` with `--reprocess-db`

---

## Phase 3: Incremental maintenance

Libraries grow continuously. New folders appear; files get edited. You do not need a full re-index every time.

Run a **incremental index** that skips files already cataloged at the same path with the same size and modification date. Only new or changed files are processed. Schedule this after backups, imports, or bulk edits.

→ `index_media.py` with `--check-existing` for size and modified date

If you add files manually (copy/paste, rsync, sync from cloud) and skip the indexer, the catalog drifts. Make indexing the last step of any import habit.

---

## Use case: Bring in another disk or import folder

A new camera card, an old external drive, or a download folder arrives. The risk is duplicating what you already have or scattering files you will never find again.

**Suggested flow:**

1. **Copy files to a staging area** — an `inbox` or `import` folder on your main volume, not straight into your dated archive.
2. **Index the staging area** — new files enter the catalog; existing paths are unchanged.
3. **Find what is already in the library** — hash lookup tells you if a file already exists elsewhere under a different name or path.
4. **Separate the unknowns** — files whose hash is *not* in the index can be moved aside for manual review; the rest are safe to merge or discard from the import batch.
5. **Move survivors into your archive structure** — dated folders, events, projects, whatever scheme you use.
6. **Update the index** — move tools update the database as they relocate files; re-index anything you moved by hand.

→ `index_media.py`, `locate_in_db.py`, `manage_dupes.py`, `move_media.py`

**Principle:** import → catalog → compare → decide → file → re-catalog.

---

## Use case: Clean up duplicates

Duplicates come in two flavors, and the tools treat them differently.

### Same file, same folder, different names

Classic `_copy`, `(1)`, or export accidents sitting next to each other. The index knows hash and folder; it can keep one copy and move the rest to a quarantine folder while removing them from the catalog.

→ `remove_dupes.py` (dry-run first)

### Files on disk that are not in the catalog at all

An old backup tree or second drive may contain files you never indexed — or files that are copies of things already archived. Scan the foreign tree, hash each file, and **move aside** anything not found in the index for review.

→ `manage_dupes.py`

### "Is this file already somewhere in my library?"

Before keeping an import, check one file at a time or in batch. Hash lookup returns every indexed location for that content.

→ `locate_in_db.py`

**Principle:** never delete blindly. Dry-run, inspect the list, then execute. Keep a quarantine directory until you are confident.

---

## Use case: Reorganize an existing disk

Restructuring — by year, event, person, or project — is the highest-risk operation because paths change. Doing it without updating the index leaves you with a catalog that points at ghosts.

**Two safe approaches:**

### Let the tool move and update together

Specify files and a destination; the mover renames on disk and updates `relpath`, metadata, and thumbnails in one step. Prefer this whenever possible.

→ `move_media.py`

### Reorganize manually, then reconcile

If you bulk-rename outside the tools (Explorer, Finder, rsync), the index is stale. Re-index affected subtrees with criteria that detect changed paths, and remove or fix orphaned records. Manual reorg without re-indexing breaks search.

→ `index_media.py` on changed folders

**Principle:** every path change must be reflected in the index — either by the move tool or by a deliberate re-index.

---

## Use case: Fix metadata across many files

Location tags, keywords, captions, and dates often need batch correction after a trip or a scan of old film. Write tags with exiftool wrappers, then refresh affected rows in the index so search and thumbnails reflect the new metadata.

→ `apply_exif.py`, then `--reprocess-db` or targeted `index_media.py`

Separate from file moves: metadata edits change *what you can search for*, not *where the file lives*.

---

## Use case: Add a second volume (another NAS share or drive)

Your photo archive and your document archive may live on different mounts. Register each as its own volume in the same database. Index them independently. Search can filter by volume or span everything.

→ `manage_volumes.py` for each volume, then `index_media.py --volume …`

When you retire a drive, the volume's rows remain as historical record until you explicitly prune them.

---

## Use case: Move to a new computer or remount path

Copy the database file with your files (or store it on the NAS). On the new machine, register the volume with the **new mount path**. Relative paths in the database still resolve correctly; only the mount prefix changes.

→ `manage_volumes.py set …` with updated `--mount`

Verify with a few `search_media.py` lookups before deleting anything on the old system.

---

## Use case: Migrate from an older index format

If you have a legacy database that stored absolute paths instead of volume + relpath, run the one-time migration script, verify counts and samples, then continue with the normal lifecycle.

→ `migrate_db_v2.py`, `inspect_db.py`

---

## Recommended habits

1. **Index before you organize.** The catalog is your safety net during dedup and moves.
2. **Dry-run destructive steps.** Duplicates removal and bulk moves offer preview modes — use them.
3. **Incremental index on a schedule.** After imports or bulk edits, run a quick update pass.
4. **One quarantine folder.** Moves from dedup tools land here until you delete with confidence.
5. **Keep the database with the library.** Back it up alongside your files; rebuilding metadata from scratch is expensive.
6. **Search to verify, not to assume.** After any large operation, spot-check counts and a sample of moved paths.

---

## Lifecycle at a glance

| Stage | What you are doing | Primary tools |
|-------|-------------------|---------------|
| **Bootstrap** | First catalog of a volume | `manage_volumes.py`, `index_media.py` |
| **Explore** | Find, browse, verify | `search_media.py`, `locate_in_db.py` |
| **Maintain** | Pick up new/changed files | `index_media.py` (incremental) |
| **Import** | Ingest card, disk, or folder | index → hash check → `manage_dupes.py` → `move_media.py` |
| **Dedupe** | Remove redundant copies | `remove_dupes.py`, `locate_in_db.py` |
| **Reorganize** | Restructure folders | `move_media.py`, re-index |
| **Enrich** | Tags, dates, locations | `apply_exif.py`, re-index |
| **Expand** | Another drive or share | new volume + index |
| **Relocate** | New PC or mount letter | update volume mount, verify search |

---

## When things feel overwhelming

You do not have to index twenty years of backups in one weekend. A practical sequence:

1. Index your **current** active volume — the drive you actually use.
2. Search and browse until you trust the catalog.
3. Tackle **one import or one duplicate folder** at a time.
4. Re-index after each batch of changes.

The index grows with you. A partial catalog of what matters today is more useful than a perfect plan you never start.

---

*Command reference and troubleshooting: [MEDIA_INDEX_USER_MANUAL.md](MEDIA_INDEX_USER_MANUAL.md)*
