#!/usr/bin/env python3
"""remove_dupes.py - Remove duplicate files from the indexed media database.

This script reads the media index database, identifies files in the same folder
that have the same hash (duplicates), and moves all but the first one to a
separate directory. The moved files are removed from the database and an audit
record is created.
"""

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Import shared utilities
from media_utils import create_database_schema


# ==================== Database Operations ====================

def create_audit_table(conn: sqlite3.Connection):
    """Create the audit table for tracking removed duplicates."""
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS removed_duplicates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_file_id INTEGER NOT NULL,
            original_volume TEXT NOT NULL,
            original_fullpath TEXT NOT NULL,
            original_name TEXT NOT NULL,
            original_size INTEGER NOT NULL,
            original_hash TEXT NOT NULL,
            moved_to_path TEXT NOT NULL,
            kept_file_id INTEGER NOT NULL,
            kept_fullpath TEXT NOT NULL,
            removal_date TEXT NOT NULL,
            removal_reason TEXT NOT NULL
        )
    """)
    
    # Create index for audit queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_removed_hash 
        ON removed_duplicates(original_hash)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_removed_date 
        ON removed_duplicates(removal_date)
    """)
    
    conn.commit()


def find_duplicates_in_same_folder(conn: sqlite3.Connection, base_dir: Optional[str] = None) -> Dict[str, List[Dict]]:
    """Find all files that have the same hash and are in the same folder.
    
    Args:
        conn: Database connection
        base_dir: Optional base directory to filter files (only process files under this directory)
    
    Returns:
        Dictionary mapping folder paths to lists of duplicate file groups
        Each group is a list of file records with the same hash
    """
    cursor = conn.cursor()
    
    # Build the WHERE clause for base_dir filtering
    base_dir_filter = ""
    if base_dir:
        # Normalize base_dir for comparison
        base_dir_normalized = os.path.normpath(base_dir)
        # Add trailing slash for proper prefix matching
        if not base_dir_normalized.endswith(os.sep):
            base_dir_normalized += os.sep
        base_dir_filter = f"AND fullpath LIKE '{base_dir_normalized}%'"
    
    # Find all files with duplicate hashes in the same folder
    # Group by folder (directory part of fullpath) and hash
    query = f"""
        WITH file_folders AS (
            SELECT 
                id,
                volume,
                fullpath,
                name,
                size,
                mime_type,
                extension,
                file_hash,
                indexed_date,
                SUBSTR(fullpath, 1, LENGTH(fullpath) - LENGTH(name)) AS folder
            FROM files
            WHERE file_hash IS NOT NULL
            {base_dir_filter}
        )
        SELECT 
            folder,
            file_hash,
            COUNT(*) as duplicate_count,
            GROUP_CONCAT(id || '|' || fullpath || '|' || name || '|' || size || '|' || indexed_date, ':::') as file_info
        FROM file_folders
        GROUP BY folder, file_hash
        HAVING COUNT(*) > 1
        ORDER BY folder, file_hash
    """
    
    cursor.execute(query)
    
    duplicates_by_folder = {}
    
    for row in cursor.fetchall():
        folder = row[0]
        file_hash = row[1]
        duplicate_count = row[2]
        file_info_str = row[3]
        
        # Parse file info
        files = []
        for file_str in file_info_str.split(':::'):
            parts = file_str.split('|')
            files.append({
                'id': int(parts[0]),
                'fullpath': parts[1],
                'name': parts[2],
                'size': int(parts[3]),
                'indexed_date': parts[4],
                'file_hash': file_hash
            })
        
        # Sort by indexed_date to keep the first one
        files.sort(key=lambda x: x['indexed_date'])
        
        if folder not in duplicates_by_folder:
            duplicates_by_folder[folder] = []
        
        duplicates_by_folder[folder].append({
            'hash': file_hash,
            'files': files,
            'keep': files[0],
            'remove': files[1:]
        })
    
    return duplicates_by_folder


def get_file_details(conn: sqlite3.Connection, file_id: int) -> Dict:
    """Get full file details from database.
    
    Args:
        conn: Database connection
        file_id: File ID
    
    Returns:
        Dictionary with file details
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, volume, fullpath, name, size, mime_type, extension, file_hash, indexed_date
        FROM files
        WHERE id = ?
    """, (file_id,))
    
    row = cursor.fetchone()
    if row:
        return {
            'id': row[0],
            'volume': row[1],
            'fullpath': row[2],
            'name': row[3],
            'size': row[4],
            'mime_type': row[5],
            'extension': row[6],
            'file_hash': row[7],
            'indexed_date': row[8]
        }
    return None


def remove_file_from_database(conn: sqlite3.Connection, file_id: int):
    """Remove a file and its associated metadata from the database.
    
    Args:
        conn: Database connection
        file_id: File ID to remove
    """
    cursor = conn.cursor()
    
    # Delete from related tables (cascading should handle this, but being explicit)
    cursor.execute("DELETE FROM image_metadata WHERE file_id = ?", (file_id,))
    cursor.execute("DELETE FROM video_metadata WHERE file_id = ?", (file_id,))
    cursor.execute("DELETE FROM thumbnails WHERE file_id = ?", (file_id,))
    
    # Delete from main files table
    cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))


def create_audit_record(conn: sqlite3.Connection, removed_file: Dict, kept_file: Dict,
                       moved_to_path: str, removal_date: str):
    """Create an audit record for a removed duplicate.
    
    Args:
        conn: Database connection
        removed_file: Dictionary with removed file details
        kept_file: Dictionary with kept file details
        moved_to_path: Path where file was moved to
        removal_date: Timestamp of removal
    """
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO removed_duplicates (
            original_file_id, original_volume, original_fullpath, original_name,
            original_size, original_hash, moved_to_path, kept_file_id, kept_fullpath,
            removal_date, removal_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        removed_file['id'],
        removed_file['volume'],
        removed_file['fullpath'],
        removed_file['name'],
        removed_file['size'],
        removed_file['file_hash'],
        moved_to_path,
        kept_file['id'],
        kept_file['fullpath'],
        removal_date,
        'Duplicate in same folder'
    ))


# ==================== File Operations ====================

def move_duplicate_file(source_path: str, dest_root: str, volume: str,
                       base_dir: Optional[str], dry_run: bool, verbose: int) -> Optional[str]:
    """Move a duplicate file to the destination directory.
    
    Args:
        source_path: Original file path
        dest_root: Root directory for duplicates
        volume: Volume tag
        base_dir: Base directory to make paths relative to (optional)
        dry_run: If True, don't actually move the file
        verbose: Verbosity level
    
    Returns:
        Destination path where file was (or would be) moved, or None on error
    """
    try:
        # Create destination path relative to base_dir if provided
        if base_dir:
            # Make source_path relative to base_dir
            base_dir_normalized = os.path.normpath(base_dir)
            source_path_normalized = os.path.normpath(source_path)
            
            # Ensure base_dir ends with separator for proper prefix check
            if not base_dir_normalized.endswith(os.sep):
                base_dir_check = base_dir_normalized + os.sep
            else:
                base_dir_check = base_dir_normalized
            
            if source_path_normalized.startswith(base_dir_normalized + os.sep) or source_path_normalized == base_dir_normalized:
                # Remove base_dir prefix to get relative path
                source_path_relative = os.path.relpath(source_path_normalized, base_dir_normalized)
            else:
                # If source is not under base_dir, this is an error
                print(f"    ERROR: File {source_path} is not under base directory {base_dir}", file=sys.stderr)
                print(f"           Skipping this file.", file=sys.stderr)
                return None
        else:
            # No base_dir, use full path
            source_path_relative = source_path.lstrip('/')
        
        # Create destination path: dest_root/relative_path (without volume)
        dest_path = os.path.join(dest_root, source_path_relative)
        
        if verbose >= 2:
            print(f"    Source: {source_path}")
            print(f"    Dest:   {dest_path}")
        
        if not dry_run:
            # Check if source file exists
            if not os.path.exists(source_path):
                print(f"    Warning: Source file does not exist: {source_path}", file=sys.stderr)
                return None
            
            # Create destination directory
            dest_dir = os.path.dirname(dest_path)
            os.makedirs(dest_dir, exist_ok=True)
            
            # Move the file
            shutil.move(source_path, dest_path)
            
            if verbose >= 2:
                print(f"    ✓ Moved")
        else:
            if verbose >= 2:
                print(f"    [DRY RUN] Would move")
        
        return dest_path
        
    except Exception as e:
        print(f"    Error moving file {source_path}: {e}", file=sys.stderr)
        return None


def process_duplicate_group(conn: sqlite3.Connection, folder: str, group: Dict,
                           dest_root: str, base_dir: Optional[str], dry_run: bool,
                           verbose: int, removal_date: str) -> Tuple[int, int]:
    """Process a group of duplicate files.
    
    Args:
        conn: Database connection
        folder: Folder path
        group: Dictionary with duplicate group info
        dest_root: Root directory for moved files
        base_dir: Base directory to make paths relative to (optional)
        dry_run: If True, don't actually make changes
        verbose: Verbosity level
        removal_date: Timestamp for audit records
    
    Returns:
        Tuple of (files_removed, files_kept)
    """
    kept_file = group['keep']
    files_to_remove = group['remove']
    
    if verbose >= 1:
        print(f"\n  Folder: {folder}")
        print(f"  Hash: {group['hash'][:16]}...")
        print(f"  Keeping: {kept_file['name']} (indexed: {kept_file['indexed_date']})")
        print(f"  Removing {len(files_to_remove)} duplicate(s):")
    
    removed_count = 0
    
    for file_to_remove in files_to_remove:
        if verbose >= 1:
            print(f"    - {file_to_remove['name']} (indexed: {file_to_remove['indexed_date']})")
        
        # Get full file details
        file_details = get_file_details(conn, file_to_remove['id'])
        if not file_details:
            print(f"      Warning: Could not get file details for ID {file_to_remove['id']}", file=sys.stderr)
            continue
        
        # Move the file
        moved_to_path = move_duplicate_file(
            file_details['fullpath'],
            dest_root,
            file_details['volume'],
            base_dir,
            dry_run,
            verbose
        )
        
        if moved_to_path:
            if not dry_run:
                # Create audit record
                create_audit_record(
                    conn,
                    file_details,
                    kept_file,
                    moved_to_path,
                    removal_date
                )
                
                # Remove from database
                remove_file_from_database(conn, file_to_remove['id'])
                
                if verbose >= 2:
                    print(f"    ✓ Removed from database")
            
            removed_count += 1
    
    return removed_count, 1


# ==================== Main ====================

def main():
    parser = argparse.ArgumentParser(
        description="Remove duplicate files from the media index database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This script identifies files in the same folder that have identical hashes
(duplicates) and moves all but the first indexed file to a separate directory.
The moved files are removed from the database and audit records are created.

Examples:
  # Preview what would be removed (dry-run)
  python3 remove_dupes.py --db media.db --dest /removed_dupes --dry-run
  
  # Remove duplicates and move to separate directory
  python3 remove_dupes.py --db media.db --dest /removed_dupes
  
  # Use base directory for relative paths
  python3 remove_dupes.py --db media.db --dest /removed_dupes --base-dir /mnt/photo
  # Example: /mnt/photo/2010/abc.jpg -> /removed_dupes/2010/abc.jpg
  
  # Verbose output
  python3 remove_dupes.py --db media.db --dest /removed_dupes -v 2 --dry-run
  
  # Quiet mode (only summary)
  python3 remove_dupes.py --db media.db --dest /removed_dupes -v 0
        """
    )
    
    parser.add_argument("--db-path", "--db", required=True,
                       help="Path to media index database")
    parser.add_argument("--dest", required=True,
                       help="Destination directory for removed duplicate files")
    parser.add_argument("--base-dir", default=None,
                       help="Base directory for indexed files (e.g., /mnt/photo). "
                            "Paths in dest will be relative to this directory.")
    parser.add_argument("--verbose", "-v", type=int, default=1, choices=[0, 1, 2, 3],
                       help="Verbosity level: 0=quiet, 1=summary, 2=detailed, 3=debug (default: 1)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be done without actually making changes")
    parser.add_argument("--limit", type=int,
                       help="Limit number of duplicate groups to process (useful with --dry-run for testing)")
    
    args = parser.parse_args()
    
    # Validate database path
    if not os.path.exists(args.db_path):
        print(f"Error: Database file does not exist: {args.db_path}", file=sys.stderr)
        sys.exit(1)
    
    # Validate base directory if provided
    if args.base_dir:
        if not os.path.exists(args.base_dir):
            print(f"Error: Base directory does not exist: {args.base_dir}", file=sys.stderr)
            sys.exit(1)
        # Normalize the base directory path
        args.base_dir = os.path.normpath(os.path.abspath(args.base_dir))
    
    # Connect to database
    conn = sqlite3.connect(args.db_path)
    
    # Create audit table if it doesn't exist
    create_audit_table(conn)
    
    # Get removal timestamp
    removal_date = datetime.now().isoformat()
    
    if args.verbose >= 1:
        print("=" * 60)
        print("Remove Duplicates from Database")
        print("=" * 60)
        print(f"Database: {args.db_path}")
        print(f"Destination: {args.dest}")
        if args.base_dir:
            print(f"Base directory: {args.base_dir}")
            print(f"  (Paths will be relative to base directory)")
        if args.limit:
            print(f"Limit: {args.limit} duplicate groups")
        if args.dry_run:
            print("Mode: DRY RUN (no changes will be made)")
        print()
    
    # Find duplicates
    start_time = datetime.now()
    
    if args.verbose >= 1:
        print("Scanning database for duplicates in same folder...")
        if args.base_dir:
            print(f"  Filtering files under: {args.base_dir}")
    
    duplicates_by_folder = find_duplicates_in_same_folder(conn, args.base_dir)
    
    if not duplicates_by_folder:
        print("\nNo duplicates found in the same folder!")
        conn.close()
        return
    
    # Count total duplicates
    total_groups = sum(len(groups) for groups in duplicates_by_folder.values())
    total_files_to_remove = sum(
        len(group['remove'])
        for groups in duplicates_by_folder.values()
        for group in groups
    )
    
    if args.verbose >= 1:
        print(f"Found {total_groups} duplicate group(s) across {len(duplicates_by_folder)} folder(s)")
        print(f"Total files to remove: {total_files_to_remove}")
    
    # Process duplicates
    total_removed = 0
    total_kept = 0
    groups_processed = 0
    
    for folder, groups in duplicates_by_folder.items():
        for group in groups:
            # Check if we've reached the limit
            if args.limit and groups_processed >= args.limit:
                if args.verbose >= 1:
                    print(f"\nReached limit of {args.limit} duplicate groups. Stopping.")
                break
            
            removed, kept = process_duplicate_group(
                conn,
                folder,
                group,
                args.dest,
                args.base_dir,
                args.dry_run,
                args.verbose,
                removal_date
            )
            total_removed += removed
            total_kept += kept
            groups_processed += 1
        
        # Break outer loop too if limit reached
        if args.limit and groups_processed >= args.limit:
            break
    
    # Commit changes
    if not args.dry_run:
        conn.commit()
        if args.verbose >= 2:
            print("\n✓ Database changes committed")
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    # Close database
    conn.close()
    
    # Print summary
    print("\n" + "=" * 60)
    print("Duplicate removal complete!")
    print(f"Files removed: {total_removed}")
    print(f"Files kept: {total_kept}")
    print(f"Duration: {duration:.2f} seconds")
    if args.dry_run:
        print("\n[DRY RUN] No actual changes were made")
    print("=" * 60)


if __name__ == "__main__":
    main()
