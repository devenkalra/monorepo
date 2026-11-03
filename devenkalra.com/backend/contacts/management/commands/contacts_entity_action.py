"""Run a named People & Orgs action (dry-run by default).

  python manage.py contacts_entity_action fill_psalutation
  python manage.py contacts_entity_action fill_psalutation --ids id1,id2
  python manage.py contacts_entity_action fill_psalutation --overwrite
  python manage.py contacts_entity_action fill_psalutation --apply --max-writes 500

Without --ids, fill_psalutation uses every non-archived person in the local EntityCache.
"""
from django.core.management.base import BaseCommand, CommandError

from contacts import entity_actions
from contacts.models import EntityCache
from contacts.runner import writes_enabled


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('action', nargs='?', help='Action id (see --list)')
        parser.add_argument('--list', action='store_true', dest='list_actions',
                            help='list available actions and exit')
        parser.add_argument('--ids', help='comma-separated ClickUp task ids (default: all people in cache)')
        parser.add_argument('--overwrite', action='store_true',
                            help='replace existing PSalutation values (fill_psalutation)')
        parser.add_argument('--apply', action='store_true', help='write to ClickUp (default is a dry run)')
        parser.add_argument('--max-writes', type=int, help='write budget; required with --apply')

    def handle(self, *args, **opts):
        if opts['list_actions'] or not opts.get('action'):
            for a in entity_actions.list_actions():
                self.stdout.write(f'{a["id"]}: {a["label"]}')
            if not opts.get('action'):
                return

        action = opts['action']
        if action not in entity_actions.ACTIONS:
            raise CommandError(f'Unknown action "{action}". Use --list.')

        dry = not opts['apply']
        if not dry:
            if opts.get('max_writes') is None:
                raise CommandError('--apply requires --max-writes N')
            if not writes_enabled():
                raise CommandError('Live ClickUp writes are disabled (CONTACTS_CLICKUP_WRITES_ENABLED).')

        if opts.get('ids'):
            ids = [x.strip() for x in opts['ids'].split(',') if x.strip()]
        else:
            ids = [c.task_id for c in EntityCache.objects.filter(list_key='people')
                   if not (c.row or {}).get('archived')]

        if not ids:
            raise CommandError('No people to act on (refresh the People & Orgs list, or pass --ids).')

        try:
            # Plan always; apply separately so --max-writes can gate the WriteGuard.
            plan = entity_actions.ACTIONS[action]['plan'](ids, overwrite=opts['overwrite'])
        except entity_actions.ActionError as e:
            raise CommandError(str(e)) from e

        summary = plan['summary']
        self.stdout.write(
            f'{"Dry run" if dry else "Apply"} {action}: {summary["selected"]} selected, '
            f'{summary["would_change"]} would change, {summary["skipped"]} skipped.'
        )
        for c in plan['changes']:
            if c.get('would_change'):
                self.stdout.write(
                    f'  CHANGE  {c["name"]}: {c.get("before") or "(empty)"} → {c["after"]} '
                    f'[{c.get("source")}]'
                )
            elif opts.get('verbosity', 1) >= 2 and c.get('skip_reason'):
                self.stdout.write(f'  skip    {c.get("name")}: {c["skip_reason"]}')

        shown_skip = [c for c in plan['changes'] if c.get('skip_reason') and not c.get('would_change')]
        if shown_skip and opts.get('verbosity', 1) < 2:
            self.stdout.write(f'  ({len(shown_skip)} skipped — re-run with -v 2 to list them)')

        if dry:
            self.stdout.write(self.style.NOTICE(
                'Re-run with --apply --max-writes N to write to ClickUp.'))
            return

        try:
            out = entity_actions.ACTIONS[action]['apply'](
                plan, user='cli', max_writes=opts['max_writes'])
        except entity_actions.ActionError as e:
            raise CommandError(str(e)) from e
        self.stdout.write(self.style.SUCCESS(
            f'Applied: {out.get("ok", 0)} updated, {out.get("failed", 0)} failed.'))
        for r in out.get('results') or []:
            if not r.get('ok'):
                self.stdout.write(self.style.ERROR(f'  FAIL {r.get("name")}: {r.get("error")}'))
