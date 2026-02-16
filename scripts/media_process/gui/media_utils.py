#!/usr/bin/env python3
"""
Shared utilities for media processing scripts
"""

import hashlib
import mimetypes
import sqlite3


def create_database_schema(conn: sqlite3.Connection):
    """Create the database schema for media indexing."""
    cursor = conn.cursor()
    
    # Main files table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            volume TEXT NOT NULL,
            fullpath TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            created_date TEXT,
            modified_date TEXT NOT NULL,
            size INTEGER NOT NULL,
            mime_type TEXT,
            extension TEXT,
            file_hash TEXT,
            indexed_date TEXT NOT NULL,
            UNIQUE(volume, fullpath)
        )
    """)
    
    # Image metadata table
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
    
    # Video metadata table
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
    
    # Thumbnails table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS thumbnails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            thumbnail_data BLOB NOT NULL,
            thumbnail_width INTEGER,
            thumbnail_height INTEGER,
            FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
        )
    """)
    
    # Skipped files table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skipped_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_timestamp TEXT NOT NULL,
            fullpath TEXT NOT NULL,
            skip_reason TEXT NOT NULL,
            volume TEXT,
            file_size INTEGER,
            recorded_date TEXT NOT NULL
        )
    """)
    
    # Audit table for tracking all operations
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
    
    # Create indexes for faster queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_volume ON files(volume)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_extension ON files(extension)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_hash ON files(file_hash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_image_date_taken ON image_metadata(date_taken)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_image_location ON image_metadata(latitude, longitude)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_skipped_run_timestamp ON skipped_files(run_timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_operation ON audit_log(operation)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_file_path ON audit_log(file_path)")
    
    conn.commit()


def calculate_file_hash(filepath: str, chunk_size: int = 8192) -> str:
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
    """Get MIME type of a file."""
    mime_type, _ = mimetypes.guess_type(filepath)
    return mime_type or 'application/octet-stream'


def is_image_file(mime_type: str, extension: str = '') -> bool:
    """Check if file is an image (including RAW formats)."""
    # Standard image MIME types
    if mime_type and mime_type.startswith('image/'):
        return True
    
    # RAW image formats (MIME type detection often fails for these)
    raw_extensions = {
        '.cr2', '.cr3', '.nef', '.arw', '.dng', '.orf', '.rw2', 
        '.pef', '.srw', '.raf', '.raw', '.rwl', '.mrw', '.erf', 
        '.3fr', '.dcr', '.kdc', '.mef', '.mos', '.nrw', '.ptx', 
        '.r3d', '.x3f', '.iiq'
    }
    return extension.lower() in raw_extensions


def is_video_file(mime_type: str) -> bool:
    """Check if file is a video."""
    return mime_type.startswith('video/')


def log_audit(conn: sqlite3.Connection, operation: str, file_path: str,
              success: bool = True, error_message: str = None,
              file_hash: str = None, old_path: str = None, new_path: str = None,
              old_volume: str = None, new_volume: str = None,
              metadata_before: str = None, metadata_after: str = None,
              additional_info: str = None):
    """Log an operation to the audit table.
    
    Args:
        conn: Database connection
        operation: Type of operation (delete, move, update_exif, index, etc.)
        file_path: Path to the file being operated on
        success: Whether the operation succeeded
        error_message: Error message if operation failed
        file_hash: File hash for tracking
        old_path: Original path (for move operations)
        new_path: New path (for move operations)
        old_volume: Original volume (for move operations)
        new_volume: New volume (for move operations)
        metadata_before: JSON string of metadata before operation
        metadata_after: JSON string of metadata after operation
        additional_info: Any additional information
    """
    from datetime import datetime
    
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
        additional_info
    ))
    conn.commit()
