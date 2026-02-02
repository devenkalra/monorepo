#!/usr/bin/env python3
"""manage_dupes.py - Manage duplicate files using the media index database.

This script scans a source directory and identifies files that already exist
in the media index database (by hash). Duplicates can be moved to a separate
directory structure, preserving the original folder hierarchy.
"""

import argparse
import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

# Import shared utilities
from media_utils import (
    calculate_file_hash,
    find_file_by_hash,
    find_files_by_hash,
    get_file_info,
    get_mime_type,
    is_image_file,
    is_video_file
)


# ==================== Pattern Matching ====================

def should_skip_path(path: str, skip_patterns: List[str], literal: bool = False) -> bool:
    """Check if a path should be skipped based on patterns.
    
    Args:
        path: Path to check
        skip_patterns: List of patterns to match against
        literal: If True, treat patterns as literal strings; if False, treat as regex
    
    Returns:
        True if path matches any skip pattern, False otherwise
    """
    path_str = str(path)
    for pattern in skip_patterns:
        try:
            if literal:
                escaped_pattern = re.escape(pattern)
                if re.search(escaped_pattern, path_str):
                    return True
            else:
                if re.search(pattern, path_str):
                    return True
        except re.error as e:
            print(f"Warning: Invalid regex pattern '{pattern}': {e}", file=sys.stderr)
            if pattern in path_str:
                return True
    return False


def matches_include_pattern(path: str, include_patterns: List[str], literal: bool = False) -> bool:
    """Check if a path matches any of the include patterns.
    
    If no include patterns are specified, all paths match.
    
    Args:
        path: Path to check
        include_patterns: List of patterns to match against
        literal: If True, treat patterns as literal strings; if False, treat as regex
    
    Returns:
        True if path matches any include pattern (or no patterns specified), False otherwise
    """
    if not include_patterns:
        return True
    
    path_str = str(path)
    for pattern in include_patterns:
        try:
            if literal:
                escaped_pattern = re.escape(pattern)
                if re.search(escaped_pattern, path_str):
                    return True
            else:
                if re.search(pattern, path_str):
                    return True
        except re.error as e:
            print(f"Warning: Invalid regex pattern '{pattern}': {e}", file=sys.stderr)
            if pattern in path_str:
                return True
    return False


# ==================== Duplicate Management ====================

def process_file(filepath: str, source_root: str, dest_root: str, conn: sqlite3.Connection,
                verbose: int, dry_run: bool, action: str) -> Tuple[str, Optional[str]]:
    """Process a single file to check for duplicates.
    
    Args:
        filepath: Path to file to check
        source_root: Root directory being scanned
        dest_root: Destination root for duplicates
        conn: Database connection
        verbose: Verbosity level
        dry_run: If True, don't actually move files
        action: Action to take ('move' or 'copy')
    
    Returns:
        Tuple of (status, duplicate_path)
        - status: 'duplicate', 'unique', 'error', 'skipped'
        - duplicate_path: Path to original file in database (if duplicate)
    """
    try:
        # Calculate file hash
        if verbose >= 2:
            print(f"  Calculating hash...")
        
        file_hash = calculate_file_hash(filepath)
        
        # Check if file exists in database
        matches = find_files_by_hash(conn, file_hash)
        
        if not matches:
            if verbose >= 1:
                print(f"Unique: {filepath}")
            return 'unique', None
        
        # File is a duplicate
        original = matches[0]  # First indexed file
        
        if verbose >= 1:
            action_str = "[DRY RUN] Would move" if dry_run else ("Moving" if action == 'move' else "Copying")
            print(f"Duplicate: {filepath}")
            print(f"  Original: {original['fullpath']}")
            print(f"  {action_str} to duplicate directory...")
        
        # Calculate relative path from source root
        rel_path = os.path.relpath(filepath, source_root)
        dest_path = os.path.join(dest_root, rel_path)
        
        if not dry_run:
            # Create destination directory
            dest_dir = os.path.dirname(dest_path)
            os.makedirs(dest_dir, exist_ok=True)
            
            # Move or copy the file
            if action == 'move':
                shutil.move(filepath, dest_path)
            else:  # copy
                shutil.copy2(filepath, dest_path)
            
            if verbose >= 2:
                print(f"  -> {dest_path}")
        elif verbose >= 2:
            print(f"  -> {dest_path}")
        
        return 'duplicate', original['fullpath']
        
    except Exception as e:
        print(f"Error processing {filepath}: {e}", file=sys.stderr)
        return 'error', None


def scan_directory(source_dir: str, dest_dir: str, conn: sqlite3.Connection,
                   skip_patterns: List[str], include_patterns: List[str],
                   literal_patterns: bool, verbose: int, dry_run: bool,
                   action: str, media_only: bool, limit: Optional[int] = None) -> Tuple[int, int, int]:
    """Scan directory for duplicate files.
    
    Args:
        source_dir: Source directory to scan
        dest_dir: Destination directory for duplicates
        conn: Database connection
        skip_patterns: Patterns to skip
        include_patterns: Patterns to include
        literal_patterns: If True, treat patterns as literal strings
        verbose: Verbosity level
        dry_run: If True, don't actually move files
        action: Action to take ('move' or 'copy')
        media_only: If True, only process media files (images/videos)
    
    Returns:
        Tuple of (duplicates_found, unique_files, errors)
    """
    duplicates_found = 0
    unique_files = 0
    errors = 0
    skipped_files = 0
    files_processed = 0
    
    print(f"\nScanning directory: {source_dir}")
    print(f"Duplicate destination: {dest_dir}")
    print(f"Action: {action}")
    print(f"Media only: {media_only}")
    if limit:
        print(f"Limit: {limit} files")
    if dry_run:
        print(f"Mode: DRY RUN (no changes will be made)")
    print()
    
    for root, dirs, files in os.walk(source_dir):
        # Check if current directory should be skipped
        if should_skip_path(root, skip_patterns, literal_patterns):
            if verbose >= 1:
                print(f"Skipping directory: {root}")
            dirs.clear()
            continue
        
        # Filter out directories to skip
        dirs[:] = [d for d in dirs if not should_skip_path(os.path.join(root, d), skip_patterns, literal_patterns)]
        
        for filename in files:
            # Check if we've reached the limit
            if limit and files_processed >= limit:
                print(f"\nReached limit of {limit} files. Stopping.")
                return duplicates_found, unique_files, errors
            
            filepath = os.path.join(root, filename)
            
            # Check if file matches include pattern
            if not matches_include_pattern(filepath, include_patterns, literal_patterns):
                skipped_files += 1
                continue
            
            # Check if file should be skipped
            if should_skip_path(filepath, skip_patterns, literal_patterns):
                skipped_files += 1
                continue
            
            # If media_only, check if it's a media file
            if media_only:
                mime_type = get_mime_type(filepath)
                extension = os.path.splitext(filepath)[1].lower()
                if not (is_image_file(mime_type, extension) or is_video_file(mime_type)):
                    if verbose >= 2:
                        print(f"Skipping non-media file: {filepath}")
                    skipped_files += 1
                    continue
            
            # Process the file
            status, original_path = process_file(
                filepath, source_dir, dest_dir, conn,
                verbose, dry_run, action
            )
            
            if status == 'duplicate':
                duplicates_found += 1
                files_processed += 1
            elif status == 'unique':
                unique_files += 1
                files_processed += 1
            elif status == 'error':
                errors += 1
    
    if verbose >= 1 and skipped_files > 0:
        print(f"\nSkipped {skipped_files} files (patterns/non-media)")
    
    return duplicates_found, unique_files, errors


# ==================== Main ====================

def main():
    parser = argparse.ArgumentParser(
        description="Manage duplicate files using the media index database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Find duplicates in a directory (dry-run)
  python3 manage_dupes.py --source /backup/photos --destination /duplicates --db media.db --dry-run
  
  # Move duplicates to separate directory
  python3 manage_dupes.py --source /backup/photos --destination /duplicates --db media.db --action move
  
  # Copy duplicates instead of moving
  python3 manage_dupes.py --source /backup/photos --destination /duplicates --db media.db --action copy
  
  # Only process media files
  python3 manage_dupes.py --source /backup --destination /duplicates --db media.db --media-only
  
  # Verbose output
  python3 manage_dupes.py --source /backup --destination /duplicates --db media.db -v 2
        """
    )
    
    parser.add_argument("--source", required=True,
                       help="Source directory to scan for duplicates")
    parser.add_argument("--destination", required=True,
                       help="Destination directory for duplicate files (preserves structure)")
    parser.add_argument("--db-path", "--db", required=True,
                       help="Path to media index database")
    parser.add_argument("--action", choices=['move', 'copy'], default='move',
                       help="Action to take with duplicates (default: move)")
    parser.add_argument("--media-only", action="store_true",
                       help="Only process media files (images and videos)")
    parser.add_argument("--include-pattern", action="append", default=[],
                       help="Pattern to include in paths (regex by default; can be repeated)")
    parser.add_argument("--skip-pattern", action="append", default=[],
                       help="Pattern to skip in paths (regex by default; can be repeated)")
    parser.add_argument("--literal-patterns", action="store_true",
                       help="Treat patterns as literal strings instead of regex")
    parser.add_argument("--verbose", "-v", type=int, default=1, choices=[0, 1, 2, 3],
                       help="Verbosity level: 0=quiet, 1=summary, 2=detailed, 3=debug (default: 1)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be done without actually moving/copying files")
    parser.add_argument("--limit", type=int,
                       help="Limit number of files to process (useful with --dry-run for testing)")
    
    args = parser.parse_args()
    
    # Validate paths
    if not os.path.exists(args.source):
        print(f"Error: Source directory does not exist: {args.source}", file=sys.stderr)
        sys.exit(1)
    
    if not os.path.exists(args.db_path):
        print(f"Error: Database file does not exist: {args.db_path}", file=sys.stderr)
        sys.exit(1)
    
    # Connect to database
    conn = sqlite3.connect(args.db_path)
    
    # Scan for duplicates
    start_time = datetime.now()
    
    duplicates, unique, errors = scan_directory(
        args.source,
        args.destination,
        conn,
        args.skip_pattern,
        args.include_pattern,
        args.literal_patterns,
        args.verbose,
        args.dry_run,
        args.action,
        args.media_only,
        args.limit
    )
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    # Close database
    conn.close()
    
    # Print summary
    print("\n" + "=" * 60)
    print("Duplicate scan complete!")
    print(f"Duplicates found: {duplicates}")
    print(f"Unique files: {unique}")
    print(f"Errors: {errors}")
    print(f"Duration: {duration:.2f} seconds")
    print("=" * 60)


if __name__ == "__main__":
    main()
