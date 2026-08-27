"""Tests for geocode map thumbnail generation."""
import io
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient
from unittest.mock import patch

User = get_user_model()


def _fake_tile(*args, **kwargs):
    return Image.new("RGB", (256, 256), (80, 160, 80))


class GeocodeMapThumbnailTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="mapuser",
            email="map@example.com",
            password="testpass123",
        )
        self.client.force_authenticate(user=self.user)
        self.temp_media = tempfile.mkdtemp()
        self.settings_override = override_settings(MEDIA_ROOT=self.temp_media)
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.temp_media, ignore_errors=True)

    def test_requires_auth(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/geocode/map/", {"lat": "37.8", "lon": "-122.4"})
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_requires_coords(self):
        response = self.client.get("/api/geocode/map/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("people.geocode_views._fetch_tile", side_effect=_fake_tile)
    def test_creates_attachment_like_map_image(self, _mock_tile):
        response = self.client.get(
            "/api/geocode/map/",
            {"lat": "37.7749", "lon": "-122.4194", "q": "San Francisco"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("url", response.data)
        self.assertIn("thumbnail_url", response.data)
        self.assertEqual(response.data["filename"], "map.png")
        self.assertEqual(response.data["caption"], "San Francisco")
        self.assertTrue(str(response.data["url"]).endswith(".png"))
        self.assertTrue(str(response.data["thumbnail_url"]).endswith("_thumb.png"))
