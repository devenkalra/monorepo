#!/usr/bin/env python3
"""Backup a media index SQLite database in full or incremental split form.

Strategy (matches a split differential backup model):

1. **Metadata archive** — online-consistent copy of the catalog with the heavy
   ``thumbnails`` table removed, compressed as ``metadata_backup_*.tar.gz``.
   Always a full metadata snapshot (small without BLOBs).

2. **Thumbnail archive** — separate SQLite file containing only ``thumbnails``
   rows, compressed as ``thumbnail_patch_*.tar.gz`` (incremental) or
   ``thumbnail_full_*.tar.gz`` (full).

Incremental thumbnail backups select rows with ``created_at`` on or after a
cutoff (default: last successful thumbnail backup recorded in state file, or
``--since``, or 24 hours).

Restore helpers can merge a metadata archive and/or thumbnail archive back into
a target database.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import tarfile
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from media_utils import _ensure_thumbnail_schema, create_database_schema

STATE_FILENAME = '.media_index_backup_state.json'
METADATA_PREFIX = 'metadata_backup_'
THUMBNAIL_PATCH_PREFIX = 'thumbnail_patch_'
THUMBNAIL_FULL_PREFIX = 'thumbnail_full_'


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_since(value: str) -> str:
    """Normalize a user-supplied cutoff to ISO text for SQLite comparison."""
    value = value.strip()
    for fmt in (
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d',
    ):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date/time format: {value!r}")


def default_incremental_cutoff(hours: int = 24) -> str:
    dt = datetime.now(timezone.utc) - timedelta(hours=hours)
    return dt.replace(microsecond=0).isoformat()


def load_state(backup_dir: Path) -> Dict:
    path = backup_dir / STATE_FILENAME
    if not path.exists():
        return {}
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def save_state(backup_dir: Path, state: Dict):
    backup_dir.mkdir(parents=True, exist_ok=True)
    path = backup_dir / STATE_FILENAME
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write('\n')


def sqlite_path_literal(path: Path) -> str:
    """Return a SQLite-safe path string for ATTACH/VACUUM INTO."""
    return str(path.resolve()).replace('\\', '/')


def open_source_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.execute('PRAGMA query_only = ON')
    return conn


def vacuum_into(source_db: Path, dest_db: Path, verbose: int = 0):
    """Create an online-consistent copy via VACUUM INTO."""
    dest_db.parent.mkdir(parents=True, exist_ok=True)
    if dest_db.exists():
        dest_db.unlink()

    conn = sqlite3.connect(str(source_db))
    try:
        if verbose >= 2:
            print(f"VACUUM INTO {dest_db}")
        conn.execute("VACUUM INTO ?", (sqlite_path_literal(dest_db),))
    finally:
        conn.close()


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def strip_thumbnails(db_path: Path, verbose: int = 0):
    conn = sqlite3.connect(str(db_path))
    try:
        if table_exists(conn, 'thumbnails'):
            if verbose >= 2:
                print(f"Dropping thumbnails table from {db_path.name}")
            conn.execute('DROP TABLE thumbnails')
            conn.commit()
    finally:
        conn.close()


def compress_tar_gz(source_path: Path, archive_path: Path, arcname: Optional[str] = None):
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if archive_path.exists():
        archive_path.unlink()
    name = arcname or source_path.name
    with tarfile.open(archive_path, 'w:gz') as tar:
        tar.add(str(source_path), arcname=name)


def extract_tar_gz(archive_path: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, 'r:gz') as tar:
        tar.extractall(dest_dir)
    members = list(dest_dir.iterdir())
    if len(members) == 1 and members[0].is_file():
        return members[0]
    db_files = [p for p in dest_dir.rglob('*.db') if p.is_file()]
    if len(db_files) == 1:
        return db_files[0]
    raise FileNotFoundError(f"Could not find a single .db file in {archive_path}")


def count_thumbnails(source_db: Path, since: Optional[str] = None,
                     include_missing_created_at: bool = False) -> int:
    conn = open_source_db(source_db)
    try:
        if not table_exists(conn, 'thumbnails'):
            return 0
        if since is None:
            return conn.execute('SELECT COUNT(*) FROM thumbnails').fetchone()[0]
        if include_missing_created_at:
            query = """
                SELECT COUNT(*) FROM thumbnails
                WHERE created_at >= ? OR created_at IS NULL
            """
        else:
            query = "SELECT COUNT(*) FROM thumbnails WHERE created_at >= ?"
        return conn.execute(query, (since,)).fetchone()[0]
    finally:
        conn.close()


def export_thumbnails(source_db: Path, patch_db: Path, since: Optional[str] = None,
                      include_missing_created_at: bool = False, verbose: int = 0) -> int:
    """Export thumbnail rows into a standalone SQLite file. Returns row count."""
    patch_db.parent.mkdir(parents=True, exist_ok=True)
    if patch_db.exists():
        patch_db.unlink()

    conn = sqlite3.connect(str(source_db))
    try:
        if not table_exists(conn, 'thumbnails'):
            if verbose >= 1:
                print('Source database has no thumbnails table.')
            conn.execute(
                f"ATTACH DATABASE '{sqlite_path_literal(patch_db)}' AS patch"
            )
            conn.execute("""
                CREATE TABLE patch.thumbnails (
                    id INTEGER PRIMARY KEY,
                    file_id INTEGER NOT NULL,
                    thumbnail_data BLOB NOT NULL,
                    thumbnail_width INTEGER,
                    thumbnail_height INTEGER,
                    created_at TEXT
                )
            """)
            conn.commit()
            return 0

        attach = f"ATTACH DATABASE '{sqlite_path_literal(patch_db)}' AS patch"
        conn.execute(attach)
        conn.execute('DROP TABLE IF EXISTS patch.thumbnails')

        if since is None:
            sql = """
                CREATE TABLE patch.thumbnails AS
                SELECT id, file_id, thumbnail_data, thumbnail_width, thumbnail_height, created_at
                FROM main.thumbnails
            """
            params: Tuple = ()
        elif include_missing_created_at:
            sql = """
                CREATE TABLE patch.thumbnails AS
                SELECT id, file_id, thumbnail_data, thumbnail_width, thumbnail_height, created_at
                FROM main.thumbnails
                WHERE created_at >= ? OR created_at IS NULL
            """
            params = (since,)
        else:
            sql = """
                CREATE TABLE patch.thumbnails AS
                SELECT id, file_id, thumbnail_data, thumbnail_width, thumbnail_height, created_at
                FROM main.thumbnails
                WHERE created_at >= ?
            """
            params = (since,)

        conn.execute(sql, params)
        count = conn.execute('SELECT COUNT(*) FROM patch.thumbnails').fetchone()[0]
        conn.execute('DETACH DATABASE patch')
        conn.commit()
        if verbose >= 2:
            scope = 'all rows' if since is None else f'created_at >= {since}'
            print(f"Exported {count} thumbnail row(s) ({scope})")
        return count
    finally:
        conn.close()


def backup_metadata(source_db: Path, backup_dir: Path, timestamp: str,
                    dry_run: bool = False, verbose: int = 0) -> Optional[Path]:
    archive_name = f'{METADATA_PREFIX}{timestamp}.tar.gz'
    archive_path = backup_dir / archive_name

    if dry_run:
        print(f'[DRY RUN] Would write metadata archive: {archive_path}')
        return archive_path

    with tempfile.TemporaryDirectory(prefix='media_meta_backup_') as tmp:
        temp_db = Path(tmp) / f'metadata_{timestamp}.db'
        vacuum_into(source_db, temp_db, verbose=verbose)
        strip_thumbnails(temp_db, verbose=verbose)
        compress_tar_gz(temp_db, archive_path)

    size_mb = archive_path.stat().st_size / (1024 * 1024)
    if verbose >= 1:
        print(f'Metadata archive: {archive_path} ({size_mb:.2f} MB)')
    return archive_path


def backup_thumbnails(source_db: Path, backup_dir: Path, mode: str, since: Optional[str],
                      include_missing_created_at: bool, timestamp: str, date_tag: str,
                      dry_run: bool = False, verbose: int = 0) -> Optional[Path]:
    is_full = mode == 'full'
    prefix = THUMBNAIL_FULL_PREFIX if is_full else THUMBNAIL_PATCH_PREFIX
    name_stem = f'{prefix}{timestamp if is_full else date_tag}'
    archive_path = backup_dir / f'{name_stem}.tar.gz'

    expected = count_thumbnails(
        source_db,
        since=None if is_full else since,
        include_missing_created_at=include_missing_created_at and not is_full,
    )
    if expected == 0:
        if verbose >= 1:
            if is_full:
                print('No thumbnails in source database; skipping thumbnail archive.')
            else:
                print(f'No thumbnails with created_at >= {since}; skipping patch archive.')
        return None

    if dry_run:
        print(f'[DRY RUN] Would write thumbnail archive ({expected} row(s)): {archive_path}')
        return archive_path

    with tempfile.TemporaryDirectory(prefix='media_thumb_backup_') as tmp:
        patch_db = Path(tmp) / f'{name_stem}.db'
        exported = export_thumbnails(
            source_db,
            patch_db,
            since=None if is_full else since,
            include_missing_created_at=include_missing_created_at and not is_full,
            verbose=verbose,
        )
        if exported == 0:
            if verbose >= 1:
                print('Thumbnail export produced no rows; skipping archive.')
            return None
        compress_tar_gz(patch_db, archive_path)

    size_mb = archive_path.stat().st_size / (1024 * 1024)
    if verbose >= 1:
        label = 'Full thumbnail archive' if is_full else 'Incremental thumbnail patch'
        print(f'{label}: {archive_path} ({size_mb:.2f} MB, {exported} row(s))')
    return archive_path


def resolve_incremental_cutoff(args, state: Dict, source_db: Path) -> str:
    if args.since:
        return parse_since(args.since)
    prev = state.get('last_thumbnail_backup')
    if prev and state.get('source_db') == str(source_db.resolve()):
        return prev
    return default_incremental_cutoff(args.lookback_hours)


def cmd_backup(args) -> int:
    source_db = Path(args.db_path).resolve()
    backup_dir = Path(args.backup_dir).resolve()

    if not source_db.exists():
        print(f'Error: database not found: {source_db}', file=sys.stderr)
        return 1

    backup_dir.mkdir(parents=True, exist_ok=True)
    state = load_state(backup_dir)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    date_tag = datetime.now().strftime('%Y-%m-%d')
    mode = args.mode
    run_metadata = not args.thumbnails_only
    run_thumbnails = not args.metadata_only
    now = utc_now_iso()

    if args.verbose >= 1:
        print('=' * 70)
        print('Media index database backup')
        print('=' * 70)
        print(f'Source:  {source_db}')
        print(f'Target:  {backup_dir}')
        print(f'Mode:    {mode}')
        if args.dry_run:
            print('Dry run: yes')
        print()

    since = None
    if run_thumbnails and mode == 'incremental':
        since = resolve_incremental_cutoff(args, state, source_db)
        if args.verbose >= 1:
            print(f'Thumbnail incremental cutoff: {since}')

    metadata_archive = None
    thumbnail_archive = None

    if run_metadata:
        metadata_archive = backup_metadata(
            source_db, backup_dir, timestamp,
            dry_run=args.dry_run, verbose=args.verbose,
        )

    if run_thumbnails:
        thumbnail_archive = backup_thumbnails(
            source_db, backup_dir, mode, since,
            include_missing_created_at=args.include_missing_created_at,
            timestamp=timestamp, date_tag=date_tag,
            dry_run=args.dry_run, verbose=args.verbose,
        )

    if args.dry_run:
        print('\nDry run complete; state file not updated.')
        return 0

    state.update({
        'source_db': str(source_db),
        'last_run': now,
        'last_mode': mode,
    })
    if metadata_archive:
        state['last_metadata_backup'] = now
        state['last_metadata_archive'] = metadata_archive.name
    if thumbnail_archive:
        state['last_thumbnail_backup'] = now
        state['last_thumbnail_archive'] = thumbnail_archive.name
    if mode == 'full':
        state['last_full_backup'] = now
    save_state(backup_dir, state)

    if args.verbose >= 1:
        print('\nBackup complete.')
    return 0


def restore_metadata(archive_path: Path, target_db: Path, dry_run: bool, verbose: int) -> int:
    if dry_run:
        print(f'[DRY RUN] Would restore metadata from {archive_path} to {target_db}')
        return 0

    with tempfile.TemporaryDirectory(prefix='media_meta_restore_') as tmp:
        extracted = extract_tar_gz(archive_path, Path(tmp))
        target_db.parent.mkdir(parents=True, exist_ok=True)
        if target_db.exists():
            backup_copy = target_db.with_suffix(target_db.suffix + '.pre-restore.bak')
            shutil.copy2(target_db, backup_copy)
            if verbose >= 1:
                print(f'Existing database backed up to {backup_copy}')
        shutil.copy2(extracted, target_db)

    if verbose >= 1:
        print(f'Metadata restored to {target_db}')
    return 0


def restore_thumbnails(archive_path: Path, target_db: Path, dry_run: bool, verbose: int) -> int:
    if dry_run:
        print(f'[DRY RUN] Would merge thumbnails from {archive_path} into {target_db}')
        return 0

    with tempfile.TemporaryDirectory(prefix='media_thumb_restore_') as tmp:
        patch_db = extract_tar_gz(archive_path, Path(tmp))
        conn = sqlite3.connect(str(target_db))
        try:
            create_database_schema(conn)
            _ensure_thumbnail_schema(conn.cursor())
            attach = f"ATTACH DATABASE '{sqlite_path_literal(patch_db)}' AS patch"
            conn.execute(attach)
            if not table_exists(conn, 'thumbnails'):
                raise RuntimeError('Patch database has no thumbnails table')
            conn.execute("""
                INSERT OR REPLACE INTO main.thumbnails
                    (id, file_id, thumbnail_data, thumbnail_width, thumbnail_height, created_at)
                SELECT id, file_id, thumbnail_data, thumbnail_width, thumbnail_height, created_at
                FROM patch.thumbnails
            """)
            merged = conn.execute('SELECT COUNT(*) FROM patch.thumbnails').fetchone()[0]
            conn.commit()
            conn.execute('DETACH DATABASE patch')
        finally:
            conn.close()

    if verbose >= 1:
        print(f'Merged {merged} thumbnail row(s) into {target_db}')
    return 0


def cmd_restore(args) -> int:
    target_db = Path(args.db_path).resolve()

    if args.metadata_archive:
        rc = restore_metadata(Path(args.metadata_archive).resolve(), target_db,
                              dry_run=args.dry_run, verbose=args.verbose)
        if rc != 0:
            return rc

    if args.thumbnail_archive:
        rc = restore_thumbnails(Path(args.thumbnail_archive).resolve(), target_db,
                                dry_run=args.dry_run, verbose=args.verbose)
        if rc != 0:
            return rc

    if not args.metadata_archive and not args.thumbnail_archive:
        print('Error: specify --metadata-archive and/or --thumbnail-archive', file=sys.stderr)
        return 1

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Backup or restore a media index SQLite database.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Incremental split backup (metadata snapshot + new thumbnails)
  python backup_media_db.py --db-path files.db --backup-dir D:/backups/catalog

  # Full backup including all thumbnails
  python backup_media_db.py --db-path files.db --backup-dir D:/backups/catalog --mode full

  # Metadata only
  python backup_media_db.py --db-path files.db --backup-dir D:/backups/catalog --metadata-only

  # Incremental thumbnails since a specific time
  python backup_media_db.py --db-path files.db --backup-dir D:/backups/catalog \\
      --thumbnails-only --since 2026-07-01T00:00:00

  # Restore metadata baseline then merge thumbnail patches
  python backup_media_db.py restore --db-path files.db \\
      --metadata-archive D:/backups/catalog/metadata_backup_20260703_120000.tar.gz
  python backup_media_db.py restore --db-path files.db \\
      --thumbnail-archive D:/backups/catalog/thumbnail_patch_2026-07-03.tar.gz
        """,
    )
    sub = parser.add_subparsers(dest='command')

    backup = sub.add_parser('backup', help='Create backup archives (default)')
    backup.add_argument('--db-path', required=True, help='Live media index database')
    backup.add_argument('--backup-dir', required=True, help='Directory for archives and state file')
    backup.add_argument('--mode', choices=['incremental', 'full'], default='incremental',
                        help='Incremental exports new thumbnails; full exports all thumbnails')
    backup.add_argument('--since', help='Thumbnail cutoff (ISO date/time) for incremental mode')
    backup.add_argument('--lookback-hours', type=int, default=24,
                        help='Default thumbnail lookback when no state/since (default: 24)')
    backup.add_argument('--include-missing-created-at', action='store_true', default=True,
                        help='Include thumbnails with NULL created_at in incremental exports (default: on)')
    backup.add_argument('--no-include-missing-created-at', dest='include_missing_created_at',
                        action='store_false', help='Exclude NULL created_at rows from incremental exports')
    backup.add_argument('--metadata-only', action='store_true',
                        help='Only write the metadata archive')
    backup.add_argument('--thumbnails-only', action='store_true',
                        help='Only write the thumbnail archive')
    backup.add_argument('--dry-run', action='store_true', help='Report actions without writing files')
    backup.add_argument('--verbose', '-v', type=int, default=1, choices=[0, 1, 2],
                        help='Verbosity level')

    restore = sub.add_parser('restore', help='Restore metadata and/or merge thumbnail archives')
    restore.add_argument('--db-path', required=True, help='Target database to restore into')
    restore.add_argument('--metadata-archive', help='metadata_backup_*.tar.gz to restore')
    restore.add_argument('--thumbnail-archive', help='thumbnail_patch_*.tar.gz or thumbnail_full_*.tar.gz')
    restore.add_argument('--dry-run', action='store_true')
    restore.add_argument('--verbose', '-v', type=int, default=1, choices=[0, 1, 2])

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ('backup', 'restore'):
        argv = ['backup'] + argv
    args = parser.parse_args(argv)

    if args.command == 'backup':
        return cmd_backup(args)
    if args.command == 'restore':
        return cmd_restore(args)
    parser.error(f'Unknown command: {args.command}')
    return 2


if __name__ == '__main__':
    sys.exit(main())
