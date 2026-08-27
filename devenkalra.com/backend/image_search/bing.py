"""Fetch and parse Bing's public image-search HTML.

Bing's Image Search API is retired and the HTML results are not CORS-accessible
from a browser, so the server fetches `images/async` and extracts result cards.
"""
from __future__ import annotations

import html
import json
import re
from urllib.parse import parse_qs, unquote, urlencode, urlparse

from core.http_client import DEFAULT_USER_AGENT, WebFetchError, fetch_url

BING_ASYNC = "https://www.bing.com/images/async"
IUSC_RE = re.compile(r"<a\b[^>]*\bclass=\"[^\"]*\biusc\b[^\"]*\"[^>]*>", re.I)
ATTR_RE = re.compile(r"\b(m|href)=\"([^\"]*)\"", re.I)
THUMB_ID_RE = re.compile(r"[?&]id=([^&]+)", re.I)
PATH_DIM_RE = re.compile(r"[-_](\d{2,5})x(\d{2,5})(?=\.[a-z0-9]{3,4}$)", re.I)

SIZE_PRESETS = {
    "small": "+filterui:imagesize-small",
    "medium": "+filterui:imagesize-medium",
    "large": "+filterui:imagesize-large",
    "wallpaper": "+filterui:imagesize-wallpaper",
}
ASPECT_PRESETS = {
    "square": "+filterui:aspect-square",
    "wide": "+filterui:aspect-wide",
    "tall": "+filterui:aspect-tall",
}
DATE_PRESETS = {
    "day": "+filterui:age-lt1440",
    "week": "+filterui:age-lt10080",
    "month": "+filterui:age-lt43200",
    "year": "+filterui:age-lt525600",
}
SAFE_SEARCH = {"off", "moderate", "strict"}
SAFE_SEARCH_COOKIE = {"off": "OFF", "moderate": "DEMOTE", "strict": "STRICT"}

IMAGE_ACCEPT = "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"


def bing_headers(safe: str = "") -> dict[str, str]:
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    cookie = SAFE_SEARCH_COOKIE.get(safe)
    if cookie:
        headers["Cookie"] = f"SRCHHPGUSR=ADLT={cookie}"
    return headers


def image_headers() -> dict[str, str]:
    return {
        "User-Agent": DEFAULT_USER_AGENT,
        "Referer": "https://www.bing.com/",
        "Accept": IMAGE_ACCEPT,
    }


def build_qft(size: str, aspect: str, min_width: int, min_height: int, date: str = "") -> str:
    parts: list[str] = []
    if size in SIZE_PRESETS:
        parts.append(SIZE_PRESETS[size])
    elif min_width or min_height:
        parts.append(f"+filterui:imagesize-custom_{min_width or 0}_{min_height or 0}")
    if aspect in ASPECT_PRESETS:
        parts.append(ASPECT_PRESETS[aspect])
    if date in DATE_PRESETS:
        parts.append(DATE_PRESETS[date])
    return "".join(parts)


def fetch_bing(query: str, offset: int, count: int, qft: str, safe: str = "moderate") -> str:
    if safe not in SAFE_SEARCH:
        safe = "moderate"
    params = {
        "q": query,
        "first": str(offset),
        "count": str(count),
        "mmasync": "1",
        "adlt": safe,
    }
    if qft:
        params["qft"] = qft
    url = f"{BING_ASYNC}?{urlencode(params)}"
    resp = fetch_url(url, headers=bing_headers(safe), timeout=20, max_bytes=2 * 1024 * 1024)
    return resp.body.decode("utf-8", "ignore")


def parse_int(values: list[str] | None) -> int:
    if not values:
        return 0
    try:
        return int(values[0])
    except (TypeError, ValueError):
        return 0


def normalize_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = unquote(parsed.path or "").rstrip("/").lower()
    path = PATH_DIM_RE.sub("", path)
    return f"{host}{path}"


def identity_keys(
    image_url: str,
    data: dict,
    turl: str,
    qs: dict[str, list[str]],
) -> list[str]:
    keys: list[str] = []
    md5 = str(data.get("md5") or "").strip().lower()
    if md5:
        keys.append(f"md5:{md5}")
    mid = str(data.get("mid") or (qs.get("id") or [""])[0] or "").strip().lower()
    if mid:
        keys.append(f"mid:{mid}")
    cid = str(data.get("cid") or "").strip().lower()
    if cid:
        keys.append(f"cid:{cid}")
    thumb = THUMB_ID_RE.search(turl or "")
    if thumb:
        keys.append(f"th:{unquote(thumb.group(1)).lower()}")
    url_key = normalize_url(image_url)
    if url_key:
        keys.append(f"url:{url_key}")
    return keys


def parse_images(page_html: str) -> list[dict]:
    images: list[dict] = []
    seen: set[str] = set()
    for match in IUSC_RE.finditer(page_html):
        tag = match.group(0)
        attrs = {k.lower(): v for k, v in ATTR_RE.findall(tag)}
        raw_m = attrs.get("m")
        if not raw_m:
            continue
        try:
            data = json.loads(html.unescape(raw_m))
        except json.JSONDecodeError:
            continue
        href = html.unescape(attrs.get("href") or "")
        parsed = urlparse(href if href.startswith("http") else f"https://www.bing.com{href}")
        qs = parse_qs(parsed.query)
        image_url = data.get("murl") or unquote(qs.get("mediaurl", [""])[0])
        if not image_url:
            continue
        turl = data.get("turl") or ""
        keys = identity_keys(image_url, data, turl, qs)
        if any(key in seen for key in keys):
            continue
        seen.update(keys)
        cdn_url = unquote(qs.get("cdnurl", [""])[0])
        title = re.sub(r"[\ue000\ue001]", "", data.get("t") or data.get("desc") or "")
        images.append(
            {
                "title": html.unescape(title).strip(),
                "image_url": image_url,
                "thumb_url": turl,
                "cdn_url": cdn_url,
                "source_url": data.get("purl") or "",
                "width": parse_int(qs.get("expw")),
                "height": parse_int(qs.get("exph")),
                "md5": data.get("md5") or "",
                "mid": data.get("mid") or "",
                "cid": data.get("cid") or "",
                "bytes": None,
            }
        )
    return images


def search_images(
    query: str,
    *,
    offset: int = 0,
    count: int = 35,
    size: str = "",
    aspect: str = "",
    date: str = "",
    safe: str = "moderate",
    min_width: int = 0,
    min_height: int = 0,
) -> dict:
    qft = build_qft(size, aspect, min_width, min_height, date)
    page = fetch_bing(query, offset, count, qft, safe)
    return {
        "query": query,
        "offset": offset,
        "next_offset": offset + count,
        "images": parse_images(page),
    }


__all__ = [
    "SAFE_SEARCH",
    "WebFetchError",
    "build_qft",
    "image_headers",
    "parse_images",
    "search_images",
]
