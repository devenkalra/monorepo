"""
Hierarchical storage for WhatsApp media - same scheme as people/utils: abc/def/abcdef...xyz.ext
"""
import hashlib
import os
from django.conf import settings
from pathlib import Path


def save_bytes_deduplicated(content: bytes, filename: str, subdir: str = 'wa_assistant'):
    """
    Saves bytes to MEDIA_ROOT using content-addressable scheme:
    wa_assistant/abc/def/abcdef...xyz.ext

    Returns:
        dict: {
            'url': media_url,
            'sha256': sha_hash,
            'path': relative_path,
            'thumbnail_url': optional
        }
    """
    sha = hashlib.sha256()
    sha.update(content)
    file_hash = sha.hexdigest()

    prefix1 = file_hash[:3]
    prefix2 = file_hash[3:6]
    ext = Path(filename).suffix or '.bin'
    stored_filename = f"{file_hash}{ext}"

    relative_path = os.path.join(subdir, prefix1, prefix2, stored_filename)
    full_path = os.path.join(settings.MEDIA_ROOT, relative_path)

    if not os.path.exists(full_path):
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'wb') as f:
            f.write(content)

    url = f"{settings.MEDIA_URL}{relative_path}"
    result = {
        'url': url,
        'sha256': file_hash,
        'path': relative_path,
    }

    # Thumbnail for images
    try:
        from PIL import Image
        from io import BytesIO

        if ext.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
            thumb_filename = f"{file_hash}_thumb{ext}"
            thumb_relative_path = os.path.join(subdir, prefix1, prefix2, thumb_filename)
            thumb_full_path = os.path.join(settings.MEDIA_ROOT, thumb_relative_path)

            if not os.path.exists(thumb_full_path):
                image = Image.open(BytesIO(content))
                image.thumbnail((256, 256))
                image.save(thumb_full_path)

            result['thumbnail_url'] = f"{settings.MEDIA_URL}{thumb_relative_path}"
    except (ImportError, Exception):
        pass

    return result
