import json
import sys
from collections import defaultdict

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_datetime

from vacation_list.models import VacTag, VacCategory, VacItem, VacList, VacListItem


def _dt(value):
    if not value:
        return None
    if isinstance(value, str) and value.endswith('Z'):
        value = value[:-1] + '+00:00'
    return parse_datetime(value)


class Command(BaseCommand):
    help = (
        'Import a vacation_list dumpdata fixture and assign every row to one user. '
        'Primary keys are remapped so existing production rows are not overwritten.'
    )

    def add_arguments(self, parser):
        parser.add_argument('fixture', help='Path to dumpdata JSON (use - for stdin)')
        parser.add_argument('--email', required=True, help='Production owner email')
        parser.add_argument(
            '--replace',
            action='store_true',
            help='Delete this user\'s existing vacation rows before import',
        )

    def handle(self, *args, **options):
        User = get_user_model()
        email = options['email']
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist as exc:
            raise CommandError(f'No user with email {email}') from exc

        path = options['fixture']
        if path == '-':
            raw = sys.stdin.read()
        else:
            with open(path, encoding='utf-8') as fh:
                raw = fh.read()
        try:
            rows = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CommandError(f'Invalid JSON fixture: {exc}') from exc
        if not isinstance(rows, list):
            raise CommandError('Fixture must be a JSON list of dumpdata objects')

        by_model = defaultdict(list)
        for row in rows:
            by_model[row['model']].append(row)

        with transaction.atomic():
            if options['replace']:
                deleted = {
                    'list_items': VacListItem.objects.filter(user=user).delete()[0],
                    'lists': VacList.objects.filter(user=user).delete()[0],
                    'items': VacItem.objects.filter(user=user).delete()[0],
                    'tags': VacTag.objects.filter(user=user).delete()[0],
                    'categories': VacCategory.objects.filter(user=user).delete()[0],
                }
                self.stdout.write(f'Removed existing rows for {user.email}: {deleted}')

            tag_map = self._import_named(VacTag, by_model['vacation_list.vactag'], user)
            cat_map = self._import_named(VacCategory, by_model['vacation_list.vaccategory'], user)
            item_map = self._import_items(by_model['vacation_list.vacitem'], user, cat_map, tag_map)
            list_map = self._import_lists(by_model['vacation_list.vaclist'], user, tag_map)
            item_count = self._import_list_items(
                by_model['vacation_list.vaclistitem'], user, item_map, list_map
            )

        self.stdout.write(self.style.SUCCESS(
            f'Imported for {user.email}: '
            f'{len(tag_map)} tags, {len(cat_map)} categories, {len(item_map)} items, '
            f'{len(list_map)} lists, {item_count} list items'
        ))

    def _stamp(self, model, pk, fields):
        created = _dt(fields.get('created_at'))
        modified = _dt(fields.get('modified_on'))
        updates = {}
        if created:
            updates['created_at'] = created
        if modified:
            updates['modified_on'] = modified
        if updates:
            model.objects.filter(pk=pk).update(**updates)

    def _import_named(self, model, rows, user):
        mapping = {}
        for row in rows:
            obj = model.objects.create(user=user, name=row['fields']['name'])
            self._stamp(model, obj.pk, row['fields'])
            mapping[row['pk']] = obj.pk
        return mapping

    def _import_items(self, rows, user, cat_map, tag_map):
        mapping = {}
        pending_tags = []
        for row in rows:
            fields = row['fields']
            category_id = fields.get('category')
            obj = VacItem.objects.create(
                user=user,
                name=fields['name'],
                name_group=fields.get('name_group') or '',
                description=fields.get('description'),
                category_id=cat_map.get(category_id) if category_id else None,
            )
            self._stamp(VacItem, obj.pk, fields)
            mapping[row['pk']] = obj.pk
            tag_ids = [tag_map[t] for t in (fields.get('tags') or []) if t in tag_map]
            if tag_ids:
                pending_tags.append((obj, tag_ids))
        for obj, tag_ids in pending_tags:
            obj.tags.set(tag_ids)
        return mapping

    def _import_lists(self, rows, user, tag_map):
        mapping = {}
        pending_tags = []
        for row in rows:
            fields = row['fields']
            obj = VacList.objects.create(
                user=user,
                name=fields['name'],
                is_archived=bool(fields.get('is_archived', False)),
            )
            self._stamp(VacList, obj.pk, fields)
            mapping[row['pk']] = obj.pk
            tag_ids = [tag_map[t] for t in (fields.get('initial_tags') or []) if t in tag_map]
            if tag_ids:
                pending_tags.append((obj, tag_ids))
        for obj, tag_ids in pending_tags:
            obj.initial_tags.set(tag_ids)
        return mapping

    def _import_list_items(self, rows, user, item_map, list_map):
        created = 0
        for row in rows:
            fields = row['fields']
            item_id = item_map.get(fields.get('item'))
            list_id = list_map.get(fields.get('in_list'))
            if not item_id or not list_id:
                continue
            obj = VacListItem.objects.create(
                user=user,
                item_id=item_id,
                in_list_id=list_id,
                need=bool(fields.get('need', True)),
                done=bool(fields.get('done', False)),
            )
            self._stamp(VacListItem, obj.pk, fields)
            created += 1
        return created
