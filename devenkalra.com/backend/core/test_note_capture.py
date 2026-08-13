from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .models import NoteNode, Page
from .note_capture import capture_dropped, ensure_temp_folder, youtube_video_id


class NoteCaptureTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='noter', password='password123')
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def test_youtube_video_id_parsing(self):
        self.assertEqual(youtube_video_id('https://www.youtube.com/watch?v=dQw4w9WgXcQ'), 'dQw4w9WgXcQ')
        self.assertEqual(youtube_video_id('https://youtu.be/dQw4w9WgXcQ'), 'dQw4w9WgXcQ')
        self.assertIsNone(youtube_video_id('https://example.com/watch?v=dQw4w9WgXcQ'))

    def test_capture_plain_text_creates_note_under_temp(self):
        result = capture_dropped(text='Shopping list\n- milk\n- eggs')
        self.assertEqual(result['kind'], 'text')
        folder = NoteNode.objects.get(id=result['temp_folder_id'])
        self.assertEqual(folder.title, '_Temp')
        self.assertTrue(folder.is_folder)
        self.assertIsNone(folder.parent_id)
        node = NoteNode.objects.get(id=result['node']['id'])
        self.assertEqual(node.parent_id, folder.id)
        page = Page.objects.get(id=result['page']['id'])
        self.assertEqual(page.title, 'Shopping list')
        self.assertIn('- milk', page.content)
        self.assertEqual(page.category, 'Notebook')

    def test_capture_reports_progress_steps(self):
        steps = []
        capture_dropped(text='Progress check', on_progress=steps.append)
        self.assertTrue(any('Looking at dropped content' in s for s in steps))
        self.assertTrue(any('text note' in s.lower() for s in steps))
        self.assertTrue(any('Saving note' in s for s in steps))
        self.assertIn('Done', steps)

    def test_capture_reuses_existing_temp_folder(self):
        first = ensure_temp_folder()
        second = ensure_temp_folder()
        self.assertEqual(first.id, second.id)
        capture_dropped(text='one')
        capture_dropped(text='two')
        self.assertEqual(NoteNode.objects.filter(title='_Temp', page__isnull=True).count(), 1)

    @patch(
        'core.note_capture._process_youtube_transcript',
        return_value='## Summary\n\nA recap.\n\n## Key points\n\n- Point one\n\n## Transcript\n\nHello from the transcript.',
    )
    @patch('core.note_capture._youtube_transcript', return_value='Hello from the transcript.')
    @patch('core.note_capture._youtube_title', return_value='Demo Video')
    def test_capture_youtube_note(self, _title, _transcript, _processed):
        result = capture_dropped(url='https://www.youtube.com/watch?v=dQw4w9WgXcQ')
        self.assertEqual(result['kind'], 'youtube')
        page = Page.objects.get(id=result['page']['id'])
        self.assertEqual(page.title, 'Demo Video')
        self.assertIn('youtube.com/embed/dQw4w9WgXcQ', page.content)
        self.assertIn('referrerpolicy="strict-origin-when-cross-origin"', page.content)
        self.assertIn('## Summary', page.content)
        self.assertIn('## Key points', page.content)
        self.assertIn('Hello from the transcript.', page.content)
        self.assertIn('https://www.youtube.com/watch?v=dQw4w9WgXcQ', page.content)

    @patch('core.note_capture._openai_chat', return_value='')
    @patch('core.note_capture._youtube_transcript', return_value='raw captions um uh hello')
    @patch('core.note_capture._youtube_title', return_value='Fallback Video')
    def test_youtube_falls_back_to_raw_transcript_without_llm(self, _title, _transcript, _chat):
        result = capture_dropped(url='https://www.youtube.com/watch?v=dQw4w9WgXcQ')
        page = Page.objects.get(id=result['page']['id'])
        self.assertIn('## Transcript', page.content)
        self.assertIn('raw captions um uh hello', page.content)
        self.assertNotIn('## Key points', page.content)

    @patch(
        'core.note_capture._openai_chat',
        return_value='## Summary\n\nThe host explains X.\n\n## Key points\n\n- X matters\n\n## Transcript\n\nThe host explains X clearly.',
    )
    def test_process_youtube_transcript_markdown(self, _chat):
        from .note_capture import _process_youtube_transcript

        markdown = _process_youtube_transcript(
            'Demo',
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            'um so like the host explains x',
        )
        self.assertIn('## Summary', markdown)
        self.assertIn('## Key points', markdown)
        self.assertIn('## Transcript', markdown)
        self.assertIn('The host explains X', markdown)

    @patch('core.note_capture._summarize_page', return_value='A short summary of the article.')
    @patch('core.note_capture._fetch_web_page', return_value=('Example Domain', 'This domain is for use in examples.'))
    def test_capture_public_url_note(self, _fetch, _summary):
        result = capture_dropped(url='https://example.com/article')
        self.assertEqual(result['kind'], 'web')
        page = Page.objects.get(id=result['page']['id'])
        self.assertEqual(page.title, 'Example Domain')
        self.assertIn('https://example.com/article', page.content)
        self.assertIn('A short summary of the article.', page.content)

    def test_paragraph_with_url_is_plain_text_not_web(self):
        result = capture_dropped(text='Read this later: https://example.com/long-article and take notes.')
        self.assertEqual(result['kind'], 'text')
        page = Page.objects.get(id=result['page']['id'])
        self.assertIn('Read this later', page.content)

    def test_localhost_url_is_rejected(self):
        with self.assertRaises(ValueError):
            capture_dropped(url='http://127.0.0.1/secret')

    def test_capture_api_requires_auth(self):
        self.client.credentials()
        response = self.client.post('/api/note-nodes/capture/', {'text': 'hello'}, format='json')
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_capture_api_creates_text_note(self):
        response = self.client.post('/api/note-nodes/capture/', {'text': 'Dropped idea'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertEqual(data['kind'], 'text')
        self.assertEqual(data['page']['title'], 'Dropped idea')
        self.assertTrue(NoteNode.objects.filter(id=data['node']['id'], parent_id=data['temp_folder_id']).exists())

    def test_capture_api_empty_payload(self):
        response = self.client.post('/api/note-nodes/capture/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_move_note_to_another_folder(self):
        dest = NoteNode.objects.create(title='Projects', page=None)
        created = capture_dropped(text='Move me')
        node_id = created['node']['id']
        response = self.client.patch(
            f'/api/note-nodes/{node_id}/',
            {'parent': dest.id},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        node = NoteNode.objects.get(id=node_id)
        self.assertEqual(node.parent_id, dest.id)

    def test_cannot_move_folder_into_itself(self):
        folder = NoteNode.objects.create(title='Loop', page=None)
        response = self.client.patch(
            f'/api/note-nodes/{folder.id}/',
            {'parent': folder.id},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(
        LOCALAI_URL='http://localai.example:8180',
        LOCALAI_API_KEY='local-key',
        LOCALAI_MODEL='qwen3-32b',
        EMAIL_OPENAI_API_KEY='sk-test',
        EMAIL_OPENAI_MODEL='gpt-4.1-mini',
    )
    @patch('core.note_capture._chat_once', return_value='from local')
    def test_openai_chat_prefers_localai(self, chat):
        from .note_capture import _openai_chat

        text = _openai_chat(system='sys', user='hello')
        self.assertEqual(text, 'from local')
        self.assertEqual(chat.call_count, 1)
        self.assertEqual(chat.call_args.kwargs['base_url'], 'http://localai.example:8180/v1')
        self.assertEqual(chat.call_args.kwargs['model'], 'qwen3-32b')

    @override_settings(
        LOCALAI_URL='http://localai.example:8180',
        LOCALAI_API_KEY='local-key',
        LOCALAI_MODEL='qwen3-32b',
        EMAIL_OPENAI_API_KEY='sk-test',
        EMAIL_OPENAI_MODEL='gpt-4.1-mini',
    )
    @patch('core.note_capture._chat_once', side_effect=[RuntimeError('local down'), 'from openai'])
    def test_openai_chat_falls_back_to_openai(self, chat):
        from .note_capture import _openai_chat

        text = _openai_chat(system='sys', user='hello')
        self.assertEqual(text, 'from openai')
        self.assertEqual(chat.call_count, 2)
        self.assertIsNone(chat.call_args.kwargs.get('base_url'))
        self.assertEqual(chat.call_args.kwargs['model'], 'gpt-4.1-mini')
