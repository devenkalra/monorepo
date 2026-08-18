from pathlib import Path
import json

from django.conf import settings
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner


SIGN_SALT = 'audio-library-stream'
AUDIO_TYPES = {
    '.mp3': 'audio/mpeg',
    '.m4a': 'audio/mp4',
    '.aac': 'audio/aac',
    '.flac': 'audio/flac',
    '.ogg': 'audio/ogg',
    '.wav': 'audio/wav',
    '.opus': 'audio/ogg',
}


def parse_audio_library_roots(raw):
    raw = (raw or '').strip()
    if not raw:
        return []
    if raw.startswith('['):
        data = json.loads(raw)
        rows = []
        for item in data:
            slug = str(item.get('slug') or '').strip()
            path = str(item.get('path') or '').strip()
            if not slug or not path:
                continue
            rows.append({
                'slug': slug,
                'path': path,
                'label': str(item.get('label') or slug).strip() or slug,
            })
        return rows
    rows = []
    for part in raw.split(','):
        part = part.strip()
        if not part or '=' not in part:
            continue
        slug, rest = part.split('=', 1)
        slug = slug.strip()
        path, _, label = rest.partition('|')
        path = path.strip()
        if not slug or not path:
            continue
        rows.append({
            'slug': slug,
            'path': path,
            'label': (label.strip() or slug),
        })
    return rows


def configured_roots():
    return list(getattr(settings, 'AUDIO_LIBRARY_ROOTS', None) or [])


def root_for_slug(slug):
    for row in configured_roots():
        if row['slug'] == slug:
            return row
    return None


def allowed_extensions():
    raw = getattr(settings, 'AUDIO_LIBRARY_EXTENSIONS', '.mp3') or '.mp3'
    return {
        ext.lower() if ext.startswith('.') else f'.{ext.lower()}'
        for ext in raw.split(',')
        if ext.strip()
    }


def sign_ttl():
    return int(getattr(settings, 'AUDIO_LIBRARY_SIGN_TTL', 21600) or 21600)


def stream_signature(track_id):
    return TimestampSigner(salt=SIGN_SALT).sign(str(track_id))


def unsign_stream(signature, max_age=None):
    return TimestampSigner(salt=SIGN_SALT).unsign(
        signature,
        max_age=sign_ttl() if max_age is None else max_age,
    )


def verify_stream_signature(signature, track_id):
    try:
        return unsign_stream(signature) == str(track_id)
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return False


def resolve_under_root(root_path, relpath):
    root = Path(root_path).resolve()
    if not root.is_dir():
        return None
    candidate = (root / relpath).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def resolve_track_file(track):
    root = root_for_slug(track.folder_slug)
    if not root:
        return None
    path = resolve_under_root(root['path'], track.relpath)
    if path is None or not path.is_file():
        return None
    if path.suffix.lower() not in allowed_extensions():
        return None
    return path


def content_type_for(path):
    return AUDIO_TYPES.get(Path(path).suffix.lower(), 'application/octet-stream')


def cover_file(track_id):
    from django.conf import settings
    return Path(settings.MEDIA_ROOT) / 'audio_covers' / f'{int(track_id)}.jpg'
