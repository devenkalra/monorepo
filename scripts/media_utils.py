#!/usr/bin/env python3
"""Shared utilities for media indexing and processing."""

import hashlib
import mimetypes
import os
import re
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Tuple


RAW_IMAGE_EXTENSIONS = {
    '.cr2', '.cr3', '.nef', '.arw', '.dng', '.orf', '.rw2',
    '.pef', '.srw', '.raf', '.raw', '.rwl', '.mrw', '.erf',
    '.3fr', '.dcr', '.kdc', '.mef', '.mos', '.nrw', '.ptx',
    '.r3d', '.x3f', '.iiq',
}

OFFICE_EXTENSIONS = {
    '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.odt', '.ods', '.odp', '.rtf',
}

DOCUMENT_EXTENSIONS = {'.pdf', '.txt'} | OFFICE_EXTENSIONS

EMAIL_EXTENSIONS = {'.eml'}

# SQL expression: normalize EXIF date_taken (2026:01:09 ...) to YYYYMMDD
SQL_DATE_TAKEN_YMD = "REPLACE(REPLACE(SUBSTR(im.date_taken, 1, 10), ':', '-'), '-', '')"


def sql_file_date_ymd(field: str) -> str:
    """SQL expression to normalize an ISO/filesystem date column to YYYYMMDD."""
    return f"REPLACE(REPLACE(SUBSTR({field}, 1, 10), ':', '-'), '-', '')"


def normalize_date_filter(value: str) -> str:
    """Normalize a user date filter to YYYYMMDD for comparable matching."""
    value = value.strip()
    if not value:
        raise ValueError('empty date filter')
    for sep in ('T', ' '):
        if sep in value:
            value = value.split(sep, 1)[0]
    digits = re.sub(r'\D', '', value)
    if len(digits) >= 8:
        return digits[:8]
    raise ValueError(f'invalid date filter (use YYYYMMDD or YYYY-MM-DD): {value!r}')


def normalize_volume_name(name: str) -> str:
    """Return canonical case-insensitive volume name (lowercase)."""
    return name.strip().lower()


def normalize_path(path: str) -> str:
    """Normalize a local filesystem path for consistent comparisons."""
    return os.path.normpath(os.path.abspath(path))


def clean_mount_path(path: str) -> str:
    """Normalize a volume mount path, tolerating shell quoting artifacts.

    PowerShell treats ``"d:\\"`` as an escaped closing quote, often passing
    ``d:\\"`` to the process. Also accepts bare ``d:`` for a drive root.
    """
    cleaned = path.strip()
    while cleaned and cleaned[0] in '"\'':
        cleaned = cleaned[1:]
    while cleaned and cleaned[-1] in '"\'':
        cleaned = cleaned[:-1]
    cleaned = cleaned.strip()
    if len(cleaned) == 2 and cleaned[1] == ':':
        cleaned += os.sep
    return cleaned


def normalize_src_root(path: str) -> str:
    """Normalize a canonical source-root path for portable storage."""
    cleaned = path.strip().replace('\\', '/')
    while '//' in cleaned:
        cleaned = cleaned.replace('//', '/')
    return cleaned.rstrip('/')


def to_storage_relpath(filepath: str, root: str) -> str:
    """Convert an absolute filepath to a portable relative path from root."""
    rel = os.path.relpath(normalize_path(filepath), normalize_path(root))
    return rel.replace('\\', '/')


def resolve_file_path(mount_path: str, relpath: str) -> str:
    """Resolve a stored relpath to an absolute path on this machine."""
    return normalize_path(os.path.join(mount_path, relpath.replace('/', os.sep)))


def create_database_schema(conn: sqlite3.Connection):
    """Create the database schema for media indexing (v2)."""
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS volumes (
            name TEXT PRIMARY KEY,
            src_root TEXT NOT NULL,
            mount_path TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS image_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            raw_exif TEXT,
            width INTEGER,
            height INTEGER,
            date_taken TEXT,
            exposure_time TEXT,
            focal_length REAL,
            focal_length_35mm INTEGER,
            f_number REAL,
            camera_make TEXT,
            camera_model TEXT,
            lens_model TEXT,
            iso INTEGER,
            latitude REAL,
            longitude REAL,
            altitude REAL,
            city TEXT,
            state TEXT,
            country TEXT,
            country_code TEXT,
            coverage TEXT,
            caption TEXT,
            keywords TEXT,
            FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS video_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            width INTEGER,
            height INTEGER,
            frame_rate REAL,
            video_codec TEXT,
            audio_channels INTEGER,
            audio_bit_rate_kbps REAL,
            duration_seconds REAL,
            FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
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
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS document_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            page_count INTEGER,
            title TEXT,
            author TEXT,
            text_preview TEXT,
            FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
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
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS thumbnails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            thumbnail_data BLOB NOT NULL,
            thumbnail_width INTEGER,
            thumbnail_height INTEGER,
            created_at TEXT,
            FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
        )
    """)

    _ensure_thumbnail_schema(cursor)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skipped_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_timestamp TEXT NOT NULL,
            relpath TEXT NOT NULL,
            skip_reason TEXT NOT NULL,
            volume TEXT,
            file_size INTEGER,
            recorded_date TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            operation TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_hash TEXT,
            old_path TEXT,
            new_path TEXT,
            old_volume TEXT,
            new_volume TEXT,
            metadata_before TEXT,
            metadata_after TEXT,
            success INTEGER NOT NULL,
            error_message TEXT,
            additional_info TEXT
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_volume ON files(volume)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_extension ON files(extension)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_hash ON files(file_hash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_relpath ON files(relpath)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_image_date_taken ON image_metadata(date_taken)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_image_location ON image_metadata(latitude, longitude)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_skipped_run_timestamp ON skipped_files(run_timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_operation ON audit_log(operation)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_file_path ON audit_log(file_path)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_thumbnails_created_at ON thumbnails(created_at)"
    )

    conn.commit()


def _ensure_thumbnail_schema(cursor: sqlite3.Cursor):
    """Add thumbnail columns introduced after initial schema release."""
    cursor.execute("PRAGMA table_info(thumbnails)")
    columns = {row[1] for row in cursor.fetchall()}
    if 'created_at' not in columns:
        cursor.execute("ALTER TABLE thumbnails ADD COLUMN created_at TEXT")


def set_volume(conn: sqlite3.Connection, name: str, src_root: str, mount_path: str) -> Dict:
    """Create or update a volume mapping."""
    canonical = normalize_volume_name(name)
    src_root_norm = normalize_src_root(src_root)
    mount_path_norm = normalize_path(clean_mount_path(mount_path))
    updated_at = datetime.now().isoformat()

    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO volumes (name, src_root, mount_path, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            src_root = excluded.src_root,
            mount_path = excluded.mount_path,
            updated_at = excluded.updated_at
    """, (canonical, src_root_norm, mount_path_norm, updated_at))
    conn.commit()

    return {
        'name': canonical,
        'src_root': src_root_norm,
        'mount_path': mount_path_norm,
        'updated_at': updated_at,
    }


def get_volume(conn: sqlite3.Connection, name: str) -> Optional[Dict]:
    """Look up a volume by case-insensitive name."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name, src_root, mount_path, updated_at FROM volumes WHERE name = ?",
        (normalize_volume_name(name),),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return {
        'name': row[0],
        'src_root': row[1],
        'mount_path': row[2],
        'updated_at': row[3],
    }


def list_volumes(conn: sqlite3.Connection) -> List[Dict]:
    """Return all registered volumes."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name, src_root, mount_path, updated_at FROM volumes ORDER BY name"
    )
    return [
        {'name': row[0], 'src_root': row[1], 'mount_path': row[2], 'updated_at': row[3]}
        for row in cursor.fetchall()
    ]


def find_files_by_hash(conn: sqlite3.Connection, file_hash: str) -> List[Dict]:
    """Find all indexed files with a matching hash."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, volume, relpath, name, created_date, modified_date,
               size, mime_type, extension, indexed_date
        FROM files
        WHERE file_hash = ?
        ORDER BY indexed_date DESC
    """, (file_hash,))

    results = []
    for row in cursor.fetchall():
        volume = get_volume(conn, row[1])
        mount_path = volume['mount_path'] if volume else ''
        results.append({
            'id': row[0],
            'volume': row[1],
            'relpath': row[2],
            'fullpath': resolve_file_path(mount_path, row[2]) if mount_path else row[2],
            'name': row[3],
            'created_date': row[4],
            'modified_date': row[5],
            'size': row[6],
            'mime_type': row[7],
            'extension': row[8],
            'indexed_date': row[9],
        })
    return results


def find_file_by_hash(conn: sqlite3.Connection, file_hash: str) -> Optional[Dict]:
    """Return the first indexed file with a matching hash."""
    matches = find_files_by_hash(conn, file_hash)
    return matches[0] if matches else None


def _file_row_to_dict(row: tuple, conn: sqlite3.Connection) -> Dict:
    """Convert a files table row into a dictionary with resolved path."""
    volume = get_volume(conn, row[1])
    mount_path = volume['mount_path'] if volume else ''
    resolved = resolve_file_path(mount_path, row[2]) if mount_path else row[2]
    return {
        'id': row[0],
        'volume': row[1],
        'relpath': row[2],
        'fullpath': resolved,
        'resolved_path': resolved,
        'name': row[3],
        'created_date': row[4],
        'modified_date': row[5],
        'size': row[6],
        'mime_type': row[7],
        'extension': row[8],
        'file_hash': row[9],
        'indexed_date': row[10],
    }


def lookup_file_by_volume_relpath(conn: sqlite3.Connection, volume_name: str,
                                  relpath: str) -> Optional[Dict]:
    """Find a file by volume name and stored relative path."""
    cursor = conn.cursor()
    normalized_relpath = relpath.replace('\\', '/').lstrip('/')
    cursor.execute("""
        SELECT id, volume, relpath, name, created_date, modified_date,
               size, mime_type, extension, file_hash, indexed_date
        FROM files
        WHERE volume = ? AND relpath = ?
    """, (normalize_volume_name(volume_name), normalized_relpath))
    row = cursor.fetchone()
    return _file_row_to_dict(row, conn) if row else None


def lookup_file_by_abs_path(conn: sqlite3.Connection, abs_path: str) -> Optional[Dict]:
    """Find an indexed file from an absolute path on this machine."""
    abs_path = normalize_path(abs_path)
    for volume in list_volumes(conn):
        mount_path = normalize_path(volume['mount_path'])
        try:
            rel = to_storage_relpath(abs_path, mount_path)
        except ValueError:
            continue
        if rel.startswith('..'):
            continue
        record = lookup_file_by_volume_relpath(conn, volume['name'], rel)
        if record:
            return record
    return None


def lookup_file_by_id(conn: sqlite3.Connection, file_id: int) -> Optional[Dict]:
    """Find a file record by database id."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, volume, relpath, name, created_date, modified_date,
               size, mime_type, extension, file_hash, indexed_date
        FROM files
        WHERE id = ?
    """, (file_id,))
    row = cursor.fetchone()
    return _file_row_to_dict(row, conn) if row else None


def relpath_for_abs_path(conn: sqlite3.Connection, volume_name: str, abs_path: str) -> str:
    """Compute the stored relpath for a file under a volume mount."""
    volume = get_volume(conn, volume_name)
    if not volume:
        raise ValueError(f"Volume not registered: {volume_name}")
    return to_storage_relpath(abs_path, volume['mount_path'])


def delete_file_metadata(conn: sqlite3.Connection, file_id: int):
    """Delete all metadata rows associated with a file."""
    cursor = conn.cursor()
    for table in METADATA_TABLES:
        cursor.execute(f"DELETE FROM {table} WHERE file_id = ?", (file_id,))
    cursor.execute("DELETE FROM thumbnails WHERE file_id = ?", (file_id,))


def insert_thumbnail(conn: sqlite3.Connection, file_id: int, thumbnail_data: bytes,
                     thumbnail_width: int, thumbnail_height: int,
                     created_at: Optional[str] = None) -> int:
    """Insert a thumbnail row and return its id."""
    cursor = conn.cursor()
    _ensure_thumbnail_schema(cursor)
    if created_at is None:
        created_at = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO thumbnails (file_id, thumbnail_data, thumbnail_width, thumbnail_height, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (file_id, thumbnail_data, thumbnail_width, thumbnail_height, created_at))
    return cursor.lastrowid


def calculate_file_hash(filepath: str, chunk_size: int = 8192) -> Optional[str]:
    """Calculate SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(chunk_size), b''):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    except Exception as e:
        print(f"Error calculating hash for {filepath}: {e}")
        return None


def get_mime_type(filepath: str) -> str:
    """Get MIME type of a file, with octet-stream fallback for legacy callers."""
    return guess_mime_type(filepath) or 'application/octet-stream'


def guess_mime_type(filepath: str) -> Optional[str]:
    """Guess MIME type from a path or filename; returns None when unknown."""
    mime_type, _ = mimetypes.guess_type(filepath)
    return mime_type


def is_image_file(mime_type: str, extension: str = '') -> bool:
    """Check if file is an image (including RAW formats)."""
    if mime_type and mime_type.startswith('image/'):
        return True
    return extension.lower() in RAW_IMAGE_EXTENSIONS


def is_video_file(mime_type: str) -> bool:
    """Check if file is a video."""
    return bool(mime_type and mime_type.startswith('video/'))


def is_audio_file(mime_type: str, extension: str = '') -> bool:
    """Check if file is audio."""
    if mime_type and mime_type.startswith('audio/'):
        return True
    return extension.lower() in {'.mp3', '.flac', '.wav', '.aac', '.m4a', '.ogg', '.wma', '.opus'}


def is_document_file(mime_type: str, extension: str = '') -> bool:
    """Check if file is a supported document."""
    ext = extension.lower()
    if ext in DOCUMENT_EXTENSIONS:
        return True
    if mime_type in {
        'application/pdf',
        'text/plain',
        'text/markdown',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-powerpoint',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'application/vnd.oasis.opendocument.text',
        'application/vnd.oasis.opendocument.spreadsheet',
        'application/vnd.oasis.opendocument.presentation',
        'application/rtf',
    }:
        return True
    return mime_type.startswith('text/') and ext == '.txt'


def is_email_file(mime_type: str, extension: str = '') -> bool:
    """Check if file is an email message."""
    if extension.lower() in EMAIL_EXTENSIONS:
        return True
    return mime_type in {'message/rfc822', 'application/vnd.ms-outlook'}


def get_indexable_file_type(mime_type: str, extension: str = '') -> Optional[str]:
    """Return the indexable file category, or None if unsupported."""
    if is_image_file(mime_type, extension):
        return 'image'
    if is_video_file(mime_type):
        return 'video'
    if is_audio_file(mime_type, extension):
        return 'audio'
    if is_document_file(mime_type, extension):
        return 'document'
    if is_email_file(mime_type, extension):
        return 'email'
    return None


METADATA_TABLES = (
    'image_metadata',
    'video_metadata',
    'audio_metadata',
    'document_metadata',
    'email_metadata',
)

UNKNOWN_MIME_TYPE = 'UNKNOWN'


def classify_file_type(mime_type: str, extension: str = '') -> str:
    """Return file category for cataloging, including ``unknown`` for other types."""
    return get_indexable_file_type(mime_type, extension) or 'unknown'


def catalog_mime_type(mime_type: str = '', extension: str = '', filepath: str = '') -> str:
    """Return MIME type stored in the files table.

    Uses ``mimetypes`` guessing from the filepath and extension where possible.
    Falls back to a provided detected MIME type, then ``UNKNOWN``.
    """
    for source in (filepath, f'file{extension}' if extension else ''):
        if source:
            guessed = guess_mime_type(source)
            if guessed:
                return guessed
    if mime_type and mime_type not in {UNKNOWN_MIME_TYPE, 'application/octet-stream'}:
        return mime_type
    return UNKNOWN_MIME_TYPE


def has_rich_metadata(file_type: str) -> bool:
    """True when the file type has type-specific metadata/thumbnail extraction."""
    return file_type != 'unknown'


def log_audit(conn: sqlite3.Connection, operation: str, file_path: str,
              success: bool = True, error_message: str = None,
              file_hash: str = None, old_path: str = None, new_path: str = None,
              old_volume: str = None, new_volume: str = None,
              metadata_before: str = None, metadata_after: str = None,
              additional_info: str = None):
    """Log an operation to the audit table."""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO audit_log (
            timestamp, operation, file_path, file_hash,
            old_path, new_path, old_volume, new_volume,
            metadata_before, metadata_after,
            success, error_message, additional_info
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().isoformat(),
        operation,
        file_path,
        file_hash,
        old_path,
        new_path,
        old_volume,
        new_volume,
        metadata_before,
        metadata_after,
        1 if success else 0,
        error_message,
        additional_info,
    ))
    conn.commit()


try:
    from PIL import Image, ImageOps
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = None  # type: ignore
    ImageOps = None  # type: ignore


def prepare_image_for_thumbnail(img: "Image.Image") -> "Image.Image":
    """Apply EXIF orientation and convert to RGB for JPEG thumbnails."""
    if ImageOps is not None:
        img = ImageOps.exif_transpose(img)
    if img.mode == 'RGB':
        return img
    if img.mode == 'RGBA':
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        return background
    return img.convert('RGB')


def thumbnail_jpeg_dimensions(blob: bytes) -> Tuple[int, int]:
    """Return pixel width and height of a JPEG thumbnail blob."""
    if not PIL_AVAILABLE or not blob:
        return 0, 0
    try:
        import io
        with Image.open(io.BytesIO(blob)) as img:
            return img.size
    except Exception:
        return 0, 0


def normalize_thumbnail_blob(blob: bytes) -> Tuple[bytes, int, int]:
    """Apply EXIF orientation to stored JPEG bytes; return (jpeg, width, height)."""
    if not PIL_AVAILABLE or not blob:
        return blob, 0, 0
    try:
        import io
        with Image.open(io.BytesIO(blob)) as img:
            img = prepare_image_for_thumbnail(img)
            width, height = img.size
            out = io.BytesIO()
            img.save(out, format='JPEG', quality=90)
            return out.getvalue(), width, height
    except Exception:
        return blob, 0, 0
