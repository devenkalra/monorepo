#!/usr/bin/env python3
"""locate_in_db.py - Find files in database by hash."""

import argparse
import json
import os
import sqlite3
import sys
from typing import Dict, List, Optional

from media_utils import calculate_file_hash, find_files_by_hash


def find_by_hash(conn: sqlite3.Connection, file_hash: str) -> List[Dict]:
    """Find all files in database with matching hash."""
    return find_files_by_hash(conn, file_hash)


def get_file_metadata(conn: sqlite3.Connection, file_id: int, mime_type: str) -> Optional[Dict]:
    """Get metadata for a file."""
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
                'keywords': row[10],
            }

    if mime_type and mime_type.startswith('video/'):
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
                'video_codec': row[4],
            }

    if mime_type and mime_type.startswith('audio/'):
        cursor.execute("""
            SELECT duration_seconds, audio_codec, bit_rate_kbps, title, artist, album
            FROM audio_metadata
            WHERE file_id = ?
        """, (file_id,))
        row = cursor.fetchone()
        if row:
            return {
                'type': 'audio',
                'duration': row[0],
                'audio_codec': row[1],
                'bit_rate_kbps': row[2],
                'title': row[3],
                'artist': row[4],
                'album': row[5],
            }

    cursor.execute("""
        SELECT page_count, title, author
        FROM document_metadata
        WHERE file_id = ?
    """, (file_id,))
    row = cursor.fetchone()
    if row:
        return {
            'type': 'document',
            'page_count': row[0],
            'title': row[1],
            'author': row[2],
        }

    cursor.execute("""
        SELECT subject, sender, email_date, has_attachments, attachment_count
        FROM email_metadata
        WHERE file_id = ?
    """, (file_id,))
    row = cursor.fetchone()
    if row:
        return {
            'type': 'email',
            'subject': row[0],
            'sender': row[1],
            'email_date': row[2],
            'has_attachments': bool(row[3]),
            'attachment_count': row[4],
        }

    return None


def format_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def _format_match_path(match: Dict) -> str:
    return f"{match['volume']}:{match['relpath']} ({match['fullpath']})"


def _match_details(conn: sqlite3.Connection, match: Dict, show_metadata: bool) -> List[str]:
    details = [
        f"Vol:{match['volume']}",
        f"Rel:{match['relpath']}",
        f"Size:{format_size(match['size'])}",
    ]
    if os.path.exists(match['fullpath']):
        details.append("Exists")
    else:
        details.append("Missing")

    if show_metadata:
        metadata = get_file_metadata(conn, match['id'], match['mime_type'])
        if metadata:
            if metadata['type'] == 'image':
                if metadata['width'] and metadata['height']:
                    details.append(f"{metadata['width']}x{metadata['height']}")
                if metadata['date_taken']:
                    details.append(f"Date:{metadata['date_taken']}")
            elif metadata['type'] == 'video':
                if metadata['width'] and metadata['height']:
                    details.append(f"{metadata['width']}x{metadata['height']}")
                if metadata['duration']:
                    minutes, seconds = divmod(int(metadata['duration']), 60)
                    details.append(f"Dur:{minutes}:{seconds:02d}")
            elif metadata['type'] == 'document' and metadata.get('title'):
                details.append(f"Title:{metadata['title']}")
            elif metadata['type'] == 'email' and metadata.get('subject'):
                details.append(f"Subject:{metadata['subject']}")
    return details


def print_results_text(query_file: str, file_hash: str, matches: List[Dict],
                       conn: sqlite3.Connection, show_metadata: bool, show_hash: bool):
    return {
        'query_file': query_file,
        'file_hash': file_hash,
        'matches': matches,
        'show_metadata': show_metadata,
        'show_hash': show_hash,
    }


def print_grouped_results(results: List[Dict], conn: sqlite3.Connection):
    not_found = []
    uniques = []
    dupes = []

    for result in results:
        matches = result['matches']
        if len(matches) == 0:
            not_found.append(result['query_file'])
        elif len(matches) == 1:
            uniques.append(result)
        else:
            dupes.append(result)

    print("=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)
    print()

    if not_found:
        print("NOT FOUND IN DATABASE")
        print("-" * 80)
        for file_path in not_found:
            print(f"  {file_path}")
        print()

    if uniques:
        print("UNIQUE FILES (Found once)")
        print("-" * 80)
        for item in uniques:
            print(f"  Candidate: {item['query_file']}")
            if item['show_hash']:
                print(f"    Hash: {item['file_hash']}")
            match = item['matches'][0]
            print(f"    Match: {_format_match_path(match)}")
            details = _match_details(conn, match, item['show_metadata'])
            print(f"      [{' | '.join(details)}]")
            print()

    if dupes:
        print("DUPLICATES (Found multiple times)")
        print("-" * 80)
        for item in dupes:
            print(f"  Candidate: {item['query_file']}")
            if item['show_hash']:
                print(f"    Hash: {item['file_hash']}")
            print(f"    Duplicates ({len(item['matches'])}):")
            for match in item['matches']:
                print(f"      {_format_match_path(match)}")
                details = _match_details(conn, match, item['show_metadata'])
                print(f"        [{' | '.join(details)}]")
            print()

    print("=" * 80)
    print(f"Total: {len(not_found)} not found, {len(uniques)} unique, {len(dupes)} with duplicates")
    print("=" * 80)
    print()


def print_results_json(query_file: str, file_hash: str, matches: List[Dict],
                       conn: sqlite3.Connection, show_metadata: bool):
    output = {
        'query_file': query_file,
        'hash': file_hash,
        'match_count': len(matches),
        'matches': [],
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
  python3 locate_in_db.py --file photo.jpg --db-path media.db
  python3 locate_in_db.py --files photo1.jpg photo2.jpg --db-path media.db --metadata
        """,
    )

    parser.add_argument("--file", "--files", dest="files", action="append", default=[],
                        help="File(s) to search for (can be repeated)")
    parser.add_argument("--db-path", "--db", required=True, help="Path to media database")
    parser.add_argument("--metadata", "-m", action="store_true",
                        help="Show metadata for matching files")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--show-hash", action="store_true", help="Show file hash in output")
    parser.add_argument("--summary", "-s", action="store_true", help="Show only summary statistics")
    parser.add_argument("--limit", type=int, help="Limit number of files to process")

    args = parser.parse_args()

    if not args.files:
        parser.error("At least one file must be specified with --file")

    if not os.path.exists(args.db_path):
        print(f"Error: Database file does not exist: {args.db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(args.db_path)
    files_to_process = args.files
    if args.limit and args.limit > 0:
        files_to_process = files_to_process[:args.limit]

    total_files = 0
    total_matches = 0
    files_with_matches = 0
    results = []

    for file_path in files_to_process:
        if not os.path.exists(file_path):
            print(f"Warning: File not found: {file_path}", file=sys.stderr)
            continue

        total_files += 1
        try:
            file_hash = calculate_file_hash(file_path)
        except Exception as e:
            print(f"Error computing hash for {file_path}: {e}", file=sys.stderr)
            continue

        matches = find_by_hash(conn, file_hash)
        if matches:
            files_with_matches += 1
            total_matches += len(matches)

        if args.json:
            print_results_json(file_path, file_hash, matches, conn, args.metadata)
        else:
            results.append(print_results_text(
                file_path, file_hash, matches, conn, args.metadata, args.show_hash,
            ))

    if not args.json and not args.summary:
        print_grouped_results(results, conn)

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

    conn.close()


if __name__ == "__main__":
    main()
