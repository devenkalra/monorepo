from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from people.models import EntityRelation, Movie, Note, Person
from people.from_drop import _is_safe_to_fetch, _request_headers


User = get_user_model()


class FakeResponse:
    def __init__(self, content, content_type='text/html', status_code=200, url='https://example.com/x'):
        self.content = content
        self.headers = {'Content-Type': content_type}
        self.status_code = status_code
        self.is_redirect = False
        self.url = url

    def iter_content(self, size=1024):
        yield self.content


class FromDropApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='dropper', password='secret', email='dropper@example.com')
        self.other = User.objects.create_user(username='other', password='secret', email='other@example.com')
        self.client.force_authenticate(self.user)

    @patch('people.from_drop.llm_available', return_value=False)
    def test_empty_drop_rejected(self, _llm):
        res = self.client.post('/api/entities/from-drop/', {}, format='json')
        self.assertEqual(res.status_code, 400)

    @patch('people.from_drop.llm_available', return_value=False)
    def test_movie_text_creates_director_relation(self, _llm):
        existing = Person.objects.create(user=self.user, display='Christopher Nolan', first_name='Christopher', last_name='Nolan')
        res = self.client.post(
            '/api/entities/from-drop/',
            {
                'text': 'Inception (2010)\nDirected by Christopher Nolan\nA thief who steals corporate secrets through dream-sharing.',
                'html': '',
            },
            format='json',
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['type'], 'Movie')
        self.assertIn('Inception', res.data['display'])
        self.assertEqual(res.data['year'], 2010)
        movie = Movie.objects.get(pk=res.data['id'])
        rel = EntityRelation.objects.get(from_entity=movie, relation_type='HAS_DIRECTOR')
        self.assertEqual(rel.to_entity_id, existing.id)
        self.assertEqual(Person.objects.filter(user=self.user).count(), 1)

    @patch('people.from_drop.llm_available', return_value=False)
    def test_book_text_creates_author(self, _llm):
        res = self.client.post(
            '/api/entities/from-drop/',
            {
                'text': 'The Hobbit\nAuthor: J.R.R. Tolkien\nThis paperback follows Bilbo Baggins. ISBN 978-0-261-10221-7',
            },
            format='json',
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['type'], 'Book')
        author = Person.objects.get(user=self.user, display='J.R.R. Tolkien')
        self.assertTrue(EntityRelation.objects.filter(
            from_entity_id=res.data['id'],
            to_entity=author,
            relation_type='HAS_AS_AUTHOR',
        ).exists())

    @patch('people.from_drop.llm_available', return_value=False)
    @patch('people.from_drop._http_get')
    def test_image_link_is_downloaded_and_rebased(self, mock_get, _llm):
        image_url = 'https://cdn.example.com/poster.jpg'
        mock_get.return_value = FakeResponse(b'\xff\xd8\xff' + b'x' * 40, content_type='image/jpeg', url=image_url)
        html = f'<p>Inception poster</p><img src="{image_url}">'
        res = self.client.post(
            '/api/entities/from-drop/',
            {
                'text': 'Inception\nDirected by Christopher Nolan',
                'html': html,
            },
            format='json',
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['type'], 'Movie')
        self.assertTrue(res.data['photos'])
        local_url = res.data['photos'][0]['url']
        self.assertTrue(local_url.startswith('/media/'))
        self.assertIn(local_url, res.data['description'])
        self.assertNotIn(image_url, res.data['description'])

    @patch('people.from_drop.llm_available', return_value=False)
    def test_dropped_image_file_becomes_note_photo(self, _llm):
        upload = SimpleUploadedFile('ridge.jpg', b'\xff\xd8\xff' + b'y' * 40, content_type='image/jpeg')
        res = self.client.post(
            '/api/entities/from-drop/',
            {'files': upload},
            format='multipart',
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['type'], 'Note')
        self.assertEqual(res.data['photos'][0]['filename'], 'ridge.jpg')
        self.assertTrue(Note.objects.filter(pk=res.data['id'], user=self.user).exists())

    @patch('people.from_drop.llm_available', return_value=False)
    def test_unauthenticated_rejected(self, _llm):
        self.client.force_authenticate(user=None)
        res = self.client.post('/api/entities/from-drop/', {'text': 'Hello'}, format='json')
        self.assertIn(res.status_code, (401, 403))

    def test_private_urls_are_blocked(self):
        self.assertFalse(_is_safe_to_fetch('http://127.0.0.1/secret'))
        self.assertFalse(_is_safe_to_fetch('http://localhost/x'))
        self.assertFalse(_is_safe_to_fetch('file:///etc/passwd'))

    @patch('people.from_drop.llm_available', return_value=False)
    @patch('people.from_drop._is_safe_to_fetch', return_value=True)
    @patch('people.from_drop._http_get')
    def test_upload_from_url_downloads_on_server(self, mock_get, _safe, _llm):
        image_url = 'https://cdn.example.com/cover.jpg'
        mock_get.return_value = FakeResponse(b'\xff\xd8\xff' + b'z' * 40, content_type='image/jpeg', url=image_url)
        res = self.client.post('/api/upload/from-url/', {'url': image_url}, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertTrue(res.data.get('url', '').startswith('/media/'))

    def test_upload_from_url_rejects_private_hosts(self):
        res = self.client.post('/api/upload/from-url/', {'url': 'http://127.0.0.1/secret.jpg'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('cannot be fetched', res.data.get('detail', ''))

    def test_amazon_image_fetch_sends_browser_headers(self):
        headers = _request_headers(
            'https://m.media-amazon.com/images/I/712oZqfQxTL._SL1500_.jpg',
        )
        self.assertIn('Mozilla/5.0', headers['User-Agent'])
        self.assertIn('image/', headers['Accept'])
        self.assertEqual(headers['Referer'], 'https://www.amazon.com/')

    @patch('people.from_drop.llm_available', return_value=False)
    def test_duplicate_movie_is_reused(self, _llm):
        first = self.client.post(
            '/api/entities/from-drop/',
            {
                'text': 'Inception (2010)\nDirected by Christopher Nolan\nA thief who steals corporate secrets through dream-sharing.',
            },
            format='json',
        )
        self.assertEqual(first.status_code, 201, first.data)
        movie_id = first.data['id']
        second = self.client.post(
            '/api/entities/from-drop/',
            {
                'text': 'Inception (2010)\nDirected by Christopher Nolan\nA thief who steals corporate secrets through dream-sharing.',
            },
            format='json',
        )
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(second.data['id'], movie_id)
        self.assertEqual(second.data['drop_summary']['action'], 'reused')
        self.assertTrue(any('Reused existing Movie' in line for line in second.data['drop_summary']['lines']))
        self.assertEqual(Movie.objects.filter(user=self.user).count(), 1)
        self.assertIn('drop_summary', first.data)
        self.assertEqual(first.data['drop_summary']['action'], 'created')

    @patch('people.from_drop.llm_parse', return_value={
        'type': 'Note',
        'display': 'The Porter',
        'description': '<p>Eli Goree stars in The Porter.</p>',
        'relations': [{'relation_type': 'HAS_ACTOR', 'display': 'Eli Goree', 'type': 'Person'}],
    })
    def test_actor_relation_upgrades_note_to_movie(self, _llm_parse):
        res = self.client.post(
            '/api/entities/from-drop/',
            {'text': 'Eli Goree talks about filming The Porter in Halifax.'},
            format='json',
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['type'], 'Movie')
        actor = Person.objects.get(user=self.user, display='Eli Goree')
        self.assertTrue(EntityRelation.objects.filter(
            from_entity_id=res.data['id'],
            to_entity=actor,
            relation_type='HAS_ACTOR',
        ).exists())

    @patch('people.from_drop.llm_available', return_value=False)
    def test_forced_type_skips_guessing(self, _llm):
        res = self.client.post(
            '/api/entities/from-drop/',
            {
                'type': 'Note',
                'text': 'Inception (2010)\nDirected by Christopher Nolan\nA thief who steals corporate secrets through dream-sharing.',
            },
            format='json',
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['type'], 'Note')
        self.assertFalse(EntityRelation.objects.filter(from_entity_id=res.data['id']).exists())
        self.assertFalse(Movie.objects.filter(user=self.user).exists())

    @patch('people.from_drop.llm_available', return_value=False)
    def test_forced_type_extracts_movie_fields(self, _llm):
        res = self.client.post(
            '/api/entities/from-drop/',
            {
                'type': 'Movie',
                'text': 'Some article about dreams.\nDirected by Christopher Nolan\nReleased in 2010.',
            },
            format='json',
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['type'], 'Movie')
        self.assertEqual(res.data['year'], 2010)
        self.assertTrue(EntityRelation.objects.filter(
            from_entity_id=res.data['id'],
            relation_type='HAS_DIRECTOR',
        ).exists())

    @patch('people.from_drop.llm_available', return_value=False)
    def test_invalid_forced_type_rejected(self, _llm):
        res = self.client.post(
            '/api/entities/from-drop/',
            {'type': 'Spaceship', 'text': 'Apollo 11'},
            format='json',
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn('Unknown entity type', str(res.data))
