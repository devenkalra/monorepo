# Media Index — Current Capability (v2)

This document describes the Python tooling under `scripts/` for creating and managing a SQLite-based media index. It reflects the v2 volume-based schema (July 2026), centered on `index_media.py`, `manage_volumes.py`, and `media_utils.py`.

## Overview

The media index system registers **volumes** (logical collections with a NAS `src_root` and local `mount_path`), scans under the mount recursively, extracts metadata from images, videos, audio, documents, and email, generates thumbnails, computes SHA-256 hashes, and stores **relative paths** (`relpath`) in SQLite. Absolute paths are resolved at runtime from `volumes.mount_path`.

```
┌─────────────────────────────────────────────────────────────────┐
│                        Media index database (v2)                 │
│  volumes │ files │ image/video/audio/document/email_metadata    │
│  thumbnails │ skipped_files │ audit_log │ removed_duplicates    │
└───────────────▲───────────────────────────────▲─────────────────┘
                │                               │
     ┌──────────┴──────────┐         ┌─────────┴──────────┐
     │ manage_volumes.py   │         │  Consumer scripts   │
     │ index_media.py      │         │ manage_dupes        │
     │ show_thumbnails.py  │         │ locate_in_db        │
     └──────────┬──────────┘         │ remove_dupes        │
                │                    │ move_media          │
     ┌──────────┴──────────┐         │ apply_exif          │
     │   media_utils.py    │◀────────└────────────────────┘
     │  schema, volumes    │
     └─────────────────────┘
```

### Script locations

| Script | Path | Role |
|--------|------|------|
| `media_utils.py` | `scripts/` | Canonical shared DB schema, volume helpers, file-type detection |
| `manage_volumes.py` | `scripts/` | Register volume name → `src_root` + `mount_path` |
| `index_media.py` | `scripts/` | Primary indexer (requires registered volume) |
| `show_thumbnails.py` | `scripts/` | View thumbnail blobs by file id or path |
| `manage_dupes.py` | `scripts/media_process/` | Move/copy files not in index |
| `locate_in_db.py` | `scripts/media_process/` | Hash lookup against index |
| `remove_dupes.py` | `scripts/` | Remove same-folder hash duplicates from DB |
| `move_media.py` | `scripts/media_process/` | Move files and update DB records |
| `apply_exif.py` | `scripts/media_process/` | Write EXIF/XMP; optional DB re-index |
| `show_exif.py` | `scripts/` | Display metadata (no DB) |
| `image_process.py` | `scripts/media_process/` | Tkinter GUI wrapping the above |
| `audit_utils.py` | `scripts/` | File-based audit logging (used by `move_media`) |

`gui/media_utils.py` re-exports from `scripts/media_utils.py`. `setup.py` registers console entry points including `photo-volumes` and `photo-show-thumbnails`.

---

## Volume workflow

Volumes must be registered before indexing:

```bash
python3 manage_volumes.py set photo --src-root /volume1/photo --mount /mnt/photo --db-path media.db
python3 index_media.py --volume photo --db-path media.db
```

Volume names are stored **lowercase**. The indexer resolves the scan root from `volumes.mount_path`, not from a `--path` argument.

---

## Original specification (`spec.txt`)

The original design called for:

- Recursive scan with `volume_tag` and `skip_pattern`
- Per-file base fields: volume, path, name, create/modify dates, size, mime, extension, hash
- Image-specific metadata and thumbnails
- Video-specific metadata
- Duplicate management tooling

**Status:** Implemented in v2 with volume-based paths, plus audio/document/email support, `manage_volumes.py`, and `show_thumbnails.py`. AI summaries and FTS search are deferred.

---

## Database schema (`media_utils.create_database_schema`)

### `volumes` — mount registration

| Column | Type | Notes |
|--------|------|-------|
| `name` | TEXT PK | Lowercase volume identifier |
| `src_root` | TEXT | NAS-side path (posix, e.g. `/volume1/photo`) |
| `mount_path` | TEXT | Local mount path used for scanning |
| `updated_at` | TEXT | ISO timestamp |

### `files` — core index record

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `volume` | TEXT | FK to `volumes.name` |
| `relpath` | TEXT | Path relative to volume mount; unique per `(volume, relpath)` |
| `name` | TEXT | Basename |
| `created_date` | TEXT | ISO timestamp from filesystem ctime |
| `modified_date` | TEXT | ISO timestamp from mtime |
| `size` | INTEGER | Bytes |
| `mime_type` | TEXT | From `mimetypes` + extension heuristics |
| `extension` | TEXT | Lowercase including dot |
| `file_hash` | TEXT | SHA-256 hex digest |
| `indexed_date` | TEXT | When this record was last indexed |

Indexes: `volume`, `extension`, `file_hash`.

Lookup helpers resolve `relpath` → absolute path via `resolve_file_path(mount_path, relpath)`.

### Type-specific metadata tables

- `image_metadata` — EXIF normalization, GPS, keywords, etc.
- `video_metadata` — dimensions, codec, duration, frame rate
- `audio_metadata` — duration, codec, bit rate, channels
- `document_metadata` — page count, author, title (PDF/Office/text)
- `email_metadata` — headers only (subject, from, to, date); body not stored

### `thumbnails` — JPEG blob per file

`thumbnail_data` (BLOB), `thumbnail_width`, `thumbnail_height` (default target 200×200).

### `skipped_files` — per-run skip audit

Records `relpath` (not absolute path) with `run_timestamp`, `skip_reason`, `volume`, `file_size`.

### `audit_log` — operation history

Used by `apply_exif` and available for other scripts.

### `removed_duplicates` — created by `remove_dupes.py`

Tracks duplicates removed from the index using `original_relpath` / `kept_relpath`.

---

## `index_media.py` — primary indexer

### What it does

1. Opens or creates the SQLite database and ensures schema exists.
2. Resolves `volume` → `mount_path` from the `volumes` table.
3. Walks mount path + optional `start_dir`(s) recursively.
4. Applies include patterns (if any), then skip patterns.
5. For each candidate file, checks whether it is already indexed.
6. Extracts metadata and thumbnails for supported file types.
7. Commits in batches; prints a run summary.

### Command-line interface

```
python3 index_media.py --volume NAME [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--volume` | *(required)* | Registered volume name |
| `--start-dir` | volume mount root | Subdirectory under mount; repeatable |
| `--db-path` | `media_index.db` | SQLite database file |
| `--include-pattern` | all indexable types | Regex (or literal) path filter; OR logic |
| `--skip-pattern` | none | Regex (or literal) path filter |
| `--literal-patterns` | off | Treat patterns as literal strings |
| `--max-depth` | unlimited | `0` = files in start dir only |
| `--check-existing` | `relpath` + `volume` | Skip if record matches all listed criteria |
| `--verbose` / `-v` | `0` | `0` quiet … `3` full metadata output |
| `--dry-run` | off | Report actions without DB changes |
| `--limit` | none | Cap files processed |

`--check-existing` choices: `relpath`, `fullpath` (alias for `relpath`), `volume`, `size`, `modified_date`, `hash`.

### File processing pipeline

**Base info** (`get_file_info`): volume, `relpath`, name, dates, size, extension, MIME type, hash.

**Supported types:** images, videos, audio, documents (PDF, txt, Office), `.eml` email.

**Hash**: SHA-256 (`media_utils.calculate_file_hash`).

### Example commands

```bash
# Register volume once
python3 manage_volumes.py set photo --src-root /volume1/photo --mount /mnt/photo --db-path media.db

# Index entire mount
python3 index_media.py --volume photo --db-path media.db

# Index specific years, skip unchanged by size+mtime
python3 index_media.py --volume photo --start-dir 2024 --start-dir 2025 \
  --check-existing size --check-existing modified_date --db-path media.db
```

---

## Related tools

| Tool | Purpose |
|------|---------|
| `manage_volumes.py` | `set`, `list`, `show`, `resolve` volume mappings |
| `show_thumbnails.py` | Export/open thumbnails by `--file-id`, `--relpath`, or `--file` |
| `locate_in_db.py` | Find all DB rows matching a file hash |
| `move_media.py` | Move files; update `relpath` in DB |
| `remove_dupes.py` | Deduplicate within folders; audit to `removed_duplicates` |
| `apply_exif.py` | Write tags; re-index via `index_media --volume` when `--reprocess-db` |

---

*Remaining sections below may still reference the legacy `--path` / `fullpath` model from v1.*
- If `(fullpath, volume)` exists but criteria differ → update record, delete old metadata/thumbnails, re-extract.
- Non-image/non-video files → skip with reason `not_media_file`.

**Images** (`process_image`):

- EXIF via `exiftool -json -G`.
- Normalization picks the best available tag from EXIF/XMP/IPTC/Composite groups (see `normalize_exif_data`).
- GPS coordinates parsed from DMS or decimal formats.

**Videos** (`get_video_metadata`):

- `ffprobe -show_streams -show_format` for dimensions, codec, frame rate, audio channels, bit rate, duration.

**Thumbnails** (`generate_thumbnail`, max 200×200 JPEG):

- Standard images: Pillow resize.
- RAW formats (`.cr2`, `.nef`, `.dng`, etc.): embedded preview via exiftool (`PreviewImage`, `JpgFromRaw`, `ThumbnailImage`), then Pillow.
- Videos: ffmpeg frame extraction with fallback seek strategies (1s → 0s → no seek).

**Hash**: SHA-256 streaming read (`media_utils.calculate_file_hash`).

### Supported file types

- **Images:** any `image/*` MIME type plus a large set of RAW extensions (`.cr2`, `.cr3`, `.nef`, `.arw`, `.dng`, etc.).
- **Videos:** any `video/*` MIME type.

### External dependencies

| Tool | Required | Purpose |
|------|----------|---------|
| `exiftool` | **Yes** (script exits if missing) | Image EXIF, RAW previews |
| `ffprobe` | Warn if missing | Video metadata |
| `ffmpeg` | For video thumbnails | Frame extraction |
| Pillow | Warn if missing | Thumbnails |

### Example commands

```bash
# Full index of a photo volume
python3 index_media.py --path /mnt/photo --volume PHOTO \
  --db-path /data/media-index/files.db \
  --literal-patterns --skip-pattern "/.filerun" --skip-pattern "/.DS_Store"

# Incremental: skip files with same size and mtime
python3 index_media.py --path /mnt/photo --start-dir 2024 --volume PHOTO \
  --db-path files.db --check-existing size --check-existing modified_date

# Dry-run with verbose output, limited to 10 files
python3 index_media.py --path /mnt/photo --volume PHOTO --dry-run -v 2 --limit 10
```

---

## Shared utilities (`media_utils.py`)

| Function | Purpose |
|----------|---------|
| `create_database_schema(conn)` | Create all tables and indexes |
| `calculate_file_hash(filepath)` | SHA-256 hex digest |
| `get_mime_type(filepath)` | `mimetypes.guess_type` with octet-stream fallback |
| `is_image_file(mime, extension)` | Standard images + RAW extensions |
| `is_video_file(mime)` | `video/*` prefix check |
| `log_audit(conn, ...)` | Insert row into `audit_log` |

---

## Database consumer scripts

### `manage_dupes.py` — isolate files not in the index

Scans a **source** directory, hashes each file, and checks the index. Files **not** found by hash are treated as duplicates of nothing in the index — they are **moved or copied** to a **destination** tree preserving relative paths.

| Option | Description |
|--------|-------------|
| `--source` | Directory to scan |
| `--destination` | Root for relocated files |
| `--db-path` | Existing index database |
| `--action` | `move` (default) or `copy` |
| `--media-only` | Restrict to image/video files |
| `--include-pattern` / `--skip-pattern` | Same semantics as indexer |
| `--dry-run`, `--limit`, `-v` | Testing and verbosity |

**Note:** This script imports `find_files_by_hash` and `find_file_by_hash` from `media_utils`, but those functions are **not defined** in the current `media_utils.py`. The script will fail at import until those helpers are added (or the import is inlined). `locate_in_db.find_by_hash` is the working equivalent.

### `locate_in_db.py` — hash lookup

Given one or more files on disk, computes hash and returns all matching `files` rows (with optional image/video metadata, JSON output, summary mode).

```bash
python3 locate_in_db.py --files photo.jpg --db-path files.db --metadata
```

### `remove_dupes.py` — deduplicate within the index

Operates **on the database**, not an external source tree. Finds groups of files in the **same folder** with the **same hash**, keeps the earliest-indexed file, moves the rest to `--dest`, removes them from the DB, and writes `removed_duplicates` audit rows.

```bash
python3 remove_dupes.py --db files.db --dest /removed_dupes --base-dir /mnt/photo --dry-run
```

### `move_media.py` — relocate indexed files

Moves explicit file list to a destination directory, updates (or inserts) DB records with new paths, re-extracts metadata and thumbnails using `index_media` functions, and writes a file-based audit log via `audit_utils`.

```bash
python3 move_media.py --files img1.jpg img2.jpg \
  --destination /photos/2024 --volume MainLibrary --db media.db
```

### `apply_exif.py` — metadata editing with optional re-index

Writes EXIF/XMP tags via exiftool (YAML tags, CLI `--set`, geocoding, keywords, captions). When `--db-path` and `--reprocess-db` are set, re-runs indexing for changed files by shelling out to `index_media.py` (looks for it alongside `apply_exif.py` in `media_process/`).

---

## Supporting tools (no direct index writes)

| Script | Role |
|--------|------|
| `show_exif.py` | Display EXIF/GPS/video metadata from files via exiftool |
| `image_process.py` | GUI launcher for index, dupes, move, locate, apply_exif, show_exif |
| `find_location.py` / `guess_location.py` | Geocoding helpers used by apply_exif |
| `find_similar_images.py` | Visual similarity (separate from hash-based dupes) |

---

## Typical workflows

### Initial library index

```bash
python3 scripts/index_media.py --path /mnt/photo --volume PHOTO \
  --db-path /data/media-index/files.db \
  --literal-patterns --skip-pattern "/.DS_Store"
```

### Incremental re-scan (years at a time)

```bash
for year in 1984 1986 1987 1988 1989; do
  python3 scripts/index_media.py --path /mnt/photo --start-dir "$year" \
    --volume PHOTO --db-path files.db \
    --check-existing size --check-existing modified_date \
    --literal-patterns --skip-pattern "/.filerun" --skip-pattern "/.DS_Store" -v 2
done
```

### Find whether a file is already indexed

```bash
python3 scripts/media_process/locate_in_db.py --files /path/to/file.jpg --db-path files.db
```

### Clean up hash duplicates in one folder

```bash
python3 scripts/remove_dupes.py --db files.db --dest /dupes_archive --dry-run -v 2
```

### Import a backup tree, moving only unknown files

```bash
python3 scripts/media_process/manage_dupes.py \
  --source /backup/photos --destination /unknown_dupes --db-path files.db --dry-run
```

*(Requires `find_files_by_hash` to be added to `media_utils` first.)*

---

## Testing

`scripts/tests/test_index_media.py` — unit tests for pattern matching, database checks, EXIF normalization, GPS parsing, and scan/process logic.

`scripts/tests/test_media_utils.py` — schema, hash, MIME, image/video detection.

Run via `scripts/tests/run_all_tests.sh`.

---

## Known gaps and layout notes

1. **`manage_dupes.py` import error:** Expects `find_files_by_hash` / `find_file_by_hash` in `media_utils`; only `locate_in_db.find_by_hash` exists today.
2. **Split module paths:** `index_media.py` imports `from media_utils import ...` at the `scripts/` level, but `media_utils.py` lives under `media_process/gui/`. Tests add the parent dir to `sys.path`; production use may require `PYTHONPATH` or `pip install -e .` from `scripts/`.
3. **`apply_exif` reprocess path:** Looks for `index_media.py` next to itself in `media_process/`; the actual file is at `scripts/index_media.py`.
4. **`setup.py` flat layout:** Lists modules at package root; repo stores several under `media_process/`.
5. **Backup copy:** `index_media2026-01-22-20-37.py` is a dated snapshot; `index_media.py` is the active version.
6. **Spec field naming:** Spec used `focal_length35mm` and `video_encoder`; DB uses `focal_length_35mm` and `video_codec`.

---

## Summary

The media index system delivers a production-capable SQLite catalog of images and videos with rich EXIF normalization, video probe data, embedded thumbnails, SHA-256 hashing, and flexible incremental indexing. The database is the hub for duplicate management (`remove_dupes`, `manage_dupes`), relocation (`move_media`), lookup (`locate_in_db`), and metadata refresh (`apply_exif` + reprocess). The core indexer (`index_media.py`) fully implements the original `spec.txt` requirements and adds pattern filtering, depth control, dry-run, skip auditing, and configurable existence checks.
