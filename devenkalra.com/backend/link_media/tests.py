from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from link_media.models import LinkMedia
from link_media.pages import ensure_link_media_page


@override_settings(FRONTEND_URL='https://devenkalra.com')
class LinkMediaTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser('admin', 'a@example.com', 'x')
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=self.admin).key}')

    def test_upload_and_public_serve(self):
        upload = SimpleUploadedFile('flyer.pdf', b'%PDF-1.4 hello', content_type='application/pdf')
        r = self.client.post(
            '/api/link-media/',
            {'file': upload, 'slug': 'ytf-flyer', 'title': 'YTF Flyer'},
            format='multipart',
        )
        self.assertEqual(r.status_code, 201, r.content)
        data = r.json()
        self.assertEqual(data['slug'], 'ytf-flyer')
        self.assertEqual(data['url'], 'https://devenkalra.com/f/ytf-flyer')
        self.assertEqual(data['path'], '/f/ytf-flyer')

        anon = APIClient()
        public = anon.get('/f/ytf-flyer')
        self.assertEqual(public.status_code, 200)
        self.assertEqual(public['Content-Type'], 'application/pdf')
        self.assertIn('inline', public['Content-Disposition'])
        self.assertEqual(b''.join(public.streaming_content), b'%PDF-1.4 hello')

        item = LinkMedia.objects.get(slug='ytf-flyer')
        item.refresh_from_db()
        self.assertEqual(item.download_count, 1)

    def test_private_not_publicly_served(self):
        upload = SimpleUploadedFile('secret.txt', b'secret', content_type='text/plain')
        r = self.client.post(
            '/api/link-media/',
            {'file': upload, 'slug': 'secret', 'is_public': '0'},
            format='multipart',
        )
        self.assertEqual(r.status_code, 201, r.content)
        anon = APIClient()
        self.assertEqual(anon.get('/f/secret').status_code, 404)

    def test_slug_conflict_and_replace_file(self):
        u1 = SimpleUploadedFile('a.pdf', b'one', content_type='application/pdf')
        self.assertEqual(
            self.client.post('/api/link-media/', {'file': u1, 'slug': 'same'}, format='multipart').status_code,
            201,
        )
        u2 = SimpleUploadedFile('b.pdf', b'two', content_type='application/pdf')
        conflict = self.client.post('/api/link-media/', {'file': u2, 'slug': 'same'}, format='multipart')
        self.assertEqual(conflict.status_code, 409)

        item = LinkMedia.objects.get(slug='same')
        u3 = SimpleUploadedFile('c.pdf', b'three', content_type='application/pdf')
        patched = self.client.patch(
            f'/api/link-media/{item.pk}/',
            {'file': u3},
            format='multipart',
        )
        self.assertEqual(patched.status_code, 200, patched.content)
        anon = APIClient()
        self.assertEqual(b''.join(anon.get('/f/same').streaming_content), b'three')

    def test_ensure_page(self):
        page, created, menu, _ = ensure_link_media_page()
        self.assertEqual(page.slug, 'link-media')
        self.assertTrue(created)
        self.assertEqual(menu.roles_with_access, 'superuser')
