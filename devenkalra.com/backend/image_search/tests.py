from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import User
from PIL import Image
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from django.test import SimpleTestCase

from image_search.bing import build_qft, parse_images
from image_search.pages import PAGE_SLUG, ensure_image_search_page
from image_search.quality import parse_download_items, score_image


SAMPLE_HTML = '''
<a class="iusc" m="{&quot;murl&quot;:&quot;https://cdn.example.com/photo.jpg&quot;,&quot;turl&quot;:&quot;https://tse.example.com/th?id=OIP.abc&quot;,&quot;t&quot;:&quot;Lake photo&quot;,&quot;purl&quot;:&quot;https://source.example.com/page&quot;,&quot;md5&quot;:&quot;abc123&quot;,&quot;mid&quot;:&quot;mid1&quot;,&quot;cid&quot;:&quot;cid1&quot;}" href="/images/search?view=detailV2&amp;mediaurl=https%3A%2F%2Fcdn.example.com%2Fphoto.jpg&amp;expw=1920&amp;exph=1080&amp;cdnurl=https%3A%2F%2Ftse.example.com%2Fth%3Fid%3DOIP.abc"></a>
'''


def _jpeg_bytes(width=32, height=24, color=(40, 120, 200)):
    buf = BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="JPEG", quality=80)
    return buf.getvalue()


class BingParseTests(SimpleTestCase):
    def test_build_qft_presets(self):
        self.assertIn("imagesize-large", build_qft("large", "wide", 0, 0, "week"))
        self.assertIn("aspect-wide", build_qft("large", "wide", 0, 0, "week"))
        self.assertIn("age-lt10080", build_qft("large", "wide", 0, 0, "week"))

    def test_build_qft_custom_size(self):
        self.assertEqual(
            build_qft("", "", 800, 600, ""),
            "+filterui:imagesize-custom_800_600",
        )

    def test_parse_images(self):
        images = parse_images(SAMPLE_HTML)
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]["title"], "Lake photo")
        self.assertEqual(images[0]["image_url"], "https://cdn.example.com/photo.jpg")
        self.assertEqual(images[0]["width"], 1920)
        self.assertEqual(images[0]["height"], 1080)

    def test_parse_download_items_dedupes(self):
        items = parse_download_items({
            "items": [
                {"url": "https://a.example/x.jpg", "title": "A"},
                {"url": "https://a.example/x.jpg", "title": "dup"},
                {"url": "https://b.example/y.jpg"},
            ]
        })
        self.assertEqual(len(items), 2)


class QualityScoreTests(SimpleTestCase):
    def test_score_jpeg(self):
        data = _jpeg_bytes()
        result = score_image(data, claimed_w=32, claimed_h=24)
        self.assertIsNotNone(result)
        self.assertEqual(result["width"], 32)
        self.assertEqual(result["height"], 24)
        self.assertEqual(result["format"], "JPEG")
        self.assertGreaterEqual(result["score"], 0)


class ImageSearchApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("searcher", "s@example.com", "pw")
        self.token = Token.objects.create(user=self.user)

    def test_search_requires_auth(self):
        res = self.client.get("/api/images/search/", {"q": "cats"})
        self.assertIn(res.status_code, (401, 403))

    def test_search_requires_query(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        res = self.client.get("/api/images/search/")
        self.assertEqual(res.status_code, 400)

    @patch("image_search.views.search_images")
    def test_search_returns_images(self, mock_search):
        mock_search.return_value = {
            "query": "lake",
            "offset": 0,
            "next_offset": 35,
            "images": [{"title": "Lake", "image_url": "https://cdn.example.com/a.jpg"}],
        }
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        res = self.client.get("/api/images/search/", {"q": "lake", "size": "large"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["images"][0]["title"], "Lake")
        mock_search.assert_called_once()

    def test_sizes_skips_private_urls(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        res = self.client.post(
            "/api/images/sizes/",
            {"urls": ["http://127.0.0.1/secret.jpg", "not-a-url"]},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["sizes"], {})

    def test_ensure_page(self):
        page, created, menu, _ = ensure_image_search_page()
        self.assertEqual(page.slug, PAGE_SLUG)
        self.assertIn("user", page.roles_with_access)
        self.assertEqual(menu.page_id, page.id)
        self.assertIsNone(menu.parent_id)
