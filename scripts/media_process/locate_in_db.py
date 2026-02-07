#!/usr/bin/env python3
"""locate_in_db.py - Find files in database by hash.

This script takes one or more files, computes their hash, and finds all
matching files in the database. Useful for finding duplicates, verifying
file locations, and checking if files are already indexed.
"""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Import shared utilities
try:
    from media_utils import calculate_file_hash
except ImportError:
    print("Error: media_utils module not found", file=sys.stderr)
    print("Make sure media_utils.py is in the same directory", file=sys.stderr)
    sys.exit(1)


def find_by_hash(conn: sqlite3.Connection, file_hash: str) -> List[Dict]:
    """Find all files in database with matching hash.
    
    Args:
        conn: Database connection
        file_hash: File hash to search for
    
    Returns:
        List of dictionaries with file information
    """
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, volume, fullpath, name, created_date, modified_date, 
               size, mime_type, extension, indexed_date
        FROM files
        WHERE file_hash = ?
        ORDER BY indexed_date DESC
    """, (file_hash,))
    
    results = []
    for row in cursor.fetchall():
        results.append({
            'id': row[0],
            'volume': row[1],
            'fullpath': row[2],
            'name': row[3],
            'created_date': row[4],
            'modified_date': row[5],
            'size': row[6],
            'mime_type': row[7],
            'extension': row[8],
            'indexed_date': row[9]
        })
    
    return results


def get_file_metadata(conn: sqlite3.Connection, file_id: int, mime_type: str) -> Optional[Dict]:
    """Get metadata for a file.
    
    Args:
        conn: Database connection
        file_id: File ID
        mime_type: MIME type to determine metadata table
    
    Returns:
        Dictionary with metadata or None
    """
    cursor = conn.cursor()
    
    if mime_type and mime_type.startswith('image/'):
        cursor.execute("""
            SELECT width, height, date_taken, camera_make, camera_model,
                   latitude, longitude, city, state, country, keywords
            FROM image_metadata
            WHERE file_id = ?
        """, (file_id,))
        
        row = cursor.fetchone()
        if row:
            return {
                'type': 'image',
                'width': row[0],
                'height': row[1],
                'date_taken': row[2],
                'camera_make': row[3],
                'camera_model': row[4],
                'latitude': row[5],
                'longitude': row[6],
                'city': row[7],
                'state': row[8],
                'country': row[9],
                'keywords': row[10]
            }
    
    elif mime_type and mime_type.startswith('video/'):
        cursor.execute("""
            SELECT width, height, duration_seconds, frame_rate, video_codec
            FROM video_metadata
            WHERE file_id = ?
        """, (file_id,))
        
        row = cursor.fetchone()
        if row:
            return {
                'type': 'video',
                'width': row[0],
                'height': row[1],
                'duration': row[2],
                'frame_rate': row[3],
                'video_codec': row[4]
            }
    
    return None


def format_size(size_bytes: int) -> str:
    """Format file size in human-readable format.
    
    Args:
        size_bytes: Size in bytes
    
    Returns:
        Formatted string (e.g., "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def print_results_text(query_file: str, file_hash: str, matches: List[Dict], 
                       conn: sqlite3.Connection, show_metadata: bool, show_hash: bool):
    """Print results in text format.
    
    Args:
        query_file: Original query file path
        file_hash: Computed hash
        matches: List of matching files
        conn: Database connection
        show_metadata: Whether to show metadata
        show_hash: Whether to show hash
    """
    # Store result for grouping
    return {
        'query_file': query_file,
        'file_hash': file_hash,
        'matches': matches,
        'show_metadata': show_metadata,
        'show_hash': show_hash
    }


def print_grouped_results(results: List[Dict], conn: sqlite3.Connection):
    """Print results grouped by category.
    
    Args:
        results: List of result dictionaries
        conn: Database connection
    """
    # Categorize results
    not_found = []
    uniques = []
    dupes = []
    
    for result in results:
        query_file = result['query_file']
        matches = result['matches']
        
        if len(matches) == 0:
            not_found.append(query_file)
        elif len(matches) == 1:
            uniques.append({
                'query_file': query_file,
                'match': matches[0],
                'file_hash': result['file_hash'],
                'show_metadata': result['show_metadata'],
                'show_hash': result['show_hash']
            })
        else:
            dupes.append({
                'query_file': query_file,
                'matches': matches,
                'file_hash': result['file_hash'],
                'show_metadata': result['show_metadata'],
                'show_hash': result['show_hash']
            })
    
    # Print results
    print("=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)
    print()
    
    # Not Found section
    if not_found:
        print("NOT FOUND IN DATABASE")
        print("-" * 80)
        for file_path in not_found:
            print(f"  {file_path}")
        print()
    
    # Uniques section
    if uniques:
        print("UNIQUE FILES (Found once)")
        print("-" * 80)
        for item in uniques:
            print(f"  Candidate: {item['query_file']}")
            if item['show_hash']:
                print(f"    Hash: {item['file_hash']}")
            print(f"    Match:")
            match = item['match']
            
            # Print file path
            print(f"      {match['fullpath']}")
            
            # Print details on separate line if metadata requested
            if item['show_metadata']:
                details = []
                
                # Add basic info
                details.append(f"Vol:{match['volume']}")
                details.append(f"Size:{format_size(match['size'])}")
                
                # Check existence
                if os.path.exists(match['fullpath']):
                    details.append("✓Exists")
                else:
                    details.append("✗Missing")
                
                # Get metadata
                metadata = get_file_metadata(conn, match['id'], match['mime_type'])
                if metadata:
                    if metadata['type'] == 'image':
                        if metadata['width'] and metadata['height']:
                            details.append(f"{metadata['width']}x{metadata['height']}")
                        if metadata['date_taken']:
                            details.append(f"Date:{metadata['date_taken']}")
                        if metadata['city'] or metadata['state']:
                            loc = ', '.join(filter(None, [metadata['city'], metadata['state']]))
                            if loc:
                                details.append(f"Loc:{loc}")
                    elif metadata['type'] == 'video':
                        if metadata['width'] and metadata['height']:
                            details.append(f"{metadata['width']}x{metadata['height']}")
                        if metadata['duration']:
                            minutes, seconds = divmod(int(metadata['duration']), 60)
                            details.append(f"Dur:{minutes}:{seconds:02d}")
                
                print(f"        [{' | '.join(details)}]")
            print()
    
    # Duplicates section
    if dupes:
        print("DUPLICATES (Found multiple times)")
        print("-" * 80)
        for item in dupes:
            print(f"  Candidate: {item['query_file']}")
            if item['show_hash']:
                print(f"    Hash: {item['file_hash']}")
            print(f"    Duplicates ({len(item['matches'])}):")
            
            for match in item['matches']:
                # Print file path
                print(f"      {match['fullpath']}")
                
                # Print details on separate line if metadata requested
                if item['show_metadata']:
                    details = []
                    
                    # Add basic info
                    details.append(f"Vol:{match['volume']}")
                    details.append(f"Size:{format_size(match['size'])}")
                    
                    # Check existence
                    if os.path.exists(match['fullpath']):
                        details.append("✓Exists")
                    else:
                        details.append("✗Missing")
                    
                    # Get metadata
                    metadata = get_file_metadata(conn, match['id'], match['mime_type'])
                    if metadata:
                        if metadata['type'] == 'image':
                            if metadata['width'] and metadata['height']:
                                details.append(f"{metadata['width']}x{metadata['height']}")
                            if metadata['date_taken']:
                                details.append(f"Date:{metadata['date_taken']}")
                            if metadata['city'] or metadata['state']:
                                loc = ', '.join(filter(None, [metadata['city'], metadata['state']]))
                                if loc:
                                    details.append(f"Loc:{loc}")
                        elif metadata['type'] == 'video':
                            if metadata['width'] and metadata['height']:
                                details.append(f"{metadata['width']}x{metadata['height']}")
                            if metadata['duration']:
                                minutes, seconds = divmod(int(metadata['duration']), 60)
                                details.append(f"Dur:{minutes}:{seconds:02d}")
                    
                    print(f"        [{' | '.join(details)}]")
            print()
    
    print("=" * 80)
    print(f"Total: {len(not_found)} not found, {len(uniques)} unique, {len(dupes)} with duplicates")
    print("=" * 80)
    print()


def print_results_json(query_file: str, file_hash: str, matches: List[Dict],
                      conn: sqlite3.Connection, show_metadata: bool):
    """Print results in JSON format.
    
    Args:
        query_file: Original query file path
        file_hash: Computed hash
        matches: List of matching files
        conn: Database connection
        show_metadata: Whether to show metadata
    """
    output = {
        'query_file': query_file,
        'hash': file_hash,
        'match_count': len(matches),
        'matches': []
    }
    
    for match in matches:
        match_data = dict(match)
        match_data['exists'] = os.path.exists(match['fullpath'])
        
        if show_metadata:
            metadata = get_file_metadata(conn, match['id'], match['mime_type'])
            if metadata:
                match_data['metadata'] = metadata
        
        output['matches'].append(match_data)
    
    print(json.dumps(output, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="Find files in database by hash",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Find matches for single file
  python3 locate_in_db.py --file photo.jpg --db-path media.db
  
  # Find matches for multiple files
  python3 locate_in_db.py --files photo1.jpg photo2.jpg video.mp4 --db-path media.db
  
  # Show metadata for matches
  python3 locate_in_db.py --file photo.jpg --db-path media.db --metadata
  
  # Output as JSON
  python3 locate_in_db.py --file photo.jpg --db-path media.db --json
  
  # Show hash values
  python3 locate_in_db.py --file photo.jpg --db-path media.db --show-hash
        """
    )
    
    parser.add_argument("--file", "--files", dest="files", action="append", default=[],
                       help="File(s) to search for (can be repeated)")
    parser.add_argument("--db-path", "--db", required=True,
                       help="Path to media database")
    parser.add_argument("--metadata", "-m", action="store_true",
                       help="Show metadata for matching files")
    parser.add_argument("--json", action="store_true",
                       help="Output results as JSON")
    parser.add_argument("--show-hash", action="store_true",
                       help="Show file hash in output")
    parser.add_argument("--summary", "-s", action="store_true",
                       help="Show only summary statistics")
    
    parser.add_argument("--limit", type=int,
                       help="Limit number of files to process (useful for testing)")
    
    args = parser.parse_args()
    
    # Validate inputs
    if not args.files:
        parser.error("At least one file must be specified with --file")
    
    if not os.path.exists(args.db_path):
        print(f"Error: Database file does not exist: {args.db_path}", file=sys.stderr)
        sys.exit(1)
    
    # Connect to database
    conn = sqlite3.connect(args.db_path)
    
    # Apply limit if specified
    files_to_process = args.files
    if args.limit and args.limit > 0:
        original_count = len(files_to_process)
        files_to_process = files_to_process[:args.limit]
        print(f"Limit applied: Processing {len(files_to_process)} of {original_count} file(s).\n")
    
    # Process each file
    total_files = 0
    total_matches = 0
    files_with_matches = 0
    results = []
    
    for file_path in files_to_process:
        if not os.path.exists(file_path):
            print(f"Warning: File not found: {file_path}", file=sys.stderr)
            continue
        
        total_files += 1
        
        # Compute hash
        try:
            file_hash = calculate_file_hash(file_path)
        except Exception as e:
            print(f"Error computing hash for {file_path}: {e}", file=sys.stderr)
            continue
        
        # Find matches
        matches = find_by_hash(conn, file_hash)
        
        if matches:
            files_with_matches += 1
            total_matches += len(matches)
        
        # Collect results
        if args.json:
            # Print JSON immediately for each file
            print_results_json(file_path, file_hash, matches, conn, args.metadata)
        else:
            # Collect for grouped output
            result = print_results_text(file_path, file_hash, matches, conn, 
                                       args.metadata, args.show_hash)
            results.append(result)
    
    # Print grouped results (text mode only)
    if not args.json and not args.summary:
        print_grouped_results(results, conn)
    
    # Print summary
    if args.summary:
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Files queried: {total_files}")
        print(f"Files with matches: {files_with_matches}")
        print(f"Files without matches: {total_files - files_with_matches}")
        print(f"Total matches found: {total_matches}")
        if files_with_matches > 0:
            print(f"Average matches per file: {total_matches / files_with_matches:.1f}")
        print("=" * 80)
    
    # Close database
    conn.close()


if __name__ == "__main__":
    main()
