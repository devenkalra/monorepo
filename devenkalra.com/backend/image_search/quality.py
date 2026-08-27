"""Download, size-probe, quality-score, and zip images from public URLs."""
from __future__ import annotations

import io
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import unquote, urlparse

from PIL import Image, ImageFile, ImageFilter, ImageStat

from core.http_client import WebFetchError, fetch_url, is_public_http_url
from image_search.bing import image_headers

ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = 40_000_000

MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024
DOWNLOAD_FILE_BYTES = 12 * 1024 * 1024
DOWNLOAD_MAX_ITEMS = 80
QUALITY_EDGE = 384
UNSAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
EXT_BY_FORMAT = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
    "GIF": ".gif",
    "BMP": ".bmp",
    "TIFF": ".tif",
    "AVIF": ".avif",
    "HEIF": ".heif",
    "HEIC": ".heic",
}
MIME_BY_EXT = {
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".avif": "image/avif",
    ".heif": "image/heif",
    ".heic": "image/heic",
}


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def probe_bytes(url: str) -> int | None:
    if not is_public_http_url(url):
        return None
    try:
        resp = fetch_url(
            url,
            headers=image_headers(),
            timeout=5,
            max_bytes=64,
            range_header="bytes=0-0",
            raise_http_error=False,
        )
    except WebFetchError:
        return None
    return resp.content_length()


def download_image(url: str, limit: int = MAX_DOWNLOAD_BYTES, timeout: int = 10) -> bytes | None:
    if not is_public_http_url(url):
        return None
    try:
        resp = fetch_url(
            url,
            headers=image_headers(),
            timeout=timeout,
            max_bytes=limit,
        )
    except WebFetchError:
        return None
    return resp.body or None


def score_image(data: bytes, claimed_w: int = 0, claimed_h: int = 0, nbytes: int | None = None) -> dict | None:
    try:
        with Image.open(io.BytesIO(data)) as src:
            src.load()
            fmt = (src.format or "").upper() or None
            width, height = src.size
            rgb = src.convert("RGB")
    except Exception:
        return None
    if width < 8 or height < 8:
        return None

    long_edge = max(width, height)
    work = rgb
    if long_edge > QUALITY_EDGE:
        scale = QUALITY_EDGE / long_edge
        work = rgb.resize(
            (max(8, int(width * scale)), max(8, int(height * scale))),
            Image.Resampling.BILINEAR,
        )
    gray = work.convert("L")
    stat = ImageStat.Stat(gray)
    mean = float(stat.mean[0])
    contrast_raw = float(stat.stddev[0])
    edges = gray.filter(ImageFilter.FIND_EDGES)
    sharp_raw = float(ImageStat.Stat(edges).stddev[0])
    hist = gray.histogram()
    pixel_count = max(1, work.size[0] * work.size[1])
    clip = (sum(hist[:8]) + sum(hist[248:])) / pixel_count

    sharpness = _clamp(sharp_raw / 36.0 * 100.0)
    contrast = _clamp(contrast_raw / 58.0 * 100.0)
    exposure = _clamp(100.0 - clip * 520.0)
    if mean < 42:
        exposure *= mean / 42.0
    elif mean > 220:
        exposure *= (255.0 - mean) / 35.0
    exposure = _clamp(exposure)

    used_bytes = nbytes if nbytes and nbytes > 0 else len(data)
    bpp = (used_bytes * 8.0) / max(1, width * height)
    fmt_u = fmt or ""
    if fmt_u in ("AVIF", "HEIF", "HEIC"):
        compression = _clamp((bpp - 0.05) / 0.85 * 100.0)
    elif fmt_u == "WEBP":
        compression = _clamp((bpp - 0.12) / 2.0 * 100.0)
    elif fmt_u in ("PNG", "BMP", "TIFF", "GIF"):
        compression = 78.0
    else:
        compression = _clamp((bpp - 0.28) / 3.8 * 100.0)

    score = 0.35 * sharpness + 0.25 * contrast + 0.20 * exposure + 0.20 * compression
    if claimed_w and width < claimed_w * 0.7:
        score *= 0.75
    if claimed_h and height < claimed_h * 0.7:
        score *= 0.85

    return {
        "score": round(_clamp(score)),
        "sharpness": round(sharpness),
        "contrast": round(contrast),
        "exposure": round(exposure),
        "compression": round(compression),
        "width": width,
        "height": height,
        "format": fmt,
        "bpp": round(bpp, 2),
    }


def analyze_one(item: dict) -> tuple[str, dict | None]:
    url = str(item.get("url") or "")
    claimed_w = int(item.get("width") or 0)
    claimed_h = int(item.get("height") or 0)
    nbytes = item.get("bytes")
    try:
        nbytes_i = int(nbytes) if nbytes not in (None, "", -1) else None
    except (TypeError, ValueError):
        nbytes_i = None
    data = download_image(url)
    if not data:
        return url, None
    return url, score_image(data, claimed_w, claimed_h, nbytes_i)


def probe_quality(items: list[dict]) -> dict[str, dict]:
    unique: list[dict] = []
    seen: set[str] = set()
    for item in items:
        url = str(item.get("url") or "")
        if url and url not in seen and is_public_http_url(url):
            seen.add(url)
            unique.append(item)
    out: dict[str, dict] = {}
    if not unique:
        return out
    workers = min(4, len(unique))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(analyze_one, item): item for item in unique}
        for future in as_completed(futures):
            try:
                url, result = future.result()
            except Exception:
                continue
            if url and result:
                out[url] = result
    return out


def probe_sizes(urls: list[str]) -> dict[str, int]:
    unique = []
    seen: set[str] = set()
    for url in urls:
        if url and url not in seen and is_public_http_url(url):
            seen.add(url)
            unique.append(url)
    sizes: dict[str, int] = {}
    if not unique:
        return sizes
    workers = min(8, len(unique))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(probe_bytes, url): url for url in unique}
        for future in as_completed(futures):
            url = futures[future]
            try:
                nbytes = future.result()
            except Exception:
                nbytes = None
            if nbytes is not None:
                sizes[url] = nbytes
    return sizes


def image_ext(data: bytes, url: str) -> str:
    try:
        with Image.open(io.BytesIO(data)) as src:
            fmt = (src.format or "").upper()
    except Exception:
        fmt = ""
    if fmt in EXT_BY_FORMAT:
        return EXT_BY_FORMAT[fmt]
    path = unquote(urlparse(url).path).lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".bmp", ".tif", ".tiff"):
        if path.endswith(ext):
            return ".jpg" if ext in (".jpeg",) else ".tif" if ext == ".tiff" else ext
    return ".jpg"


def safe_stem(title: str, url: str) -> str:
    stem = UNSAFE_NAME_RE.sub("-", (title or "").strip())[:80].strip("-._")
    if not stem:
        stem = UNSAFE_NAME_RE.sub("-", Path(unquote(urlparse(url).path)).stem)[:80].strip("-._")
    return stem or "image"


def unique_name(stem: str, ext: str, used: set[str]) -> str:
    name = f"{stem}{ext}"
    n = 2
    while name in used:
        name = f"{stem}-{n}{ext}"
        n += 1
    used.add(name)
    return name


def parse_download_items(payload: dict) -> list[dict]:
    raw = payload.get("items")
    items: list[dict] = []
    seen: set[str] = set()
    if isinstance(raw, list) and raw:
        source = raw[:DOWNLOAD_MAX_ITEMS]
    elif payload.get("url"):
        source = [{"url": payload.get("url"), "title": payload.get("title") or ""}]
    else:
        source = []
    for item in source:
        if isinstance(item, str):
            url, title = item, ""
        elif isinstance(item, dict):
            url, title = str(item.get("url") or ""), str(item.get("title") or "")
        else:
            continue
        if url and url not in seen:
            seen.add(url)
            items.append({"url": url, "title": title})
    return items


def fetch_download_bytes(items: list[dict]) -> list[tuple[dict, bytes | None]]:
    cleaned = [item for item in items if is_public_http_url(item["url"])]
    if not cleaned:
        return [(item, None) for item in items]
    results: dict[str, bytes | None] = {}
    workers = min(4, len(cleaned))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(download_image, item["url"], DOWNLOAD_FILE_BYTES, 20): item["url"]
            for item in cleaned
        }
        for future in as_completed(futures):
            url = futures[future]
            try:
                results[url] = future.result()
            except Exception:
                results[url] = None
    return [(item, results.get(item["url"])) for item in items]


def build_download_zip(fetched: list[tuple[dict, bytes | None]]) -> bytes | None:
    buf = io.BytesIO()
    used: set[str] = set()
    ok = 0
    failed: list[str] = []
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        for item, data in fetched:
            url = item["url"]
            if not data:
                failed.append(url)
                continue
            name = unique_name(safe_stem(item.get("title") or "", url), image_ext(data, url), used)
            zf.writestr(name, data)
            ok += 1
        if failed:
            zf.writestr("_failed.txt", "\n".join(failed) + "\n")
    if not ok:
        return None
    return buf.getvalue()
