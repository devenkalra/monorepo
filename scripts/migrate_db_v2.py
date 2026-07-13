#!/usr/bin/env python3
"""Migrate a v1 media index database (fullpath) to v2 (volumes + relpath)."""

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from typing import Optional

from media_utils import (
    normalize_path,
    normalize_src_root,
    normalize_volume_name,
    resolve_file_path,
    set_volume,
)


def detect_old_mount(conn: sqlite3.Connection) -> str:
    """Infer the old absolute mount prefix from stored fullpaths."""
    cur = conn.cursor()
    cur.execute("SELECT fullpath FROM files LIMIT 1")
    row = cur.fetchone()
    if not row:
        raise ValueError("files table is empty; cannot infer old mount path")
    sample = row[0].replace('\\', '/')
    # Use first two segments: /mnt/photo
    parts = [p for p in sample.split('/') if p]
    if len(parts) < 2:
        raise ValueError(f"Unexpected fullpath format: {sample}")
    return '/' + '/'.join(parts[:2])


def fullpath_to_relpath(fullpath: str, old_mount: str) -> str:
    """Strip old mount prefix and return portable relpath."""
    norm = fullpath.replace('\\', '/')
    mount = old_mount.replace('\\', '/').rstrip('/')
    prefix = mount + '/'
    if norm.startswith(prefix):
        return norm[len(prefix):]
    if norm == mount:
        return ''
    raise ValueError(f"Path does not start with old mount {mount}: {fullpath}")


def convert_abs_path(fullpath: str, old_mount: str, new_mount: str) -> str:
    """Convert a stored absolute path to the new local mount."""
    relpath = fullpath_to_relpath(fullpath, old_mount)
    return resolve_file_path(new_mount, relpath)


def is_v2_schema(conn: sqlite3.Connection) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='volumes'")
    if not cur.fetchone():
        return False
    cur.execute("PRAGMA table_info(files)")
    cols = {row[1] for row in cur.fetchall()}
    return 'relpath' in cols and 'fullpath' not in cols


def migrate_files_table(conn: sqlite3.Connection, old_mount: str, dry_run: bool) -> int:
    read_cur = conn.cursor()
    write_cur = conn.cursor()
    read_cur.execute("SELECT COUNT(*) FROM files")
    total = read_cur.fetchone()[0]

    write_cur.execute("""
        CREATE TABLE files_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            volume TEXT NOT NULL,
            relpath TEXT NOT NULL,
            name TEXT NOT NULL,
            created_date TEXT,
            modified_date TEXT NOT NULL,
            size INTEGER NOT NULL,
            mime_type TEXT,
            extension TEXT,
            file_hash TEXT,
            indexed_date TEXT NOT NULL,
            UNIQUE(volume, relpath)
        )
    """)

    read_cur.execute("""
        SELECT id, volume, fullpath, name, created_date, modified_date, size,
               mime_type, extension, file_hash, indexed_date
        FROM files
    """)
    batch = []
    converted = 0
    for row in read_cur:
        file_id, volume, fullpath, name, created_date, modified_date, size, mime_type, extension, file_hash, indexed_date = row
        relpath = fullpath_to_relpath(fullpath, old_mount)
        vol = normalize_volume_name(volume)
        batch.append((file_id, vol, relpath, name, created_date, modified_date, size, mime_type, extension, file_hash, indexed_date))
        converted += 1
        if len(batch) >= 5000:
            write_cur.executemany("""
                INSERT INTO files_new (id, volume, relpath, name, created_date, modified_date, size, mime_type, extension, file_hash, indexed_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, batch)
            batch.clear()
    if batch:
        write_cur.executemany("""
            INSERT INTO files_new (id, volume, relpath, name, created_date, modified_date, size, mime_type, extension, file_hash, indexed_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, batch)

    if converted != total:
        raise RuntimeError(f"files migration row count mismatch: read {converted}, expected {total}")

    if not dry_run:
        write_cur.execute("DROP TABLE files")
        write_cur.execute("ALTER TABLE files_new RENAME TO files")
    return converted


def migrate_skipped_files(conn: sqlite3.Connection, old_mount: str, dry_run: bool) -> int:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='skipped_files'")
    if not cur.fetchone():
        return 0

    cur.execute("PRAGMA table_info(skipped_files)")
    cols = {row[1] for row in cur.fetchall()}
    if 'relpath' in cols and 'fullpath' not in cols:
        return 0

    cur.execute("""
        CREATE TABLE skipped_files_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_timestamp TEXT NOT NULL,
            relpath TEXT NOT NULL,
            skip_reason TEXT NOT NULL,
            volume TEXT,
            file_size INTEGER,
            recorded_date TEXT NOT NULL
        )
    """)

    cur.execute("""
        SELECT id, run_timestamp, fullpath, skip_reason, volume, file_size, recorded_date
        FROM skipped_files
    """)
    rows = []
    for row in cur.fetchall():
        sid, run_ts, fullpath, reason, volume, size, recorded = row
        relpath = fullpath_to_relpath(fullpath, old_mount)
        vol = normalize_volume_name(volume) if volume else None
        rows.append((sid, run_ts, relpath, reason, vol, size, recorded))

    cur.executemany("""
        INSERT INTO skipped_files_new (id, run_timestamp, relpath, skip_reason, volume, file_size, recorded_date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, rows)

    if not dry_run:
        cur.execute("DROP TABLE skipped_files")
        cur.execute("ALTER TABLE skipped_files_new RENAME TO skipped_files")
    return len(rows)


def migrate_removed_duplicates(conn: sqlite3.Connection, old_mount: str, new_mount: str, dry_run: bool) -> int:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='removed_duplicates'")
    if not cur.fetchone():
        return 0

    cur.execute("PRAGMA table_info(removed_duplicates)")
    cols = {row[1] for row in cur.fetchall()}
    if 'original_relpath' in cols:
        return 0

    cur.execute("""
        CREATE TABLE removed_duplicates_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_file_id INTEGER NOT NULL,
            original_volume TEXT NOT NULL,
            original_relpath TEXT NOT NULL,
            original_name TEXT NOT NULL,
            original_size INTEGER NOT NULL,
            original_hash TEXT NOT NULL,
            moved_to_path TEXT NOT NULL,
            kept_file_id INTEGER NOT NULL,
            kept_relpath TEXT NOT NULL,
            removal_date TEXT NOT NULL,
            removal_reason TEXT NOT NULL
        )
    """)

    cur.execute("""
        SELECT id, original_file_id, original_volume, original_fullpath, original_name,
               original_size, original_hash, moved_to_path, kept_file_id, kept_fullpath,
               removal_date, removal_reason
        FROM removed_duplicates
    """)
    rows = []
    for row in cur.fetchall():
        (rid, orig_id, orig_vol, orig_fp, orig_name, orig_size, orig_hash,
         moved_to, kept_id, kept_fp, removal_date, removal_reason) = row
        rows.append((
            rid, orig_id, normalize_volume_name(orig_vol),
            fullpath_to_relpath(orig_fp, old_mount), orig_name, orig_size, orig_hash,
            convert_abs_path(moved_to, old_mount, new_mount) if moved_to else moved_to,
            kept_id, fullpath_to_relpath(kept_fp, old_mount),
            removal_date, removal_reason,
        ))

    cur.executemany("""
        INSERT INTO removed_duplicates_new (
            id, original_file_id, original_volume, original_relpath, original_name,
            original_size, original_hash, moved_to_path, kept_file_id, kept_relpath,
            removal_date, removal_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)

    if not dry_run:
        cur.execute("DROP TABLE removed_duplicates")
        cur.execute("ALTER TABLE removed_duplicates_new RENAME TO removed_duplicates")
    return len(rows)


def migrate_audit_log(conn: sqlite3.Connection, old_mount: str, new_mount: str, dry_run: bool) -> int:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'")
    if not cur.fetchone():
        return 0

    updated = 0
    cur.execute("SELECT id, file_path, old_path, new_path FROM audit_log")
    for row_id, file_path, old_path, new_path in cur.fetchall():
        new_file_path = file_path
        new_old_path = old_path
        new_new_path = new_path
        try:
            if file_path and file_path.replace('\\', '/').startswith(old_mount.replace('\\', '/')):
                new_file_path = convert_abs_path(file_path, old_mount, new_mount)
            if old_path and old_path.replace('\\', '/').startswith(old_mount.replace('\\', '/')):
                new_old_path = convert_abs_path(old_path, old_mount, new_mount)
            if new_path and new_path.replace('\\', '/').startswith(old_mount.replace('\\', '/')):
                new_new_path = convert_abs_path(new_path, old_mount, new_mount)
        except ValueError:
            continue
        if not dry_run and (new_file_path != file_path or new_old_path != old_path or new_new_path != new_path):
            cur.execute(
                "UPDATE audit_log SET file_path=?, old_path=?, new_path=? WHERE id=?",
                (new_file_path, new_old_path, new_new_path, row_id),
            )
            updated += 1
    return updated


def ensure_v2_auxiliary_tables(conn: sqlite3.Connection):
    """Create v2 tables that do not exist in v1, without touching files."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS volumes (
            name TEXT PRIMARY KEY,
            src_root TEXT NOT NULL,
            mount_path TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    for ddl in [
        """
        CREATE TABLE IF NOT EXISTS audio_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            duration_seconds REAL,
            audio_codec TEXT,
            bit_rate_kbps REAL,
            sample_rate INTEGER,
            channels INTEGER,
            title TEXT,
            artist TEXT,
            album TEXT,
            FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS document_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            page_count INTEGER,
            title TEXT,
            author TEXT,
            text_preview TEXT,
            FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS email_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            message_id TEXT,
            subject TEXT,
            sender TEXT,
            recipients TEXT,
            cc TEXT,
            email_date TEXT,
            has_attachments INTEGER,
            attachment_count INTEGER,
            FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
        )
        """,
    ]:
        cur.execute(ddl)
    conn.commit()


def recreate_indexes(conn: sqlite3.Connection):
    cur = conn.cursor()
    for stmt in [
        "CREATE INDEX IF NOT EXISTS idx_files_volume ON files(volume)",
        "CREATE INDEX IF NOT EXISTS idx_files_extension ON files(extension)",
        "CREATE INDEX IF NOT EXISTS idx_files_hash ON files(file_hash)",
        "CREATE INDEX IF NOT EXISTS idx_files_relpath ON files(relpath)",
        "CREATE INDEX IF NOT EXISTS idx_image_date_taken ON image_metadata(date_taken)",
        "CREATE INDEX IF NOT EXISTS idx_image_location ON image_metadata(latitude, longitude)",
        "CREATE INDEX IF NOT EXISTS idx_skipped_run_timestamp ON skipped_files(run_timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_removed_hash ON removed_duplicates(original_hash)",
        "CREATE INDEX IF NOT EXISTS idx_removed_date ON removed_duplicates(removal_date)",
        "CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_audit_operation ON audit_log(operation)",
        "CREATE INDEX IF NOT EXISTS idx_audit_file_path ON audit_log(file_path)",
    ]:
        cur.execute(stmt)


def verify_migration(conn: sqlite3.Connection, expected_files: int):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM files")
    files_count = cur.fetchone()[0]
    if files_count != expected_files:
        raise RuntimeError(f"files count mismatch: expected {expected_files}, got {files_count}")

    cur.execute("SELECT COUNT(*) FROM volumes")
    if cur.fetchone()[0] != 1:
        raise RuntimeError("expected exactly one volume row")

    cur.execute("SELECT COUNT(*) FROM files WHERE volume != 'photo'")
    if cur.fetchone()[0] != 0:
        raise RuntimeError("unexpected non-photo volume values after migration")

    cur.execute("SELECT COUNT(*) FROM files WHERE relpath LIKE '/%' OR relpath LIKE '%\\\\%'")
    bad = cur.fetchone()[0]
    if bad:
        raise RuntimeError(f"{bad} relpaths still look like absolute paths")

    cur.execute("SELECT COUNT(*) FROM image_metadata")
    img_meta = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM thumbnails")
    thumbs = cur.fetchone()[0]
    print(f"Verified: {files_count} files, {img_meta} image_metadata, {thumbs} thumbnails")


def migrate_database(
    db_path: str,
    volume_name: str,
    mount_path: str,
    src_root: str,
    old_mount: Optional[str] = None,
    backup: bool = True,
    dry_run: bool = False,
):
    if not os.path.exists(db_path):
        raise FileNotFoundError(db_path)

    if is_v2_schema(sqlite3.connect(db_path)):
        print(f"Already v2 schema: {db_path}")
        return

    backup_path = None
    if backup and not dry_run:
        backup_path = f"{db_path}.v1.{datetime.now().strftime('%Y%m%d-%H%M%S')}.bak"
        print(f"Backing up to {backup_path}")
        shutil.copy2(db_path, backup_path)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(files)")
        file_cols = {row[1] for row in cur.fetchall()}
        if 'fullpath' not in file_cols:
            raise ValueError("files table has no fullpath column; unexpected schema")

        cur.execute("SELECT COUNT(*) FROM files")
        expected_files = cur.fetchone()[0]

        detected_mount = old_mount or detect_old_mount(conn)
        mount_norm = normalize_path(mount_path)
        src_root_norm = normalize_src_root(src_root)
        vol = normalize_volume_name(volume_name)

        print(f"Database: {db_path}")
        print(f"Files to migrate: {expected_files}")
        print(f"Old mount prefix: {detected_mount}")
        print(f"New volume: {vol}")
        print(f"New mount_path: {mount_norm}")
        print(f"New src_root: {src_root_norm}")

        if dry_run:
            cur.execute("SELECT fullpath FROM files LIMIT 3")
            for (fp,) in cur.fetchall():
                rel = fullpath_to_relpath(fp, detected_mount)
                resolved = resolve_file_path(mount_norm, rel)
                print(f"  {fp}")
                print(f"    -> relpath: {rel}")
                print(f"    -> resolves: {resolved}")
            print("Dry run complete (no changes written).")
            return

        ensure_v2_auxiliary_tables(conn)
        set_volume(conn, vol, src_root_norm, mount_norm)

        files_migrated = migrate_files_table(conn, detected_mount, dry_run=False)
        skipped_migrated = migrate_skipped_files(conn, detected_mount, dry_run=False)
        removed_migrated = migrate_removed_duplicates(conn, detected_mount, mount_norm, dry_run=False)
        audit_updated = migrate_audit_log(conn, detected_mount, mount_norm, dry_run=False)
        recreate_indexes(conn)

        conn.commit()
        verify_migration(conn, expected_files)

        print("Migration complete:")
        print(f"  files: {files_migrated}")
        print(f"  skipped_files: {skipped_migrated}")
        print(f"  removed_duplicates: {removed_migrated}")
        print(f"  audit_log rows updated: {audit_updated}")
        if backup_path:
            print(f"  backup: {backup_path}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Migrate v1 media index DB to v2 volume schema")
    parser.add_argument("--db-path", default="files.db", help="Path to SQLite database")
    parser.add_argument("--volume", default="PHOTO", help="Volume name (case-insensitive)")
    parser.add_argument("--mount", default=r"p:\\", help="Local mount path")
    parser.add_argument("--src-root", default="/volume1/photo", help="NAS source root path")
    parser.add_argument("--old-mount", help="Old absolute mount prefix (default: auto-detect)")
    parser.add_argument("--no-backup", action="store_true", help="Skip backup copy")
    parser.add_argument("--dry-run", action="store_true", help="Preview conversion only")
    args = parser.parse_args()

    migrate_database(
        db_path=args.db_path,
        volume_name=args.volume,
        mount_path=args.mount,
        src_root=args.src_root,
        old_mount=args.old_mount,
        backup=not args.no_backup,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
