"""One-time migration: move relationships into the Relationship data field on People and Orgs.

Reads legacy description sections (**Relationships** / **Organizations** / **People**) and the
Introduced by task-link field, merges both sides with inverse labels, writes JSON into
Relationship data, strips managed sections from the description (notes only), and clears
Introduced by.

  python manage.py contacts_migrate_relationships
  python manage.py contacts_migrate_relationships --apply --max-writes 20000

Dry run by default (no ClickUp writes). Requires Relationship data on both lists.
"""
from django.core.management.base import BaseCommand, CommandError

from contacts.engine.errors import ConfigError, SafetyStop
from contacts.migrate_relationships import migrate
from contacts.runner import writes_enabled


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='write to ClickUp (default is a dry run)')
        parser.add_argument('--max-writes', type=int, help='write budget; required with --apply')

    def handle(self, *args, **opts):
        dry = not opts['apply']
        max_ops = opts.get('max_writes')
        if not dry:
            if max_ops is None:
                raise CommandError('--apply requires --max-writes N')
            if not writes_enabled():
                raise CommandError('Live ClickUp writes are disabled (CONTACTS_CLICKUP_WRITES_ENABLED).')
        try:
            rows, guard, warnings = migrate(dry=dry, max_ops=max_ops)
        except (ConfigError, SafetyStop) as e:
            raise CommandError(str(e))

        changed = [r for r in rows if r['changed'] and not r['skip_reason']]
        edges = sum(r['edge_count'] for r in rows)
        self.stdout.write(f'{"Dry run" if dry else "Applied"}: {len(rows)} tasks, {edges} edges total, '
                          f'{len(changed)} task(s) would change, {guard.ops} write(s) '
                          f'{"planned" if dry else "made"}.')
        for w in warnings[:40]:
            self.stdout.write(self.style.WARNING(w))
        if len(warnings) > 40:
            self.stdout.write(self.style.WARNING(f'… and {len(warnings) - 40} more warnings'))
        for r in sorted(changed, key=lambda x: (x['kind'], x['name'].lower()))[:30]:
            bits = [f'{r["edge_count"]} edge(s)']
            if r['strip_desc']:
                bits.append('strip description sections')
            if r['clear_intro']:
                bits.append('clear Introduced by')
            self.stdout.write(f'  {r["kind"]}: {r["name"]} — ' + ', '.join(bits))
        if len(changed) > 30:
            self.stdout.write(f'  … and {len(changed) - 30} more')
        if dry:
            self.stdout.write(self.style.NOTICE('Re-run with --apply --max-writes N to write to ClickUp.'))
