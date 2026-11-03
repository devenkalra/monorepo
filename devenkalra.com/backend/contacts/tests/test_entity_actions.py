from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from contacts import entities, entity_actions
from contacts.engine import ClickUp, WriteGuard
from contacts.engine.fields import MERGED
from contacts.models import EntityCache, GoogleAccount

from .fakes import FakeClickUp, FakePeople, make_fields, make_task
from .test_engine import person


class FirstNameTests(SimpleTestCase):
    def test_from_display_name(self):
        self.assertEqual(entity_actions.first_name_from_display('Dr. Raj Kalra'), 'Raj')
        self.assertEqual(entity_actions.first_name_from_display('Kalra, Deven'), 'Deven')
        self.assertEqual(entity_actions.first_name_from_display('J. Robert Smith'), 'Robert')
        self.assertEqual(entity_actions.first_name_from_display('Ada Lovelace'), 'Ada')
        self.assertIsNone(entity_actions.first_name_from_display('ada@example.com'))
        self.assertIsNone(entity_actions.first_name_from_display('+15551234567'))
        self.assertIsNone(entity_actions.first_name_from_display(''))

    def test_resolve_prefers_google_given_and_skips_empty(self):
        row = {'name': 'Pay My Bill', 'google_id': 'people/c1'}
        self.assertEqual(entity_actions.resolve_first_name(row, 'Ada')[0], 'Ada')
        first, source, skip = entity_actions.resolve_first_name(row, None)
        self.assertIsNone(first)
        self.assertEqual(source, 'google')
        self.assertIn('no given name', skip)

    def test_resolve_parses_name_without_google(self):
        row = {'name': 'Mr. Bob Jones', 'google_id': ''}
        first, source, skip = entity_actions.resolve_first_name(row, None)
        self.assertEqual((first, source, skip), ('Bob', 'name', None))


@override_settings(CONTACTS_CLICKUP_TOKEN='tok', CONTACTS_CLICKUP_LIST_ID='P1',
                   CONTACTS_CLICKUP_ORGS_LIST_ID='O1', CONTACTS_CLICKUP_WRITES_ENABLED=True)
class FillPsalutationApiTests(TestCase):
    def setUp(self):
        admin = get_user_model().objects.create_superuser('admin', 'admin@example.com', 'pw')
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=admin).key}')
        GoogleAccount.objects.create(email='me@example.com', refresh_token='rt',
                                     scopes='https://www.googleapis.com/auth/contacts.readonly openid email')

        fields = make_fields() + [
            {'id': 'f-psalutation', 'name': 'PSalutation', 'type': 'short_text', 'type_config': {}},
        ]
        self.fake = FakeClickUp([
            make_task('ada', 'Ada Lovelace', google_id='people/ada', status='st-0'),
            make_task('bob', 'Mr. Bob Jones', linkedin_url='https://linkedin.com/in/bob', status='st-0'),
            make_task('biz', 'Pay My Bill', google_id='people/biz', status='st-0'),
            make_task('old', 'Merged Person', status='st-3', google_id='people/old'),
        ], fields=fields)

        ada = person('people/ada', 'Ada Lovelace', 'ada@example.com')
        ada['names'] = [{'displayName': 'Ada Lovelace', 'givenName': 'Ada', 'familyName': 'Lovelace'}]
        biz = person('people/biz', 'Pay My Bill')
        biz['names'] = [{'displayName': 'Pay My Bill'}]
        self.people = FakePeople([ada, biz])

        for tid, name, gid, match in (
            ('ada', 'Ada Lovelace', 'people/ada', 'active'),
            ('bob', 'Mr. Bob Jones', '', 'active'),
            ('biz', 'Pay My Bill', 'people/biz', 'active'),
            ('old', 'Merged Person', 'people/old', MERGED),
        ):
            EntityCache.objects.create(task_id=tid, list_key='people', row={
                'id': tid, 'list': 'people', 'name': name, 'google_id': gid, 'archived': False,
                'match': match, 'groups': [], 'sources': [], 'emails': '', 'phones': '',
                'company': '', 'title': '', 'relationships': 0, 'updated': 0, 'url': '',
                'google_link': '',
            })

        def _client(list_id='', guard=None):
            return ClickUp('tok', list_id or 'P1', guard or WriteGuard(dry=True), session=self.fake)

        patcher = mock.patch.object(entities, '_client', _client)
        patcher.start()
        self.addCleanup(patcher.stop)
        gpatch = mock.patch('contacts.google_auth.people_service', lambda **kw: self.people)
        gpatch.start()
        self.addCleanup(gpatch.stop)

    def test_preview_and_apply_fill_psalutation(self):
        r = self.client.post('/api/contacts/entities/actions/', {
            'action': 'fill_psalutation',
            'ids': ['ada', 'bob', 'biz', 'old'],
            'dry_run': True,
        }, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        out = r.json()
        by_id = {c['id']: c for c in out['changes']}
        self.assertTrue(by_id['ada']['would_change'])
        self.assertEqual(by_id['ada']['after'], 'Ada')
        self.assertEqual(by_id['ada']['source'], 'google')
        self.assertTrue(by_id['bob']['would_change'])
        self.assertEqual(by_id['bob']['after'], 'Bob')
        self.assertEqual(by_id['bob']['source'], 'name')
        self.assertFalse(by_id['biz']['would_change'])
        self.assertIn('no given name', by_id['biz']['skip_reason'])
        self.assertEqual(by_id['old']['skip_reason'], 'merged')

        r = self.client.post('/api/contacts/entities/actions/', {
            'action': 'fill_psalutation',
            'ids': ['ada', 'bob'],
            'dry_run': False,
        }, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['ok'], 2)
        ada_vals = {cf['id']: cf['value'] for cf in self.fake.tasks['ada']['custom_fields']}
        self.assertEqual(ada_vals.get('f-psalutation'), 'Ada')
        bob_vals = {cf['id']: cf['value'] for cf in self.fake.tasks['bob']['custom_fields']}
        self.assertEqual(bob_vals.get('f-psalutation'), 'Bob')

    def test_skips_existing_unless_overwrite(self):
        self.fake.tasks['bob']['custom_fields'].append({'id': 'f-psalutation', 'value': 'Robert'})
        r = self.client.post('/api/contacts/entities/actions/', {
            'action': 'fill_psalutation', 'ids': ['bob'], 'dry_run': True,
        }, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['changes'][0]['skip_reason'], 'PSalutation already set')

        r = self.client.post('/api/contacts/entities/actions/', {
            'action': 'fill_psalutation', 'ids': ['bob'], 'dry_run': True, 'overwrite': True,
        }, format='json')
        self.assertTrue(r.json()['changes'][0]['would_change'])
        self.assertEqual(r.json()['changes'][0]['after'], 'Bob')
