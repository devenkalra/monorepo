from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from productions.models import Production, Scene


User = get_user_model()


class ProductionApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='maker', password='secret', email='maker@example.com')
        self.other = User.objects.create_user(username='other', password='secret', email='other@example.com')
        self.client.force_authenticate(self.user)

    def _create(self, **kwargs):
        payload = {
            'title': 'Trail Story',
            'type': 'short_form_documentary',
            **kwargs,
        }
        return self.client.post('/api/productions/productions/', payload, format='json')

    def test_unauthenticated_rejected(self):
        self.client.force_authenticate(user=None)
        res = self.client.get('/api/productions/productions/')
        self.assertIn(res.status_code, (401, 403))

    def test_productions_are_isolated_per_user(self):
        Production.objects.create(title='Mine', production_type='reel', user=self.user)
        Production.objects.create(title='Theirs', production_type='reel', user=self.other)
        res = self.client.get('/api/productions/productions/')
        self.assertEqual([row['title'] for row in res.data], ['Mine'])
        self.client.force_authenticate(self.other)
        res = self.client.get('/api/productions/productions/')
        self.assertEqual([row['title'] for row in res.data], ['Theirs'])

    def test_cannot_fetch_other_users_production(self):
        theirs = Production.objects.create(title='Theirs', production_type='reel', user=self.other)
        res = self.client.get(f'/api/productions/productions/{theirs.id}/')
        self.assertEqual(res.status_code, 404)

    def test_create_requires_title_and_type(self):
        res = self.client.post('/api/productions/productions/', {'type': 'reel'}, format='json')
        self.assertEqual(res.status_code, 400)
        res = self._create()
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['type'], 'short_form_documentary')
        self.assertEqual(res.data['type_label'], 'Short Form Documentary')

    def test_archive_hidden_from_default_list(self):
        created = self._create()
        pk = created.data['id']
        self.client.post(f'/api/productions/productions/{pk}/archive/')
        res = self.client.get('/api/productions/productions/')
        self.assertEqual(res.data, [])
        res = self.client.get('/api/productions/productions/?archived=1')
        self.assertEqual(len(res.data), 1)
        self.assertTrue(res.data[0]['is_archived'])

    def test_search_and_type_filter(self):
        self._create(title='Yosemite Reel', type='reel', tags=['yosemite', 'hike'])
        self._create(title='Long doc', type='long_form_documentary', tags=['city'])
        res = self.client.get('/api/productions/productions/?q=yosemite')
        self.assertEqual([row['title'] for row in res.data], ['Yosemite Reel'])
        res = self.client.get('/api/productions/productions/?type=long_form_documentary')
        self.assertEqual([row['title'] for row in res.data], ['Long doc'])

    def test_scene_title_roundtrip(self):
        pk = self._create().data['id']
        created = self.client.post(
            '/api/productions/scenes/',
            {'production_id': pk, 'title': 'Open on the ridge', 'scene_type': 'Hook'},
            format='json',
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data['title'], 'Open on the ridge')
        self.client.patch(
            f'/api/productions/scenes/{created.data["id"]}/',
            {'title': 'Cold open'},
            format='json',
        )
        detail = self.client.get(f'/api/productions/productions/{pk}/')
        self.assertEqual(detail.data['scenes'][0]['title'], 'Cold open')

    def test_scene_times_cascade_on_duration_and_end(self):
        pk = self._create().data['id']
        first = self.client.post(
            '/api/productions/scenes/',
            {'production_id': pk, 'scene_type': 'Hook', 'duration': '10', 'voiceover': 'Hello'},
            format='json',
        )
        second = self.client.post(
            '/api/productions/scenes/',
            {'production_id': pk, 'scene_type': 'Intro', 'duration': '10'},
            format='json',
        )
        third = self.client.post(
            '/api/productions/scenes/',
            {'production_id': pk, 'scene_type': 'Body', 'duration': '10'},
            format='json',
        )
        self.assertEqual(first.data['start'], '0:00')
        self.assertEqual(second.data['start'], '10')
        self.client.patch(f'/api/productions/scenes/{first.data["id"]}/', {'duration': '15'}, format='json')
        detail = self.client.get(f'/api/productions/productions/{pk}/')
        starts = [scene['start'] for scene in detail.data['scenes']]
        self.assertEqual(starts, ['0:00', '15', '25'])
        self.client.patch(f'/api/productions/scenes/{second.data["id"]}/', {'end': '40'}, format='json')
        detail = self.client.get(f'/api/productions/productions/{pk}/')
        scenes = detail.data['scenes']
        self.assertEqual(scenes[1]['duration'], '25')
        self.assertEqual(scenes[2]['start'], '40')
        self.assertEqual(third.data['id'], scenes[2]['id'])

    def test_end_before_start_does_not_cascade(self):
        pk = self._create().data['id']
        first = self.client.post(
            '/api/productions/scenes/',
            {'production_id': pk, 'duration': '10'},
            format='json',
        )
        second = self.client.post(
            '/api/productions/scenes/',
            {'production_id': pk, 'duration': '10'},
            format='json',
        )
        res = self.client.patch(
            f'/api/productions/scenes/{second.data["id"]}/',
            {'end': '5'},
            format='json',
        )
        self.assertEqual(res.status_code, 400)
        detail = self.client.get(f'/api/productions/productions/{pk}/')
        self.assertEqual([scene['start'] for scene in detail.data['scenes']], ['0:00', '10'])
        self.assertEqual(first.data['id'], detail.data['scenes'][0]['id'])

    def test_insert_after_places_scene_and_cascades(self):
        pk = self._create().data['id']
        first = self.client.post(
            '/api/productions/scenes/',
            {'production_id': pk, 'title': 'A', 'duration': '10'},
            format='json',
        )
        self.client.post(
            '/api/productions/scenes/',
            {'production_id': pk, 'title': 'C', 'duration': '10'},
            format='json',
        )
        middle = self.client.post(
            '/api/productions/scenes/',
            {'production_id': pk, 'title': 'B', 'duration': '8', 'after_id': first.data['id']},
            format='json',
        )
        self.assertEqual(middle.status_code, 201)
        detail = self.client.get(f'/api/productions/productions/{pk}/')
        titles = [scene['title'] for scene in detail.data['scenes']]
        starts = [scene['start'] for scene in detail.data['scenes']]
        self.assertEqual(titles, ['A', 'B', 'C'])
        self.assertEqual(starts, ['0:00', '10', '18'])

    def test_move_recomputes_starts(self):
        pk = self._create().data['id']
        a = self.client.post('/api/productions/scenes/', {'production_id': pk, 'scene_type': 'A', 'duration': '5'}, format='json')
        b = self.client.post('/api/productions/scenes/', {'production_id': pk, 'scene_type': 'B', 'duration': '20'}, format='json')
        self.client.post(f'/api/productions/scenes/{b.data["id"]}/move/', {'direction': 'up'}, format='json')
        detail = self.client.get(f'/api/productions/productions/{pk}/')
        types = [scene['scene_type'] for scene in detail.data['scenes']]
        starts = [scene['start'] for scene in detail.data['scenes']]
        self.assertEqual(types, ['B', 'A'])
        self.assertEqual(starts, ['0:00', '20'])
        self.assertEqual(a.data['id'], detail.data['scenes'][1]['id'])

    def test_teleprompter_and_asset_todos(self):
        pk = self._create().data['id']
        self.client.post(
            '/api/productions/scenes/',
            {
                'production_id': pk,
                'scene_type': 'Hook',
                'voiceover': 'Open on the ridge',
                'assets': ['Drone shot', 'Map'],
            },
            format='json',
        )
        self.client.post(
            '/api/productions/scenes/',
            {
                'production_id': pk,
                'scene_type': 'Intro',
                'voiceover': '',
                'assets': ['drone shot'],
            },
            format='json',
        )
        detail = self.client.get(f'/api/productions/productions/{pk}/')
        self.assertEqual(detail.data['teleprompter'], '[HOOK]\nOpen on the ridge')
        names = {row['name_key']: row for row in detail.data['asset_todos']}
        self.assertEqual(len(names['drone shot']['scenes']), 2)
        self.assertEqual(names['drone shot']['status'], 'todo')
        self.client.patch(
            f'/api/productions/productions/{pk}/assets/',
            {'name': 'Drone shot', 'status': 'done'},
            format='json',
        )
        detail = self.client.get(f'/api/productions/productions/{pk}/')
        names = {row['name_key']: row for row in detail.data['asset_todos']}
        self.assertEqual(names['drone shot']['status'], 'done')

    def test_duplicate_copies_script_and_asset_status(self):
        pk = self._create(title='Original', tags=['desert']).data['id']
        self.client.post(
            '/api/productions/scenes/',
            {'production_id': pk, 'scene_type': 'Hook', 'voiceover': 'Hi', 'assets': ['Map']},
            format='json',
        )
        self.client.patch(
            f'/api/productions/productions/{pk}/assets/',
            {'name': 'Map', 'status': 'in_progress'},
            format='json',
        )
        res = self.client.post(f'/api/productions/productions/{pk}/duplicate/')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['title'], 'Copy of Original')
        self.assertEqual(res.data['tags'], ['desert'])
        self.assertEqual(res.data['scenes'][0]['voiceover'], 'Hi')
        self.assertEqual(res.data['asset_todos'][0]['status'], 'in_progress')
        self.assertEqual(Production.objects.filter(user=self.user).count(), 2)
        self.assertEqual(Scene.objects.filter(user=self.user).count(), 2)

    def test_cannot_add_scene_to_other_users_production(self):
        theirs = Production.objects.create(title='Theirs', production_type='reel', user=self.other)
        res = self.client.post(
            '/api/productions/scenes/',
            {'production_id': theirs.id, 'duration': '10'},
            format='json',
        )
        self.assertEqual(res.status_code, 400)

    def _seed_exportable(self):
        created = self._create(
            title='Ridge Walk',
            subtitle='A climb',
            type='reel',
            description='One hard mile.',
            tags=['trail', 'heat'],
        )
        pk = created.data['id']
        self.client.post(
            '/api/productions/scenes/',
            {
                'production_id': pk,
                'title': 'Open',
                'scene_type': 'Hook',
                'duration': '8',
                'visuals': 'Face on the ridge',
                'voiceover': 'I did not pack enough water.',
                'music': 'thin drone',
                'assets': ['Drone shot', 'Map'],
            },
            format='json',
        )
        self.client.post(
            '/api/productions/scenes/',
            {
                'production_id': pk,
                'title': 'Close',
                'scene_type': 'Outro',
                'duration': '6',
                'visuals': 'Walk away',
                'voiceover': 'See you at the next saddle.',
            },
            format='json',
        )
        self.client.patch(
            f'/api/productions/productions/{pk}/assets/',
            {'name': 'Map', 'status': 'in_progress'},
            format='json',
        )
        return pk

    def test_export_one_is_portable_json(self):
        pk = self._seed_exportable()
        res = self.client.get(f'/api/productions/productions/{pk}/export/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['format'], 'bldrdojo.productions')
        self.assertEqual(res.data['version'], 1)
        self.assertEqual(len(res.data['productions']), 1)
        payload = res.data['productions'][0]
        self.assertEqual(payload['title'], 'Ridge Walk')
        self.assertEqual(payload['type'], 'reel')
        self.assertEqual(payload['tags'], ['trail', 'heat'])
        self.assertNotIn('id', payload)
        self.assertEqual([scene['title'] for scene in payload['scenes']], ['Open', 'Close'])
        self.assertNotIn('id', payload['scenes'][0])
        self.assertNotIn('start', payload['scenes'][0])
        self.assertEqual(payload['scenes'][0]['assets'], ['Drone shot', 'Map'])
        statuses = {row['name']: row['status'] for row in payload['asset_statuses']}
        self.assertEqual(statuses['Map'], 'in_progress')
        self.assertIn('attachment', res['Content-Disposition'])
        self.assertIn('ridge-walk.json', res['Content-Disposition'])

    def test_cannot_export_other_users_production(self):
        theirs = Production.objects.create(title='Theirs', production_type='reel', user=self.other)
        res = self.client.get(f'/api/productions/productions/{theirs.id}/export/')
        self.assertEqual(res.status_code, 404)

    def test_export_all_includes_archived(self):
        self._seed_exportable()
        second = self._create(title='City Reel', type='reel').data['id']
        self.client.post(f'/api/productions/productions/{second}/archive/')
        res = self.client.get('/api/productions/productions/export/')
        self.assertEqual(res.status_code, 200)
        titles = {row['title'] for row in res.data['productions']}
        self.assertEqual(titles, {'Ridge Walk', 'City Reel'})
        archived = {row['title']: row['is_archived'] for row in res.data['productions']}
        self.assertTrue(archived['City Reel'])
        self.assertFalse(archived['Ridge Walk'])

    def test_import_roundtrip_creates_new_ids(self):
        pk = self._seed_exportable()
        exported = self.client.get(f'/api/productions/productions/{pk}/export/').data
        Production.objects.filter(user=self.user).delete()
        res = self.client.post('/api/productions/productions/import/', exported, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['count'], 1)
        created = res.data['productions'][0]
        self.assertNotEqual(created['id'], pk)
        self.assertEqual(created['title'], 'Ridge Walk')
        self.assertEqual(created['subtitle'], 'A climb')
        self.assertEqual(created['type'], 'reel')
        self.assertEqual([scene['title'] for scene in created['scenes']], ['Open', 'Close'])
        self.assertEqual(created['scenes'][0]['start'], '0:00')
        self.assertEqual(created['scenes'][1]['start'], '8')
        self.assertEqual(created['scenes'][0]['voiceover'], 'I did not pack enough water.')
        self.assertEqual(created['scenes'][0]['assets'], ['Drone shot', 'Map'])
        todos = {row['name']: row['status'] for row in created['asset_todos']}
        self.assertEqual(todos['Map'], 'in_progress')
        self.assertEqual(Production.objects.filter(user=self.user).count(), 1)

    def test_import_accepts_bare_production_object(self):
        res = self.client.post(
            '/api/productions/productions/import/',
            {
                'title': 'Bare import',
                'type': 'long_form_documentary',
                'scenes': [{'title': 'Only', 'duration': '12', 'voiceover': 'Hello'}],
            },
            format='json',
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['count'], 1)
        created = res.data['productions'][0]
        self.assertEqual(created['title'], 'Bare import')
        self.assertEqual(created['type'], 'long_form_documentary')
        self.assertEqual(created['scenes'][0]['duration'], '12')
        self.assertEqual(created['scenes'][0]['voiceover'], 'Hello')

    def test_import_rejects_empty_and_assigns_to_current_user(self):
        res = self.client.post('/api/productions/productions/import/', {'productions': []}, format='json')
        self.assertEqual(res.status_code, 400)
        res = self.client.post(
            '/api/productions/productions/import/',
            {'scenes': [{'title': 'No title on production'}]},
            format='json',
        )
        self.assertEqual(res.status_code, 400)
        res = self.client.post(
            '/api/productions/productions/import/',
            {'title': 'Owned', 'scenes': []},
            format='json',
        )
        self.assertEqual(res.status_code, 201)
        production = Production.objects.get(pk=res.data['productions'][0]['id'])
        self.assertEqual(production.user, self.user)
        self.assertEqual(production.scenes.count(), 0)
