#!/usr/bin/env python3
"""Copy one user's local trips data onto bldrdojo production.

Dumps from the local Docker backend, remaps ownership to the given email on
production (default: deven@kalra.com), and replaces that user's existing trips.

The trips app must already be deployed and migrated on production. If the
import command is not in the running image yet, this script copies it into
the container before importing.

Examples (from the monorepo root, on your local machine):

  python scripts/push_trips_to_prod.py --dump-only -o trips.json

  python scripts/push_trips_to_prod.py --ssh deploy@bldrdojo.com

  python scripts/push_trips_to_prod.py --ssh deploy@bldrdojo.com --email deven@kalra.com
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


DEFAULT_EMAIL = 'deven@kalra.com'
DEFAULT_LOCAL_CONTAINER = 'bldrdojo-local-backend'
DEFAULT_REPO_DIR = '/home/deploy/apps/monorepo'
DEFAULT_COMPOSE_FILE = 'docker-compose.production.yml'
DEFAULT_PROJECT = 'data-backend'
DEFAULT_SERVICE = 'backend'
IMPORT_COMMAND = Path(__file__).resolve().parents[1] / 'data-backend' / 'trips' / 'management' / 'commands' / 'import_trip_fixture.py'


def run(cmd, **kwargs):
    print('+ ' + ' '.join(cmd))
    return subprocess.run(cmd, check=True, **kwargs)


def _json_from_manage_stdout(text: str) -> str:
    stripped = text.lstrip()
    if stripped.startswith('{'):
        return stripped
    start = text.find('\n{')
    if start == -1:
        raise RuntimeError('dump_trip_fixture did not print a JSON object')
    return text[start + 1 :]


def dump_local(container: str, email: str, dest: Path) -> None:
    cmd = [
        'docker', 'exec', container,
        'python', 'manage.py', 'dump_trip_fixture',
        '--email', email,
    ]
    print('+ ' + ' '.join(cmd))
    proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    if proc.stderr:
        print(proc.stderr, end='')
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(_json_from_manage_stdout(proc.stdout), encoding='utf-8')
    print(f'Wrote {dest} ({dest.stat().st_size} bytes)')


def push_via_ssh(args, fixture: Path) -> None:
    replace_flag = ' --replace' if args.replace else ''
    remote_importer = '/tmp/import_trip_fixture.py'
    print(f'+ scp {IMPORT_COMMAND} {args.ssh}:{remote_importer}')
    subprocess.run(['scp', str(IMPORT_COMMAND), f'{args.ssh}:{remote_importer}'], check=True)
    install = (
        f"cd '{args.repo_dir}' && "
        f"docker compose -p '{args.project}' -f '{args.compose_file}' "
        f"cp '{remote_importer}' '{args.service}:/app/trips/management/commands/import_trip_fixture.py'"
    )
    print(f'+ ssh {args.ssh} {install}')
    subprocess.run(['ssh', args.ssh, install], check=True)

    import_cmd = (
        f"cd '{args.repo_dir}' && "
        f"docker compose -p '{args.project}' -f '{args.compose_file}' "
        f"exec -T '{args.service}' python manage.py import_trip_fixture "
        f"- --email '{args.email}'{replace_flag}"
    )
    print(f'+ ssh {args.ssh} {import_cmd}')
    with fixture.open('rb') as fh:
        subprocess.run(['ssh', args.ssh, import_cmd], check=True, stdin=fh)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--email', default=DEFAULT_EMAIL, help='Owner email on local and production')
    parser.add_argument('--local-container', default=DEFAULT_LOCAL_CONTAINER)
    parser.add_argument('-o', '--output', default='trips.json', help='Local fixture path')
    parser.add_argument('--ssh', help='user@host of the production server')
    parser.add_argument('--repo-dir', default=DEFAULT_REPO_DIR)
    parser.add_argument('--compose-file', default=DEFAULT_COMPOSE_FILE)
    parser.add_argument('--project', default=DEFAULT_PROJECT)
    parser.add_argument('--service', default=DEFAULT_SERVICE)
    parser.add_argument('--replace', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--dump-only', action='store_true', help='Write the fixture and stop')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    fixture = Path(args.output).resolve()
    if args.dry_run:
        print(f'Would dump {args.email} from {args.local_container} to {fixture}')
        if args.ssh:
            print(f'Would ssh to {args.ssh} and import into {args.service} (--replace={args.replace})')
        return 0

    dump_local(args.local_container, args.email, fixture)
    if args.dump_only or not args.ssh:
        if not args.ssh:
            print('\nFixture is ready. From this machine:')
            print(f'  python scripts/push_trips_to_prod.py --ssh deploy@YOUR_SERVER --email {args.email}')
        return 0

    push_via_ssh(args, fixture)
    print('Done.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f'Command failed with exit {exc.returncode}', file=sys.stderr)
        raise SystemExit(exc.returncode)
