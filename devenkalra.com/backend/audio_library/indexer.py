from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import re

from .models import AudioTrack
from .roots import allowed_extensions, configured_roots, cover_file, resolve_under_root


COVER_FILENAMES = (
    'cover.jpg', 'cover.jpeg', 'cover.png', 'cover.webp',
    'folder.jpg', 'folder.jpeg', 'folder.png',
    'album.jpg', 'album.jpeg', 'front.jpg',
    'albumart.jpg', 'albumartsmall.jpg',
)
_folder_cover_cache = {}


def _is_hidden_path(path, root):
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        parts = path.parts
    return any(part.startswith('.') for part in parts)


def _first_text(value):
    if value is None:
        return ''
    if isinstance(value, list):
        value = value[0] if value else ''
    text = str(value).strip()
    return text


def _tag_value(audio, *keys, limit=500):
    if audio is None:
        return ''
    for key in keys:
        text = _first_text(audio.get(key) if hasattr(audio, 'get') else None)
        if text:
            return text[:limit]
    return ''


def _id3_text(tags, *frame_ids, limit=500):
    if tags is None:
        return ''
    for frame_id in frame_ids:
        frame = tags.get(frame_id)
        if frame is None:
            continue
        texts = getattr(frame, 'text', None)
        text = _first_text(texts[0] if texts else frame)
        if text:
            return text[:limit]
    return ''


def _parse_year(value):
    text = _first_text(value)
    if not text:
        return None
    match = re.search(r'(?:^|\D)((?:19|20)\d{2})(?:\D|$)', text) or re.search(r'^(\d{4})', text)
    if not match:
        return None
    year = int(match.group(1))
    if 1000 <= year <= 2100:
        return year
    return None


def _parse_bpm(value):
    text = _first_text(value)
    if not text:
        return None
    match = re.search(r'(\d+(?:\.\d+)?)', text)
    if not match:
        return None
    bpm = float(match.group(1))
    if bpm <= 0 or bpm > 400:
        return None
    return bpm


def empty_tags():
    return {
        'title': '',
        'artist': '',
        'composer': '',
        'genre': '',
        'album': '',
        'year': None,
        'bpm': None,
        'duration_seconds': None,
        'cover_bytes': None,
    }


def read_tags(path):
    tags = empty_tags()
    try:
        from mutagen import File as MutagenFile
        from mutagen.id3 import ID3, ID3NoHeaderError
    except ImportError:
        return tags

    try:
        audio = MutagenFile(path, easy=True)
    except Exception:
        audio = None
    if audio is not None:
        info = getattr(audio, 'info', None)
        length = getattr(info, 'length', None) if info is not None else None
        if length:
            tags['duration_seconds'] = float(length)
        tags['title'] = _tag_value(audio, 'title')
        tags['artist'] = _tag_value(audio, 'artist', 'albumartist')
        tags['composer'] = _tag_value(audio, 'composer')
        tags['genre'] = _tag_value(audio, 'genre')
        tags['album'] = _tag_value(audio, 'album')
        tags['year'] = _parse_year(_tag_value(audio, 'date', 'year'))
        tags['bpm'] = _parse_bpm(_tag_value(audio, 'bpm'))

    id3 = None
    try:
        id3 = ID3(path)
    except (ID3NoHeaderError, Exception):
        id3 = None
    if id3 is not None:
        tags['title'] = tags['title'] or _id3_text(id3, 'TIT2')
        tags['artist'] = tags['artist'] or _id3_text(id3, 'TPE1', 'TPE2')
        tags['composer'] = tags['composer'] or _id3_text(id3, 'TCOM')
        tags['genre'] = tags['genre'] or _id3_text(id3, 'TCON')
        tags['album'] = tags['album'] or _id3_text(id3, 'TALB')
        if tags['year'] is None:
            tags['year'] = _parse_year(_id3_text(id3, 'TDRC', 'TYER', 'TDAT'))
        if tags['bpm'] is None:
            tags['bpm'] = _parse_bpm(_id3_text(id3, 'TBPM'))
        tags['cover_bytes'] = _apic_bytes(id3)
    if not tags.get('cover_bytes'):
        tags['cover_bytes'] = _folder_cover_bytes(Path(path).parent)
    return tags


def _apic_bytes(id3):
    frames = []
    if hasattr(id3, 'getall'):
        frames = list(id3.getall('APIC'))
    if not frames:
        frames = [id3[key] for key in id3.keys() if str(key).startswith('APIC')]
    if not frames:
        return None
    front = next((frame for frame in frames if getattr(frame, 'type', None) == 3), frames[0])
    data = getattr(front, 'data', None)
    return data or None


def _folder_cover_bytes(folder):
    key = str(folder)
    if key in _folder_cover_cache:
        return _folder_cover_cache[key]
    data = None
    try:
        names = {p.name.lower(): p for p in folder.iterdir() if p.is_file()}
    except OSError:
        names = {}
    for name in COVER_FILENAMES:
        match = names.get(name)
        if match is None:
            continue
        try:
            data = match.read_bytes()
            break
        except OSError:
            continue
    _folder_cover_cache[key] = data
    return data


def thumbnail_jpeg(image_bytes, size=256):
    if not image_bytes:
        return None
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        image = Image.open(BytesIO(image_bytes))
        image = image.convert('RGB')
        image.thumbnail((size, size))
        buf = BytesIO()
        image.save(buf, format='JPEG', quality=82, optimize=True)
        return buf.getvalue()
    except Exception:
        return None


def save_cover(track, image_bytes):
    dest = cover_file(track.id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    thumb = thumbnail_jpeg(image_bytes)
    if not thumb:
        if dest.exists():
            dest.unlink()
        if track.has_cover:
            track.has_cover = False
            track.save(update_fields=['has_cover'])
        return False
    dest.write_bytes(thumb)
    if not track.has_cover:
        track.has_cover = True
        track.save(update_fields=['has_cover'])
    return True


def iter_audio_files(root_path):
    root = Path(root_path)
    if not root.is_dir():
        return
    allowed = allowed_extensions()
    for path in root.rglob('*'):
        if not path.is_file() or path.suffix.lower() not in allowed:
            continue
        if _is_hidden_path(path, root):
            continue
        resolved = resolve_under_root(root, path.relative_to(root))
        if resolved is None:
            continue
        yield resolved


def index_roots(roots=None):
    roots = list(roots if roots is not None else configured_roots())
    counts = {'scanned': 0, 'upserted': 0, 'removed': 0, 'covers': 0, 'missing_roots': 0}
    _folder_cover_cache.clear()
    for row in roots:
        root_path = Path(row['path'])
        if not root_path.is_dir():
            counts['missing_roots'] += 1
            continue
        seen = set()
        for path in iter_audio_files(root_path):
            counts['scanned'] += 1
            relpath = path.relative_to(root_path.resolve()).as_posix()
            seen.add(relpath)
            parent = '/'.join(relpath.split('/')[:-1])
            stat = path.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            tags = read_tags(path)
            cover_bytes = tags.pop('cover_bytes', None)
            defaults = {
                'filename': path.name,
                'parent': parent,
                'title': tags['title'] or path.stem,
                'artist': tags['artist'],
                'composer': tags['composer'],
                'genre': tags['genre'],
                'album': tags['album'],
                'year': tags['year'],
                'bpm': tags['bpm'],
                'duration_seconds': tags['duration_seconds'],
                'size_bytes': stat.st_size,
                'mtime': mtime,
            }
            track, _created = AudioTrack.objects.update_or_create(
                folder_slug=row['slug'],
                relpath=relpath,
                defaults=defaults,
            )
            if save_cover(track, cover_bytes):
                counts['covers'] += 1
            counts['upserted'] += 1
        stale = AudioTrack.objects.filter(folder_slug=row['slug']).exclude(relpath__in=seen)
        for track_id in stale.values_list('id', flat=True):
            dest = cover_file(track_id)
            if dest.exists():
                dest.unlink()
        deleted, _ = stale.delete()
        counts['removed'] += deleted
    configured_slugs = {row['slug'] for row in roots}
    extra = AudioTrack.objects.exclude(folder_slug__in=configured_slugs)
    for track_id in extra.values_list('id', flat=True):
        dest = cover_file(track_id)
        if dest.exists():
            dest.unlink()
    deleted, _ = extra.delete()
    counts['removed'] += deleted
    return counts
