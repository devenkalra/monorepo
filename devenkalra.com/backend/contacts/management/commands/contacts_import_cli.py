"""Import state from the old contacts_mgmt scripts: Google sync token, ignored labels, review decisions.

  python manage.py contacts_import_cli --dir contacts_mgmt [--skip-sync-token]
"""
import csv
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from contacts.engine.fields import task_id_from_url
from contacts.engine.normalize import norm_li, norm_phone
from contacts.models import ContactsState, ReviewItem
from contacts.runner import IGNORE_KEY, SYNC_TOKEN_KEY

DECISIONS = {**dict.fromkeys(('s', 'y', 'yes', 'same', 'merge', 'link'), 'same'),
             **dict.fromkeys(('n', 'no', 'new', 'different', 'create'), 'new')}


def _norm_key(source, k):
    if source == 'linkedin':
        return norm_li(k) or (k or '')
    if source == 'whatsapp':
        return norm_phone(k) or (k or '')
    return k or ''


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('--dir', default='contacts_mgmt')
        parser.add_argument('--skip-sync-token', action='store_true')

    def handle(self, *args, **o):
        d = Path(o['dir'])
        if not d.is_dir():
            raise CommandError(f'No such directory: {d}')

        state = d / 'sync_state.json'
        if state.exists() and not o['skip_sync_token']:
            token = json.loads(state.read_text()).get('google_sync_token')
            if token:
                ContactsState.put(SYNC_TOKEN_KEY, token)
                self.stdout.write('Imported the Google sync token.')

        ignore = d / 'ignore_labels.txt'
        if ignore.exists():
            pats = [ln.split('#', 1)[0].strip() for ln in ignore.read_text(encoding='utf-8').splitlines()]
            pats = sorted({p for p in pats if p} | set(ContactsState.get(IGNORE_KEY, [])))
            ContactsState.put(IGNORE_KEY, pats)
            self.stdout.write(f'Ignored Google labels: {len(pats)} pattern(s).')

        for source in ('linkedin', 'whatsapp', 'google'):
            path = d / f'{source}_review.csv'
            if not path.exists():
                continue
            created = decided = 0
            with open(path, encoding='utf-8-sig', newline='') as fh:
                for r in csv.DictReader(fh):
                    key = _norm_key(source, r.get('key') or r.get('linkedin_url'))
                    if not key:
                        continue
                    decision = DECISIONS.get((r.get('decision') or '').strip().lower(), 'pending')
                    url = r.get('suggested_task_url') or ''
                    defaults = {
                        'name': (r.get('name') or r.get('linkedin_name') or '')[:500],
                        'company': (r.get('company') or '')[:500], 'title': (r.get('title') or '')[:500],
                        'suggested_task_id': task_id_from_url(url) or '',
                        'suggested_task_name': (r.get('suggested_task_name') or '')[:500],
                    }
                    item, was_created = ReviewItem.objects.get_or_create(source=source, key=key, defaults=defaults)
                    if decision != 'pending' and item.decision == ReviewItem.Decision.PENDING:
                        item.decision = decision
                        item.decided_by = 'imported from CSV'
                        item.decided_at = timezone.now()
                        item.save()
                        decided += 1
                    created += was_created
            self.stdout.write(f'{source}_review.csv: {created} new review items, {decided} decisions imported.')
