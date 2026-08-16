from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APITestCase

from vacation_list.models import VacCategory, VacItem, VacList, VacListItem, VacTag


User = get_user_model()


class VacationListApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='vacuser', password='secret', email='vac@example.com')
        self.other = User.objects.create_user(username='other', password='secret', email='other@example.com')
        self.client.force_authenticate(self.user)

    def test_unauthenticated_rejected(self):
        self.client.force_authenticate(user=None)
        res = self.client.get('/api/vacation/lists/')
        self.assertIn(res.status_code, (401, 403))

    def test_lists_are_isolated_per_user(self):
        VacList.objects.create(name='Mine', user=self.user)
        VacList.objects.create(name='Theirs', user=self.other)

        res = self.client.get('/api/vacation/lists/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual([row['name'] for row in res.data], ['Mine'])

        self.client.force_authenticate(self.other)
        res = self.client.get('/api/vacation/lists/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual([row['name'] for row in res.data], ['Theirs'])

    def test_cannot_fetch_other_users_list(self):
        theirs = VacList.objects.create(name='Theirs', user=self.other)
        res = self.client.get(f'/api/vacation/lists/{theirs.id}/')
        self.assertEqual(res.status_code, 404)

    def test_cannot_attach_other_users_tag(self):
        tag = VacTag.objects.create(name='secret', user=self.other)
        res = self.client.post(
            '/api/vacation/items/',
            {'name': 'Sunscreen', 'tag_ids': [tag.id]},
            format='json',
        )
        self.assertEqual(res.status_code, 400)

    def test_populate_all_items_uses_own_catalog_only(self):
        VacItem.objects.create(name='Other item', user=self.other)
        mine = self.client.post('/api/vacation/items/', {'name': 'Mine'}, format='json')
        self.assertEqual(mine.status_code, 201)
        lst = self.client.post(
            '/api/vacation/lists/',
            {'name': 'Beach trip', 'populate': 'all_items'},
            format='json',
        )
        self.assertEqual(lst.status_code, 201)
        self.assertEqual(lst.data['added'], 1)
        items = self.client.get(f'/api/vacation/lists/{lst.data["id"]}/items/')
        self.assertEqual(len(items.data), 1)
        self.assertEqual(items.data[0]['item_detail']['name'], 'Mine')

    def test_cannot_copy_other_users_list(self):
        theirs = VacList.objects.create(name='Theirs', user=self.other)
        res = self.client.post(
            '/api/vacation/lists/',
            {'name': 'Clone', 'populate': 'copy', 'copy_from_id': theirs.id},
            format='json',
        )
        self.assertEqual(res.status_code, 400)

    def test_create_list_from_catalog(self):
        tag = self.client.post('/api/vacation/tags/', {'name': 'beach'}, format='json')
        self.assertEqual(tag.status_code, 201)
        item = self.client.post(
            '/api/vacation/items/',
            {'name': 'Sunscreen', 'tag_ids': [tag.data['id']]},
            format='json',
        )
        self.assertEqual(item.status_code, 201)
        lst = self.client.post(
            '/api/vacation/lists/',
            {'name': 'Beach trip', 'populate': 'all_items'},
            format='json',
        )
        self.assertEqual(lst.status_code, 201)
        self.assertEqual(lst.data['added'], 1)
        self.assertEqual(VacList.objects.filter(user=self.user).count(), 1)
        self.assertEqual(VacItem.objects.filter(user=self.user).count(), 1)
        items = self.client.get(f'/api/vacation/lists/{lst.data["id"]}/items/')
        self.assertEqual(items.status_code, 200)
        self.assertEqual(len(items.data), 1)
        self.assertEqual(items.data[0]['item_detail']['name'], 'Sunscreen')
        self.assertEqual(VacList.objects.get().user, self.user)
        self.assertEqual(VacItem.objects.get(name='Sunscreen').user, self.user)

    def test_dump_import_assigns_rows_to_target_user(self):
        import tempfile
        from pathlib import Path

        tag = VacTag.objects.create(name='Beach', user=self.user)
        cat = VacCategory.objects.create(name='Toiletries', user=self.user)
        item = VacItem.objects.create(name='Sunscreen', user=self.user, category=cat)
        item.tags.add(tag)
        vac_list = VacList.objects.create(name='Trip', user=self.user)
        VacListItem.objects.create(user=self.user, item=item, in_list=vac_list, need=True, done=False)

        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / 'vac.json'
            call_command('dump_vacation_fixture', email=self.user.email, output=str(fixture))
            call_command(
                'import_vacation_fixture',
                str(fixture),
                email=self.other.email,
                replace=True,
            )

        self.assertEqual(VacList.objects.filter(user=self.other, name='Trip').count(), 1)
        self.assertEqual(VacItem.objects.filter(user=self.other, name='Sunscreen').count(), 1)
        cloned = VacItem.objects.get(user=self.other, name='Sunscreen')
        self.assertEqual(cloned.category.name, 'Toiletries')
        self.assertEqual(list(cloned.tags.values_list('name', flat=True)), ['Beach'])
        self.assertEqual(VacList.objects.filter(user=self.user, name='Trip').count(), 1)
