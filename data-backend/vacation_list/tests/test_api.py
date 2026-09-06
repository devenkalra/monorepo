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


class VacationItemBulkTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='vacbulk', password='secret', email='vacbulk@example.com')
        self.other = User.objects.create_user(username='vacother', password='secret', email='vacother@example.com')
        self.client.force_authenticate(self.user)
        self.beach = VacTag.objects.create(name='Beach', user=self.user)
        self.cold = VacTag.objects.create(name='Cold', user=self.user)
        self.toiletries = VacCategory.objects.create(name='Toiletries', user=self.user)
        self.docs = VacCategory.objects.create(name='Documents', user=self.user)
        self.sunscreen = VacItem.objects.create(name='Sunscreen', user=self.user)
        self.passport = VacItem.objects.create(name='Passport', user=self.user)
        self.theirs = VacItem.objects.create(name='Theirs', user=self.other)
        self.other_tag = VacTag.objects.create(name='Secret', user=self.other)
        self.other_cat = VacCategory.objects.create(name='Secret cat', user=self.other)

    def test_bulk_requires_ids(self):
        res = self.client.post('/api/vacation/items/bulk/', {'name_group': 'Kit'}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_bulk_requires_an_action(self):
        res = self.client.post(
            '/api/vacation/items/bulk/',
            {'ids': [self.sunscreen.id]},
            format='json',
        )
        self.assertEqual(res.status_code, 400)

    def test_bulk_set_group(self):
        res = self.client.post(
            '/api/vacation/items/bulk/',
            {'ids': [self.sunscreen.id, self.passport.id], 'name_group': 'Essentials'},
            format='json',
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['updated'], 2)
        self.sunscreen.refresh_from_db()
        self.passport.refresh_from_db()
        self.assertEqual(self.sunscreen.name_group, 'Essentials')
        self.assertEqual(self.passport.name_group, 'Essentials')

    def test_bulk_set_category(self):
        res = self.client.post(
            '/api/vacation/items/bulk/',
            {'ids': [self.sunscreen.id], 'category_id': self.toiletries.id},
            format='json',
        )
        self.assertEqual(res.status_code, 200)
        self.sunscreen.refresh_from_db()
        self.assertEqual(self.sunscreen.category_id, self.toiletries.id)

    def test_bulk_add_tag_keeps_existing(self):
        self.sunscreen.tags.add(self.beach)
        res = self.client.post(
            '/api/vacation/items/bulk/',
            {'ids': [self.sunscreen.id, self.passport.id], 'add_tag_id': self.cold.id},
            format='json',
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['updated'], 2)
        self.assertCountEqual(
            list(self.sunscreen.tags.values_list('id', flat=True)),
            [self.beach.id, self.cold.id],
        )
        self.assertEqual(list(self.passport.tags.values_list('id', flat=True)), [self.cold.id])

        again = self.client.post(
            '/api/vacation/items/bulk/',
            {'ids': [self.sunscreen.id], 'add_tag_id': self.cold.id},
            format='json',
        )
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.data['updated'], 0)

    def test_bulk_remove_tag_only_if_present(self):
        self.sunscreen.tags.add(self.beach, self.cold)
        res = self.client.post(
            '/api/vacation/items/bulk/',
            {'ids': [self.sunscreen.id, self.passport.id], 'remove_tag_id': self.beach.id},
            format='json',
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['updated'], 1)
        self.assertEqual(list(self.sunscreen.tags.values_list('id', flat=True)), [self.cold.id])
        self.assertEqual(self.passport.tags.count(), 0)

    def test_bulk_delete_cascades_list_rows(self):
        vac_list = VacList.objects.create(name='Trip', user=self.user)
        VacListItem.objects.create(user=self.user, item=self.sunscreen, in_list=vac_list)
        res = self.client.post(
            '/api/vacation/items/bulk/',
            {'ids': [self.sunscreen.id], 'delete': True},
            format='json',
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['deleted'], 1)
        self.assertFalse(VacItem.objects.filter(id=self.sunscreen.id).exists())
        self.assertFalse(VacListItem.objects.filter(item_id=self.sunscreen.id).exists())
        self.assertTrue(VacItem.objects.filter(id=self.passport.id).exists())

    def test_bulk_ignores_other_users_items_and_tags(self):
        res = self.client.post(
            '/api/vacation/items/bulk/',
            {'ids': [self.theirs.id], 'name_group': 'Stolen'},
            format='json',
        )
        self.assertEqual(res.status_code, 400)
        self.theirs.refresh_from_db()
        self.assertEqual(self.theirs.name_group, '')

        bad_tag = self.client.post(
            '/api/vacation/items/bulk/',
            {'ids': [self.sunscreen.id], 'add_tag_id': self.other_tag.id},
            format='json',
        )
        self.assertEqual(bad_tag.status_code, 400)
        self.assertEqual(self.sunscreen.tags.count(), 0)

        bad_cat = self.client.post(
            '/api/vacation/items/bulk/',
            {'ids': [self.sunscreen.id], 'category_id': self.other_cat.id},
            format='json',
        )
        self.assertEqual(bad_cat.status_code, 400)


def _png_upload(name='shot.png'):
    import io
    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    buf = io.BytesIO()
    Image.new('RGB', (8, 8), (20, 90, 160)).save(buf, format='PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


class VacationItemImageTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='vacimg', password='secret', email='vacimg@example.com')
        self.other = User.objects.create_user(username='vacimg2', password='secret', email='vacimg2@example.com')
        self.client.force_authenticate(self.user)
        self.item = VacItem.objects.create(name='Passport', user=self.user)

    def test_upload_and_replace_and_delete_image(self):
        res = self.client.post(
            f'/api/vacation/items/{self.item.id}/image/',
            {'file': _png_upload('one.png')},
            format='multipart',
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data['image'])
        self.item.refresh_from_db()
        first_name = self.item.image.name

        res = self.client.post(
            f'/api/vacation/items/{self.item.id}/image/',
            {'file': _png_upload('two.png')},
            format='multipart',
        )
        self.assertEqual(res.status_code, 200)
        self.item.refresh_from_db()
        self.assertTrue(self.item.image)
        self.assertNotEqual(self.item.image.name, first_name)

        res = self.client.delete(f'/api/vacation/items/{self.item.id}/image/')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data['image'])
        self.item.refresh_from_db()
        self.assertFalse(self.item.image)

    def test_rejects_non_image(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        res = self.client.post(
            f'/api/vacation/items/{self.item.id}/image/',
            {'file': SimpleUploadedFile('notes.txt', b'hello', content_type='text/plain')},
            format='multipart',
        )
        self.assertEqual(res.status_code, 400)
        self.item.refresh_from_db()
        self.assertFalse(self.item.image)

    def test_cannot_upload_to_other_users_item(self):
        theirs = VacItem.objects.create(name='Theirs', user=self.other)
        res = self.client.post(
            f'/api/vacation/items/{theirs.id}/image/',
            {'file': _png_upload()},
            format='multipart',
        )
        self.assertEqual(res.status_code, 404)


class VacationItemArchiveTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='vacarch', password='secret', email='vacarch@example.com')
        self.client.force_authenticate(self.user)
        self.active = VacItem.objects.create(name='Sunscreen', user=self.user)
        self.hidden = VacItem.objects.create(name='Old tent', user=self.user, is_archived=True)

    def test_list_hides_archived_by_default(self):
        res = self.client.get('/api/vacation/items/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual([row['name'] for row in res.data], ['Sunscreen'])

        archived = self.client.get('/api/vacation/items/?archived=1')
        self.assertEqual([row['name'] for row in archived.data], ['Old tent'])

    def test_bulk_archive_and_unarchive(self):
        res = self.client.post(
            '/api/vacation/items/bulk/',
            {'ids': [self.active.id], 'archive': True},
            format='json',
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['updated'], 1)
        self.active.refresh_from_db()
        self.assertTrue(self.active.is_archived)

        res = self.client.post(
            '/api/vacation/items/bulk/',
            {'ids': [self.active.id], 'unarchive': True},
            format='json',
        )
        self.assertEqual(res.status_code, 200)
        self.active.refresh_from_db()
        self.assertFalse(self.active.is_archived)

    def test_archived_item_stays_on_packing_list(self):
        vac_list = VacList.objects.create(name='Trip', user=self.user)
        VacListItem.objects.create(user=self.user, item=self.hidden, in_list=vac_list)
        items = self.client.get(f'/api/vacation/lists/{vac_list.id}/items/')
        self.assertEqual(items.status_code, 200)
        self.assertEqual(len(items.data), 1)
        self.assertEqual(items.data[0]['item_detail']['name'], 'Old tent')
        self.assertTrue(items.data[0]['item_detail']['is_archived'])

    def test_populate_all_skips_archived(self):
        lst = self.client.post(
            '/api/vacation/lists/',
            {'name': 'Beach', 'populate': 'all_items'},
            format='json',
        )
        self.assertEqual(lst.status_code, 201)
        self.assertEqual(lst.data['added'], 1)
        items = self.client.get(f'/api/vacation/lists/{lst.data["id"]}/items/')
        self.assertEqual([row['item_detail']['name'] for row in items.data], ['Sunscreen'])
