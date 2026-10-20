from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from unittest.mock import patch

from people.models import Book, EntityRelation, Movie, Note, Person
from people.text_import import build_import_payload, import_text, prepare_text_import


User = get_user_model()


class TextImportBuildTests(TestCase):
    @patch('people.text_import.llm_available', return_value=False)
    def test_builds_one_note_per_line(self, _llm):
        payload = build_import_payload('bought milk\n\ncalled mom\n', 'Note')
        self.assertEqual(payload['import_version'], '2.0')
        self.assertEqual(len(payload['entities']), 2)
        self.assertEqual(payload['entities'][0]['type'], 'Note')
        self.assertEqual(payload['entities'][0]['import_op'], 'create')
        self.assertEqual(payload['entities'][0]['description'], '<p>bought milk</p>')
        self.assertEqual(payload['entities'][1]['description'], '<p>called mom</p>')
        self.assertEqual(payload['entities'][0]['tags'], ['imported/text'])

    @patch('people.text_import.llm_available', return_value=False)
    def test_defaults_to_note(self, _llm):
        payload = build_import_payload('a thought')
        self.assertEqual(payload['entities'][0]['type'], 'Note')

    @patch('people.text_import.llm_available', return_value=False)
    def test_rejects_empty_text(self, _llm):
        from people.text_import import TextImportError
        with self.assertRaises(TextImportError):
            build_import_payload('   \n  ')

    @patch('people.text_import.llm_available', return_value=True)
    @patch('productions.llm.chat_completion')
    def test_uses_llm_fields_when_available(self, mock_chat, _available):
        mock_chat.return_value = (
            '{"items":[{"display":"Ada Lovelace","description":'
            '"<p>Ada Lovelace was a mathematician and writer.</p>'
            '<p>She is often called the first computer programmer.</p>",'
            '"first_name":"Ada","last_name":"Lovelace","profession":"Mathematician"}]}'
        )
        payload = build_import_payload('Ada Lovelace, mathematician', 'Person')
        person = payload['entities'][0]
        self.assertEqual(person['type'], 'Person')
        self.assertEqual(person['first_name'], 'Ada')
        self.assertEqual(person['last_name'], 'Lovelace')
        self.assertEqual(person['profession'], 'Mathematician')
        self.assertIn('first computer programmer', person['description'])
        self.assertGreater(len(person['description']), 80)
        self.assertIn('<p>', person['description'])

    def test_prompt_asks_for_detailed_description(self):
        from people.text_import import _system_prompt
        prompt = _system_prompt('Note')
        self.assertIn('detailed HTML write-up', prompt)
        self.assertNotIn('Keep description short', prompt)

    def test_coerces_credit_fields_into_relations(self):
        from people.text_import import _item_relations
        rows = _item_relations(
            {
                'display': 'The Odyssey',
                'director': 'Christopher Nolan',
                'actors': ['Matt Damon', 'Zendaya'],
                'composer': 'Hans Zimmer',
            },
            'Movie',
        )
        types = {row['relation_type'] for row in rows}
        names = {row['display'] for row in rows}
        self.assertEqual(types, {'HAS_DIRECTOR', 'HAS_ACTOR', 'HAS_MUS_DIRECTOR'})
        self.assertIn('Matt Damon', names)
        self.assertIn('Hans Zimmer', names)

    def test_reads_directed_by_from_line(self):
        from people.text_import import _item_relations
        rows = _item_relations({}, 'Movie', 'The Odyssey directed by Chris Nolan')
        self.assertTrue(any(row['relation_type'] == 'HAS_DIRECTOR' and row['display'] == 'Chris Nolan' for row in rows))

    def test_reads_book_author_from_line(self):
        from people.text_import import _item_relations
        rows = _item_relations({}, 'Book', 'The Housemaid by Freida McFadden')
        self.assertTrue(any(
            row['relation_type'] == 'HAS_AS_AUTHOR' and row['display'] == 'Freida McFadden'
            for row in rows
        ))
        dashed = _item_relations({}, 'Book', 'The Inmate - Freida McFadden')
        self.assertTrue(any(
            row['relation_type'] == 'HAS_AS_AUTHOR' and row['display'] == 'Freida McFadden'
            for row in dashed
        ))

    def test_copies_shared_book_author_onto_sibling_titles(self):
        from people.text_import import _fill_shared_book_authors, _item_relations
        items = _fill_shared_book_authors(
            [
                {'display': 'The Housemaid', 'author': 'Freida McFadden'},
                {'display': 'The Inmate', 'description': '<p>A prison thriller.</p>'},
                {'display': 'The Teacher'},
            ],
            ['The Housemaid', 'The Inmate', 'The Teacher'],
        )
        for item, line in zip(items, ['The Housemaid', 'The Inmate', 'The Teacher']):
            rows = _item_relations(item, 'Book', line)
            self.assertTrue(any(
                row['relation_type'] == 'HAS_AS_AUTHOR' and row['display'] == 'Freida McFadden'
                for row in rows
            ), item)

    @patch('people.text_import._llm_items')
    def test_multiple_books_share_one_author(self, mock_llm):
        user = User.objects.create_user(username='bookuser', password='secret', email='book@example.com')
        mock_llm.return_value = [
            {'display': 'The Housemaid', 'author': 'Freida McFadden'},
            {'display': 'The Inmate'},
            {'display': 'The Teacher'},
        ]
        payload = build_import_payload(
            'The Housemaid\nThe Inmate\nThe Teacher',
            'Book',
            user=user,
        )
        books = [item for item in payload['entities'] if item.get('type') == 'Book']
        people = [item for item in payload['entities'] if item.get('type') == 'Person']
        self.assertEqual(len(books), 3)
        self.assertEqual(len(people), 1)
        self.assertEqual(people[0]['display'], 'Freida McFadden')
        author_ref = people[0]['import_ref']
        author_rels = [
            item for item in payload['relations']
            if item.get('relation_type') == 'HAS_AS_AUTHOR'
        ]
        self.assertEqual(len(author_rels), 3)
        self.assertTrue(all(item.get('to_import_ref') == author_ref for item in author_rels))

    @patch('people.text_import.llm_available', return_value=True)
    @patch('productions.llm.chat_completion')
    def test_enrichment_fills_missing_cast(self, mock_chat, _available):
        from people.text_import import _item_relations, _llm_items
        mock_chat.side_effect = [
            '{"items":[{"display":"The Odyssey","relations":[{"relation_type":"HAS_DIRECTOR","display":"Christopher Nolan"}]}]}',
            '{"items":[{"display":"The Odyssey","actors":["Matt Damon","Tom Holland"],"composer":"Hans Zimmer"}]}',
        ]
        items = _llm_items(['The Odyssey directed by Chris Nolan'], 'Movie')
        types = {row['relation_type'] for row in _item_relations(items[0], 'Movie')}
        self.assertIn('HAS_DIRECTOR', types)
        self.assertIn('HAS_ACTOR', types)
        self.assertIn('HAS_MUS_DIRECTOR', types)
        self.assertEqual(mock_chat.call_count, 2)

    @patch('people.text_import.llm_available', return_value=True)
    @patch('productions.llm.chat_completion')
    def test_enrichment_fills_book_authors_for_every_title(self, mock_chat, _available):
        from people.text_import import _item_relations, _llm_items
        mock_chat.side_effect = [
            '{"items":['
            '{"display":"The Housemaid","description":"<p>A maid thriller.</p>"},'
            '{"display":"The Inmate","description":"<p>A prison thriller.</p>"},'
            '{"display":"The Teacher","description":"<p>A school thriller.</p>"}'
            ']}',
            '{"items":['
            '{"display":"The Housemaid","author":"Freida McFadden"},'
            '{"display":"The Inmate","author":"Freida McFadden"},'
            '{"display":"The Teacher","author":"Freida McFadden"}'
            ']}',
        ]
        items = _llm_items(['The Housemaid', 'The Inmate', 'The Teacher'], 'Book')
        self.assertEqual(mock_chat.call_count, 2)
        second = mock_chat.call_args_list[1]
        prompt = second.kwargs.get('prompt') or (second.args[0] if second.args else '')
        self.assertIn('HAS_AS_AUTHOR', prompt)
        self.assertIn('The Inmate', prompt)
        self.assertIn('The Teacher', prompt)
        for item in items:
            rows = _item_relations(item, 'Book')
            self.assertTrue(any(
                row['relation_type'] == 'HAS_AS_AUTHOR' and row['display'] == 'Freida McFadden'
                for row in rows
            ), item)

    @patch('people.text_import._llm_items')
    def test_chris_nolan_reuses_christopher(self, mock_llm):
        user = User.objects.create_user(username='nolanuser', password='secret', email='nolan@example.com')
        nolan = Person.objects.create(
            user=user,
            display='Christopher Nolan',
            first_name='Christopher',
            last_name='Nolan',
        )
        mock_llm.return_value = [{
            'display': 'The Odyssey',
            'relations': [{'relation_type': 'HAS_DIRECTOR', 'display': 'Chris Nolan'}],
        }]
        payload = build_import_payload('The Odyssey directed by Chris Nolan', 'Movie', user=user)
        self.assertTrue(any(
            item['relation_type'] == 'HAS_DIRECTOR' and item.get('to_entity') == str(nolan.id)
            for item in payload['relations']
        ))
        self.assertFalse(any(item.get('display') == 'Chris Nolan' for item in payload['entities']))

    @patch('people.text_import._llm_items')
    def test_reuses_existing_director_and_creates_missing_people(self, mock_llm):
        user = User.objects.create_user(username='reluser', password='secret', email='rel@example.com')
        nolan = Person.objects.create(
            user=user,
            display='Christopher Nolan',
            first_name='Christopher',
            last_name='Nolan',
        )
        mock_llm.return_value = [{
            'display': 'Inception',
            'year': 2010,
            'relations': [
                {'relation_type': 'HAS_DIRECTOR', 'display': 'Christopher Nolan'},
                {'relation_type': 'HAS_ACTOR', 'display': 'Leonardo DiCaprio'},
                {'relation_type': 'HAS_MUS_DIRECTOR', 'display': 'Hans Zimmer'},
            ],
        }]
        payload = build_import_payload('Inception', 'Movie', user=user)
        displays = {item['display']: item for item in payload['entities']}
        self.assertEqual(displays['Inception']['type'], 'Movie')
        self.assertIn('Leonardo DiCaprio', displays)
        self.assertIn('Hans Zimmer', displays)
        self.assertNotIn('Christopher Nolan', displays)
        rels = {(item['relation_type'], item.get('to_entity'), item.get('to_import_ref')) for item in payload['relations']}
        self.assertTrue(any(item['relation_type'] == 'HAS_DIRECTOR' and item.get('to_entity') == str(nolan.id) for item in payload['relations']))
        self.assertTrue(any(item['relation_type'] == 'HAS_ACTOR' for item in payload['relations']))
        self.assertTrue(any(item['relation_type'] == 'HAS_MUS_DIRECTOR' for item in payload['relations']))
        self.assertEqual(len(rels), 3)

    @patch('people.text_import._llm_items')
    def test_ambiguous_related_person_needs_confirmation(self, mock_llm):
        user = User.objects.create_user(username='ambig', password='secret', email='ambig@example.com')
        first = Person.objects.create(user=user, display='John Smith', first_name='John', last_name='Smith', profession='Director')
        Person.objects.create(user=user, display='John Smith', first_name='John', last_name='Smith', profession='Actor')
        mock_llm.return_value = [{
            'display': 'Some Film',
            'relations': [{'relation_type': 'HAS_DIRECTOR', 'display': 'John Smith'}],
        }]
        built = prepare_text_import('Some Film', 'Movie', user=user)
        self.assertTrue(built['needs_confirmation'])
        self.assertEqual(len(built['confirmations']), 1)
        self.assertEqual(built['confirmations'][0]['query'], 'John Smith')
        self.assertEqual(len(built['confirmations'][0]['candidates']), 2)
        self.assertIsNone(built['payload'])

        confirmed = import_text(
            'Some Film',
            user,
            entity_type='Movie',
            draft=built['draft'],
            confirmations={built['confirmations'][0]['key']: {'action': 'use', 'id': str(first.id)}},
            confirm=True,
        )
        self.assertTrue(confirmed['success'])
        movie = Movie.objects.get(user=user, display='Some Film')
        self.assertTrue(EntityRelation.objects.filter(
            from_entity=movie,
            to_entity=first,
            relation_type='HAS_DIRECTOR',
        ).exists())
        self.assertEqual(Person.objects.filter(user=user).count(), 2)

    @patch('people.text_import._llm_items')
    def test_create_ambiguous_related_does_not_reuse_related_ref(self, mock_llm):
        user = User.objects.create_user(username='dupref', password='secret', email='dupref@example.com')
        Person.objects.create(user=user, display='John Smith', first_name='John', last_name='Smith', profession='Director')
        Person.objects.create(user=user, display='John Smith', first_name='John', last_name='Smith', profession='Actor')
        mock_llm.return_value = [{
            'display': 'Some Film',
            'relations': [
                {'relation_type': 'HAS_DIRECTOR', 'display': 'John Smith'},
                {'relation_type': 'HAS_ACTOR', 'display': 'Leonardo DiCaprio'},
            ],
        }]
        built = prepare_text_import('Some Film', 'Movie', user=user)
        self.assertTrue(built['needs_confirmation'])
        key = built['confirmations'][0]['key']
        confirmed = import_text(
            'Some Film',
            user,
            entity_type='Movie',
            draft=built['draft'],
            confirmations={key: {'action': 'create'}},
            confirm=True,
        )
        self.assertTrue(confirmed['success'], confirmed)
        self.assertFalse(confirmed.get('errors'))
        self.assertEqual(Movie.objects.filter(user=user, display='Some Film').count(), 1)
        self.assertTrue(Person.objects.filter(user=user, display='Leonardo DiCaprio').exists())
        self.assertEqual(Person.objects.filter(user=user, display='John Smith').count(), 3)


class TextImportApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='textimport',
            email='textimport@example.com',
            password='testpass123',
        )
        self.client.force_authenticate(user=self.user)

    def _confirm(self, preview, extra_tag=None, confirmations=None):
        body = {
            'type': preview.data.get('type'),
            'draft': preview.data['draft'],
            'confirmations': confirmations or {},
            'confirm': True,
        }
        if extra_tag:
            body['extra_tag'] = extra_tag
        return self.client.post('/api/entities/import_text/', body, format='json')

    def _main_confirmations(self, preview, action='use'):
        choices = {}
        for item in preview.data.get('confirmations') or []:
            if item.get('kind') != 'main':
                continue
            if action == 'use' and item.get('candidates'):
                choices[item['key']] = {'action': 'use', 'id': item['candidates'][0]['id']}
            else:
                choices[item['key']] = {'action': action}
        return choices

    @patch('people.text_import.llm_available', return_value=False)
    def test_import_text_creates_notes(self, _llm):
        preview = self.client.post(
            '/api/entities/import_text/',
            {'text': 'first idea\nsecond idea', 'type': 'Note'},
            format='json',
        )
        self.assertEqual(preview.status_code, status.HTTP_200_OK, preview.data)
        self.assertTrue(preview.data['needs_confirmation'])
        self.assertEqual(preview.data['preview']['create_count'], 2)
        self.assertEqual(Note.objects.filter(user=self.user).count(), 0)
        response = self._confirm(preview)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['created'], 2)
        self.assertEqual(Note.objects.filter(user=self.user).count(), 2)
        self.assertTrue(Note.objects.filter(user=self.user, description='<p>first idea</p>').exists())

    @patch('people.text_import.llm_available', return_value=False)
    def test_import_text_creates_people(self, _llm):
        preview = self.client.post(
            '/api/entities/import_text/',
            {'text': 'Grace Hopper', 'type': 'Person'},
            format='json',
        )
        self.assertEqual(preview.status_code, status.HTTP_200_OK, preview.data)
        response = self._confirm(preview)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        person = Person.objects.get(user=self.user)
        self.assertEqual(person.first_name, 'Grace')
        self.assertEqual(person.last_name, 'Hopper')

    def test_rejects_unknown_type(self):
        response = self.client.post(
            '/api/entities/import_text/',
            {'text': 'x', 'type': 'Spaceship'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('people.text_import._llm_items')
    def test_import_text_creates_missing_related_people(self, mock_llm):
        mock_llm.return_value = [{
            'display': 'Inception',
            'year': 2010,
            'relations': [
                {'relation_type': 'HAS_DIRECTOR', 'display': 'Christopher Nolan'},
                {'relation_type': 'HAS_ACTOR', 'display': 'Leonardo DiCaprio'},
            ],
        }]
        preview = self.client.post(
            '/api/entities/import_text/',
            {'text': 'Inception', 'type': 'Movie'},
            format='json',
        )
        self.assertEqual(preview.status_code, status.HTTP_200_OK, preview.data)
        self.assertTrue(preview.data['needs_confirmation'])
        self.assertGreaterEqual(preview.data['preview']['create_count'], 3)
        response = self._confirm(preview)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data['success'])
        movie = Movie.objects.get(user=self.user, display='Inception')
        director = Person.objects.get(user=self.user, display='Christopher Nolan')
        actor = Person.objects.get(user=self.user, display='Leonardo DiCaprio')
        self.assertTrue(EntityRelation.objects.filter(
            from_entity=movie, to_entity=director, relation_type='HAS_DIRECTOR',
        ).exists())
        self.assertTrue(EntityRelation.objects.filter(
            from_entity=movie, to_entity=actor, relation_type='HAS_ACTOR',
        ).exists())

    @patch('people.text_import._llm_items')
    def test_import_text_asks_before_ambiguous_relation(self, mock_llm):
        Person.objects.create(user=self.user, display='Pat Lee', first_name='Pat', last_name='Lee')
        Person.objects.create(user=self.user, display='Pat Lee', first_name='Pat', last_name='Lee')
        mock_llm.return_value = [{
            'display': 'Ambiguous Movie',
            'relations': [{'relation_type': 'HAS_DIRECTOR', 'display': 'Pat Lee'}],
        }]
        response = self.client.post(
            '/api/entities/import_text/',
            {'text': 'Ambiguous Movie', 'type': 'Movie'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data['needs_confirmation'])
        self.assertFalse(Movie.objects.filter(user=self.user).exists())
        key = response.data['confirmations'][0]['key']
        chosen_id = response.data['confirmations'][0]['candidates'][0]['id']
        confirm = self.client.post(
            '/api/entities/import_text/',
            {
                'text': 'Ambiguous Movie',
                'type': 'Movie',
                'draft': response.data['draft'],
                'confirmations': {key: {'action': 'use', 'id': chosen_id}},
                'confirm': True,
            },
            format='json',
        )
        self.assertEqual(confirm.status_code, status.HTTP_200_OK, confirm.data)
        self.assertTrue(confirm.data['success'])
        movie = Movie.objects.get(user=self.user, display='Ambiguous Movie')
        self.assertTrue(EntityRelation.objects.filter(
            from_entity=movie,
            to_entity_id=chosen_id,
            relation_type='HAS_DIRECTOR',
        ).exists())

    @patch('people.text_import.llm_available', return_value=False)
    def test_preview_lists_create_and_found(self, _llm):
        existing = Person.objects.create(
            user=self.user,
            display='Christopher Nolan',
            first_name='Christopher',
            last_name='Nolan',
        )
        with patch('people.text_import._llm_items', return_value=[{
            'display': 'Inception',
            'relations': [
                {'relation_type': 'HAS_DIRECTOR', 'display': 'Christopher Nolan'},
                {'relation_type': 'HAS_ACTOR', 'display': 'Leonardo DiCaprio'},
            ],
        }]):
            preview = self.client.post(
                '/api/entities/import_text/',
                {'text': 'Inception', 'type': 'Movie'},
                format='json',
            )
        self.assertEqual(preview.status_code, status.HTTP_200_OK, preview.data)
        self.assertTrue(preview.data['needs_confirmation'])
        self.assertFalse(Movie.objects.filter(user=self.user).exists())
        displays = {item['display'] for item in preview.data['preview']['create']}
        self.assertIn('Inception', displays)
        self.assertIn('Leonardo DiCaprio', displays)
        self.assertNotIn('Christopher Nolan', displays)
        found_ids = {item['id'] for item in preview.data['preview']['found']}
        self.assertIn(str(existing.id), found_ids)
        response = self._confirm(preview, extra_tag='nolan-films')
        self.assertTrue(response.data['success'])
        movie = Movie.objects.get(user=self.user, display='Inception')
        self.assertIn('imported/text', movie.tags)
        self.assertIn('nolan-films', movie.tags)
        actor = Person.objects.get(user=self.user, display='Leonardo DiCaprio')
        self.assertIn('nolan-films', actor.tags)
        existing.refresh_from_db()
        self.assertNotIn('nolan-films', existing.tags or [])

    @patch('people.text_import.llm_available', return_value=False)
    @patch('people.text_import._llm_items')
    def test_preview_lists_existing_main_as_update(self, mock_llm, _available):
        existing = Note.objects.create(
            user=self.user,
            display='Ada Lovelace',
            description='<p>Ada wrote the first algorithm.</p>',
            tags=['keep-me'],
        )
        mock_llm.return_value = [{
            'display': 'Ada Lovelace',
            'description': '<p>She is often called the first computer programmer.</p>',
        }]
        preview = self.client.post(
            '/api/entities/import_text/',
            {'text': 'Ada Lovelace', 'type': 'Note'},
            format='json',
        )
        self.assertEqual(preview.status_code, status.HTTP_200_OK, preview.data)
        self.assertTrue(preview.data['needs_confirmation'])
        self.assertEqual(preview.data['preview']['update_count'], 0)
        self.assertEqual(preview.data['preview']['create_count'], 0)
        self.assertEqual(preview.data['preview']['ambiguity_count'], 1)
        choice = preview.data['confirmations'][0]
        self.assertEqual(choice['kind'], 'main')
        self.assertEqual(choice['match'], 'exact')
        self.assertIn('first computer programmer', choice['incoming_description'])
        self.assertEqual(choice['candidates'][0]['id'], str(existing.id))
        self.assertIn('first algorithm', choice['candidates'][0]['merged_description'])
        self.assertIn('first computer programmer', choice['candidates'][0]['merged_description'])
        self.assertEqual(Note.objects.filter(user=self.user).count(), 1)
        response = self._confirm(preview, extra_tag='biography', confirmations=self._main_confirmations(preview))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['updated'], 1)
        self.assertEqual(response.data['created'], 0)
        existing.refresh_from_db()
        self.assertEqual(Note.objects.filter(user=self.user).count(), 1)
        self.assertIn('first algorithm', existing.description)
        self.assertIn('first computer programmer', existing.description)
        self.assertEqual(existing.tags, ['keep-me'])

    @patch('people.text_import.llm_available', return_value=False)
    @patch('people.text_import._llm_items')
    def test_duplicate_main_can_create_instead_of_merge(self, mock_llm, _available):
        Note.objects.create(
            user=self.user,
            display='Ada Lovelace',
            description='<p>Ada wrote the first algorithm.</p>',
        )
        mock_llm.return_value = [{
            'display': 'Ada Lovelace',
            'description': '<p>She is often called the first computer programmer.</p>',
        }]
        preview = self.client.post(
            '/api/entities/import_text/',
            {'text': 'Ada Lovelace', 'type': 'Note'},
            format='json',
        )
        self.assertEqual(preview.status_code, status.HTTP_200_OK, preview.data)
        response = self._confirm(preview, confirmations=self._main_confirmations(preview, action='create'))
        self.assertTrue(response.data['success'], response.data)
        self.assertEqual(response.data['created'], 1)
        self.assertEqual(response.data['updated'], 0)
        self.assertEqual(Note.objects.filter(user=self.user, display='Ada Lovelace').count(), 2)

    @patch('people.text_import.llm_available', return_value=True)
    @patch('people.text_import._llm_items')
    @patch('productions.llm.chat_completion')
    def test_merges_existing_description_with_llm(self, mock_chat, mock_llm, _available):
        existing = Note.objects.create(
            user=self.user,
            display='Ada Lovelace',
            description='<p>Ada wrote the first algorithm.</p>',
        )
        mock_llm.return_value = [{
            'display': 'Ada Lovelace',
            'description': '<p>She is often called the first computer programmer.</p>',
        }]
        mock_chat.return_value = '{"description":"<p>Ada wrote the first algorithm and is often called the first computer programmer.</p>"}'
        preview = self.client.post(
            '/api/entities/import_text/',
            {'text': 'Ada Lovelace', 'type': 'Note'},
            format='json',
        )
        self.assertEqual(preview.status_code, status.HTTP_200_OK, preview.data)
        self.assertIn('first computer programmer', preview.data['confirmations'][0]['incoming_description'])
        self.assertIn('first algorithm', preview.data['confirmations'][0]['candidates'][0]['merged_description'])
        response = self._confirm(preview, confirmations=self._main_confirmations(preview))
        self.assertTrue(response.data['success'])
        existing.refresh_from_db()
        self.assertIn('first algorithm', existing.description)
        self.assertIn('first computer programmer', existing.description)
        mock_chat.assert_called()

    @patch('people.text_import.llm_available', return_value=False)
    @patch('people.text_import._llm_items')
    def test_ambiguous_main_needs_confirmation_before_update(self, mock_llm, _available):
        first = Note.objects.create(
            user=self.user,
            display='The Odyssey',
            description='<p>First copy.</p>',
        )
        Note.objects.create(
            user=self.user,
            display='The Odyssey',
            description='<p>Second copy.</p>',
        )
        mock_llm.return_value = [{
            'display': 'The Odyssey',
            'description': '<p>Nolan film.</p>',
        }]
        preview = self.client.post(
            '/api/entities/import_text/',
            {'text': 'The Odyssey', 'type': 'Note'},
            format='json',
        )
        self.assertEqual(preview.status_code, status.HTTP_200_OK, preview.data)
        self.assertTrue(preview.data['needs_confirmation'])
        self.assertEqual(preview.data['preview']['update_count'], 0)
        self.assertEqual(preview.data['preview']['create_count'], 0)
        self.assertEqual(preview.data['preview']['ambiguity_count'], 1)
        self.assertEqual(preview.data['confirmations'][0]['kind'], 'main')
        self.assertIn('Nolan film', preview.data['confirmations'][0]['incoming_description'])
        self.assertIn('First copy', preview.data['confirmations'][0]['candidates'][0]['merged_description'])
        key = preview.data['confirmations'][0]['key']
        confirm = self.client.post(
            '/api/entities/import_text/',
            {
                'text': 'The Odyssey',
                'type': 'Note',
                'draft': preview.data['draft'],
                'confirmations': {key: {'action': 'use', 'id': str(first.id)}},
                'confirm': True,
            },
            format='json',
        )
        self.assertEqual(confirm.status_code, status.HTTP_200_OK, confirm.data)
        self.assertEqual(confirm.data['updated'], 1)
        self.assertEqual(Note.objects.filter(user=self.user).count(), 2)
        first.refresh_from_db()
        self.assertIn('First copy', first.description)
        self.assertIn('Nolan film', first.description)

    @patch('people.text_import.llm_available', return_value=False)
    @patch('people.text_import._llm_items')
    def test_updates_existing_movie_and_keeps_related_create(self, mock_llm, _available):
        movie = Movie.objects.create(
            user=self.user,
            display='Inception',
            year=2010,
            description='<p>A thief enters dreams.</p>',
            tags=['keep-movie'],
        )
        mock_llm.return_value = [{
            'display': 'Inception',
            'year': 2010,
            'description': '<p>The job is to plant an idea.</p>',
            'relations': [
                {'relation_type': 'HAS_DIRECTOR', 'display': 'Christopher Nolan'},
            ],
        }]
        preview = self.client.post(
            '/api/entities/import_text/',
            {'text': 'Inception', 'type': 'Movie'},
            format='json',
        )
        self.assertEqual(preview.status_code, status.HTTP_200_OK, preview.data)
        choice = next(item for item in preview.data['confirmations'] if item.get('kind') == 'main')
        self.assertEqual(choice['candidates'][0]['id'], str(movie.id))
        self.assertIn('plant an idea', choice['incoming_description'])
        self.assertIn('enters dreams', choice['candidates'][0]['merged_description'])
        create_displays = {item['display'] for item in preview.data['preview']['create']}
        self.assertIn('Christopher Nolan', create_displays)
        self.assertNotIn('Inception', create_displays)
        response = self._confirm(
            preview,
            extra_tag='nolan-films',
            confirmations=self._main_confirmations(preview),
        )
        self.assertTrue(response.data['success'], response.data)
        self.assertEqual(response.data['updated'], 1)
        self.assertEqual(Movie.objects.filter(user=self.user).count(), 1)
        movie.refresh_from_db()
        self.assertIn('enters dreams', movie.description)
        self.assertIn('plant an idea', movie.description)
        self.assertEqual(movie.tags, ['keep-movie'])
        director = Person.objects.get(user=self.user, display='Christopher Nolan')
        self.assertIn('nolan-films', director.tags)
        self.assertTrue(EntityRelation.objects.filter(
            from_entity=movie,
            to_entity=director,
            relation_type='HAS_DIRECTOR',
        ).exists())
