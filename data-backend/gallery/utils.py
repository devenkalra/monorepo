import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.utils.text import slugify

from .constants import (
    IMAGE_EXTENSIONS,
    MEDIA_IMAGE,
    MEDIA_OTHER,
    MEDIA_VIDEO,
    RESERVED_USERNAMES,
    VIDEO_EXTENSIONS,
)


def guess_media_type(url: str) -> str:
    path = urlparse(url).path if '://' in (url or '') else (url or '')
    ext = Path(path).suffix.lower()
    if ext in VIDEO_EXTENSIONS:
        return MEDIA_VIDEO
    if ext in IMAGE_EXTENSIONS:
        return MEDIA_IMAGE
    return MEDIA_OTHER


def photo_source_key(photo) -> str:
    if isinstance(photo, str):
        return photo
    if isinstance(photo, dict):
        return photo.get('url') or photo.get('external_url') or photo.get('thumbnail_url') or ''
    return ''


def normalize_photo(photo) -> dict:
    if isinstance(photo, str):
        return {
            'url': photo if photo.startswith('/') or photo.startswith('http') else f'/media/{photo}',
            'thumbnail_url': '',
            'filename': Path(urlparse(photo).path).name,
            'caption': '',
            'title': '',
        }
    if not isinstance(photo, dict):
        return {}
    url = photo.get('url') or photo.get('external_url') or ''
    return {
        'url': url,
        'thumbnail_url': photo.get('thumbnail_url') or '',
        'filename': photo.get('filename') or Path(urlparse(url).path).name,
        'caption': photo.get('caption') or '',
        'title': photo.get('title') or photo.get('caption') or '',
    }


def media_filesystem_path(media_url: str) -> Path | None:
    """Resolve a /media/... URL to an absolute filesystem path under MEDIA_ROOT."""
    if not media_url or media_url.startswith('http://') or media_url.startswith('https://'):
        return None
    path = media_url
    if path.startswith(settings.MEDIA_URL):
        path = path[len(settings.MEDIA_URL) :]
    path = path.lstrip('/')
    full = Path(settings.MEDIA_ROOT) / path
    try:
        full.resolve().relative_to(Path(settings.MEDIA_ROOT).resolve())
    except (ValueError, OSError):
        return None
    return full if full.is_file() else None


def generate_video_thumbnail(media_url: str) -> str | None:
    """
    Extract a frame with ffmpeg next to the video as *_thumb.jpg.
    Returns the /media/... thumbnail URL, or None on failure.
    """
    src = media_filesystem_path(media_url)
    if not src:
        return None
    thumb = src.with_name(f'{src.stem}_thumb.jpg')
    try:
        subprocess.run(
            [
                'ffmpeg',
                '-y',
                '-ss',
                '00:00:01',
                '-i',
                str(src),
                '-frames:v',
                '1',
                '-q:v',
                '3',
                str(thumb),
            ],
            check=True,
            capture_output=True,
            timeout=60,
        )
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return None
    if not thumb.is_file():
        return None
    rel = thumb.relative_to(Path(settings.MEDIA_ROOT)).as_posix()
    return f'{settings.MEDIA_URL.rstrip("/")}/{rel}'


def ensure_public_username(user) -> str:
    """Return a URL-safe public_username, creating one if missing."""
    from people.models import UserProfile

    profile, _ = UserProfile.objects.get_or_create(user=user)
    if profile.public_username:
        return profile.public_username

    base = ''
    if user.email and '@' in user.email:
        base = user.email.split('@', 1)[0]
    if not base:
        base = user.username or f'user{user.pk}'
    base = slugify(base).replace('_', '-')[:60] or f'user{user.pk}'
    if base in RESERVED_USERNAMES:
        base = f'u-{base}'

    candidate = base
    n = 2
    while (
        candidate in RESERVED_USERNAMES
        or UserProfile.objects.filter(public_username=candidate).exclude(pk=profile.pk).exists()
    ):
        candidate = f'{base}-{n}'[:80]
        n += 1

    profile.public_username = candidate
    profile.save(update_fields=['public_username'])
    return candidate


def validate_public_username(value: str) -> str:
    value = (value or '').strip().lower()
    if not re.fullmatch(r'[a-z0-9]([a-z0-9-]{0,78}[a-z0-9])?', value):
        raise ValueError('Username must be 2–80 chars: letters, numbers, hyphens.')
    if value in RESERVED_USERNAMES:
        raise ValueError('That username is reserved.')
    return value


def unique_show_slug(gallery, base: str) -> str:
    slug = slugify(base or '')[:80] or 'show'
    taken = set(
        gallery.shows.exclude(slug='').values_list('slug', flat=True)
    )
    if slug not in taken:
        return slug
    n = 2
    while f'{slug}-{n}' in taken:
        n += 1
    return f'{slug}-{n}'[:80]


def role_at_least(role: str, needed: str) -> bool:
    order = {'view': 1, 'add_photos': 2, 'edit': 3}
    return order.get(role, 0) >= order.get(needed, 99)
