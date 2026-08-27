from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from core.http_client import WebFetchError, fetch_url, is_public_http_url


def _addrinfo(*ips):
    return [(0, 0, 0, '', (ip, 0)) for ip in ips]


class IsPublicHttpUrlTests(SimpleTestCase):
    def test_rejects_non_http_schemes(self):
        self.assertFalse(is_public_http_url('file:///etc/passwd'))
        self.assertFalse(is_public_http_url('ftp://example.com/a'))
        self.assertFalse(is_public_http_url(''))

    @patch('core.http_client.socket.getaddrinfo', return_value=_addrinfo('127.0.0.1'))
    def test_rejects_loopback(self, _mock):
        self.assertFalse(is_public_http_url('http://localhost/secret'))
        self.assertFalse(is_public_http_url('http://127.0.0.1/'))

    @patch('core.http_client.socket.getaddrinfo', return_value=_addrinfo('10.0.0.8'))
    def test_rejects_private(self, _mock):
        self.assertFalse(is_public_http_url('http://internal.lan/admin'))

    @patch('core.http_client.socket.getaddrinfo', return_value=_addrinfo('169.254.1.1'))
    def test_rejects_link_local(self, _mock):
        self.assertFalse(is_public_http_url('http://169.254.1.1/'))

    @patch('core.http_client.socket.getaddrinfo', return_value=_addrinfo('8.8.8.8'))
    def test_accepts_public_https(self, _mock):
        self.assertTrue(is_public_http_url('https://images.example.com/a.jpg'))

    @patch('core.http_client.socket.getaddrinfo', return_value=_addrinfo('8.8.8.8', '10.0.0.1'))
    def test_rejects_if_any_address_is_private(self, _mock):
        self.assertFalse(is_public_http_url('https://dual.example/'))


class FetchUrlTests(SimpleTestCase):
    @patch('core.http_client.is_public_http_url', return_value=False)
    def test_blocks_unsafe_url_before_request(self, _mock):
        with self.assertRaises(WebFetchError) as ctx:
            fetch_url('http://127.0.0.1/')
        self.assertEqual(ctx.exception.status, 400)

    @patch('core.http_client.urlopen')
    @patch('core.http_client.is_public_http_url', return_value=True)
    def test_returns_body_and_headers(self, _safe, mock_urlopen):
        resp = MagicMock()
        resp.status = 200
        resp.url = 'https://example.com/page'
        resp.headers = {'Content-Type': 'text/html', 'Content-Length': '5'}
        resp.read.side_effect = [b'hello', b'']
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        mock_urlopen.return_value = resp

        result = fetch_url('https://example.com/page')
        self.assertEqual(result.status, 200)
        self.assertEqual(result.body, b'hello')
        self.assertEqual(result.header('content-type'), 'text/html')
        self.assertEqual(result.content_length(), 5)
