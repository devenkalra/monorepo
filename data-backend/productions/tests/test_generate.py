from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from productions.generate import extract_json, normalize_script
from productions.models import Production


User = get_user_model()


class GenerateScriptTests(APITestCase):
    def test_extract_json_strips_fences(self):
        data = extract_json('```json\n{"title": "Ridge", "scenes": []}\n```')
        self.assertEqual(data['title'], 'Ridge')

    def test_normalize_fills_durations_visuals_and_type(self):
        script = normalize_script(
            {
                'title': 'Trail Story',
                'type': 'reel',
                'scenes': [
                    {
                        'title': 'Open',
                        'scene_type': 'hook',
                        'duration_seconds': 6.5,
                        'visuals': 'Face to camera on the ridge',
                        'voiceover': 'This trail almost beat me.',
                        'assets': ['drone shot'],
                    },
                    {
                        'title': 'Close',
                        'duration': '0:12',
                        'visuals': 'Sunset walk away',
                        'dialogue': 'See you at the next saddle.',
                    },
                ],
            },
            requested_type='short_form_documentary',
        )
        self.assertEqual(script['type'], 'reel')
        self.assertEqual(script['scenes'][0]['scene_type'], 'Hook')
        self.assertEqual(script['scenes'][0]['duration_seconds'], Decimal('6.500'))
        self.assertEqual(script['scenes'][1]['duration_seconds'], Decimal('12.000'))
        self.assertEqual(script['scenes'][1]['voiceover'], 'See you at the next saddle.')
        self.assertEqual(script['scenes'][0]['assets'], ['drone shot'])


class GenerateApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='maker', password='secret', email='maker@example.com')
        self.client.force_authenticate(self.user)

    def test_generate_requires_prompt(self):
        with patch('productions.views.llm_available', return_value=True):
            res = self.client.post('/api/productions/productions/generate/', {}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_generate_creates_production_from_model_json(self):
        payload = {
            'title': 'Ridge Walk',
            'subtitle': 'A short climb',
            'type': 'reel',
            'description': 'One hard mile.',
            'tags': ['trail'],
            'scenes': [
                {
                    'title': 'Hook',
                    'scene_type': 'Hook',
                    'duration_seconds': 5,
                    'visuals': 'Wide of the switchback',
                    'voiceover': 'I did not pack enough water.',
                    'assets': ['wide aerial'],
                },
                {
                    'title': 'Outro',
                    'scene_type': 'Outro',
                    'duration_seconds': 4,
                    'visuals': 'Summit wind',
                    'voiceover': 'Worth it.',
                },
            ],
        }
        with patch('productions.views.llm_available', return_value=True), patch(
            'productions.generate.chat_completion',
            return_value='{"title":"Ridge Walk"}',
        ), patch(
            'productions.generate.extract_json',
            return_value=payload,
        ):
            res = self.client.post(
                '/api/productions/productions/generate/',
                {'prompt': 'A sweaty hike to a windy summit', 'type': 'reel'},
                format='json',
            )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['title'], 'Ridge Walk')
        self.assertEqual(len(res.data['scenes']), 2)
        self.assertEqual(res.data['scenes'][0]['visuals'], 'Wide of the switchback')
        self.assertEqual(res.data['scenes'][0]['start'], '0:00')
        self.assertEqual(res.data['scenes'][1]['start'], '5')
        self.assertEqual(Production.objects.filter(user=self.user).count(), 1)
