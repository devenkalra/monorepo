#!/usr/bin/env python3
"""search_media.py - Search the media index database and inspect results."""

import argparse
import base64
import json
import os
import re
import sqlite3
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from media_utils import (
    calculate_file_hash,
    find_files_by_hash,
    get_indexable_file_type,
    get_volume,
    lookup_file_by_abs_path,
    lookup_file_by_id,
    lookup_file_by_volume_relpath,
    normalize_date_filter,
    normalize_thumbnail_blob,
    normalize_volume_name,
    resolve_file_path,
    sql_file_date_ymd,
    SQL_DATE_TAKEN_YMD,
)

DEFAULT_LIMIT = 50
MAX_OPEN_FILES = 5
VALID_SHOW_MODES = frozenset({'basic', 'metadata', 'thumbnail', 'full'})
SHOW_ALIASES = {'file': 'full'}
FILES_COLUMNS = (
    'id', 'volume', 'relpath', 'name', 'created_date', 'modified_date',
    'size', 'mime_type', 'extension', 'file_hash', 'indexed_date',
)


def format_size(size_bytes: Optional[int]) -> str:
    if size_bytes is None:
        return '-'
    size = float(size_bytes)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def safe_filename(name: str) -> str:
    return re.sub(r'[^\w.\-]+', '_', name)


def open_path(path: str):
    """Open a path with the system default application (non-blocking)."""
    if sys.platform == 'win32':
        subprocess.Popen(['cmd', '/c', 'start', '', os.path.normpath(path)])
    elif sys.platform == 'darwin':
        subprocess.Popen(['open', path])
    else:
        subprocess.Popen(['xdg-open', path])


class FileOpener:
    """Open up to max_count files without blocking on each launch."""

    def __init__(self, enabled: bool, max_count: int = MAX_OPEN_FILES):
        self.enabled = enabled
        self.max_count = max_count
        self.opened_count = 0
        self.skipped_count = 0
        self.opened_paths: List[str] = []

    def try_open(self, path: Optional[str], quiet: bool = False) -> bool:
        if not self.enabled or not path or not os.path.exists(path):
            return False
        if self.opened_count >= self.max_count:
            self.skipped_count += 1
            return False
        if not quiet:
            print(f"Opening: {path}")
        open_path(path)
        self.opened_paths.append(path)
        self.opened_count += 1
        return True

    def report_skipped(self):
        if self.skipped_count:
            print(
                f"Skipped opening {self.skipped_count} more file(s) "
                f"(--show full limit is {self.max_count})",
                file=sys.stderr,
            )


def parse_show_arg(value: str) -> set:
    """Parse a comma-separated --show value into a set of modes."""
    modes = set()
    for part in value.split(','):
        part = part.strip().lower()
        if not part:
            continue
        part = SHOW_ALIASES.get(part, part)
        if part not in VALID_SHOW_MODES:
            raise argparse.ArgumentTypeError(
                f"unknown show mode '{part}' (choose: {', '.join(sorted(VALID_SHOW_MODES))})"
            )
        modes.add(part)
    if not modes:
        raise argparse.ArgumentTypeError('--show requires at least one mode')
    return modes


def merge_show_modes(show_args: Optional[List[set]]) -> set:
    """Merge repeated --show flags into one additive set (default: basic)."""
    if not show_args:
        return {'basic'}
    merged: set = set()
    for modes in show_args:
        merged |= modes
    return merged


def get_type_metadata(conn: sqlite3.Connection, file_id: int, mime_type: str,
                      extension: str = '') -> Optional[Dict]:
    """Load type-specific metadata for a file."""
    cursor = conn.cursor()
    file_type = get_indexable_file_type(mime_type or '', extension or '')

    if file_type == 'image':
        cursor.execute("""
            SELECT width, height, date_taken, camera_make, camera_model, lens_model,
                   latitude, longitude, city, state, country, keywords, caption
            FROM image_metadata WHERE file_id = ?
        """, (file_id,))
        row = cursor.fetchone()
        if row:
            return {
                'type': 'image',
                'width': row[0], 'height': row[1], 'date_taken': row[2],
                'camera_make': row[3], 'camera_model': row[4], 'lens_model': row[5],
                'latitude': row[6], 'longitude': row[7],
                'city': row[8], 'state': row[9], 'country': row[10],
                'keywords': row[11], 'caption': row[12],
            }

    if file_type == 'video':
        cursor.execute("""
            SELECT width, height, duration_seconds, frame_rate, video_codec,
                   audio_channels, audio_bit_rate_kbps
            FROM video_metadata WHERE file_id = ?
        """, (file_id,))
        row = cursor.fetchone()
        if row:
            return {
                'type': 'video',
                'width': row[0], 'height': row[1], 'duration_seconds': row[2],
                'frame_rate': row[3], 'video_codec': row[4],
                'audio_channels': row[5], 'audio_bit_rate_kbps': row[6],
            }

    if file_type == 'audio':
        cursor.execute("""
            SELECT duration_seconds, audio_codec, bit_rate_kbps, sample_rate,
                   channels, title, artist, album
            FROM audio_metadata WHERE file_id = ?
        """, (file_id,))
        row = cursor.fetchone()
        if row:
            return {
                'type': 'audio',
                'duration_seconds': row[0], 'audio_codec': row[1],
                'bit_rate_kbps': row[2], 'sample_rate': row[3], 'channels': row[4],
                'title': row[5], 'artist': row[6], 'album': row[7],
            }

    if file_type == 'document':
        cursor.execute("""
            SELECT page_count, title, author, text_preview
            FROM document_metadata WHERE file_id = ?
        """, (file_id,))
        row = cursor.fetchone()
        if row:
            return {
                'type': 'document',
                'page_count': row[0], 'title': row[1],
                'author': row[2], 'text_preview': row[3],
            }

    if file_type == 'email':
        cursor.execute("""
            SELECT message_id, subject, sender, recipients, cc, email_date,
                   has_attachments, attachment_count
            FROM email_metadata WHERE file_id = ?
        """, (file_id,))
        row = cursor.fetchone()
        if row:
            return {
                'type': 'email',
                'message_id': row[0], 'subject': row[1], 'sender': row[2],
                'recipients': row[3], 'cc': row[4], 'email_date': row[5],
                'has_attachments': bool(row[6]), 'attachment_count': row[7],
            }

    return None


def get_thumbnail_info(conn: sqlite3.Connection, file_id: int) -> Optional[Dict]:
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, thumbnail_width, thumbnail_height, length(thumbnail_data), created_at
        FROM thumbnails WHERE file_id = ?
    """, (file_id,))
    row = cursor.fetchone()
    if not row:
        return None
    return {
        'thumbnail_id': row[0],
        'thumbnail_width': row[1],
        'thumbnail_height': row[2],
        'thumbnail_bytes': row[3],
        'created_at': row[4],
    }


def fetch_thumbnail_blob(conn: sqlite3.Connection, file_id: int) -> Optional[bytes]:
    cursor = conn.cursor()
    cursor.execute("SELECT thumbnail_data FROM thumbnails WHERE file_id = ?", (file_id,))
    row = cursor.fetchone()
    return row[0] if row else None


def enrich_record(conn: sqlite3.Connection, record: Dict,
                  include_metadata: bool = False,
                  include_thumbnail: bool = False) -> Dict:
    """Attach resolved path and optional metadata/thumbnail info."""
    volume = get_volume(conn, record['volume'])
    record = dict(record)
    record['resolved_path'] = (
        resolve_file_path(volume['mount_path'], record['relpath'])
        if volume else record['relpath']
    )
    record['exists'] = os.path.exists(record['resolved_path'])
    if include_metadata:
        record['metadata'] = get_type_metadata(
            conn, record['id'], record.get('mime_type', ''), record.get('extension', ''),
        )
    if include_thumbnail:
        record['thumbnail'] = get_thumbnail_info(conn, record['id'])
    return record


def write_thumbnail(record: Dict, output_dir: str, conn: sqlite3.Connection) -> Optional[str]:
    blob = fetch_thumbnail_blob(conn, record['id'])
    if not blob:
        return None
    base = f"{record['id']}_{safe_filename(record['name'])}"
    if not base.lower().endswith('.jpg'):
        base += '.jpg'
    out_path = os.path.join(output_dir, base)
    with open(out_path, 'wb') as f:
        f.write(blob)
    return out_path


def build_thumbnail_gallery_html(records: Sequence[Dict], conn: sqlite3.Connection,
                                 grid_cols: int, title: str = 'Media thumbnails') -> Tuple[str, int]:
    """Build an HTML page with thumbnails in a CSS grid. Returns (html, count)."""
    cards: List[str] = []
    for rec in records:
        blob = fetch_thumbnail_blob(conn, rec['id'])
        if not blob:
            continue
        jpeg, width, height = normalize_thumbnail_blob(blob)
        if not width or not height:
            thumb = rec.get('thumbnail') or {}
            width = thumb.get('thumbnail_width') or 0
            height = thumb.get('thumbnail_height') or 0
        b64 = base64.b64encode(jpeg).decode('ascii')
        caption = (
            f"<strong>#{rec['id']}</strong> {rec['name']}<br>"
            f"<span class='relpath'>{rec['relpath']}</span>"
        )
        size_attrs = f' width="{width}" height="{height}"' if width and height else ''
        cards.append(
            f"<figure class='card'>"
            f"<img src='data:image/jpeg;base64,{b64}' alt='{rec['name']}'{size_attrs}>"
            f"<figcaption>{caption}</figcaption>"
            f"</figure>"
        )

    if not cards:
        return '', 0

    cols = max(1, min(grid_cols, len(cards)))
    grid = '\n'.join(cards)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <style>
    body {{
      font-family: system-ui, sans-serif;
      margin: 1.5rem;
      background: #1a1a1a;
      color: #eee;
    }}
    h1 {{ margin-top: 0; font-size: 1.25rem; font-weight: 600; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat({cols}, max-content);
      gap: 16px;
      align-items: start;
      justify-content: start;
    }}
    .card {{
      margin: 0;
      background: #2a2a2a;
      border-radius: 8px;
      overflow: hidden;
      box-shadow: 0 2px 8px rgba(0,0,0,.35);
      width: max-content;
      max-width: 100%;
    }}
    .card img {{
      display: block;
      width: auto;
      height: auto;
      max-width: none;
      background: #111;
    }}
    figcaption {{
      padding: 8px 10px;
      font-size: 12px;
      line-height: 1.35;
    }}
    .relpath {{ color: #aaa; word-break: break-all; }}
  </style>
</head>
<body>
  <h1>{title} ({len(cards)})</h1>
  <div class="grid">
{grid}
  </div>
</body>
</html>
"""
    return html, len(cards)


def display_thumbnail_grid(records: Sequence[Dict], conn: sqlite3.Connection,
                           html_path: str, grid_cols: int, title: str = 'Media thumbnails') -> Optional[str]:
    """Write thumbnail grid HTML and open it in the default browser."""
    html, count = build_thumbnail_gallery_html(records, conn, grid_cols, title=title)
    if count == 0:
        print('No thumbnails to display.', file=sys.stderr)
        return None

    os.makedirs(os.path.dirname(html_path) or '.', exist_ok=True)
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)

    uri = Path(html_path).resolve().as_uri()
    if not webbrowser.open(uri):
        print(f"Thumbnail grid saved to: {html_path}", file=sys.stderr)
    else:
        print(f"Thumbnail grid ({count} images, {grid_cols} columns): {html_path}")
    return html_path


def resolve_direct_lookups(conn: sqlite3.Connection, args) -> List[Dict]:
    """Resolve explicit id/relpath/path/hash lookups."""
    found: Dict[int, Dict] = {}

    for file_id in args.id or []:
        record = lookup_file_by_id(conn, int(file_id))
        if record:
            found[record['id']] = record

    volume = normalize_volume_name(args.volume) if args.volume else None
    for relpath in args.relpath or []:
        rel = relpath.replace('\\', '/').lstrip('/')
        if volume:
            record = lookup_file_by_volume_relpath(conn, volume, rel)
            if record:
                found[record['id']] = record
            continue
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT {', '.join(FILES_COLUMNS)} FROM files
            WHERE relpath = ? OR relpath LIKE ?
            ORDER BY id LIMIT 20
        """, (rel, f'%/{rel}'))
        for row in cursor.fetchall():
            record = _row_to_record(row)
            found[record['id']] = record

    for file_hash in args.hash or []:
        for record in find_files_by_hash(conn, file_hash):
            found[record['id']] = record

    for path in args.path or []:
        if path.strip().isdigit():
            record = lookup_file_by_id(conn, int(path.strip()))
            if record:
                found[record['id']] = record
            continue
        if os.path.exists(path):
            record = lookup_file_by_abs_path(conn, path)
            if record:
                found[record['id']] = record
                continue
            computed = calculate_file_hash(path)
            if computed:
                for record in find_files_by_hash(conn, computed):
                    found[record['id']] = record

    return list(found.values())


def _row_to_record(row: tuple) -> Dict:
    return dict(zip(FILES_COLUMNS, row))


def build_search_query(args) -> Tuple[str, List[Any]]:
    """Build SQL for filter-based search."""
    joins: List[str] = []
    conditions: List[str] = []
    params: List[Any] = []

    if args.volume:
        conditions.append('f.volume = ?')
        params.append(normalize_volume_name(args.volume))

    if args.name:
        conditions.append('f.name LIKE ?')
        params.append(f'%{args.name}%')

    if args.name_pattern:
        conditions.append('f.name LIKE ?')
        params.append(args.name_pattern)

    if args.relpath_pattern:
        conditions.append('f.relpath LIKE ?')
        params.append(args.relpath_pattern.replace('\\', '/'))

    if args.extension:
        ext = args.extension if args.extension.startswith('.') else f'.{args.extension}'
        conditions.append('LOWER(f.extension) = ?')
        params.append(ext.lower())

    if args.mime:
        if args.mime.endswith('%'):
            conditions.append('f.mime_type LIKE ?')
        else:
            conditions.append('f.mime_type = ?')
        params.append(args.mime)

    for field, after, before in (
        ('f.indexed_date', args.indexed_after, args.indexed_before),
        ('f.modified_date', args.modified_after, args.modified_before),
        ('f.created_date', args.created_after, args.created_before),
    ):
        ymd = sql_file_date_ymd(field)
        if after:
            conditions.append(f'{field} IS NOT NULL AND {ymd} >= ?')
            params.append(normalize_date_filter(after))
        if before:
            conditions.append(f'{field} IS NOT NULL AND {ymd} <= ?')
            params.append(normalize_date_filter(before))

    metadata_terms: List[str] = []
    if args.metadata:
        metadata_terms.append(f'%{args.metadata}%')
    if args.keywords:
        metadata_terms.append(f'%{args.keywords}%')
    if args.city:
        metadata_terms.append(f'%{args.city}%')
    if args.camera:
        metadata_terms.append(f'%{args.camera}%')

    if metadata_terms or args.date_taken_after or args.date_taken_before:
        joins.append('LEFT JOIN image_metadata im ON im.file_id = f.id')

    if args.date_taken_after:
        conditions.append(f'im.date_taken IS NOT NULL AND {SQL_DATE_TAKEN_YMD} >= ?')
        params.append(normalize_date_filter(args.date_taken_after))
    if args.date_taken_before:
        conditions.append(f'im.date_taken IS NOT NULL AND {SQL_DATE_TAKEN_YMD} <= ?')
        params.append(normalize_date_filter(args.date_taken_before))

    if metadata_terms:
        joins.append('LEFT JOIN document_metadata dm ON dm.file_id = f.id')
        joins.append('LEFT JOIN email_metadata em ON em.file_id = f.id')
        meta_clauses = []
        for term in metadata_terms:
            meta_clauses.append("""(
                im.keywords LIKE ? OR im.caption LIKE ? OR im.city LIKE ?
                OR im.state LIKE ? OR im.country LIKE ?
                OR im.camera_make LIKE ? OR im.camera_model LIKE ?
                OR dm.title LIKE ? OR dm.author LIKE ? OR dm.text_preview LIKE ?
                OR em.subject LIKE ? OR em.sender LIKE ? OR em.recipients LIKE ?
            )""")
            params.extend([term] * 13)
        conditions.append('(' + ' OR '.join(meta_clauses) + ')')

    if args.min_size is not None:
        conditions.append('f.size >= ?')
        params.append(args.min_size)
    if args.max_size is not None:
        conditions.append('f.size <= ?')
        params.append(args.max_size)

    join_sql = '\n'.join(joins)
    where_sql = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''
    order = args.order_by or 'f.indexed_date DESC'

    sql = f"""
        SELECT DISTINCT f.{', f.'.join(FILES_COLUMNS)}
        FROM files f
        {join_sql}
        {where_sql}
        ORDER BY {order}
    """
    return sql, params


def append_pagination(sql: str, args) -> str:
    """Append LIMIT/OFFSET for paginated search results."""
    start = max(0, int(args.start or 0))
    if args.all:
        if start:
            return sql + f' LIMIT -1 OFFSET {start}'
        return sql
    limit = int(args.limit or DEFAULT_LIMIT)
    if start:
        return sql + f' LIMIT {limit} OFFSET {start}'
    return sql + f' LIMIT {limit}'


def search_files(conn: sqlite3.Connection, args) -> List[Dict]:
    direct = resolve_direct_lookups(conn, args)
    if direct and not _has_filter_criteria(args, exclude_direct=True):
        return direct

    sql, params = build_search_query(args)
    sql = append_pagination(sql, args)

    cursor = conn.cursor()
    cursor.execute(sql, params)
    rows = [_row_to_record(row) for row in cursor.fetchall()]

    if direct:
        seen = {r['id'] for r in rows}
        for record in direct:
            if record['id'] not in seen:
                rows.insert(0, record)
    return rows


def _has_filter_criteria(args, exclude_direct: bool = False) -> bool:
    direct_fields = [] if exclude_direct else ['id', 'relpath', 'path', 'hash']
    for field in direct_fields:
        if getattr(args, field, None):
            return True
    return any([
        args.volume, args.name, args.name_pattern, args.relpath_pattern,
        args.extension, args.mime, args.metadata, args.keywords, args.city,
        args.camera, args.indexed_after, args.indexed_before,
        args.modified_after, args.modified_before,
        args.created_after, args.created_before,
        args.date_taken_after, args.date_taken_before,
        args.min_size is not None, args.max_size is not None,
    ])


def count_matches(conn: sqlite3.Connection, args) -> int:
    sql, params = build_search_query(args)
    count_sql = f'SELECT COUNT(*) FROM ({sql})'
    return conn.execute(count_sql, params).fetchone()[0]


def print_basic_table(records: Sequence[Dict]):
    print(f"{'ID':>7}  {'Vol':<8}  {'Size':>9}  {'Indexed':<20}  {'Relpath'}")
    print('-' * 100)
    for rec in records:
        indexed = (rec.get('indexed_date') or '')[:19]
        print(
            f"{rec['id']:>7}  {rec['volume']:<8}  {format_size(rec.get('size')):>9}  "
            f"{indexed:<20}  {rec['relpath']}"
        )


def print_thumbnail_table(records: Sequence[Dict]):
    """Print a compact table of thumbnail availability."""
    print(f"{'ID':>7}  {'Thumb':>5}  {'Bytes':>7}  {'Dims':>11}  {'Relpath'}")
    print('-' * 100)
    for rec in records:
        thumb = rec.get('thumbnail')
        if thumb:
            dims = f"{thumb['thumbnail_width']}x{thumb['thumbnail_height']}"
            print(
                f"{rec['id']:>7}  {'yes':>5}  {thumb['thumbnail_bytes']:>7}  "
                f"{dims:>11}  {rec['relpath']}"
            )
        else:
            print(f"{rec['id']:>7}  {'no':>5}  {0:>7}  {'-':>11}  {rec['relpath']}")


def print_record_details(records: Sequence[Dict], show: set):
    """Print per-record details for metadata and/or non-table modes."""
    for rec in records:
        print(f"\n{'=' * 80}")
        print(f"ID:       {rec['id']}")
        print(f"Volume:   {rec['volume']}")
        print(f"Relpath:  {rec['relpath']}")
        print(f"Name:     {rec['name']}")
        print(f"Path:     {rec.get('resolved_path', '')}")
        print(f"Exists:   {rec.get('exists', False)}")
        print(f"Size:     {format_size(rec.get('size'))} ({rec.get('size')})")
        print(f"MIME:     {rec.get('mime_type')}")
        print(f"Hash:     {rec.get('file_hash')}")
        print(f"Created:  {rec.get('created_date')}")
        print(f"Modified: {rec.get('modified_date')}")
        print(f"Indexed:  {rec.get('indexed_date')}")

        if 'metadata' in show:
            if rec.get('metadata'):
                print('Metadata:')
                for key, value in rec['metadata'].items():
                    if value is not None and value != '':
                        print(f"  {key}: {value}")
            else:
                print('Metadata: (none)')

        if 'thumbnail' in show:
            thumb = rec.get('thumbnail')
            if thumb:
                created = thumb.get('created_at') or '(unknown)'
                print(
                    f"Thumbnail: {thumb['thumbnail_width']}x{thumb['thumbnail_height']}, "
                    f"{thumb['thumbnail_bytes']} bytes, created {created}"
                )
            else:
                print('Thumbnail: (none)')
            saved = rec.get('thumbnail_path')
            if saved:
                print(f"Thumbnail saved: {saved}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Search the media index database and inspect matching files.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic search by name
  python3 search_media.py --db-path files.db --name vacation

  # Metadata text search with details
  python3 search_media.py --db-path files.db --metadata "Fort Worth" --show metadata

  # Date range on indexed files
  python3 search_media.py --db-path files.db --indexed-after 2024-01-01 --volume photo

  # Lookup by id and open files on disk
  python3 search_media.py --db-path files.db --id 42 --show full

  # Thumbnails plus metadata (additive)
  python3 search_media.py --db-path files.db --relpath-pattern "1984/%%" --show thumbnail,metadata

  # Thumbnail grid in browser
  python3 search_media.py --db-path files.db --relpath-pattern "1984/%%" --show thumbnail --limit 8 --grid-cols 4

  # JSON output
  python3 search_media.py --db-path files.db --hash abc123... --json
        """,
    )
    parser.add_argument('--db-path', required=True, help='Path to SQLite database')

    lookup = parser.add_argument_group('direct lookup')
    lookup.add_argument('--id', action='append', type=int, help='File id (repeatable)')
    lookup.add_argument('--relpath', action='append', help='Stored relpath (repeatable)')
    lookup.add_argument('--path', '--file', dest='path', action='append',
                        help='Local filesystem path (repeatable)')
    lookup.add_argument('--hash', action='append', help='SHA-256 file hash (repeatable)')

    filters = parser.add_argument_group('search filters')
    filters.add_argument('--volume', help='Volume name')
    filters.add_argument('--name', help='Filename substring search')
    filters.add_argument('--name-pattern', help='Filename SQL LIKE pattern (e.g. %.jpg)')
    filters.add_argument('--relpath-pattern', help='Relpath SQL LIKE pattern')
    filters.add_argument('--extension', help='File extension (with or without dot)')
    filters.add_argument('--mime', help='MIME type (supports trailing %% wildcard)')
    filters.add_argument('--metadata', help='Search text across metadata fields')
    filters.add_argument('--keywords', help='Search image keywords')
    filters.add_argument('--city', help='Search image city metadata')
    filters.add_argument('--camera', help='Search camera make/model')
    filters.add_argument('--indexed-after', help='Indexed on or after (ISO date)')
    filters.add_argument('--indexed-before', help='Indexed on or before (ISO date)')
    filters.add_argument('--modified-after', help='Modified on or after (ISO date)')
    filters.add_argument('--modified-before', help='Modified on or before (ISO date)')
    filters.add_argument('--created-after', help='Created on or after (ISO date)')
    filters.add_argument('--created-before', help='Created on or before (ISO date)')
    filters.add_argument('--date-taken-after', help='EXIF date taken on or after')
    filters.add_argument('--date-taken-before', help='EXIF date taken on or before')
    filters.add_argument('--min-size', type=int, help='Minimum file size in bytes')
    filters.add_argument('--max-size', type=int, help='Maximum file size in bytes')

    output = parser.add_argument_group('output')
    output.add_argument(
        '--show', action='append', type=parse_show_arg, metavar='MODES',
        help='Comma-separated modes (additive): basic (default), metadata, thumbnail, full. '
             'thumbnail opens a grid gallery in your browser.',
    )
    output.add_argument('--json', action='store_true', help='Print results as JSON')
    output.add_argument('--count-only', action='store_true', help='Print match count only')
    output.add_argument('--limit', type=int, default=DEFAULT_LIMIT,
                        help=f'Max results for open-ended searches (default {DEFAULT_LIMIT})')
    output.add_argument('--start', '-s', type=int, default=0,
                        help='Skip this many results before applying --limit (default 0)')
    output.add_argument('--all', action='store_true', help='Return all matches (no limit)')
    output.add_argument('--order-by', default='f.indexed_date DESC',
                        help='SQL ORDER BY clause (default: f.indexed_date DESC)')
    output.add_argument('--output-dir', '-o', default='thumbnails_out',
                        help='Directory for saved thumbnail JPEGs and gallery HTML')
    output.add_argument('--grid-cols', type=int, default=4,
                        help='Columns in the thumbnail grid gallery (default 4)')
    output.add_argument('--no-save', action='store_true',
                        help='Do not write individual thumbnail JPEG files (grid still displays)')
    output.add_argument('--no-grid', action='store_true',
                        help='With --show thumbnail: skip opening the browser grid gallery')

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not _has_filter_criteria(args):
        parser.error('Provide at least one lookup or search filter')

    show = merge_show_modes(args.show)
    include_metadata = 'metadata' in show or args.json
    include_thumbnail = 'thumbnail' in show or args.json

    conn = sqlite3.connect(args.db_path)

    if args.count_only:
        if resolve_direct_lookups(conn, args) and not _has_filter_criteria(args, exclude_direct=True):
            count = len(resolve_direct_lookups(conn, args))
        else:
            count = count_matches(conn, args)
        print(count)
        conn.close()
        return 0

    records = search_files(conn, args)
    if not records:
        print('No matching files found.', file=sys.stderr)
        conn.close()
        return 1

    enriched = [
        enrich_record(conn, rec, include_metadata=include_metadata,
                      include_thumbnail=include_thumbnail)
        for rec in records
    ]

    saved_thumbs: Dict[int, Optional[str]] = {}
    gallery_path: Optional[str] = None
    if 'thumbnail' in show and not args.json:
        os.makedirs(args.output_dir, exist_ok=True)
        if not args.no_save:
            for rec in enriched:
                path = write_thumbnail(rec, args.output_dir, conn)
                saved_thumbs[rec['id']] = path
                rec['thumbnail_path'] = path
        if not args.no_grid:
            gallery_path = display_thumbnail_grid(
                enriched, conn,
                os.path.join(args.output_dir, 'thumbnail_grid.html'),
                grid_cols=args.grid_cols,
            )
            if gallery_path:
                for rec in enriched:
                    rec['gallery_path'] = gallery_path

    if 'full' in show:
        opener = FileOpener(True)
        for rec in enriched:
            path = rec.get('resolved_path')
            if path and os.path.exists(path):
                opened = opener.try_open(path)
                if args.json:
                    rec['opened'] = opened
            elif not args.json:
                print(f"File not found on disk: {path}", file=sys.stderr)
        opener.report_skipped()

    if args.json:
        payload = []
        for rec in enriched:
            item = {k: v for k, v in rec.items() if k != 'thumbnail' or v is not None}
            payload.append(item)
        print(json.dumps(payload, indent=2, default=str))
    else:
        if 'basic' in show:
            if 'thumbnail' in show:
                print_thumbnail_table(enriched)
            else:
                print_basic_table(enriched)
        elif 'thumbnail' in show:
            print_thumbnail_table(enriched)

        if 'metadata' in show:
            print_record_details(enriched, show)

        if 'basic' in show and len(enriched) == (args.limit or DEFAULT_LIMIT) and not args.all and _has_filter_criteria(args, exclude_direct=True):
            total = count_matches(conn, args)
            if total > (args.start or 0) + len(enriched):
                start = args.start or 0
                end = start + len(enriched)
                print(
                    f"\n(showing {start + 1}-{end} of {total} matches; "
                    f"use --start / --limit or --all to see more)"
                )

        if 'thumbnail' in show:
            missing = [rec['id'] for rec in enriched if not rec.get('thumbnail')]
            if missing:
                print(f"\nNo thumbnail stored for file id(s): {', '.join(map(str, missing))}")

    conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
