# Media Index User Manual

This guide documents the end-to-end workflow for cataloging files with the Python tools under `scripts/`. It covers creating an index, searching it, re-indexing after changes, moving files, managing duplicates, and editing metadata.

All scripts share a **v2 volume-based SQLite schema** (July 2026). Files are stored by **logical volume** and **relative path** (`relpath`), not by a single absolute path baked into the database.

---

## Table of contents

1. [Concepts](#concepts)
2. [Prerequisites](#prerequisites)
3. [Quick start](#quick-start)
4. [Volume setup](#volume-setup)
5. [Indexing files](#indexing-files)
6. [Searching the index](#searching-the-index)
7. [Re-indexing after changes](#re-indexing-after-changes)
8. [Moving files](#moving-files)
9. [Duplicate management](#duplicate-management)
10. [Editing EXIF and refreshing the index](#editing-exif-and-refreshing-the-index)
11. [Migrating an old database](#migrating-an-old-database)
12. [Typical workflows](#typical-workflows)
13. [Troubleshooting](#troubleshooting)
14. [Script reference](#script-reference)

---

## Concepts

### What gets indexed

The indexer walks a registered **volume mount** and records:

| Stored | Source |
|--------|--------|
| Volume name, relative path, filename | Filesystem |
| Created/modified dates, size, MIME type, extension | Filesystem |
| SHA-256 hash | Computed at index time |
| Image EXIF (date taken, GPS, camera, keywords, …) | `exiftool` |
| Video/audio metadata | `ffprobe` |
| Document metadata (PDF, Office, text) | Built-in parsers |
| Email headers (`.eml`) | Parsed headers only |
| Thumbnail JPEG (200×200) | Pillow / exiftool / ffmpeg |

### Volumes and paths

A **volume** is a named library (for example `photo`) with two paths:

| Field | Meaning | Example |
|-------|---------|---------|
| `src_root` | Path on the NAS or canonical server path | `/volume1/photo` |
| `mount_path` | Local path where the volume is mounted on *this* machine | `P:\` or `/mnt/photo` |

The database stores **`relpath`** — the path relative to `mount_path`:

```
mount_path:  P:\
relpath:     2026/01/07 Christchurch/IMG_3313.JPG
resolved:    P:\2026\01\07 Christchurch\IMG_3313.JPG
```

This lets the same database work across machines that mount the library at different drive letters or mount points. Update `mount_path` with `manage_volumes.py` when you move to a new computer.

### Skip audit

Each indexing run records skipped files in `skipped_files` with a `skip_reason`, for example:

- `not_matching_include_pattern`
- `already_indexed (by relpath+volume)`
- `unsupported_file_type`

The run summary prints a breakdown by reason.

---

## Prerequisites

### Required

| Tool | Used by |
|------|---------|
| Python 3.8+ | All scripts |
| `exiftool` | `index_media.py`, `apply_exif.py`, `show_exif.py` |

### Recommended

| Tool | Purpose |
|------|---------|
| Pillow | Image thumbnails |
| `ffprobe` / `ffmpeg` | Video/audio metadata and thumbnails |
| `pdftoppm` or `mutool` | PDF thumbnails |

### Python packages

From `scripts/`:

```bash
pip install Pillow geopy requests PyYAML
```

Or install the package entry points:

```bash
cd scripts
pip install -e .
```

Console commands are then available as `photo-index`, `photo-search`, `photo-volumes`, etc. (see [Script reference](#script-reference)).

### Working directory

Run scripts from `scripts/` or ensure `media_utils.py` is importable. Examples below use:

```bash
cd scripts
```

On Windows PowerShell, use backtick line continuation or single lines.

---

## Quick start

### 1. Register a volume

```bash
python manage_volumes.py --db-path files.db set photo \
  --src-root /volume1/photo \
  --mount /mnt/photo
```

Windows:

```powershell
python manage_volumes.py --db-path files.db set photo `
  --src-root /volume1/photo `
  --mount "P:\"
```

### 2. Index a folder

```bash
python index_media.py --volume photo --db-path files.db --start-dir 2026 -v 1
```

### 3. Search

```bash
python search_media.py --db-path files.db --name IMG_3313 --show metadata
```

### 4. View thumbnails in a browser grid

```bash
python search_media.py --db-path files.db \
  --relpath-pattern "2026/01/07%" --show thumbnail --limit 20
```

---

## Volume setup

Use `manage_volumes.py` before indexing. Volume names are stored **lowercase**.

### Register or update a volume

```bash
python manage_volumes.py --db-path files.db set photo \
  --src-root /volume1/photo \
  --mount /mnt/photo
```

`--mount` must be an existing directory on the machine running the indexer.

### List volumes

```bash
python manage_volumes.py --db-path files.db list
```

### Show one volume

```bash
python manage_volumes.py --db-path files.db show photo
```

### Resolve relpath to absolute path

```bash
python manage_volumes.py --db-path files.db resolve photo \
  "2026/01/07 Christchurch/IMG_3313.JPG"
```

### When the mount path changes

Re-register the volume with the new mount. Existing `relpath` values stay valid:

```powershell
python manage_volumes.py --db-path files.db set photo `
  --src-root /volume1/photo `
  --mount "X:\photo"
```

---

## Indexing files

`index_media.py` is the primary indexer. It requires a registered `--volume`; there is no `--path` argument in v2.

### Index an entire volume

```bash
python index_media.py --volume photo --db-path files.db
```

### Index specific subdirectories

`--start-dir` is relative to the volume mount. Repeat for multiple roots:

```bash
python index_media.py --volume photo --db-path files.db \
  --start-dir 2024 --start-dir 2025
```

Windows — prefer forward slashes in `--start-dir`:

```powershell
python index_media.py --volume photo --db-path files.db `
  --start-dir "2026/01/07 Christchurch"
```

### Limit scope with patterns

| Option | Semantics |
|--------|-----------|
| `--include-pattern` | **Python regex** matched against the full absolute path (`re.search`). Multiple patterns are OR'd. If omitted, all indexable files are candidates. |
| `--skip-pattern` | Same as include, but excluded |
| `--literal-patterns` | Treat patterns as literal substrings (special regex chars escaped) |

Examples:

```bash
# Only JPEGs (regex)
python index_media.py --volume photo --db-path files.db \
  --include-pattern '\.jpe?g$' --literal-patterns

# Only paths containing "3313" (substring)
python index_media.py --volume photo --db-path files.db \
  --start-dir "2026/01/07 Christchurch" \
  --include-pattern "3313" --dry-run -v 1

# Skip hidden/system folders (literal)
python index_media.py --volume photo --db-path files.db \
  --literal-patterns --skip-pattern "/.filerun" --skip-pattern "/.DS_Store"
```

**Pattern tips:**

- `3313` matches anywhere in the path, including `IMG_3313.JPG`.
- `^photo.jpg$` does **not** match `/mnt/photo/2024/photo.jpg` — regex `^` anchors to the start of the full path. To match a filename at the end, use `[/\\]photo\.jpg$`.
- Use `--literal-patterns` when you want simple substring matching without regex surprises.

### Depth and limits

```bash
# Only files directly in start-dir (no subfolders)
python index_media.py --volume photo --start-dir 2026 --max-depth 0 --db-path files.db

# Process at most 10 files
python index_media.py --volume photo --db-path files.db --limit 10 -v 2
```

### Verbosity and dry-run

| `-v` | Output |
|-----|--------|
| `0` | Summary only (dry-run still prints per-file skip lines for `already_indexed`) |
| `1` | Each file processed or skipped |
| `2` | File type, relpath, size |
| `3` | Full metadata extraction detail |

```bash
python index_media.py --volume photo --db-path files.db --dry-run -v 1
```

Dry-run scans the filesystem and reports actions but still records skip reasons in `skipped_files` for audit.

### Supported file types

- **Images** — JPEG, PNG, GIF, TIFF, HEIC, and many RAW formats (`.cr2`, `.nef`, `.dng`, …)
- **Video** — common `video/*` types
- **Audio** — MP3, FLAC, AAC, etc.
- **Documents** — PDF, plain text, Office formats
- **Email** — `.eml` (headers only; body not stored)

---

## Searching the index

`search_media.py` is the main search and inspection tool. `show_thumbnails.py` is a thin wrapper that defaults to thumbnail display.

### Direct lookup

```bash
# By database id
python search_media.py --db-path files.db --id 42

# By stored relpath
python search_media.py --db-path files.db \
  --relpath "2026/01/07 Christchurch/IMG_3313.JPG"

# By local filesystem path (resolved via volume mount)
python search_media.py --db-path files.db \
  --path "P:\2026\01\07 Christchurch\IMG_3313.JPG"

# By SHA-256 hash
python search_media.py --db-path files.db --hash abc123...
```

### Filtered search

```bash
# Filename substring
python search_media.py --db-path files.db --name vacation

# SQL LIKE on filename or relpath (% and _ wildcards)
python search_media.py --db-path files.db --name-pattern "%.jpg"
python search_media.py --db-path files.db --relpath-pattern "2026/01/%"

# Metadata text search
python search_media.py --db-path files.db --metadata "Christchurch" --show metadata

# Location / camera / keywords
python search_media.py --db-path files.db --city "Fort Worth"
python search_media.py --db-path files.db --camera Canon --keywords beach

# Date ranges (accepts ISO dates, YYYYMMDD, EXIF-style YYYY:MM:DD)
python search_media.py --db-path files.db \
  --date-taken-after 2026-01-01 --date-taken-before 2026-01-31

python search_media.py --db-path files.db \
  --indexed-after 2026-01-01 --volume photo

# Size
python search_media.py --db-path files.db --min-size 1000000 --extension .jpg
```

**Note:** Search filters use **SQL `LIKE`**, which is different from the indexer's **regex** `--include-pattern`.

### Output modes (`--show`)

Modes are additive (comma-separated):

| Mode | Behavior |
|------|----------|
| `basic` | Default — id, volume, relpath, name, size, dates |
| `metadata` | Type-specific metadata fields |
| `thumbnail` | Save thumbnails and open an HTML grid in the browser |
| `full` | Open files on disk (max 5 per run) |

```bash
python search_media.py --db-path files.db --name IMG_3313 --show metadata,thumbnail
python search_media.py --db-path files.db --id 42 --show full
```

### Pagination and export

```bash
python search_media.py --db-path files.db --relpath-pattern "1984/%" --start 50 --limit 25
python search_media.py --db-path files.db --volume photo --count-only
python search_media.py --db-path files.db --hash abc123 --json
python search_media.py --db-path files.db --relpath-pattern "2026/%" --all --show basic
```

Thumbnail output directory (default `thumbnails_out/`):

```bash
python search_media.py --db-path files.db --id 1 --show thumbnail \
  --output-dir ./my_thumbs --grid-cols 6
```

---

## Re-indexing after changes

Understanding `--check-existing` is essential. It controls **when to skip** a file that is already in the database.

### Default behavior

If you omit `--check-existing`, the default is:

```
relpath + volume
```

A file at the same path on the same volume is **skipped** even if its content or metadata changed. The indexer does not re-extract EXIF or regenerate thumbnails.

### How skip vs update works

1. **Skip** — all `--check-existing` criteria match an existing row → file is not processed.
2. **Update** — criteria do not fully match, but a row exists for the same `(volume, relpath)` → record is updated (hash, metadata, thumbnail refreshed).
3. **Insert** — no row at that `(volume, relpath)` → new record.

### Common re-index scenarios

#### Skip unchanged files (fast incremental run)

Skip when path, volume, size, and modification time all match:

```bash
python index_media.py --volume photo --db-path files.db \
  --check-existing relpath --check-existing volume \
  --check-existing size --check-existing modified_date
```

#### Re-index files that changed on disk

Skip only when path, volume, **and** modification time still match:

```bash
python index_media.py --volume photo --db-path files.db \
  --check-existing relpath --check-existing volume \
  --check-existing modified_date
```

Files with a newer `mtime` are updated in place.

#### Re-index one file by name pattern

```powershell
python index_media.py --db-path files.db --volume photo `
  --start-dir "2026/01/07 Christchurch" `
  --include-pattern "3313" `
  --check-existing relpath --check-existing volume --check-existing modified_date `
  -v 1
```

If the file is unchanged, you will see:

```
Skipping (already indexed by relpath+volume+modified_date): ...
```

That is expected — the file matched the include filter but did not need re-processing.

#### Force metadata refresh at the same path

If content did not change but you need new EXIF in the database (for example after `apply_exif`), use a criterion that no longer matches, or re-index with only `--check-existing hash` after EXIF has changed the file bytes:

```bash
python index_media.py --volume photo --db-path files.db \
  --start-dir "2026/01/07 Christchurch" \
  --include-pattern '[/\\]IMG_3313\.JPG$' \
  --check-existing hash -v 1
```

### Reading skip output

Example summary:

```
Files skipped: 240

Skip reasons breakdown:
  - not_matching_include_pattern: 238
  - already_indexed (by relpath+volume): 2
```

- `not_matching_include_pattern` — scanned files that did not match `--include-pattern` (normal when filtering a folder).
- `already_indexed` — files that matched filters but were skipped by `--check-existing`.

Use `-v 1` or `--dry-run` to print the exact path for each `already_indexed` skip.

---

## Moving files

`move_media.py` moves files on disk **and** updates the database (`relpath`, metadata, thumbnails).

### Basic move

```bash
python media_process/move_media.py \
  --files /mnt/photo/inbox/IMG_3313.JPG \
  --destination /mnt/photo/2026/01/07 \
  --volume photo \
  --db files.db \
  --dry-run -v 2
```

Remove `--dry-run` to execute. The volume must be registered; destination paths are resolved relative to the volume mount.

### Multiple files

```bash
python media_process/move_media.py \
  --files img1.jpg --files img2.jpg \
  --destination /mnt/photo/archive/2025 \
  --volume photo --db files.db
```

### What it does per file

1. Validates source exists and destination is writable
2. Skips if destination already has same content (same hash)
3. Moves the file on disk
4. Updates or inserts the `files` row with the new `relpath`
5. Re-extracts metadata and thumbnail
6. Writes a session log to `move_media_audit.log` (via `audit_utils.py`)

### After moving between folder structures

No separate re-index step is required if `move_media.py` completed successfully — the DB already reflects the new location.

If you moved files manually outside the tool, re-index the new locations and remove stale rows, or use `move_media.py` going forward.

---

## Duplicate management

Three tools cover different duplicate scenarios.

### `locate_in_db.py` — find copies by hash

Given files on disk, compute SHA-256 and list all matching index rows:

```bash
python media_process/locate_in_db.py \
  --files photo.jpg --db-path files.db --metadata

python media_process/locate_in_db.py \
  --files a.jpg b.jpg --db-path files.db --json --summary
```

Use this to answer: *"Is this file already in my library somewhere else?"*

### `remove_dupes.py` — deduplicate within the index

Operates on the **database**, not an external import tree. Finds files in the **same folder** with the **same hash**, keeps the earliest-indexed copy, moves extras to `--dest`, removes them from the DB, and writes `removed_duplicates` audit rows.

```bash
# Preview
python remove_dupes.py --db files.db --dest /removed_dupes --dry-run -v 2

# Run on one volume and year
python remove_dupes.py --db files.db --dest /removed_dupes \
  --volume photo --base-relpath 2010
```

### `manage_dupes.py` — isolate files not in the index

Scans a **source** tree. Files whose hash is **not** found in the index are moved/copied to a **destination** tree (preserving relative paths). Use when ingesting from a card or export folder and separating unknown files.

```bash
python media_process/manage_dupes.py \
  --source /mnt/import --destination /mnt/import_review \
  --db files.db --action move --media-only --dry-run
```

---

## Editing EXIF and refreshing the index

`apply_exif.py` writes tags via `exiftool`. It can optionally re-index changed files.

### Write tags

```bash
python media_process/apply_exif.py \
  --files "P:\2026\01\07 Christchurch\IMG_3313.JPG" \
  --set "XMP-dc:Subject=Christchurch" \
  --set "IPTC:Keywords=travel" \
  --dry-run -v 1
```

Tags can also be loaded from YAML (`--tags-yaml`). Location helpers use geocoding when `geopy` is installed.

### Refresh the database after EXIF changes

```bash
python media_process/apply_exif.py \
  --files "P:\2026\01\07 Christchurch\IMG_3313.JPG" \
  --set "XMP-dc:Subject=Christchurch" \
  --db-path files.db \
  --reprocess-db -v 1
```

`--reprocess-db` shells out to `index_media.py` for each indexed file, using an include pattern that matches the filename at the end of the path and `--check-existing hash` so updated file content is picked up.

### Inspect metadata without the database

```bash
python show_exif.py photo.jpg
python show_exif.py --json video.mp4
```

---

## Migrating an old database

If you have a v1 database that stores `fullpath` instead of `relpath`, use `migrate_db_v2.py`:

```bash
python migrate_db_v2.py --db-path files.db \
  --volume photo \
  --mount "P:\" \
  --src-root /volume1/photo \
  --dry-run
```

The migrator:

1. Backs up the database (unless `--no-backup`)
2. Creates the `volumes` table
3. Converts `fullpath` → `relpath`
4. Preserves file ids, metadata, and thumbnails where possible

Inspect schema and row counts before/after:

```bash
python inspect_db.py files.db
```

---

## Typical workflows

### A. New library from scratch

```
1. manage_volumes.py set …     Register volume
2. index_media.py              Full index
3. search_media.py             Verify samples
```

```bash
python manage_volumes.py --db-path files.db set photo \
  --src-root /volume1/photo --mount /mnt/photo

python index_media.py --volume photo --db-path files.db -v 1

python search_media.py --db-path files.db --volume photo --count-only
```

### B. Nightly incremental index

```bash
python index_media.py --volume photo --db-path files.db \
  --check-existing relpath --check-existing volume \
  --check-existing size --check-existing modified_date
```

Only new or changed files are processed.

### C. Import from camera card

```
1. Copy files to inbox folder
2. index_media.py --start-dir inbox
3. manage_dupes.py (optional) — pull unknowns aside
4. move_media.py — file into dated folders
5. search_media.py — verify
```

### D. Fix metadata on a set of photos

```
1. search_media.py             Find file ids/paths
2. apply_exif.py --reprocess-db
3. search_media.py --show metadata   Confirm
```

### E. Clean up duplicate copies in one folder

```
1. remove_dupes.py --dry-run
2. remove_dupes.py
3. search_media.py / locate_in_db.py   Verify
```

### F. Move to a new computer

```
1. Copy files.db
2. manage_volumes.py set … --mount <new path>
3. search_media.py --path …   Confirm resolution
```

---

## Troubleshooting

### `volume is not registered`

Run `manage_volumes.py set` before `index_media.py`.

### `mount path is not accessible`

The volume is registered but the drive is not mounted. Mount the share, or update the mount path.

### Include pattern matches nothing (or everything skipped as `not_matching_include_pattern`)

- Remember patterns are **regex** on the **full absolute path**, not globs.
- Use `--literal-patterns` for simple substrings.
- Prefer forward slashes in `--start-dir` on Windows.
- Run with `-v 1 --dry-run` to see each decision.

### File appears skipped but should be re-indexed

- Default `--check-existing relpath volume` skips unchanged paths.
- Add `modified_date` or `hash` to only skip truly unchanged files.
- Use `-v 1` to see `Skipping (already indexed by …)` lines.

### `search_media.py` finds the file but indexer skips it

The file is already indexed at that `relpath`. Search confirms the catalog entry; the indexer is doing its skip job. Adjust `--check-existing` to re-process.

### `exiftool not found`

Install exiftool and ensure it is on `PATH`. Indexing exits without it.

### Thumbnails missing for PDF/video

Install optional tools (`pdftoppm`, `mutool`, `ffmpeg`). Indexing still succeeds; thumbnails may be omitted.

### Test with sample data

See `test_data/media_index/README.md` for a self-contained test volume and database.

---

## Script reference

### Core

| Script | Command alias | Purpose |
|--------|---------------|---------|
| `media_utils.py` | — | Shared schema, volume helpers, hashing (import only) |
| `manage_volumes.py` | `photo-volumes` | Register/list/resolve volumes |
| `index_media.py` | `photo-index` | Scan and index files |
| `search_media.py` | `photo-search` | Search, thumbnails, open files |
| `show_thumbnails.py` | `photo-show-thumbnails` | Wrapper → `search_media.py` with thumbnails |

### File operations

| Script | Command alias | Purpose |
|--------|---------------|---------|
| `media_process/move_media.py` | `photo-move` | Move files + update DB |
| `media_process/apply_exif.py` | `photo-apply-exif` | Write EXIF/XMP; optional re-index |
| `media_process/locate_in_db.py` | `photo-locate` | Hash lookup |
| `remove_dupes.py` | `photo-remove-dupes` | Remove same-folder hash dupes from DB |
| `media_process/manage_dupes.py` | `photo-manage-dupes` | Move/copy files not in index |

### Utilities

| Script | Purpose |
|--------|---------|
| `show_exif.py` | Display EXIF (no database) |
| `migrate_db_v2.py` | Convert v1 `fullpath` DB to v2 |
| `inspect_db.py` | Quick schema and row-count summary |
| `audit_utils.py` | File-based audit logging (used by `move_media`) |

### GUI

| Script | Purpose |
|--------|---------|
| `media_process/image_process.py` | Tkinter GUI wrapping index, move, EXIF, dupe tools |

### Database tables (v2)

| Table | Contents |
|-------|----------|
| `volumes` | Volume name → `src_root`, `mount_path` |
| `files` | Core catalog row per file |
| `image_metadata` / `video_metadata` / `audio_metadata` / `document_metadata` / `email_metadata` | Type-specific fields |
| `thumbnails` | JPEG blob per file |
| `skipped_files` | Per-run skip audit |
| `removed_duplicates` | Duplicates removed by `remove_dupes.py` |
| `audit_log` | General operation log |

### Tests

```bash
cd scripts
python -m unittest tests.test_index_media tests.test_search_media tests.test_media_utils -v
```

---

## Related documentation

- `MEDIA_INDEX_CAPABILITY.md` — technical capability and schema notes
- `test_data/media_index/README.md` — sample data for manual testing
- `BUGFIX_pattern_matching.md` — include-pattern regex pitfalls
- `spec.txt` — original design specification
