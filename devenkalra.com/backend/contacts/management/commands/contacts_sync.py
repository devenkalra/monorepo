"""Command-line contact sync, sharing the engine, safety checks and run history with the web app.

  python manage.py contacts_sync check
  python manage.py contacts_sync google [--full] [--photos] [--writeback] [--rename-tasks] [--token-file token.json]
  python manage.py contacts_sync linkedin Connections.csv [--messages messages.csv]
  python manage.py contacts_sync whatsapp export.json [--no-create] [--only-saved] [--trust-exact-names]
  python manage.py contacts_sync merge SURVIVOR_TASK_ID LOSER_TASK_ID
  python manage.py contacts_sync export [--out contacts.json]
  python manage.py contacts_sync import contacts.json --people-list ID [--orgs-list ID]

Every command is a dry run unless you add --apply --max-writes N (and the server allows live writes).
"""
import shutil
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError

from contacts.engine import WriteGuard, open_list
from contacts.engine.errors import ConfigError
from contacts.models import ContactsState, ReviewItem, SourceFile, SyncRun
from contacts.runner import (IGNORE_KEY, check_import_targets, claim, clickup_config, data_dir, execute_run,
                             orgs_list_id, save_upload, writes_enabled)


def _register(path, kind):
    p = Path(path)
    if not p.exists():
        raise CommandError(f'No such file: {p}')
    try:
        return save_upload(kind, SimpleUploadedFile(p.name, p.read_bytes()))
    except ConfigError as e:
        raise CommandError(str(e))


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest='cmd', required=True)
        sub.add_parser('check')

        def live_flags(p):
            p.add_argument('--apply', action='store_true', help='write to ClickUp (default is a dry run)')
            p.add_argument('--max-writes', type=int, help='write budget; required with --apply')
            p.add_argument('--fill-blanks-only', action='store_true',
                           help="never overwrite a value that's already set in ClickUp")

        g = sub.add_parser('google')
        g.add_argument('--full', action='store_true', help='ignore the sync token; also sweeps for deletions')
        g.add_argument('--photos', action='store_true', help='check photos on every contact')
        g.add_argument('--writeback', action='store_true', help='store the ClickUp task id on each Google contact')
        g.add_argument('--rename-tasks', action='store_true', help='rename ClickUp tasks when the Google name changes')
        g.add_argument('--ignore-label', action='append', default=None, metavar='PATTERN')
        g.add_argument('--token-file', help='authorized-user token JSON (as written by the old script)')
        live_flags(g)

        li = sub.add_parser('linkedin')
        li.add_argument('csv')
        li.add_argument('--messages', help='messages.csv (default: next to the connections CSV, if present)')
        live_flags(li)

        wa = sub.add_parser('whatsapp')
        wa.add_argument('json')
        wa.add_argument('--no-create', action='store_true')
        wa.add_argument('--only-saved', action='store_true')
        wa.add_argument('--trust-exact-names', action='store_true')
        live_flags(wa)

        m = sub.add_parser('merge')
        m.add_argument('survivor')
        m.add_argument('loser')
        live_flags(m)

        ex = sub.add_parser('export', help='write the People and Orgs lists, with relationships, to a JSON file')
        ex.add_argument('--out', help='also copy the export to this path')

        im = sub.add_parser('import', help='create an export\'s tasks in new, empty lists')
        im.add_argument('file')
        im.add_argument('--people-list', required=True, help='empty list to import People into')
        im.add_argument('--orgs-list', help='empty list to import Orgs into (needed if the export has Orgs)')
        live_flags(im)

    def handle(self, *args, **o):
        if o['cmd'] == 'check':
            return self._check()
        if o['cmd'] == 'export':
            return self._export(o.get('out'))
        live = o['apply']
        if live:
            if not o.get('max_writes'):
                raise CommandError('--apply needs --max-writes N (run without --apply first to see the plan size).')
            if not writes_enabled():
                raise CommandError('Live writes are disabled (set CONTACTS_CLICKUP_WRITES_ENABLED=1).')

        options, files = {'overwrite_values': not o['fill_blanks_only']}, []
        if o['cmd'] == 'google':
            options.update(full=o['full'], photos=o['photos'], writeback=o['writeback'],
                           rename_tasks=o['rename_tasks'],
                           ignore_labels=o['ignore_label'] if o['ignore_label'] is not None
                           else ContactsState.get(IGNORE_KEY, []))
        elif o['cmd'] == 'linkedin':
            files.append(_register(o['csv'], SourceFile.Kind.LINKEDIN_CONNECTIONS))
            msgs = o['messages'] or (Path(o['csv']).parent / 'messages.csv')
            if o['messages'] or Path(msgs).exists():
                files.append(_register(msgs, SourceFile.Kind.LINKEDIN_MESSAGES))
        elif o['cmd'] == 'whatsapp':
            files.append(_register(o['json'], SourceFile.Kind.WHATSAPP))
            options.update(no_create=o['no_create'], only_saved=o['only_saved'],
                           trust_exact_names=o['trust_exact_names'])
        elif o['cmd'] == 'merge':
            options.update(survivor=o['survivor'], loser=o['loser'])
        elif o['cmd'] == 'import':
            f = _register(o['file'], SourceFile.Kind.CONTACTS_EXPORT)
            options = {'people_list_id': o['people_list'], 'orgs_list_id': o['orgs_list'] or ''}
            try:
                check_import_targets(options, f)
            except ConfigError as e:
                raise CommandError(str(e))
            files.append(f)

        run = SyncRun.objects.create(source=o['cmd'], mode=SyncRun.Mode.LIVE if live else SyncRun.Mode.DRY,
                                     options=options, max_ops=o.get('max_writes') if live else None,
                                     foreground=True, created_by='cli')
        run.files.set(files)
        if not claim(run.pk, foreground=True):
            run.delete()
            raise CommandError('Another contacts run is in progress; try again when it finishes.')
        run = execute_run(run, echo=True, token_file=o.get('token_file'))
        self._summary(run)

    def _export(self, out):
        run = SyncRun.objects.create(source='export', mode=SyncRun.Mode.DRY, foreground=True, created_by='cli',
                                     options={'people_list_id': clickup_config()[1], 'orgs_list_id': orgs_list_id()})
        if not claim(run.pk, foreground=True):
            run.delete()
            raise CommandError('Another contacts run is in progress; try again when it finishes.')
        run = execute_run(run, echo=True)
        if run.output:
            path = data_dir() / run.output.path
            if out:
                shutil.copyfile(path, out)
                path = Path(out)
            self.stdout.write(f'Export written to {path}')
        self._summary(run)

    def _check(self):
        token, list_id = clickup_config()
        try:
            cu, missing = open_list(token, list_id, WriteGuard(dry=True))
        except ConfigError as e:
            raise CommandError(str(e))
        r = cu.field_report(missing)
        self.stdout.write(f"Custom fields on list {r['list_id']}:")
        for f in r['fields']:
            self.stdout.write(f"  {f['name']:<24} {f['type']}")
        for e in r['expected']:
            mark = 'ok ' if e['present'] else ('MISSING (required)' if e['required'] else 'missing (optional)')
            self.stdout.write(f"  [{mark}] {e['name']}")
        if r['status_missing_options']:
            self.stdout.write(f"  Match status needs options: {', '.join(r['status_missing_options'])}")
        if r['sources_missing_options']:
            self.stdout.write(f"  Sources needs options: {', '.join(r['sources_missing_options'])}")
        self.stdout.write('Ready.' if r['ready'] else 'Fix the items above, then run check again.')

    def _summary(self, run):
        w = self.stdout.write
        for msg in run.warnings:
            w(self.style.WARNING(f'WARNING: {msg}'))
        if run.unknown_sources:
            w(f"Add these options to the 'Sources' field: {', '.join(run.unknown_sources)}")
        if run.unknown_groups:
            w("Google labels with no matching option in the ClickUp 'Groups' field:")
            for g, n in sorted(run.unknown_groups.items(), key=lambda x: -x[1]):
                w(f'  {g}  ({n} contacts)')
        pending = ReviewItem.objects.filter(source=run.source, decision=ReviewItem.Decision.PENDING).count()
        if pending:
            w(f'{pending} possible matches need a decision in the Review tab.')
        stats = ', '.join(f'{k.lower()}={v}' for k, v in sorted(run.stats.items())) or 'nothing to do'
        w(f'\nSummary: {stats}')
        verb = 'made' if run.is_live else 'planned'
        w(f'Writes {verb}: {run.ops}' + (f' (budget {run.max_ops})' if run.max_ops else ''))
        if run.status != SyncRun.Status.DONE:
            raise CommandError(f'Run #{run.pk} {run.get_status_display().lower()}: {run.error}')
        w(self.style.SUCCESS(f'Run #{run.pk} done.'))
