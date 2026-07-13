#!/usr/bin/env python3
"""manage_volumes.py - Register and query logical volume to mount-path mappings."""

import argparse
import os
import sqlite3
import sys

from media_utils import (
    create_database_schema,
    get_volume,
    list_volumes,
    normalize_volume_name,
    normalize_path,
    clean_mount_path,
    resolve_file_path,
    set_volume,
)


def cmd_set(args, conn: sqlite3.Connection):
    raw_mount = args.mount
    mount_path = normalize_path(clean_mount_path(raw_mount))
    if not os.path.isdir(mount_path):
        print(f"Error: mount path is not a directory: {mount_path}", file=sys.stderr)
        if raw_mount != clean_mount_path(raw_mount) or '"' in raw_mount:
            print(
                'Hint: In PowerShell, "d:\\" escapes the closing quote. '
                "Use --mount D:\\  or  --mount 'd:\\'",
                file=sys.stderr,
            )
        sys.exit(1)

    record = set_volume(conn, args.name, args.src_root, mount_path)
    print(f"Volume '{record['name']}' registered")
    print(f"  src_root:   {record['src_root']}")
    print(f"  mount_path: {record['mount_path']}")
    print(f"  updated_at: {record['updated_at']}")


def cmd_list(args, conn: sqlite3.Connection):
    volumes = list_volumes(conn)
    if not volumes:
        print("No volumes registered.")
        return

    for vol in volumes:
        print(f"{vol['name']}")
        print(f"  src_root:   {vol['src_root']}")
        print(f"  mount_path: {vol['mount_path']}")
        print(f"  updated_at: {vol['updated_at']}")
        print()


def cmd_show(args, conn: sqlite3.Connection):
    vol = get_volume(conn, args.name)
    if not vol:
        print(f"Error: volume not found: {args.name}", file=sys.stderr)
        sys.exit(1)

    print(f"name:       {vol['name']}")
    print(f"src_root:   {vol['src_root']}")
    print(f"mount_path: {vol['mount_path']}")
    print(f"updated_at: {vol['updated_at']}")

    if not os.path.isdir(vol['mount_path']):
        print(f"warning:    mount path is not currently accessible", file=sys.stderr)


def cmd_resolve(args, conn: sqlite3.Connection):
    vol = get_volume(conn, args.name)
    if not vol:
        print(f"Error: volume not found: {args.name}", file=sys.stderr)
        sys.exit(1)

    resolved = resolve_file_path(vol['mount_path'], args.relpath)
    print(resolved)


def main():
    parser = argparse.ArgumentParser(
        description="Manage logical volume name to mount-path mappings.",
    )
    parser.add_argument(
        '--db-path', default='media_index.db',
        help='Path to SQLite database (default: media_index.db)',
    )

    subparsers = parser.add_subparsers(dest='command', required=True)

    set_parser = subparsers.add_parser('set', help='Register or update a volume')
    set_parser.add_argument('name', help='Logical volume name (case-insensitive)')
    set_parser.add_argument('--src-root', required=True,
                            help='Canonical source path (e.g. /volume1/photo)')
    set_parser.add_argument('--mount', required=True,
                            help='Locally mounted path (e.g. P:/ or /mnt/photo)')

    subparsers.add_parser('list', help='List registered volumes')

    show_parser = subparsers.add_parser('show', help='Show one volume')
    show_parser.add_argument('name', help='Volume name')

    resolve_parser = subparsers.add_parser(
        'resolve', help='Resolve a stored relpath to a local absolute path',
    )
    resolve_parser.add_argument('name', help='Volume name')
    resolve_parser.add_argument('relpath', help='Relative path within the volume')

    args = parser.parse_args()

    conn = sqlite3.connect(args.db_path)
    create_database_schema(conn)

    if args.command == 'set':
        cmd_set(args, conn)
    elif args.command == 'list':
        cmd_list(args, conn)
    elif args.command == 'show':
        cmd_show(args, conn)
    elif args.command == 'resolve':
        cmd_resolve(args, conn)

    conn.close()


if __name__ == '__main__':
    main()
