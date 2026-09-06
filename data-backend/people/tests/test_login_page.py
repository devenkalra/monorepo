"""Landing page should reuse an existing session instead of asking for login again."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from people.static_views import safe_login_next

User = get_user_model()


class SafeLoginNextTests(TestCase):
    def test_defaults_to_people_app(self):
        self.assertEqual(safe_login_next(None), '/app/people/')
        self.assertEqual(safe_login_next(''), '/app/people/')

    def test_allows_app_paths(self):
        self.assertEqual(safe_login_next('/app/gallery/'), '/app/gallery/')
        self.assertEqual(safe_login_next('alice/gallery/'), '/app/people/')
        self.assertEqual(safe_login_next('/alice/gallery'), '/alice/gallery')

    def test_rejects_open_redirects(self):
        self.assertEqual(safe_login_next('https://evil.example/'), '/app/people/')
        self.assertEqual(safe_login_next('//evil.example/'), '/app/people/')
        self.assertEqual(safe_login_next('/app/people/\nhttps://evil.example/'), '/app/people/')


class LoginPageResumeTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='loginresume',
            email='loginresume@example.com',
            password='testpass123',
        )

    def test_anonymous_sees_login_page(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/html')
        body = b''.join(response.streaming_content)
        self.assertIn(b'resumeExistingSession', body)

    def test_session_user_is_sent_to_app(self):
        self.client.force_login(self.user)
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/app/people/')

    def test_session_user_honors_safe_next(self):
        self.client.force_login(self.user)
        response = self.client.get('/login/', {'next': '/app/trips/'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/app/trips/')

    def test_session_user_rejects_external_next(self):
        self.client.force_login(self.user)
        response = self.client.get('/login/', {'next': 'https://evil.example/'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/app/people/')

    def test_valid_jwt_cookie_is_sent_to_app(self):
        self.client.cookies['auth-token'] = str(AccessToken.for_user(self.user))
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/app/people/')

    def test_refresh_jwt_cookie_is_sent_to_app(self):
        self.client.cookies['refresh-token'] = str(RefreshToken.for_user(self.user))
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/app/people/')

    def test_expired_jwt_cookie_stays_on_login(self):
        token = AccessToken.for_user(self.user)
        token.set_exp(lifetime=timedelta(seconds=-30))
        self.client.cookies['auth-token'] = str(token)
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
