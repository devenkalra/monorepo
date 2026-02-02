#!/usr/bin/env python3
"""move_media.py - Move media files and update database with new locations.

This script moves media files to a new destination and updates the database
with the new paths and metadata, similar to index_media.py but for moving
existing files.
"""

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

# Import shared utilities
try:
    from media_utils import (
        create_database_schema,
        calculate_file_hash,
        get_mime_type,
        is_image_file,
        is_video_file
    )
except ImportError:
    print("Error: media_utils module not found", file=sys.stderr)
    print("Make sure media_utils.py is in the same directory", file=sys.stderr)
    sys.exit(1)

# Import audit utilities
try:
    from audit_utils import (
        get_audit_logger,
        log_session_start,
        log_session_end,
        log_file_moved,
        log_skip,
        log_error
    )
except ImportError:
    print("Error: audit_utils module not found", file=sys.stderr)
    print("Make sure audit_utils.py is in the same directory", file=sys.stderr)
    sys.exit(1)

# Import index_media functions for metadata extraction
try:
    import sys
    import importlib.util
    spec = importlib.util.spec_from_file_location("index_media", 
                                                   os.path.join(os.path.dirname(__file__), "index_media.py"))
    index_media = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(index_media)
    
    get_exif_data = index_media.get_exif_data
    normalize_exif_data = index_media.normalize_exif_data
    get_video_metadata = index_media.get_video_metadata
    generate_thumbnail = index_media.generate_thumbnail
except Exception as e:
    print(f"Error: Could not import index_media.py functions: {e}", file=sys.stderr)
    print("Make sure index_media.py is in the same directory", file=sys.stderr)
    sys.exit(1)


def move_file(source_path: str, dest_dir: str, dry_run: bool, verbose: int) -> Tuple[bool, str]:
    """Move a file to destination directory.
    
    Args:
        source_path: Source file path
        dest_dir: Destination directory
        dry_run: If True, don't actually move the file
        verbose: Verbosity level
    
    Returns:
        Tuple of (success, destination_path)
    """
    try:
        # Get filename
        filename = os.path.basename(source_path)
        dest_path = os.path.join(dest_dir, filename)
        
        # Check if destination already exists
        if os.path.exists(dest_path):
            # Generate unique name
            base, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(dest_path):
                new_filename = f"{base}_{counter}{ext}"
                dest_path = os.path.join(dest_dir, new_filename)
                counter += 1
            
            if verbose >= 2:
                print(f"  Destination exists, using: {os.path.basename(dest_path)}")
        
        if dry_run:
            if verbose >= 1:
                print(f"  [DRY RUN] Would move to: {dest_path}")
            return True, dest_path
        else:
            # Create destination directory if needed
            os.makedirs(dest_dir, exist_ok=True)
            
            # Move the file
            shutil.move(source_path, dest_path)
            
            if verbose >= 2:
                print(f"  ✓ Moved to: {dest_path}")
            
            return True, dest_path
            
    except Exception as e:
        print(f"  Error moving file: {e}", file=sys.stderr)
        return False, ""


def update_or_insert_file(conn: sqlite3.Connection, old_path: str, new_path: str,
                          volume: str, verbose: int, dry_run: bool) -> Tuple[str, int]:
    """Update existing file record or insert new one.
    
    Checks if the file exists in database by old_path (source path):
    - If found: Updates the record with new path (file was moved)
    - If not found: Inserts new record (new file to database)
    
    Note: Multiple files with same hash/content can exist at different paths.
    Each unique path gets its own database record.
    
    Args:
        conn: Database connection
        old_path: Original file path (before move)
        new_path: New file path (after move)
        volume: Volume tag
        verbose: Verbosity level
        dry_run: If True, don't commit changes
    
    Returns:
        Tuple of (action, file_id) where action is 'updated', 'inserted', or 'error'
    """
    cursor = conn.cursor()
    
    try:
        # Check if file exists in database by old path
        cursor.execute("SELECT id FROM files WHERE fullpath = ?", (old_path,))
        existing = cursor.fetchone()
        
        if existing:
            file_id = existing[0]
            
            # Update the record with new path
            if not dry_run:
                # Get modified date in ISO format
                modified_date = datetime.fromtimestamp(os.path.getmtime(new_path)).isoformat()
                
                cursor.execute("""
                    UPDATE files 
                    SET fullpath = ?, 
                        volume = ?,
                        name = ?,
                        modified_date = ?,
                        indexed_date = ?
                    WHERE id = ?
                """, (
                    new_path,
                    volume,
                    os.path.basename(new_path),
                    modified_date,
                    datetime.now().isoformat(),
                    file_id
                ))
            
            if verbose >= 2:
                print(f"  Updated database record (ID: {file_id})")
            
            return 'updated', file_id
        else:
            # File not in database, insert new record
            # Get file info
            stat = os.stat(new_path)
            mime_type = get_mime_type(new_path)
            extension = os.path.splitext(new_path)[1].lower()
            file_hash = calculate_file_hash(new_path)
            
            # Get dates in ISO format
            modified_date = datetime.fromtimestamp(stat.st_mtime).isoformat()
            try:
                created_date = datetime.fromtimestamp(stat.st_ctime).isoformat()
            except Exception:
                created_date = modified_date
            
            if not dry_run:
                cursor.execute("""
                    INSERT INTO files (
                        volume, fullpath, name, created_date, modified_date,
                        size, mime_type, extension, file_hash, indexed_date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    volume,
                    new_path,
                    os.path.basename(new_path),
                    created_date,
                    modified_date,
                    stat.st_size,
                    mime_type,
                    extension,
                    file_hash,
                    datetime.now().isoformat()
                ))
                file_id = cursor.lastrowid
            else:
                file_id = -1
            
            if verbose >= 2:
                print(f"  Inserted new database record (ID: {file_id})")
            
            return 'inserted', file_id
            
    except Exception as e:
        print(f"  Error updating database: {e}", file=sys.stderr)
        return 'error', -1


def process_metadata(conn: sqlite3.Connection, file_id: int, filepath: str,
                     mime_type: str, extension: str, verbose: int, dry_run: bool):
    """Process and store metadata for a file.
    
    Args:
        conn: Database connection
        file_id: File ID in database
        filepath: Path to file
        mime_type: MIME type of file
        extension: File extension
        verbose: Verbosity level
        dry_run: If True, don't commit changes
    """
    if dry_run:
        return
    
    cursor = conn.cursor()
    
    try:
        # Process based on file type
        if is_image_file(mime_type, extension):
            # Get EXIF data
            exif_data = get_exif_data(filepath)
            
            # Store raw EXIF as JSON
            raw_exif_json = json.dumps(exif_data) if exif_data else None
            
            # Normalize EXIF data
            normalized = normalize_exif_data(exif_data)
            
            # Delete existing image metadata
            cursor.execute("DELETE FROM image_metadata WHERE file_id = ?", (file_id,))
            
            # Insert new image metadata
            cursor.execute("""
                INSERT INTO image_metadata (
                    file_id, raw_exif, width, height, date_taken,
                    exposure_time, focal_length, focal_length_35mm, f_number,
                    camera_make, camera_model, lens_model, iso,
                    latitude, longitude, altitude,
                    city, state, country, country_code, coverage,
                    caption, keywords
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                file_id,
                raw_exif_json,
                normalized.get('width'),
                normalized.get('height'),
                normalized.get('date_taken'),
                normalized.get('exposure_time'),
                normalized.get('focal_length'),
                normalized.get('focal_length_35mm'),
                normalized.get('f_number'),
                normalized.get('camera_make'),
                normalized.get('camera_model'),
                normalized.get('lens_model'),
                normalized.get('iso'),
                normalized.get('latitude'),
                normalized.get('longitude'),
                normalized.get('altitude'),
                normalized.get('city'),
                normalized.get('state'),
                normalized.get('country'),
                normalized.get('country_code'),
                normalized.get('coverage'),
                normalized.get('caption'),
                normalized.get('keywords')
            ))
            
            if verbose >= 3:
                print(f"  Stored image metadata")
            
        elif is_video_file(mime_type):
            # Get video metadata
            video_meta = get_video_metadata(filepath)
            
            # Delete existing video metadata
            cursor.execute("DELETE FROM video_metadata WHERE file_id = ?", (file_id,))
            
            # Insert new video metadata
            if video_meta:
                cursor.execute("""
                    INSERT INTO video_metadata (
                        file_id, width, height, frame_rate, video_codec,
                        audio_channels, audio_bit_rate_kbps, duration_seconds
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    file_id,
                    video_meta.get('width'),
                    video_meta.get('height'),
                    video_meta.get('frame_rate'),
                    video_meta.get('video_codec'),
                    video_meta.get('audio_channels'),
                    video_meta.get('audio_bit_rate_kbps'),
                    video_meta.get('duration_seconds')
                ))
                
                if verbose >= 3:
                    print(f"  Stored video metadata")
        
        # Generate and store thumbnail
        thumbnail_data = generate_thumbnail(filepath, mime_type, extension)
        if thumbnail_data:
            # Delete existing thumbnail
            cursor.execute("DELETE FROM thumbnails WHERE file_id = ?", (file_id,))
            
            # Insert new thumbnail
            cursor.execute("""
                INSERT INTO thumbnails (file_id, thumbnail_data, thumbnail_width, thumbnail_height)
                VALUES (?, ?, ?, ?)
            """, (file_id, thumbnail_data, 200, 200))
            
            if verbose >= 3:
                print(f"  Generated thumbnail")
                
    except Exception as e:
        if verbose >= 1:
            print(f"  Warning: Could not process metadata: {e}", file=sys.stderr)


def check_destination_file(dest_path: str, source_hash: str, verbose: int) -> Tuple[bool, str]:
    """Check if file exists in destination and if hash matches.
    
    Args:
        dest_path: Destination file path
        source_hash: Hash of source file
        verbose: Verbosity level
    
    Returns:
        Tuple of (should_skip, skip_reason)
    """
    if not os.path.exists(dest_path):
        return False, ""
    
    # File exists in destination
    dest_hash = calculate_file_hash(dest_path)
    
    if dest_hash == source_hash:
        if verbose >= 1:
            print(f"  Skipping: File already exists in destination with same hash")
        return True, "destination_exists_same_hash"
    else:
        if verbose >= 1:
            print(f"  Skipping: File exists in destination with different hash")
        return True, "destination_exists_different_hash"


def check_database_record(conn: sqlite3.Connection, dest_path: str, source_hash: str,
                         verbose: int) -> Tuple[bool, int, str]:
    """Check if file exists in database at destination path.
    
    Args:
        conn: Database connection
        dest_path: Destination file path
        source_hash: Hash of source file
        verbose: Verbosity level
    
    Returns:
        Tuple of (exists, file_id, match_type)
        match_type: 'exact_match', 'path_match_different_hash', or ''
    """
    cursor = conn.cursor()
    
    # Check by destination path only
    cursor.execute("SELECT id, file_hash FROM files WHERE fullpath = ?", (dest_path,))
    result = cursor.fetchone()
    
    if result:
        file_id, db_hash = result
        if db_hash == source_hash:
            return True, file_id, 'exact_match'
        else:
            return True, file_id, 'path_match_different_hash'
    
    # Check if file with same hash exists elsewhere (informational only)
    cursor.execute("SELECT COUNT(*), fullpath FROM files WHERE file_hash = ? LIMIT 1", (source_hash,))
    result = cursor.fetchone()
    
    if result and result[0] > 0:
        count, existing_path = result[0], result[1]
        if verbose >= 2:
            print(f"  Note: {count} file(s) with same content exist in database")
            if existing_path:
                print(f"        Example: {existing_path}")
    
    return False, -1, ''


def process_file(source_path: str, dest_dir: str, volume: str, conn: sqlite3.Connection,
                verbose: int, dry_run: bool, audit_log) -> Tuple[str, str]:
    """Process a single file: move and update database.
    
    Args:
        source_path: Source file path
        dest_dir: Destination directory
        volume: Volume tag
        conn: Database connection
        verbose: Verbosity level
        dry_run: If True, don't make changes
    
    Returns:
        Tuple of (status, message)
    """
    if verbose >= 1:
        print(f"\nProcessing: {source_path}")
    
    # Check if source exists
    if not os.path.exists(source_path):
        if verbose >= 1:
            print(f"  ✗ Source file not found")
        log_error(audit_log, 'file_not_found', f"Source file not found: {source_path}")
        return 'error', 'File not found'
    
    # Get file info before moving
    old_path = os.path.abspath(source_path)
    source_hash = calculate_file_hash(source_path)
    mime_type = get_mime_type(source_path)
    extension = os.path.splitext(source_path)[1].lower()
    
    # Determine destination path
    filename = os.path.basename(source_path)
    dest_path = os.path.join(dest_dir, filename)
    
    # Check if file already exists in destination
    should_skip, skip_reason = check_destination_file(dest_path, source_hash, verbose)
    if should_skip:
        log_skip(audit_log, source_path, skip_reason, f"dest={dest_path}, hash={source_hash}")
        return 'skipped', skip_reason
    
    # Check if file exists in database at destination path
    db_exists, file_id, match_type = check_database_record(conn, dest_path, source_hash, verbose)
    
    if db_exists:
        if match_type == 'exact_match':
            if verbose >= 1:
                print(f"  Skipping: File already in database at destination with same hash")
            log_skip(audit_log, source_path, 'db_exact_match', 
                    f"dest={dest_path}, hash={source_hash}, file_id={file_id}")
            return 'skipped', 'db_exact_match'
        elif match_type == 'path_match_different_hash':
            if verbose >= 1:
                print(f"  Skipping: File exists in database at destination with different hash")
            log_skip(audit_log, source_path, 'db_path_different_hash',
                    f"dest={dest_path}, hash={source_hash}, file_id={file_id}")
            return 'skipped', 'db_path_different_hash'
    
    # Move the file
    success, new_path = move_file(source_path, dest_dir, dry_run, verbose)
    
    if not success:
        log_error(audit_log, 'move_failed', f"Failed to move file: {source_path}")
        return 'error', 'Failed to move file'
    
    # Update or insert database record
    action, file_id = update_or_insert_file(conn, old_path, new_path, volume, verbose, dry_run)
    
    if action == 'error':
        log_error(audit_log, 'db_update_failed', f"Database update failed for: {new_path}")
        return 'error', 'Database update failed'
    
    # Process metadata if not dry run
    if not dry_run and file_id > 0:
        process_metadata(conn, file_id, new_path, mime_type, extension, verbose, dry_run)
    
    # Log successful move
    if not dry_run:
        log_file_moved(audit_log, old_path, new_path, file_id, volume, source_hash, action)
    
    if verbose >= 1:
        action_str = "Would be " + action if dry_run else action.capitalize()
        print(f"  ✓ {action_str}")
    
    return 'success', action


def main():
    parser = argparse.ArgumentParser(
        description="Move media files and update database with new locations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Move files to destination (dry-run)
  python3 move_media.py --files img1.jpg img2.jpg \\
    --destination /photos/2024 --volume MainLibrary \\
    --db media.db --dry-run
  
  # Move files with verbose output
  python3 move_media.py --files *.jpg \\
    --destination /photos/vacation --volume Vacation2024 \\
    --db media.db --verbose 2
  
  # Move files from list
  python3 move_media.py --files $(cat files.txt) \\
    --destination /photos/archive --volume Archive \\
    --db media.db
        """
    )
    
    parser.add_argument("--files", action="append", required=True,
                       help="Files to move (can be repeated)")
    parser.add_argument("--destination", "--dest", required=True,
                       help="Destination directory")
    parser.add_argument("--volume", required=True,
                       help="Volume tag for the files")
    parser.add_argument("--db-path", "--db", required=True,
                       help="Path to media database")
    parser.add_argument("--verbose", "-v", type=int, default=1, choices=[0, 1, 2, 3],
                       help="Verbosity level: 0=quiet, 1=summary, 2=detailed, 3=debug (default: 1)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be done without making changes")
    parser.add_argument("--limit", type=int,
                       help="Limit number of files to process (useful with --dry-run for testing)")
    parser.add_argument("--audit-log", type=str, default=None,
                       help="Path to audit log file (default: move_media_audit.log)")
    
    args = parser.parse_args()
    
    # Setup audit logging
    audit_log = get_audit_logger('move_media', args.audit_log)
    log_session_start(audit_log, 'move_media', vars(args))
    
    # Validate destination
    if not args.dry_run and not os.path.exists(args.destination):
        try:
            os.makedirs(args.destination, exist_ok=True)
        except Exception as e:
            error_msg = f"Could not create destination directory: {e}"
            print(f"Error: {error_msg}", file=sys.stderr)
            log_error(audit_log, 'destination_error', error_msg)
            sys.exit(1)
    
    # Connect to database
    if not os.path.exists(args.db_path):
        error_msg = f"Database file does not exist: {args.db_path}"
        print(f"Error: {error_msg}", file=sys.stderr)
        log_error(audit_log, 'database_error', error_msg)
        sys.exit(1)
    
    conn = sqlite3.connect(args.db_path)
    
    # Ensure schema exists
    create_database_schema(conn)
    
    # Flatten files list (in case of nested lists from action="append")
    files_to_process = []
    if args.files:
        for item in args.files:
            if isinstance(item, list):
                files_to_process.extend(item)
            else:
                files_to_process.append(item)
    
    # Deduplicate files (preserve order)
    seen = set()
    unique_files = []
    for file_path in files_to_process:
        # Normalize path for comparison
        normalized_path = os.path.abspath(file_path)
        if normalized_path not in seen:
            seen.add(normalized_path)
            unique_files.append(file_path)
    
    files_to_process = unique_files
    
    # Apply limit if specified
    if args.limit and args.limit > 0:
        original_count = len(files_to_process)
        files_to_process = files_to_process[:args.limit]
        if args.verbose >= 1:
            print(f"Limit applied: Processing {len(files_to_process)} of {original_count} file(s).")
    
    # Report if duplicates were found
    if args.verbose >= 1 and len(files_to_process) < len(args.files if isinstance(args.files, list) else []):
        duplicates_removed = sum(len(item) if isinstance(item, list) else 1 for item in (args.files or [])) - len(files_to_process)
        if duplicates_removed > 0:
            print(f"Note: {duplicates_removed} duplicate file path(s) removed")
            print()
    
    # Print summary
    if args.verbose >= 1:
        print("=" * 70)
        print("Move Media Files")
        print("=" * 70)
        print(f"Files to move: {len(files_to_process)}")
        print(f"Destination: {args.destination}")
        print(f"Volume: {args.volume}")
        print(f"Database: {args.db_path}")
        if args.dry_run:
            print("Mode: DRY RUN (no changes will be made)")
        print()
    
    # Process files
    start_time = datetime.now()
    
    moved_count = 0
    updated_count = 0
    inserted_count = 0
    skipped_count = 0
    skip_reasons = {}
    error_count = 0
    
    for file_path in files_to_process:
        status, action = process_file(
            file_path,
            args.destination,
            args.volume,
            conn,
            args.verbose,
            args.dry_run,
            audit_log
        )
        
        if status == 'success':
            moved_count += 1
            if action == 'updated':
                updated_count += 1
            elif action == 'inserted':
                inserted_count += 1
        elif status == 'skipped':
            skipped_count += 1
            skip_reasons[action] = skip_reasons.get(action, 0) + 1
        else:
            error_count += 1
    
    # Commit changes
    if not args.dry_run:
        conn.commit()
        if args.verbose >= 2:
            print("\n✓ Database changes committed")
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    # Close database
    conn.close()
    
    # Log session end
    stats = {
        'moved': moved_count,
        'updated': updated_count,
        'inserted': inserted_count,
        'skipped': skipped_count,
        'skip_reasons': skip_reasons,
        'errors': error_count,
        'duration': duration,
        'dry_run': args.dry_run
    }
    log_session_end(audit_log, 'move_media', stats)
    
    # Print summary
    if args.verbose >= 1:
        print("\n" + "=" * 70)
        print("Move complete!")
        print(f"Files moved: {moved_count}")
        print(f"  Database updated: {updated_count}")
        print(f"  Database inserted: {inserted_count}")
        print(f"Files skipped: {skipped_count}")
        if skip_reasons:
            for reason, count in sorted(skip_reasons.items()):
                reason_display = reason.replace('_', ' ').title()
                print(f"  {reason_display}: {count}")
        print(f"Errors: {error_count}")
        print(f"Duration: {duration:.2f} seconds")
        if args.dry_run:
            print("\n[DRY RUN] No actual changes were made")
        print("=" * 70)
    
    # Exit with error code if there were errors
    if error_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
