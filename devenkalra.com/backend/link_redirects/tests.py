from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from link_redirects.models import LinkRedirect
from link_redirects.pages import ensure_link_redirects_page


@override_settings(FRONTEND_URL='https://devenkalra.com')
class LinkRedirectTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser('admin', 'a@example.com', 'x')
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=self.admin).key}')

    def test_create_and_root_redirect(self):
        r = self.client.post('/api/link-redirects/', {
            'slug': 'rsvp',
            'title': 'Party RSVP',
            'target_url': 'https://forms.gle/example',
        }, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        data = r.json()
        self.assertEqual(data['slug'], 'rsvp')
        self.assertEqual(data['url'], 'https://devenkalra.com/rsvp')
        self.assertEqual(data['path'], '/rsvp')
        self.assertEqual(data['target_url'], 'https://forms.gle/example')

        anon = APIClient()
        public = anon.get('/rsvp')
        self.assertEqual(public.status_code, 302)
        self.assertEqual(public['Location'], 'https://forms.gle/example')

        item = LinkRedirect.objects.get(slug='rsvp')
        item.refresh_from_db()
        self.assertEqual(item.hit_count, 1)

    def test_reserved_slug_rejected(self):
        bad = self.client.post('/api/link-redirects/', {
            'slug': 'login',
            'target_url': 'https://example.com/x',
        }, format='json')
        self.assertEqual(bad.status_code, 400)

    def test_permanent_redirect(self):
        ok = self.client.post('/api/link-redirects/', {
            'slug': 'ytf-rsvp',
            'target_url': 'https://example.com/docs',
            'permanent': '1',
        }, format='json')
        self.assertEqual(ok.status_code, 201, ok.content)
        anon = APIClient()
        r = anon.get('/ytf-rsvp')
        self.assertEqual(r.status_code, 301)
        self.assertEqual(r['Location'], 'https://example.com/docs')

    def test_private_not_publicly_served(self):
        r = self.client.post('/api/link-redirects/', {
            'slug': 'secret',
            'target_url': 'https://example.com/secret',
            'is_public': '0',
        }, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        # Without a frontend_dist index.html, missing redirect falls through to 404.
        anon = APIClient()
        self.assertEqual(anon.get('/secret').status_code, 404)

    def test_slug_conflict_and_patch_target(self):
        self.assertEqual(
            self.client.post('/api/link-redirects/', {
                'slug': 'same', 'target_url': 'https://example.com/a',
            }, format='json').status_code,
            201,
        )
        conflict = self.client.post('/api/link-redirects/', {
            'slug': 'same', 'target_url': 'https://example.com/b',
        }, format='json')
        self.assertEqual(conflict.status_code, 409)

        item = LinkRedirect.objects.get(slug='same')
        patched = self.client.patch(
            f'/api/link-redirects/{item.pk}/',
            {'target_url': 'https://example.com/b'},
            format='json',
        )
        self.assertEqual(patched.status_code, 200, patched.content)
        anon = APIClient()
        self.assertEqual(anon.get('/same')['Location'], 'https://example.com/b')

    def test_ensure_page(self):
        page, created, menu, _ = ensure_link_redirects_page()
        self.assertEqual(page.slug, 'link-redirects')
        self.assertTrue(created)
        self.assertEqual(menu.roles_with_access, 'superuser')
