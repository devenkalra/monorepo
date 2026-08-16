#!/usr/bin/env python3
"""Copy one user's local vacation_list data onto bldrdojo production.

Dumps from the local Docker backend, remaps ownership to the given email on
production (default: deven@kalra.com), and replaces that user's existing
vacation rows.

The vacation_list app must already be deployed and migrated on production.

Examples (from the monorepo root):

  python scripts/push_vacation_list_to_prod.py --dump-only -o vacation_list.json

  python scripts/push_vacation_list_to_prod.py --ssh deploy@YOUR_SERVER

  python scripts/push_vacation_list_to_prod.py --ssh deploy@YOUR_SERVER \\
      --email deven@kalra.com --replace
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
REMOTE_FIXTURE = '/tmp/vacation_list.json'
CONTAINER_FIXTURE = '/tmp/vacation_list.json'


def run(cmd, **kwargs):
    print('+ ' + ' '.join(cmd))
    return subprocess.run(cmd, check=True, **kwargs)


def dump_local(container: str, email: str, dest: Path) -> None:
    remote_tmp = '/tmp/vacation_list.json'
    run([
        'docker', 'exec', container,
        'python', 'manage.py', 'dump_vacation_fixture',
        '--email', email, '-o', remote_tmp,
    ])
    dest.parent.mkdir(parents=True, exist_ok=True)
    run(['docker', 'cp', f'{container}:{remote_tmp}', str(dest)])
    print(f'Wrote {dest} ({dest.stat().st_size} bytes)')


def push_via_ssh(args, fixture: Path) -> None:
    remote_host_path = REMOTE_FIXTURE
    run(['scp', str(fixture), f'{args.ssh}:{remote_host_path}'])
    replace_flag = ' --replace' if args.replace else ''
    remote_cmd = (
        f"cd '{args.repo_dir}' && "
        f"docker compose -p '{args.project}' -f '{args.compose_file}' "
        f"cp '{remote_host_path}' '{args.service}:{CONTAINER_FIXTURE}' && "
        f"docker compose -p '{args.project}' -f '{args.compose_file}' "
        f"exec -T '{args.service}' python manage.py import_vacation_fixture "
        f"'{CONTAINER_FIXTURE}' --email '{args.email}'{replace_flag}"
    )
    run(['ssh', args.ssh, remote_cmd])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--email', default=DEFAULT_EMAIL, help='Owner email on local and production')
    parser.add_argument('--local-container', default=DEFAULT_LOCAL_CONTAINER)
    parser.add_argument('-o', '--output', default='vacation_list.json', help='Local fixture path')
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
            print(f'Would scp to {args.ssh} and import into {args.service} (--replace={args.replace})')
        return 0

    dump_local(args.local_container, args.email, fixture)
    if args.dump_only or not args.ssh:
        if not args.ssh:
            print('\nFixture is ready. On the production host, after deploying this code:')
            print(f"  docker compose -p {args.project} -f {args.compose_file} cp {fixture.name} {args.service}:{CONTAINER_FIXTURE}")
            replace_flag = ' --replace' if args.replace else ''
            print(
                f"  docker compose -p {args.project} -f {args.compose_file} exec -T {args.service} "
                f"python manage.py import_vacation_fixture {CONTAINER_FIXTURE} --email {args.email}{replace_flag}"
            )
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
