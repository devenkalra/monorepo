from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from flightstudio.models import FlightPath

User = get_user_model()


class FlightstudioApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='flyer', password='secret', email='flyer@example.com'
        )

    def test_unauthenticated_rejected(self):
        res = self.client.get('/api/flightstudio/paths/')
        self.assertIn(res.status_code, (401, 403))

    def test_capabilities_are_2d_only(self):
        self.client.force_authenticate(self.user)
        res = self.client.get('/api/flightstudio/capabilities/')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data['sim'])
        self.assertTrue(res.data['map2d'])
        self.assertTrue(res.data['map3d'])
        self.assertIn('maps_api_key', res.data)

    def test_create_list_get_update_delete_path(self):
        self.client.force_authenticate(self.user)
        created = self.client.post(
            '/api/flightstudio/paths/new/',
            {'path_id': 'shot-1', 'location': 'manhattan', 'duration': 36},
            format='json',
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data['meta']['path_id'], 'shot-1')
        self.assertGreaterEqual(len(created.data['flight_keyframes']), 2)

        listed = self.client.get('/api/flightstudio/paths/')
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.data[0]['path_id'], 'shot-1')

        detail = self.client.get('/api/flightstudio/paths/shot-1/')
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data['meta']['path_id'], 'shot-1')

        document = detail.data
        document['meta']['output_fps'] = 24
        saved = self.client.put('/api/flightstudio/paths/shot-1/', document, format='json')
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.data['meta']['output_fps'], 24)

        deleted = self.client.delete('/api/flightstudio/paths/shot-1/')
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(FlightPath.objects.filter(owner=self.user, path_id='shot-1').exists())

    def test_paths_are_per_user(self):
        other = User.objects.create_user(username='other', password='secret')
        self.client.force_authenticate(self.user)
        self.client.post(
            '/api/flightstudio/paths/new/',
            {'path_id': 'mine', 'location': 'manhattan', 'duration': 36},
            format='json',
        )
        self.client.force_authenticate(other)
        listed = self.client.get('/api/flightstudio/paths/')
        self.assertEqual(listed.data, [])
        hidden = self.client.get('/api/flightstudio/paths/mine/')
        self.assertEqual(hidden.status_code, 404)

    def test_preview_and_validate(self):
        self.client.force_authenticate(self.user)
        created = self.client.post(
            '/api/flightstudio/paths/new/',
            {'path_id': 'preview-1', 'location': 'manhattan', 'duration': 36},
            format='json',
        )
        preview = self.client.post('/api/flightstudio/paths/preview/', created.data, format='json')
        self.assertEqual(preview.status_code, 200)
        self.assertGreater(len(preview.data['samples']), 2)
        self.assertIn('lat', preview.data['samples'][0])
        self.assertGreater(len(preview.data['camera_track']), 2)
        self.assertIn('heading', preview.data['camera_track'][0])
        self.assertIn('pitch', preview.data['camera_track'][0])

        valid = self.client.post('/api/flightstudio/paths/validate/', created.data, format='json')
        self.assertEqual(valid.status_code, 200)
        self.assertIn('playable', valid.data)

    def test_earth_studio_export(self):
        self.client.force_authenticate(self.user)
        created = self.client.post(
            '/api/flightstudio/paths/new/',
            {'path_id': 'esp-1', 'location': 'manhattan', 'duration': 36},
            format='json',
        )
        res = self.client.post('/api/flightstudio/earth-studio/', created.data, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['modelVersion'], 18)
        self.assertEqual(res.data['settings']['name'], 'esp-1')

        preview = self.client.post(
            '/api/flightstudio/paths/preview/', created.data, format='json'
        )
        self.assertEqual(preview.status_code, 200)
        cam = preview.data['camera_track'][0]
        channels = {}

        def walk(node):
            if isinstance(node, dict):
                if node.get('type') in (
                    'longitude', 'latitude', 'altitude', 'rotationX', 'rotationY', 'fov'
                ) and node.get('keyframes'):
                    channels[node['type']] = node['keyframes'][0]['value']
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(res.data)
        lon = channels['longitude'] * 360.0 - 180.0
        lat = channels['latitude'] * 180.0 - 90.0
        tilt = channels['rotationY'] * 180.0
        pan = (channels['rotationX'] * 360.0) % 360.0
        self.assertAlmostEqual(lon, cam['lon'], places=4)
        self.assertAlmostEqual(lat, cam['lat'], places=4)
        self.assertAlmostEqual(tilt, 90.0 + cam['pitch'], places=1)
        self.assertAlmostEqual(pan, cam['heading'] % 360.0, places=1)

    def test_map_overlay_round_trip(self):
        self.client.force_authenticate(self.user)
        self.client.post(
            '/api/flightstudio/paths/new/',
            {'path_id': 'map-1', 'location': 'manhattan', 'duration': 36},
            format='json',
        )
        overlay = {
            'path_id': 'map-1',
            'schema_version': 1,
            'line': {'color': '#ff0000', 'width_px': 4, 'opacity': 0.8, 'dash': 'SOLID'},
            'map_keyframes': [],
            'markers': [],
        }
        saved = self.client.put('/api/flightstudio/paths/map-1/map/', overlay, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        loaded = self.client.get('/api/flightstudio/paths/map-1/map/')
        self.assertEqual(loaded.data['line']['color'], '#ff0000')

    def test_sim_routes_are_unavailable(self):
        self.client.force_authenticate(self.user)
        res = self.client.post('/api/flightstudio/simulation/start', {}, format='json')
        self.assertEqual(res.status_code, 409)

    def test_locations(self):
        self.client.force_authenticate(self.user)
        res = self.client.get('/api/flightstudio/locations/')
        self.assertEqual(res.status_code, 200)
        keys = {item['key'] for item in res.data}
        self.assertIn('manhattan', keys)

    def test_create_list_get_program_path(self):
        """Stage 6: a program path persists, lists as kind=program, and previews."""
        self.client.force_authenticate(self.user)
        demos = self.client.get('/api/flightstudio/program/demos/')
        self.assertEqual(demos.status_code, 200)
        self.assertTrue(demos.data['demos'])

        created = self.client.post(
            '/api/flightstudio/paths/new/',
            {
                'path_id': 'prog-1',
                'location': 'manhattan',
                'kind': 'program',
                'demo': 'figure-eight',
                'duration': 60,
            },
            format='json',
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data['kind'], 'program')
        self.assertEqual(created.data['path_id'], 'prog-1')
        self.assertGreaterEqual(len(created.data['program']['segments']), 2)
        # Relative demos re-home to the chosen location.
        self.assertAlmostEqual(created.data['program']['origin']['lat'], 40.7, places=2)

        listed = self.client.get('/api/flightstudio/paths/')
        self.assertEqual(listed.status_code, 200)
        row = next(item for item in listed.data if item['path_id'] == 'prog-1')
        self.assertEqual(row['kind'], 'program')

        detail = self.client.get('/api/flightstudio/paths/prog-1/')
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data['kind'], 'program')
        self.assertEqual(detail.data['program']['segments'][0]['kind'], 'LINE_TO')

        preview = self.client.post(
            '/api/flightstudio/program/preview/',
            {'program': detail.data['program'], 'samples': 60},
            format='json',
        )
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertGreater(preview.data['duration'], 0)
        self.assertGreater(len(preview.data['samples']), 2)
        self.assertIn('path_kind', preview.data['samples'][0])

        stored = FlightPath.objects.get(owner=self.user, path_id='prog-1')
        self.assertIsInstance(stored.program, dict)
        self.assertTrue(stored.program.get('segments'))

    def test_program_cut_demo_marks_break_before(self):
        self.client.force_authenticate(self.user)
        created = self.client.post(
            '/api/flightstudio/paths/new/',
            {'path_id': 'cut-1', 'kind': 'program', 'demo': 'cut', 'duration': 40},
            format='json',
        )
        self.assertEqual(created.status_code, 201, created.data)
        preview = self.client.post(
            '/api/flightstudio/program/preview/',
            {'program': created.data['program']},
            format='json',
        )
        self.assertEqual(preview.status_code, 200, preview.data)
        breaks = [row for row in preview.data['samples'] if row.get('break_before')]
        self.assertEqual(len(breaks), 1)

    def test_waypoint_ids_names_and_groups_round_trip(self):
        self.client.force_authenticate(self.user)
        created = self.client.post(
            '/api/flightstudio/paths/new/',
            {'path_id': 'named-1', 'location': 'manhattan', 'duration': 36},
            format='json',
        )
        self.assertEqual(created.status_code, 201, created.data)
        frames = created.data['flight_keyframes']
        ids = [frame['id'] for frame in frames]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(ids))
        frames[0]['name'] = 'Start'
        frames[1]['name'] = 'Turn'
        created.data['groups'] = [{
            'id': 'grp-approach',
            'name': 'Approach',
            'color': '#3ecf9a',
            'member_ids': [frames[0]['id'], frames[1]['id']],
        }]
        saved = self.client.put('/api/flightstudio/paths/named-1/', created.data, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(saved.data['flight_keyframes'][0]['name'], 'Start')
        self.assertEqual(saved.data['groups'][0]['name'], 'Approach')
        self.assertEqual(saved.data['groups'][0]['member_ids'], [frames[0]['id'], frames[1]['id']])
