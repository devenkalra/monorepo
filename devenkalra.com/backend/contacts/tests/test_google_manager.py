from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from contacts import google_manager
from contacts.models import GoogleAccount

from .fakes import FakePeople
from .test_engine import person


def _svc_factory(fake):
    def people_service(account=None, token_file=None, write=False):
        if write and not getattr(account or GoogleAccount.objects.order_by('id').first(), 'can_write', True):
            raise ValueError('Writing Google Contacts needs write access')
        return fake
    return people_service


class GoogleManagerApiTests(TestCase):
    def setUp(self):
        admin = get_user_model().objects.create_superuser('admin', 'admin@example.com', 'pw')
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=admin).key}')
        GoogleAccount.objects.create(email='me@example.com', refresh_token='r',
                                     scopes='https://www.googleapis.com/auth/contacts')
        self.groups = [
            {'resourceName': 'contactGroups/work', 'groupType': 'USER_CONTACT_GROUP',
             'name': 'contactGroups/work', 'formattedName': 'Work'},
            {'resourceName': 'contactGroups/family', 'groupType': 'USER_CONTACT_GROUP',
             'name': 'contactGroups/family', 'formattedName': 'Family'},
        ]
        ada = person('people/ada', 'Ada Lovelace', 'ada@example.com')
        ada['addresses'] = [{'city': 'London', 'region': 'England', 'country': 'United Kingdom'}]
        ada['memberships'] = [{'contactGroupMembership': {'contactGroupResourceName': 'contactGroups/work'}}]
        bob = person('people/bob', 'Bob Jones', 'bob@example.com')
        bob['phoneNumbers'] = [{'value': '+15551212'}]
        self.fake = FakePeople([ada, bob], groups=self.groups)
        patcher = mock.patch('contacts.google_auth.people_service', _svc_factory(self.fake))
        patcher.start()
        self.addCleanup(patcher.stop)
        sleep = mock.patch('contacts.google_manager.time.sleep')
        sleep.start()
        self.addCleanup(sleep.stop)

    def test_list_and_search(self):
        r = self.client.get('/api/contacts/google/contacts/')
        self.assertEqual(r.status_code, 200, r.content)
        names = {c['name'] for c in r.json()['contacts']}
        self.assertEqual(names, {'Ada Lovelace', 'Bob Jones'})

        r = self.client.get('/api/contacts/google/contacts/', {'q': 'ada'})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual([c['name'] for c in r.json()['contacts']], ['Ada Lovelace'])

        r = self.client.get('/api/contacts/google/contacts/', {'label': 'Work'})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual([c['name'] for c in r.json()['contacts']], ['Ada Lovelace'])
        self.assertEqual(r.json()['contacts'][0]['city'], 'London')
        self.assertEqual(r.json()['contacts'][0]['state'], 'England')

    def test_bulk_update_email_and_city(self):
        r = self.client.post('/api/contacts/google/contacts/bulk-update/', {
            'ids': ['people/bob'], 'field': 'email', 'value': 'bob2@example.com',
        }, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['ok'], 1)
        bob = self.fake._all['people/bob']
        self.assertEqual([e['value'] for e in bob['emailAddresses']],
                         ['bob@example.com', 'bob2@example.com'])

        r = self.client.post('/api/contacts/google/contacts/bulk-update/', {
            'ids': ['people/ada', 'people/bob'], 'field': 'city', 'value': 'Seattle',
        }, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['ok'], 2)
        self.assertEqual(self.fake._all['people/ada']['addresses'][0]['city'], 'Seattle')
        self.assertEqual(self.fake._all['people/bob']['addresses'][0]['city'], 'Seattle')

    def test_bulk_update_labels(self):
        r = self.client.post('/api/contacts/google/contacts/bulk-update/', {
            'ids': ['people/bob'], 'field': 'labels', 'value': ['Family'],
        }, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['ok'], 1)
        mems = self.fake._all['people/bob']['memberships']
        self.assertTrue(any(
            (m.get('contactGroupMembership') or {}).get('contactGroupResourceName') == 'contactGroups/family'
            for m in mems))

    def test_bulk_update_labels_and_location_together(self):
        r = self.client.post('/api/contacts/google/contacts/bulk-update/', {
            'ids': ['people/ada', 'people/bob'],
            'labels': ['Family'],
            'city': 'Austin',
            'state': 'TX',
        }, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['ok'], 2)
        ada = self.fake._all['people/ada']
        self.assertEqual(ada['addresses'][0]['city'], 'Austin')
        self.assertEqual(ada['addresses'][0]['region'], 'TX')
        self.assertTrue(any(
            (m.get('contactGroupMembership') or {}).get('contactGroupResourceName') == 'contactGroups/family'
            for m in ada['memberships']))

    def test_update_single_contact(self):
        r = self.client.put('/api/contacts/google/contacts/people/bob/', {
            'first_name': 'Robert', 'last_name': 'Jones',
            'emails': 'bob@example.com, bob.work@example.com',
            'phones': '+15559999',
            'labels': ['Work', 'Family'],
            'city': 'Denver', 'state': 'CO', 'country': 'US',
        }, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()['changed'])
        c = r.json()['contact']
        self.assertEqual(c['name'], 'Robert Jones')
        self.assertEqual(c['emails'], ['bob@example.com', 'bob.work@example.com'])
        self.assertEqual(c['city'], 'Denver')
        self.assertEqual(c['state'], 'CO')
        self.assertEqual(set(c['labels']), {'Work', 'Family'})

    def test_address_update_refreshes_formatted_value(self):
        ada = self.fake._all['people/ada']
        ada['addresses'] = [{
            'formattedValue': 'Old Street, London, England',
            'streetAddress': 'Old Street',
            'city': 'London',
            'region': 'England',
            'country': 'United Kingdom',
        }]
        r = self.client.put('/api/contacts/google/contacts/people/ada/', {
            'city': 'Portland', 'state': 'OR', 'country': 'US',
        }, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        addr = self.fake._all['people/ada']['addresses'][0]
        self.assertEqual(addr['city'], 'Portland')
        self.assertEqual(addr['region'], 'OR')
        self.assertEqual(addr['formattedValue'], 'Old Street, Portland, OR, US')
        self.assertNotIn('Old Street, London', addr['formattedValue'])

    def test_bulk_create(self):
        r = self.client.post('/api/contacts/google/contacts/bulk-create/', {
            'contacts': [{
                'first_name': 'Carol', 'last_name': 'New',
                'email': 'carol@example.com', 'phone': '+15550001',
                'labels': ['Work'], 'city': 'Austin', 'state': 'TX', 'country': 'US',
            }],
        }, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()['ok'], 1)
        created = r.json()['contacts'][0]
        self.assertEqual(created['name'], 'Carol New')
        self.assertEqual(created['city'], 'Austin')
        self.assertEqual(created['state'], 'TX')
        self.assertIn('Work', created['labels'])
        self.assertEqual(len(self.fake.creates), 1)

    def test_refuses_unknown_field(self):
        r = self.client.post('/api/contacts/google/contacts/bulk-update/', {
            'ids': ['people/ada'], 'field': 'company', 'value': 'X',
        }, format='json')
        self.assertEqual(r.status_code, 400)
