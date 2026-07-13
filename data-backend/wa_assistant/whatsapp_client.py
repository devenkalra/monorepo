"""
WhatsApp Cloud API client - fetch media and interact with the API.
"""
import os
import requests
from django.conf import settings


def get_media_url(media_id: str) -> str | None:
    """
    Fetch media URL from WhatsApp Cloud API.
    GET https://graph.facebook.com/v18.0/{media-id}
    """
    token = getattr(settings, 'WHATSAPP_ACCESS_TOKEN', None) or os.environ.get('WHATSAPP_ACCESS_TOKEN')
    if not token:
        return None

    url = f"https://graph.facebook.com/v18.0/{media_id}"
    resp = requests.get(url, headers={'Authorization': f'Bearer {token}'}, timeout=30)
    if resp.status_code != 200:
        return None

    data = resp.json()
    return data.get('url')


def download_media(media_id: str) -> tuple[bytes | None, str | None]:
    """
    Download media from WhatsApp Cloud API.
    Returns (content_bytes, mime_type) or (None, None) on failure.
    """
    token = getattr(settings, 'WHATSAPP_ACCESS_TOKEN', None) or os.environ.get('WHATSAPP_ACCESS_TOKEN')
    if not token:
        return None, None

    # Step 1: Get media URL
    media_url = get_media_url(media_id)
    if not media_url:
        return None, None

    # Step 2: Download the actual file (requires Authorization)
    resp = requests.get(media_url, headers={'Authorization': f'Bearer {token}'}, timeout=60)
    if resp.status_code != 200:
        return None, None

    mime_type = resp.headers.get('Content-Type', '').split(';')[0].strip()
    return resp.content, mime_type
