"""Per-image analysis cache. v3: Haar faces + EXIF upright + detector freshness."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError
from PIL.ExifTags import IFD

from .utils import media_filesystem_path

ANALYZER_VERSION = 3
# Higher = blurrier. Solid / out-of-focus frames sit above this.
BLUR_SKIP_THRESHOLD = 0.6


def source_key(item) -> str:
    return (getattr(item, 'url', None) or getattr(item, 'external_url', None) or '') if item else ''


def current_detector() -> str:
    """'haar' when OpenCV cascades load; 'none' otherwise."""
    return 'haar' if _haar_cascades() else 'none'


def analysis_is_fresh(analysis, url: str, version: int = ANALYZER_VERSION) -> bool:
    if not isinstance(analysis, dict):
        return False
    detector = current_detector()
    cached = analysis.get('detector')
    if detector != 'none' and cached != detector:
        return False
    return (
        analysis.get('v') == version
        and analysis.get('source_url') == url
        and 'blur' in analysis
        and 'subject' in analysis
        and 'faces' in analysis
    )


def item_blur(item) -> float:
    analysis = getattr(item, 'analysis', None) or {}
    try:
        return float(analysis.get('blur') or 0)
    except (TypeError, ValueError):
        return 0.0


def item_subject(item) -> tuple[float, float]:
    if isinstance(item, dict):
        analysis = item.get('analysis') or {}
    else:
        analysis = getattr(item, 'analysis', None) or {}
    sub = analysis.get('subject') or {}
    try:
        x = float(sub.get('x', 0.5))
        y = float(sub.get('y', 0.5))
    except (TypeError, ValueError):
        return 0.5, 0.5
    return max(0.0, min(1.0, x)), max(0.0, min(1.0, y))


def stub_analysis(url: str) -> dict:
    return {
        'v': ANALYZER_VERSION,
        'source_url': url,
        'width': 0,
        'height': 0,
        'aspect': 1.0,
        'taken_at': None,
        'faces': [],
        'subject': {'x': 0.5, 'y': 0.5},
        'blur': 0.0,
        'orientation': 'unknown',
        'detector': current_detector(),
        'analyzed_at': _now(),
    }


def subject_from_faces(faces) -> dict:
    """Area-weighted centroid of face boxes. Image center if none."""
    if not faces:
        return {'x': 0.5, 'y': 0.5}
    weighted_x = 0.0
    weighted_y = 0.0
    total = 0.0
    for face in faces:
        try:
            x = float(face.get('x', 0))
            y = float(face.get('y', 0))
            w = float(face.get('w', 0))
            h = float(face.get('h', 0))
        except (TypeError, ValueError, AttributeError):
            continue
        area = max(1e-6, w * h)
        weighted_x += (x + w / 2.0) * area
        weighted_y += (y + h / 2.0) * area
        total += area
    if total <= 0:
        return {'x': 0.5, 'y': 0.5}
    return {
        'x': round(max(0.0, min(1.0, weighted_x / total)), 4),
        'y': round(max(0.0, min(1.0, weighted_y / total)), 4),
    }


_FACE_DETECT_MAX_EDGE = 960
_HAAR_CASCADES = None
_HAAR_NAMES = (
    'haarcascade_frontalface_default.xml',
    'haarcascade_frontalface_alt2.xml',
)


def _haar_cascades():
    global _HAAR_CASCADES
    if _HAAR_CASCADES is not None:
        return _HAAR_CASCADES
    loaded = []
    try:
        import cv2
        root = getattr(getattr(cv2, 'data', None), 'haarcascades', '')
        for name in _HAAR_NAMES:
            cascade = cv2.CascadeClassifier(root + name)
            if not cascade.empty():
                loaded.append(cascade)
    except ImportError:
        loaded = []
    _HAAR_CASCADES = loaded
    return _HAAR_CASCADES


def _iou(a, b) -> float:
    ax2, ay2 = a['x'] + a['w'], a['y'] + a['h']
    bx2, by2 = b['x'] + b['w'], b['y'] + b['h']
    ix = max(0.0, min(ax2, bx2) - max(a['x'], b['x']))
    iy = max(0.0, min(ay2, by2) - max(a['y'], b['y']))
    inter = ix * iy
    union = a['w'] * a['h'] + b['w'] * b['h'] - inter
    return inter / union if union else 0.0


def _nms(faces, thresh=0.3) -> list[dict]:
    ordered = sorted(faces, key=lambda f: f['w'] * f['h'], reverse=True)
    kept = []
    for face in ordered:
        if all(_iou(face, other) < thresh for other in kept):
            kept.append(face)
    return kept


def detect_faces(gray: Image.Image) -> list[dict]:
    """Normalized face boxes {x, y, w, h} in 0–1. Empty if OpenCV is missing."""
    width, height = gray.size
    if width < 8 or height < 8:
        return []
    cascades = _haar_cascades()
    if not cascades:
        return []
    try:
        import numpy as np
    except ImportError:
        return []

    arr = np.array(gray.convert('L'))
    scale = min(1.0, _FACE_DETECT_MAX_EDGE / max(width, height))
    if scale < 1.0:
        try:
            import cv2
        except ImportError:
            return []
        small = cv2.resize(
            arr,
            (max(8, int(width * scale)), max(8, int(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
    else:
        small = arr
        scale = 1.0

    min_side = max(20, int(min(small.shape[0], small.shape[1]) * 0.04))
    faces = []
    for cascade in cascades:
        raw = cascade.detectMultiScale(
            small,
            scaleFactor=1.08,
            minNeighbors=4,
            minSize=(min_side, min_side),
        )
        for (x, y, fw, fh) in raw:
            faces.append({
                'x': float(round(max(0.0, (x / scale) / width), 4)),
                'y': float(round(max(0.0, (y / scale) / height), 4)),
                'w': float(round(min(1.0, (fw / scale) / width), 4)),
                'h': float(round(min(1.0, (fh / scale) / height), 4)),
            })
    return _nms(faces)


def analyze_image_file(path: str | Path) -> dict:
    path = Path(path)
    with Image.open(path) as raw:
        raw.load()
        taken = _taken_at(raw)
        img = ImageOps.exif_transpose(raw) or raw
        if img is not raw:
            img.load()
        width, height = img.size
        gray = img.convert('L')
        blur = _blur_score(gray)
        faces = detect_faces(gray)
    aspect = round(width / height, 4) if height else 1.0
    if aspect >= 1.15:
        orientation = 'landscape'
    elif aspect <= 0.87:
        orientation = 'portrait'
    else:
        orientation = 'square'
    return {
        'v': ANALYZER_VERSION,
        'width': width,
        'height': height,
        'aspect': aspect,
        'taken_at': taken,
        'faces': faces,
        'subject': subject_from_faces(faces),
        'blur': blur,
        'orientation': orientation,
        'detector': current_detector(),
        'analyzed_at': _now(),
    }


def ensure_item_analysis(item, save: bool = True) -> dict:
    url = source_key(item)
    current = getattr(item, 'analysis', None) or {}
    if analysis_is_fresh(current, url):
        return current

    path = media_filesystem_path(getattr(item, 'url', '') or '')
    try:
        if path:
            analysis = analyze_image_file(path)
        else:
            analysis = stub_analysis(url)
    except (OSError, UnidentifiedImageError, ValueError):
        analysis = stub_analysis(url)

    analysis['source_url'] = url
    analysis['analyzed_at'] = _now()
    item.analysis = analysis
    if save and getattr(item, 'pk', None):
        item.save(update_fields=['analysis'])
    return analysis


def ensure_analyses(items) -> None:
    for item in items or []:
        if item is None:
            continue
        ensure_item_analysis(item)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _taken_at(img: Image.Image) -> str | None:
    try:
        exif = img.getexif()
        raw = None
        if exif:
            try:
                ifd = exif.get_ifd(IFD.Exif)
                raw = ifd.get(36867) or ifd.get(36868)
            except Exception:
                raw = None
            raw = raw or exif.get(306)
        if not raw:
            return None
        text = str(raw).strip()
        if len(text) >= 19 and text[4] == ':':
            return f'{text[0:4]}-{text[5:7]}-{text[8:10]}T{text[11:19]}'
        return text
    except Exception:
        return None


def _blur_score(gray: Image.Image) -> float:
    """0 = sharp, 1 = blurry. Laplacian energy after a box downsample."""
    small = gray.convert('L').resize((64, 64), Image.Resampling.BOX)
    lap = small.filter(
        ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1, offset=128)
    ).crop((2, 2, 62, 62))
    pixels = list(lap.getdata())
    if not pixels:
        return 1.0
    mean = sum(pixels) / len(pixels)
    var = sum((p - mean) ** 2 for p in pixels) / len(pixels)
    sharpness = min(1.0, var / 250.0)
    return round(max(0.0, min(1.0, 1.0 - sharpness)), 4)
