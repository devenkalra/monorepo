from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from contacts import entities, google_auth, lookup
from contacts.engine import ClickUp
from contacts.models import EntityCache, Lookup

from .fakes import FakePeople
from .test_entities import _sync_fields
from .test_transfer import cf, field, source_workspace


def person(rid, name, emails=(), phones=(), clickup=None):
    return {
        'resourceName': rid, 'etag': f'etag-{rid}',
        'names': [{'displayName': name, 'givenName': name.split()[0], 'familyName': ' '.join(name.split()[1:])}],
        'emailAddresses': [{'value': e} for e in emails],
        'phoneNumbers': [{'value': p} for p in phones],
        'externalIds': [{'type': 'clickup', 'value': clickup}] if clickup else [],
        'memberships': [], 'metadata': {},
    }


class ParseTests(SimpleTestCase):
    def test_header_aliases_including_google_export_columns(self):
        self.assertEqual(lookup.header_field('E-mail 1 - Value'), 'email')
        self.assertEqual(lookup.header_field('Phone 2 - Value'), 'phone')
        self.assertEqual(lookup.header_field('Given Name'), 'first_name')
        self.assertEqual(lookup.header_field(' Full name '), 'name')
        self.assertIsNone(lookup.header_field('Phone 1 - Type'))
        self.assertIsNone(lookup.header_field('Company'))

    def test_parse_csv_splits_values_and_reports_columns(self):
        data = ('\ufeffFirst name,Last name,Email,Mobile,Company\n'
                'Ada,Lovelace,ADA@example.com ::: ada@work.com,650-555-0100,Engines\n'
                ',,,,\n'
                'Alan,,,,\n').encode('utf-8')
        inputs, columns = lookup.parse_csv(data)
        self.assertEqual(columns['recognized'], {'First name': 'first_name', 'Last name': 'last_name',
                                                 'Email': 'email', 'Mobile': 'phone'})
        self.assertEqual(columns['ignored'], ['Company'])
        self.assertEqual(len(inputs), 2)
        self.assertEqual(inputs[0], {'name': 'Ada Lovelace', 'emails': ['ada@example.com', 'ada@work.com'],
                                     'phones': ['+16505550100'], 'line': 2})
        self.assertEqual(inputs[1]['line'], 4)

    def test_parse_csv_semicolons_and_errors(self):
        inputs, _ = lookup.parse_csv(b'Name;Phone\nGrace Hopper;+1 202 555 0101\n')
        self.assertEqual(inputs[0]['phones'], ['+12025550101'])
        with self.assertRaisesMessage(lookup.LookupFailed, 'No name, email or phone column'):
            lookup.parse_csv(b'Company,City\nAcme,Paris\n')
        with self.assertRaisesMessage(lookup.LookupFailed, 'no rows'):
            lookup.parse_csv(b'Name,Email\n,\n')


@override_settings(CONTACTS_CLICKUP_TOKEN='tok', CONTACTS_CLICKUP_LIST_ID='P1', CONTACTS_CLICKUP_ORGS_LIST_ID='O1',
                   CONTACTS_CLICKUP_WRITES_ENABLED=True)
class LookupApiTests(TestCase):
    def setUp(self):
        from contacts.models import GoogleAccount

        admin = get_user_model().objects.create_superuser('admin', 'admin@example.com', 'pw')
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=admin).key}')
        GoogleAccount.objects.create(email='me@example.com', refresh_token='rt',
                                     scopes='https://www.googleapis.com/auth/contacts openid email')
        ws = source_workspace()
        ws.lists['P1']['fields'] += _sync_fields()
        ws.lists['P1']['fields'].append(field('p-title', 'Title', 'short_text'))
        self.groups_field = next(f for f in ws.lists['P1']['fields'] if f['name'] == 'Groups')
        self.groups_field['type_config']['options'].append({'id': 'p-g-sync', 'label': 'SyncDriven'})
        tasks = ws.lists['P1']['tasks']
        tasks['hakan']['custom_fields'] += [cf('p-gid', 'people/c1'), cf('p-emails', 'hakan@google.com')]
        tasks['reeta']['custom_fields'].append(cf('p-emails', 'reeta@example.com'))
        ws.put('P1', {'id': 'ada', 'name': 'Ada Lovelace',
                      'custom_fields': [cf('p-phones', '+16505550100'), cf('p-co', 'Engines')]})
        self.ws = ws
        self.people = FakePeople([
            person('people/c1', 'Hakan Ancin', ['hakan@google.com'], clickup='hakan'),
            person('people/c2', 'Reeta Sharma', ['reeta@example.com']),
            person('people/c3', 'Grace Hopper', ['grace@navy.mil'], ['+1 202 555 0101']),
        ])
        for p in (mock.patch.object(entities, 'ClickUp',
                                    lambda token, list_id, guard: ClickUp(token, list_id, guard, session=self.ws)),
                  mock.patch.object(google_auth, 'people_service', return_value=self.people),
                  mock.patch('contacts.engine.sources.google.time.sleep', return_value=None)):
            p.start()
            self.addCleanup(p.stop)
        self.assertEqual(self.client.post('/api/contacts/entities/').status_code, 200)

    def compare(self, rows, status=201):
        r = self.client.post('/api/contacts/lookups/', {'rows': rows}, format='json')
        self.assertEqual(r.status_code, status, r.content)
        return r.json()

    def act(self, lk, row, action, status=200):
        r = self.client.post(f'/api/contacts/lookups/{lk["id"]}/act/', {'row': row, 'action': action}, format='json')
        self.assertEqual(r.status_code, status, r.content)
        return r.json()

    @staticmethod
    def outcomes(lk):
        return [r['result']['outcome'] for r in lk['rows']]

    def value_of(self, tid, fid):
        return next((c['value'] for c in self.ws.lists['P1']['tasks'][tid]['custom_fields'] if c['id'] == fid),
                    None)

    def gid_of(self, tid):
        return self.value_of(tid, 'p-gid')

    def assert_labeled(self, tid, rid):
        self.assertIn('p-g-sync', self.value_of(tid, 'p-grp') or [])
        mems = {(m.get('contactGroupMembership') or {}).get('contactGroupResourceName')
                for m in self.people._all[rid].get('memberships') or []}
        self.assertIn('contactGroups/syncdriven', mems)

    def test_each_outcome_and_comparing_writes_nothing(self):
        lk = self.compare([
            {'name': 'Hakan Ancin', 'email': 'hakan@google.com'},
            {'email': 'REETA@example.com'},
            {'name': 'Ada Lovelace', 'phone': '650 555 0100'},
            {'email': 'grace@navy.mil'},
            {'name': 'Alan Turing', 'email': 'alan@example.com'},
            {'name': 'Reta Sharma'},
            {'name': 'Bob Smith', 'email': 'hakan@google.com'},
        ])
        self.assertEqual(self.outcomes(lk), ['exists', 'unlinked', 'clickup_only', 'google_only', 'not_found',
                                             'review', 'conflict'])
        self.assertEqual([r['result']['action'] for r in lk['rows']],
                         [None, 'link', 'create_google', 'import_clickup', 'create_both', None, None])
        self.assertIn('Name differs', lk['rows'][6]['result']['conflicts'][0])
        self.assertEqual(lk['rows'][5]['result']['clickup']['candidates'][0]['id'], 'reeta')
        self.assertEqual(lk['summary']['total'], 7)
        self.assertEqual(self.ws.writes, [])
        self.assertEqual(self.people.creates, [])
        self.assertEqual(self.people.updates, [])

    def test_link_writes_both_sides(self):
        lk = self.compare([{'email': 'reeta@example.com'}])
        lk = self.act(lk, 0, 'link')
        self.assertEqual(self.gid_of('reeta'), 'people/c2')
        self.assertTrue(any(u.get('updatePersonFields') == 'externalIds' for u in self.people.updates))
        self.assertEqual(self.outcomes(lk), ['exists'])
        self.assertEqual(lk['rows'][0]['done']['action'], 'link')
        self.assertEqual(EntityCache.objects.get(task_id='reeta').row['google_id'], 'people/c2')
        self.assert_labeled('reeta', 'people/c2')
        self.assertEqual(lk['rows'][0]['done']['warnings'], [])
        self.act(lk, 0, 'link', status=409)

    def test_missing_clickup_group_option_only_warns(self):
        self.groups_field['type_config']['options'].pop()
        lk = self.act(self.compare([{'email': 'reeta@example.com'}]), 0, 'link')
        self.assertEqual(self.gid_of('reeta'), 'people/c2')
        self.assertIn('no "SyncDriven" option', lk['rows'][0]['done']['warnings'][0])
        self.assertEqual(sum(g['formattedName'] == 'SyncDriven' for g in self.people._groups), 1)

    def test_create_in_google_from_clickup_data(self):
        lk = self.compare([{'name': 'Ada Lovelace', 'phone': '650 555 0100'}])
        lk = self.act(lk, 0, 'create_google')
        body = self.people.creates[0]
        self.assertEqual(body['names'][0], {'givenName': 'Ada', 'familyName': 'Lovelace'})
        self.assertEqual(body['phoneNumbers'][0]['value'], '+16505550100')
        self.assertEqual(body['organizations'][0]['name'], 'Engines')
        self.assertEqual(self.gid_of('ada'), 'people/new1')
        self.assert_labeled('ada', 'people/new1')
        self.assertEqual(self.outcomes(lk), ['exists'])

    def test_import_google_contact_into_clickup(self):
        lk = self.compare([{'email': 'grace@navy.mil'}])
        lk = self.act(lk, 0, 'import_clickup')
        tid = lk['rows'][0]['done']['clickup_id']
        self.assertEqual(self.ws.lists['P1']['tasks'][tid]['name'], 'Grace Hopper')
        self.assertEqual(self.gid_of(tid), 'people/c3')
        self.assert_labeled(tid, 'people/c3')
        self.assertEqual(self.people.creates, [])
        self.assertEqual(self.outcomes(lk), ['exists'])

    def test_create_in_both(self):
        lk = self.compare([{'name': 'Alan Turing', 'email': 'alan@example.com'}])
        lk = self.act(lk, 0, 'create_both')
        self.assertEqual(self.people.creates[0]['emailAddresses'][0]['value'], 'alan@example.com')
        tid = lk['rows'][0]['done']['clickup_id']
        self.assertEqual(self.ws.lists['P1']['tasks'][tid]['name'], 'Alan Turing')
        self.assert_labeled(tid, lk['rows'][0]['done']['google_id'])
        self.assertEqual(self.outcomes(lk), ['exists'])

    def test_possible_matches_can_be_created_as_new(self):
        lk = self.compare([{'name': 'Reta Sharma', 'phone': '+1 415 555 0199'}])
        res = lk['rows'][0]['result']
        self.assertEqual((res['outcome'], res['action'], res['new_action']), ('review', None, 'create_both'))
        lk = self.act(lk, 0, 'create_both')
        self.assertEqual(self.people.creates[0]['names'][0], {'givenName': 'Reta', 'familyName': 'Sharma'})
        tid = lk['rows'][0]['done']['clickup_id']
        self.assertNotEqual(tid, 'reeta')
        self.assertEqual(self.ws.lists['P1']['tasks'][tid]['name'], 'Reta Sharma')
        self.assertEqual(self.outcomes(lk), ['exists'])

    def test_as_new_never_duplicates_an_exact_match(self):
        extra = person('people/c4', 'Ada Lovelace', ['ada@lab.com'])
        self.people._people.append(extra)
        self.people._all['people/c4'] = extra
        lk = self.compare([{'name': 'Ada Lovelace', 'email': 'ada@lab.com'}])
        self.assertEqual(lk['rows'][0]['result']['new_action'], 'import_clickup')
        self.act(lk, 0, 'create_both', status=409)
        lk = self.act(lk, 0, 'import_clickup')
        self.assertEqual(self.people.creates, [])
        self.assertEqual(self.gid_of(lk['rows'][0]['done']['clickup_id']), 'people/c4')

    def test_review_choice_then_action(self):
        lk = self.compare([{'name': 'Reta Sharma'}])
        r = self.client.post(f'/api/contacts/lookups/{lk["id"]}/choose/',
                             {'row': 0, 'side': 'clickup', 'value': 'reeta'}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        row = r.json()['rows'][0]['result']
        self.assertEqual((row['outcome'], row['clickup']['id']), ('review', 'reeta'))  # Google is still rough
        r = self.client.post(f'/api/contacts/lookups/{lk["id"]}/choose/',
                             {'row': 0, 'side': 'google', 'value': 'people/c2'}, format='json')
        self.assertEqual(self.outcomes(r.json()), ['unlinked'])
        bad = self.client.post(f'/api/contacts/lookups/{lk["id"]}/choose/',
                               {'row': 0, 'side': 'google', 'value': 'people/c3'}, format='json')
        self.assertEqual(bad.status_code, 400)

    def test_conflicts_block_actions_and_changed_rows_are_refused(self):
        lk = self.compare([{'name': 'Bob Smith', 'email': 'hakan@google.com'}, {'email': 'reeta@example.com'}])
        self.act(lk, 0, 'link', status=409)
        # Reeta gets linked elsewhere after the comparison: the action re-checks and refuses.
        self.ws.lists['P1']['tasks']['reeta']['custom_fields'].append(cf('p-gid', 'people/c2'))
        self.client.post('/api/contacts/entities/')
        out = self.act(lk, 1, 'link', status=409)
        self.assertIn('now "Exists"', out['detail'])
        self.assertEqual(self.people.updates, [])
        self.assertEqual(self.outcomes(self.client.get(f'/api/contacts/lookups/{lk["id"]}/').json())[1], 'exists')

    def test_csv_upload_and_cache_status(self):
        upload = SimpleUploadedFile('people.csv', b'Name,E-mail 1 - Value\nGrace Hopper,grace@navy.mil\n',
                                    content_type='text/csv')
        r = self.client.post('/api/contacts/lookups/', {'file': upload}, format='multipart')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()['name'], 'people.csv')
        self.assertEqual(self.outcomes(r.json()), ['google_only'])
        self.assertEqual(r.json()['rows'][0]['line'], 2)
        caches = self.client.get('/api/contacts/lookups/caches/').json()
        self.assertEqual(caches['google']['contacts'], 3)
        self.assertFalse(caches['clickup']['outdated'])
        self.assertEqual(len(self.client.get('/api/contacts/lookups/').json()), 1)

    def test_outdated_or_empty_clickup_cache_is_refused(self):
        row = EntityCache.objects.get(task_id='hakan')
        row.row.pop('google_id')
        row.save()
        self.assertIn('before it kept Google links', self.compare([{'name': 'X'}], status=409)['detail'])
        EntityCache.objects.all().delete()
        self.client.get('/api/contacts/entities/')
        self.assertEqual(Lookup.objects.count(), 0)
