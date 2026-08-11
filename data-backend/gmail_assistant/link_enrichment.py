"""Extract URLs from emails and enrich by kind: web, image, YouTube, Apify social."""

from __future__ import annotations

import html as html_lib
import ipaddress
import logging
import os
import re
import socket
from typing import Any, Callable
from urllib.parse import urlparse

import requests
from django.conf import settings

from . import gmail_api

logger = logging.getLogger(__name__)

USER_AGENT = 'bldrdojo-gmail-assistant/1.0 (+link-enrichment)'
MAX_URLS_PER_EMAIL = 8
MAX_DOWNLOAD_BYTES = 2_000_000
MAX_WEB_CHARS = 15_000
MAX_TRANSCRIPT_CHARS = 100_000
MAX_APIFY_CHARS = 30_000
FETCH_TIMEOUT = 20
APIFY_TIMEOUT = 180
APIFY_TRANSCRIPT_TIMEOUT = 300
REDIRECT_TIMEOUT = 15
MAX_TRANSCRIPT_ENRICH_CHARS = 100_000

_URL_RE = re.compile(r'https?://[^\s<>\"\']+', re.IGNORECASE)
_HREF_RE = re.compile(
    r'''href\s*=\s*["'](https?://[^"']+)["']''',
    re.IGNORECASE,
)
_IMG_SRC_RE = re.compile(
    r'''(?:src|data-src)\s*=\s*["'](https?://[^"']+)["']''',
    re.IGNORECASE,
)
_YT_ID_RE = re.compile(
    r'(?:youtu\.be/|youtube(?:-nocookie)?\.com/(?:watch\?(?:[^#]*&)?v=|embed/|v/|shorts/|live/))'
    r'([A-Za-z0-9_-]{11})',
    re.IGNORECASE,
)
_IG_POST_PATH_RE = re.compile(
    r'^/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)/?',
    re.IGNORECASE,
)
_IMAGE_EXT_RE = re.compile(
    r'\.(?:jpe?g|png|gif|webp|bmp|svg)(?:$|\?)',
    re.IGNORECASE,
)
_SKIP_HOST_RE = re.compile(
    r'(unsubscribe|list-manage|mandrillapp|click\.|trk\.|tracking\.|'
    r'email\.|beacon|doubleclick|googleadservices)',
    re.IGNORECASE,
)
_SKIP_PATH_RE = re.compile(
    r'(unsubscribe|opt[-_]?out|email-preferences|manage-preferences)',
    re.IGNORECASE,
)

# Hosts that usually need a hop before Apify sees the real destination.
_SHORT_LINK_HOSTS = frozenset(
    {
        'lnkd.in',
        't.co',
        'vm.tiktok.com',
        'vt.tiktok.com',
        'bit.ly',
        'fb.watch',
        'buff.ly',
        'ow.ly',
    }
)

# kind -> hostname suffixes (matched on registrable-ish host)
_APIFY_HOSTS: dict[str, tuple[str, ...]] = {
    'instagram': ('instagram.com', 'instagr.am'),
    'facebook': ('facebook.com', 'fb.com', 'fb.watch', 'm.facebook.com'),
    'linkedin': ('linkedin.com', 'lnkd.in'),
    'twitter': ('twitter.com', 'x.com', 'mobile.twitter.com'),
    'tiktok': ('tiktok.com', 'vm.tiktok.com', 'vt.tiktok.com'),
}

ProgressCb = Callable[[str], None] | None


def extract_urls(body_text: str = '', body_html: str = '') -> list[str]:
    """Collect unique http(s) URLs from plain text and HTML href/src attributes."""
    found: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        url = _normalize_url(raw)
        if not url or url in seen:
            return
        if not _is_candidate_url(url):
            return
        seen.add(url)
        found.append(url)

    for match in _URL_RE.finditer(body_text or ''):
        add(match.group(0))
    for match in _HREF_RE.finditer(body_html or ''):
        add(match.group(1))
    for match in _IMG_SRC_RE.finditer(body_html or ''):
        add(match.group(1))
    return found


def classify_url(url: str) -> str:
    """Return youtube | instagram | facebook | linkedin | twitter | tiktok | image | web."""
    if youtube_video_id(url):
        return 'youtube'
    apify_kind = apify_source_for_url(url)
    if apify_kind:
        return apify_kind
    path = urlparse(url).path or ''
    if _IMAGE_EXT_RE.search(path):
        return 'image'
    return 'web'


def youtube_video_id(url: str) -> str | None:
    match = _YT_ID_RE.search(url or '')
    if match:
        return match.group(1)
    return None


def is_instagram_url(url: str) -> bool:
    return apify_source_for_url(url) == 'instagram'


def apify_source_for_url(url: str) -> str | None:
    host = _hostname(url)
    if not host:
        return None
    for kind, suffixes in _APIFY_HOSTS.items():
        if any(host == s or host.endswith('.' + s) for s in suffixes):
            return kind
    return None


def enrich_message(
    message: dict[str, Any],
    *,
    on_progress: ProgressCb = None,
) -> dict[str, Any]:
    """
    Extract and fetch linked content for one email.

    Returns dict with keys: urls, enrichments (list of per-URL results), block (text).
    """
    urls = extract_urls(
        message.get('body_text') or '',
        message.get('body_html') or '',
    )[:MAX_URLS_PER_EMAIL]
    enrichments: list[dict[str, Any]] = []
    for i, url in enumerate(urls, start=1):
        kind = classify_url(url)
        if on_progress:
            on_progress(f'Fetching link {i}/{len(urls)} ({kind})…')
        enrichments.append(_enrich_one(url, kind))
    block = _format_enrichment_block(message, enrichments)
    return {'urls': urls, 'enrichments': enrichments, 'block': block}


def enrich_messages(
    messages: list[dict[str, Any]],
    *,
    on_progress: ProgressCb = None,
) -> list[dict[str, Any]]:
    out = []
    for i, message in enumerate(messages, start=1):
        if on_progress:
            on_progress(f'Enriching email {i}/{len(messages)}…')
        out.append(enrich_message(message, on_progress=on_progress))
    return out


def _hostname(url: str) -> str:
    host = (urlparse(url or '').hostname or '').lower()
    if host.startswith('www.'):
        host = host[4:]
    return host


def _normalize_url(raw: str) -> str:
    url = html_lib.unescape((raw or '').strip())
    if not url:
        return ''
    # Trim common trailing punctuation left on plain-text URLs.
    while url and url[-1] in ').,;]>\'\"':
        url = url[:-1]
    return url


def _is_candidate_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return False
    host = (parsed.hostname or '').lower()
    if not host or host in ('localhost', 'metadata.google.internal'):
        return False
    if _SKIP_HOST_RE.search(host):
        return False
    path = parsed.path or ''
    if _SKIP_PATH_RE.search(path) or _SKIP_PATH_RE.search(parsed.query or ''):
        return False
    return True


def _is_safe_to_fetch(url: str) -> bool:
    """Basic SSRF guard: only public http(s) hosts."""
    if not _is_candidate_url(url):
        return False
    host = urlparse(url).hostname
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except (ValueError, IndexError):
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            return False
    return True


def _enrich_one(url: str, kind: str) -> dict[str, Any]:
    base = {'url': url, 'kind': kind, 'ok': False, 'error': '', 'content': '', 'meta': {}}
    if not _is_safe_to_fetch(url):
        base['error'] = 'URL blocked (unsafe or filtered)'
        return base
    try:
        if kind == 'youtube':
            return _fetch_youtube(url, base)
        if kind in _APIFY_HOSTS:
            result = _fetch_apify_social(url, kind, base)
            # Append spoken-audio transcripts for Instagram reels/posts & TikTok.
            if kind in ('instagram', 'tiktok'):
                return _attach_apify_transcript(url, kind, result)
            return result
        if kind == 'image':
            return _fetch_image(url, base)
        return _fetch_web(url, base)
    except Exception as exc:  # noqa: BLE001
        logger.info('enrich failed %s: %s', url, exc)
        base['error'] = str(exc)[:300]
        return base


def _http_get(url: str, *, stream: bool = False) -> requests.Response:
    resp = requests.get(
        url,
        headers={'User-Agent': USER_AGENT, 'Accept': '*/*'},
        timeout=FETCH_TIMEOUT,
        stream=stream,
        allow_redirects=True,
    )
    resp.raise_for_status()
    if not _is_safe_to_fetch(resp.url):
        raise RuntimeError('Redirected to unsafe URL')
    return resp


def _read_capped(resp: requests.Response) -> bytes:
    chunks: list[bytes] = []
    total = 0
    for chunk in resp.iter_content(chunk_size=65536):
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_DOWNLOAD_BYTES:
            raise RuntimeError(f'Response exceeds {MAX_DOWNLOAD_BYTES} bytes')
        chunks.append(chunk)
    return b''.join(chunks)


def _fetch_web(url: str, base: dict[str, Any]) -> dict[str, Any]:
    resp = _http_get(url, stream=True)
    ctype = (resp.headers.get('Content-Type') or '').split(';')[0].strip().lower()
    data = _read_capped(resp)

    if ctype.startswith('image/') or _IMAGE_EXT_RE.search(urlparse(resp.url).path or ''):
        base['kind'] = 'image'
        return _describe_image_bytes(data, ctype or 'image/jpeg', base)

    if ctype and 'html' not in ctype and 'text/' not in ctype and 'json' not in ctype:
        base['error'] = f'Unsupported content-type: {ctype or "unknown"}'
        return base

    text = data.decode(resp.encoding or 'utf-8', errors='replace')
    if 'html' in ctype or '<html' in text[:500].lower():
        text = _html_to_readable(text, base_url=resp.url)
    text = text.strip()
    if not text:
        base['error'] = 'Empty page content'
        return base
    base['ok'] = True
    base['content'] = text[:MAX_WEB_CHARS]
    base['meta'] = {
        'final_url': resp.url,
        'content_type': ctype,
        'truncated': len(text) > MAX_WEB_CHARS,
    }
    return base


def _fetch_image(url: str, base: dict[str, Any]) -> dict[str, Any]:
    resp = _http_get(url, stream=True)
    ctype = (resp.headers.get('Content-Type') or 'image/jpeg').split(';')[0].strip()
    data = _read_capped(resp)
    if not ctype.startswith('image/'):
        if b'<' in data[:200]:
            base['kind'] = 'web'
            text = _html_to_readable(
                data.decode('utf-8', errors='replace'), base_url=resp.url
            )
            base['ok'] = bool(text.strip())
            base['content'] = text[:MAX_WEB_CHARS]
            base['meta'] = {'final_url': resp.url, 'content_type': ctype}
            if not base['ok']:
                base['error'] = 'Not an image and empty text'
            return base
        base['error'] = f'Not an image ({ctype})'
        return base
    return _describe_image_bytes(data, ctype, base)


def _describe_image_bytes(
    data: bytes, content_type: str, base: dict[str, Any]
) -> dict[str, Any]:
    from . import llm

    width = height = 0
    try:
        from io import BytesIO

        from PIL import Image

        with Image.open(BytesIO(data)) as img:
            width, height = img.size
    except Exception:  # noqa: BLE001
        pass

    description = llm.describe_image_bytes(data, content_type=content_type)
    base['ok'] = True
    base['meta'] = {
        'bytes': len(data),
        'content_type': content_type,
        'width': width,
        'height': height,
        'downloaded': True,
        'described': bool(description),
    }
    if description:
        base['content'] = description
    else:
        base['content'] = (
            f'[Image downloaded: {len(data)} bytes'
            + (f', {width}x{height}' if width and height else '')
            + f', {content_type}. No vision description available.]'
        )
    return base


def _apify_token() -> str:
    return (
        getattr(settings, 'APIFY_TOKEN', '')
        or os.environ.get('APIFY_TOKEN', '')
        or os.environ.get('APIFY_API_TOKEN', '')
        or ''
    ).strip()


def _setting_or_env(name: str, default: str = '') -> str:
    return (getattr(settings, name, '') or os.environ.get(name, '') or default).strip()


def _linkedin_li_at() -> str:
    return _setting_or_env('LINKEDIN_LI_AT')


def _apify_actor_for(kind: str) -> str:
    defaults = {
        'instagram': 'apify/instagram-scraper',
        'facebook': 'apify/facebook-posts-scraper',
        'linkedin': 'simpleapi/linkedin-post-scraper',
        'twitter': 'apidojo/tweet-scraper',
        'tiktok': 'clockworks/tiktok-scraper',
    }
    env_names = {
        'instagram': 'APIFY_INSTAGRAM_ACTOR',
        'facebook': 'APIFY_FACEBOOK_ACTOR',
        'linkedin': 'APIFY_LINKEDIN_ACTOR',
        'twitter': 'APIFY_TWITTER_ACTOR',
        'tiktok': 'APIFY_TIKTOK_ACTOR',
    }
    return _setting_or_env(env_names[kind], defaults[kind])


def _apify_transcript_actor_for(kind: str) -> str:
    defaults = {
        'youtube': 'automation-lab/youtube-transcript',
        'instagram': 'khadinakbar/instagram-transcript-scraper',
        'tiktok': 'clockworks/tiktok-transcript-extractor',
    }
    env_names = {
        'youtube': 'APIFY_YOUTUBE_TRANSCRIPT_ACTOR',
        'instagram': 'APIFY_INSTAGRAM_TRANSCRIPT_ACTOR',
        'tiktok': 'APIFY_TIKTOK_TRANSCRIPT_ACTOR',
    }
    if kind not in defaults:
        return ''
    return _setting_or_env(env_names[kind], defaults[kind])


def _run_apify_actor(
    actor: str,
    run_input: dict[str, Any],
    *,
    timeout: float = APIFY_TIMEOUT,
) -> list[Any]:
    token = _apify_token()
    if not token:
        raise RuntimeError('APIFY_TOKEN is not configured')
    actor_id = actor.replace('/', '~')
    endpoint = f'https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items'
    resp = requests.post(
        endpoint,
        params={'token': token},
        json=run_input,
        headers={'Content-Type': 'application/json', 'User-Agent': USER_AGENT},
        timeout=timeout,
    )
    if resp.status_code >= 400:
        raise RuntimeError(
            f'Apify actor {actor} failed ({resp.status_code}): {resp.text[:400]}'
        )
    try:
        items = resp.json()
    except ValueError as exc:
        raise RuntimeError('Apify returned non-JSON response') from exc
    if not isinstance(items, list):
        raise RuntimeError('Unexpected Apify response shape')
    return items


def _maybe_resolve_short_link(url: str) -> str:
    host = _hostname(url)
    if host not in _SHORT_LINK_HOSTS:
        return url
    try:
        resp = requests.get(
            url,
            headers={'User-Agent': USER_AGENT},
            timeout=REDIRECT_TIMEOUT,
            allow_redirects=True,
        )
        final = resp.url or url
        if _is_safe_to_fetch(final):
            return final
    except Exception as exc:  # noqa: BLE001
        logger.info('short-link resolve failed %s: %s', url, exc)
    return url


def _apify_run_input(kind: str, url: str) -> dict[str, Any]:
    if kind == 'instagram':
        path = urlparse(url).path or ''
        limit = 1 if _IG_POST_PATH_RE.match(path) else 5
        return {
            'directUrls': [url],
            'resultsType': 'posts',
            'resultsLimit': limit,
        }
    if kind == 'facebook':
        return {
            'startUrls': [{'url': url}],
            'resultsLimit': 5,
        }
    if kind == 'linkedin':
        payload: dict[str, Any] = {
            'postUrls': [url],
            'maxPostsPerSource': 3,
            'includeComments': True,
            'maxCommentsPerPost': 15,
            'crawlLinkedPosts': False,
        }
        cookie = _linkedin_li_at()
        if cookie:
            payload['li_at'] = cookie
        return payload
    if kind == 'twitter':
        return {
            'startUrls': [url],
            'maxItems': 15,
        }
    if kind == 'tiktok':
        return {
            'postURLs': [url],
            'resultsPerPage': 1,
        }
    raise RuntimeError(f'Unsupported Apify kind: {kind}')


def _fetch_apify_social(url: str, kind: str, base: dict[str, Any]) -> dict[str, Any]:
    token = _apify_token()
    if not token:
        base['error'] = 'APIFY_TOKEN is not configured'
        return base

    resolved = _maybe_resolve_short_link(url)
    # Re-classify after short-link hop (lnkd.in → linkedin.com, t.co → x.com, …).
    resolved_kind = apify_source_for_url(resolved) or kind
    base['kind'] = resolved_kind
    if resolved != url:
        base['meta'] = {**(base.get('meta') or {}), 'resolved_url': resolved}

    if resolved_kind == 'linkedin' and not _linkedin_li_at():
        logger.info('LinkedIn enrich without LINKEDIN_LI_AT for %s', resolved)

    actor = _apify_actor_for(resolved_kind)
    run_input = _apify_run_input(resolved_kind, resolved)
    try:
        items = _run_apify_actor(actor, run_input, timeout=APIFY_TIMEOUT)
    except Exception as exc:  # noqa: BLE001
        # TikTok: metadata scrape may fail while transcript still works.
        if resolved_kind == 'tiktok':
            base['error'] = str(exc)[:300]
            base['meta'] = {**(base.get('meta') or {}), 'actor': actor}
            return base
        raise

    if not items:
        hint = ''
        if resolved_kind == 'linkedin' and not _linkedin_li_at():
            hint = (
                ' Set LINKEDIN_LI_AT (browser cookie while logged into LinkedIn) '
                'for group/private posts.'
            )
        base['error'] = f'Apify returned no {resolved_kind} data for this URL.{hint}'
        base['meta'] = {
            **(base.get('meta') or {}),
            'actor': actor,
            'needs_linkedin_cookie': resolved_kind == 'linkedin'
            and not _linkedin_li_at(),
        }
        return base

    text = _format_apify_items(resolved_kind, items)
    if not text.strip():
        base['error'] = f'Apify returned {resolved_kind} items without usable text'
        base['meta'] = {
            **(base.get('meta') or {}),
            'actor': actor,
            'item_count': len(items),
        }
        return base

    base['ok'] = True
    base['content'] = text[:MAX_APIFY_CHARS]
    base['meta'] = {
        **(base.get('meta') or {}),
        'actor': actor,
        'item_count': len(items),
        'truncated': len(text) > MAX_APIFY_CHARS,
        'used_linkedin_cookie': bool(
            resolved_kind == 'linkedin' and _linkedin_li_at()
        ),
    }
    return base


def _instagram_looks_like_video(url: str) -> bool:
    path = urlparse(url).path or ''
    return bool(_IG_POST_PATH_RE.match(path))


def _transcript_run_input(kind: str, url: str) -> dict[str, Any]:
    if kind == 'youtube':
        return {
            'urls': [url],
            'language': 'en',
            'mergeSegments': True,
        }
    if kind == 'instagram':
        return {'instagramUrls': [url]}
    if kind == 'tiktok':
        return {
            'postURLs': [url],
            'downloadSubtitlesOptions': (
                'DOWNLOAD_AND_TRANSCRIBE_VIDEOS_WITHOUT_SUBTITLES'
            ),
        }
    raise RuntimeError(f'No transcript actor input for kind={kind}')


def _extract_transcript_text(items: list[Any]) -> str:
    """Pull plain transcript text from heterogeneous Apify transcript actors."""
    parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get('success') is False and not _item_main_text(item):
            note = item.get('error') or item.get('message') or 'no transcript'
            parts.append(f'[Transcript unavailable: {note}]')
            continue
        for key in (
            'fullText',
            'transcript',
            'transcriptText',
            'text',
            'captions',
            'subtitleText',
            'srt',
        ):
            val = item.get(key)
            if isinstance(val, str) and val.strip():
                parts.append(val.strip())
                break
            if isinstance(val, list) and val:
                # segments: [{text, start, ...}] or list of strings
                segs = []
                for seg in val:
                    if isinstance(seg, dict):
                        t = (seg.get('text') or seg.get('transcript') or '').strip()
                        if t:
                            segs.append(t)
                    elif seg:
                        segs.append(str(seg).strip())
                if segs:
                    parts.append(' '.join(segs))
                    break
        else:
            # Nested transcriptItems (Instagram carousel parts)
            nested = item.get('transcriptItems') or item.get('segments') or []
            if isinstance(nested, list) and nested:
                segs = []
                for seg in nested:
                    if isinstance(seg, dict):
                        t = (seg.get('text') or seg.get('transcript') or '').strip()
                        if t:
                            segs.append(t)
                if segs:
                    parts.append('\n\n'.join(segs))
    # Prefer real transcripts over "unavailable" notes when mixed.
    real = [p for p in parts if not p.startswith('[Transcript unavailable')]
    return '\n\n'.join(real or parts).strip()


def _attach_apify_transcript(
    url: str, kind: str, result: dict[str, Any]
) -> dict[str, Any]:
    """Fetch spoken transcript via Apify and append to enrichment content."""
    resolved = (result.get('meta') or {}).get('resolved_url') or url
    if kind == 'instagram' and not _instagram_looks_like_video(resolved):
        return result

    actor = _apify_transcript_actor_for(kind)
    if not actor or not _apify_token():
        return result

    try:
        items = _run_apify_actor(
            actor,
            _transcript_run_input(kind, resolved),
            timeout=APIFY_TRANSCRIPT_TIMEOUT,
        )
        transcript = _extract_transcript_text(items)[:MAX_TRANSCRIPT_ENRICH_CHARS]
    except Exception as exc:  # noqa: BLE001
        logger.info('Apify transcript failed kind=%s url=%s: %s', kind, resolved, exc)
        meta = dict(result.get('meta') or {})
        meta['transcript_error'] = str(exc)[:300]
        meta['transcript_actor'] = actor
        result['meta'] = meta
        # TikTok with no metadata but we tried transcript — keep prior error.
        return result

    meta = dict(result.get('meta') or {})
    meta['transcript_actor'] = actor
    meta['has_transcript'] = bool(transcript)
    result['meta'] = meta

    if not transcript:
        return result

    result['transcript'] = transcript
    existing = (result.get('content') or '').strip()
    # Keep a (possibly capped) copy in content for the LLM block; full text is in
    # result['transcript'] and is appended to EmailSummary.details after summarize.
    block = f'Transcript:\n{transcript[:MAX_TRANSCRIPT_ENRICH_CHARS]}'
    if existing:
        result['content'] = f'{existing}\n\n{block}'[
            : MAX_APIFY_CHARS + MAX_TRANSCRIPT_ENRICH_CHARS
        ]
    else:
        result['content'] = block
        result['ok'] = True
        result['error'] = ''
    return result


def _format_apify_items(kind: str, items: list[Any]) -> str:
    chunks: list[str] = []
    for i, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        if item.get('error') and not _item_has_text(item):
            chunks.append(f'Item {i}: error — {item.get("error")}')
            continue
        lines: list[str] = [f'{kind.title()} item {i}']
        owner = (
            item.get('ownerUsername')
            or item.get('username')
            or item.get('userName')
            or item.get('authorName')
            or item.get('author')
            or item.get('pageName')
            or item.get('ownerFullName')
            or ''
        )
        if isinstance(owner, dict):
            owner = (
                owner.get('name')
                or owner.get('username')
                or owner.get('userName')
                or ''
            )
        if owner:
            lines.append(f'Author: {owner}')
        for label, key in (
            ('Name', 'ownerFullName'),
            ('Name', 'fullName'),
            ('Headline', 'authorHeadline'),
            ('Type', 'type'),
            ('Type', 'productType'),
        ):
            val = item.get(key)
            if val and str(val) != str(owner):
                lines.append(f'{label}: {val}')
                break
        post_url = (
            item.get('url')
            or item.get('postUrl')
            or item.get('inputUrl')
            or item.get('webUrl')
        )
        if post_url:
            lines.append(f'URL: {post_url}')
        for label, key in (
            ('Date', 'timestamp'),
            ('Date', 'takenAtTimestamp'),
            ('Date', 'time'),
            ('Date', 'createdAt'),
            ('Date', 'postedAtISO'),
            ('Date', 'date'),
        ):
            if item.get(key) is not None:
                lines.append(f'{label}: {item[key]}')
                break
        for label, key in (
            ('Likes', 'likesCount'),
            ('Likes', 'likeCount'),
            ('Reactions', 'reactionsCount'),
            ('Comments', 'commentsCount'),
            ('Comments', 'commentCount'),
            ('Shares', 'sharesCount'),
            ('Shares', 'shareCount'),
            ('Reposts', 'retweetCount'),
            ('Views', 'videoViewCount'),
            ('Views', 'viewCount'),
            ('Plays', 'videoPlayCount'),
            ('Followers', 'followersCount'),
            ('Following', 'followsCount'),
            ('Posts', 'postsCount'),
        ):
            if item.get(key) is not None:
                lines.append(f'{label}: {item[key]}')
        caption = _item_main_text(item)
        if caption:
            lines.append('')
            lines.append(caption)
        hashtags = item.get('hashtags') or []
        if isinstance(hashtags, list) and hashtags:
            tags = ' '.join(f'#{str(t).lstrip("#")}' for t in hashtags[:30] if t)
            if tags:
                lines.append(f'Hashtags: {tags}')
        mentions = item.get('mentions') or []
        if isinstance(mentions, list) and mentions:
            mens = ' '.join(f'@{str(m).lstrip("@")}' for m in mentions[:20] if m)
            if mens:
                lines.append(f'Mentions: {mens}')
        first = item.get('firstComment') or ''
        if first:
            lines.append(f'First comment: {str(first).strip()[:300]}')
        latest = item.get('latestComments') or item.get('comments') or []
        if isinstance(latest, list) and latest:
            comment_bits = []
            for c in latest[:5]:
                if isinstance(c, dict):
                    t = (
                        c.get('text') or c.get('commentText') or c.get('message') or ''
                    ).strip()
                    u = (
                        c.get('ownerUsername')
                        or c.get('username')
                        or c.get('authorName')
                        or ''
                    )
                    if t:
                        comment_bits.append(f'@{u}: {t}' if u else t)
                elif c:
                    comment_bits.append(str(c))
            if comment_bits:
                lines.append('Recent comments:')
                lines.extend(f'- {b[:300]}' for b in comment_bits)
        chunks.append('\n'.join(lines))
    return '\n\n'.join(chunks)


def _item_main_text(item: dict[str, Any]) -> str:
    for key in (
        'caption',
        'text',
        'fullText',
        'message',
        'postText',
        'content',
        'description',
        'biography',
        'title',
    ):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ''


def _item_has_text(item: dict[str, Any]) -> bool:
    return bool(_item_main_text(item) or item.get('username') or item.get('url'))


def _fetch_youtube(url: str, base: dict[str, Any]) -> dict[str, Any]:
    video_id = youtube_video_id(url)
    if not video_id:
        base['error'] = 'Could not parse YouTube video id'
        return base

    transcript = ''
    source = ''
    # Prefer Apify transcript scraper when configured.
    if _apify_token():
        actor = _apify_transcript_actor_for('youtube')
        try:
            items = _run_apify_actor(
                actor,
                _transcript_run_input('youtube', url),
                timeout=APIFY_TRANSCRIPT_TIMEOUT,
            )
            transcript = _extract_transcript_text(items)
            source = actor
        except Exception as exc:  # noqa: BLE001
            logger.info('Apify YouTube transcript failed, falling back: %s', exc)
            base['meta'] = {
                **(base.get('meta') or {}),
                'transcript_actor_error': str(exc)[:300],
            }

    if not transcript:
        try:
            transcript = _youtube_transcript_local(video_id)
            source = source or 'youtube-transcript-api'
        except Exception as exc:  # noqa: BLE001
            if not transcript:
                base['error'] = f'No transcript available ({exc})'[:300]
                base['meta'] = {
                    **(base.get('meta') or {}),
                    'video_id': video_id,
                }
                return base

    if not transcript:
        base['error'] = 'No transcript available'
        base['meta'] = {**(base.get('meta') or {}), 'video_id': video_id}
        return base

    base['ok'] = True
    base['transcript'] = transcript
    base['content'] = f'Transcript:\n{transcript[:MAX_TRANSCRIPT_CHARS]}'
    base['meta'] = {
        **(base.get('meta') or {}),
        'video_id': video_id,
        'transcript_source': source,
        'has_transcript': True,
        'truncated': len(transcript) > MAX_TRANSCRIPT_CHARS,
    }
    return base


def collect_full_transcripts(enrichments: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Return [{kind, url, text}] for enrichments that have a full transcript."""
    out: list[dict[str, str]] = []
    for enr in enrichments or []:
        text = (enr.get('transcript') or '').strip()
        if not text:
            content = enr.get('content') or ''
            marker = '\nTranscript:\n'
            if content.startswith('Transcript:\n'):
                text = content[len('Transcript:\n') :].strip()
            elif marker in content:
                text = content.split(marker, 1)[1].strip()
        if not text:
            continue
        out.append(
            {
                'kind': str(enr.get('kind') or 'video'),
                'url': str(enr.get('url') or ''),
                'text': text,
            }
        )
    return out


def append_full_transcripts_to_details(
    details: str, enrichments: list[dict[str, Any]]
) -> str:
    """Ensure EmailSummary.details includes verbatim full transcripts.

    Uses plain-text section markers (not Markdown/HTML). The Gmail UI renders
    details via linkifyHtml (escaped text + autolinks), so Markdown headings
    would otherwise show as literal "## …".
    """
    transcripts = collect_full_transcripts(enrichments)
    if not transcripts:
        return (details or '').strip()

    body = (details or '').strip()
    # Avoid double-append if task is retried / details already has our section.
    if 'Full transcript(s)' in body:
        return body

    rule = '─' * 40
    parts = [body] if body else []
    parts.append(f'{rule}\nFull transcript(s)\n{rule}')
    for i, item in enumerate(transcripts, start=1):
        label = item['kind'].title()
        header_lines = [f'{i}. {label}']
        if item['url']:
            header_lines.append(item['url'])
        parts.append('\n'.join(header_lines))
        parts.append(item['text'])
    return '\n\n'.join(parts).strip()


def _youtube_transcript_local(video_id: str) -> str:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        raise RuntimeError(
            'youtube-transcript-api is not installed on the worker'
        ) from exc

    try:
        api = YouTubeTranscriptApi()
        fetched = api.fetch(video_id)
        parts = [getattr(s, 'text', None) or s.get('text', '') for s in fetched]
        return ' '.join(p for p in parts if p).strip()
    except Exception:
        pass
    try:
        rows = YouTubeTranscriptApi.get_transcript(video_id)  # type: ignore[attr-defined]
        return ' '.join(r.get('text', '') for r in rows).strip()
    except Exception as exc:
        raise RuntimeError(f'Transcript fetch failed: {exc}') from exc


def _html_to_readable(raw_html: str, *, base_url: str = '') -> str:  # noqa: ARG001
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return gmail_api.html_to_text(raw_html)

    soup = BeautifulSoup(raw_html or '', 'html.parser')
    for tag in soup(['script', 'style', 'noscript', 'svg', 'iframe']):
        tag.decompose()
    title = ''
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    root = soup.find('article') or soup.find('main') or soup.body or soup
    text = root.get_text('\n', strip=True) if root else ''
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    if title and title.lower() not in text[:200].lower():
        text = f'{title}\n\n{text}'
    return text


def _format_enrichment_block(
    message: dict[str, Any], enrichments: list[dict[str, Any]]
) -> str:
    lines = [
        '===== EMAIL =====',
        f"From: {message.get('from_addr') or ''}",
        f"Subject: {message.get('subject') or ''}",
        f"Date: {message.get('date_iso') or ''}",
        '',
        (message.get('body_text') or message.get('snippet') or '').strip(),
        '',
        '===== LINKED CONTENT =====',
    ]
    if not enrichments:
        lines.append('(No URLs found in this email.)')
        return '\n'.join(lines)

    for i, item in enumerate(enrichments, start=1):
        lines.append(f'--- Link {i} ({item.get("kind")}) ---')
        lines.append(f'URL: {item.get("url")}')
        if item.get('ok'):
            meta = item.get('meta') or {}
            if meta.get('video_id'):
                lines.append(f'YouTube video id: {meta["video_id"]}')
            if meta.get('actor'):
                lines.append(f'Apify actor: {meta["actor"]}')
            if meta.get('resolved_url'):
                lines.append(f'Resolved URL: {meta["resolved_url"]}')
            if meta.get('downloaded'):
                dims = (
                    f' ({meta.get("width")}x{meta.get("height")})'
                    if meta.get('width')
                    else ''
                )
                lines.append(f'Image: downloaded {meta.get("bytes", 0)} bytes{dims}')
            lines.append('')
            lines.append(item.get('content') or '')
        else:
            lines.append(f'Fetch failed: {item.get("error") or "unknown error"}')
        lines.append('')
    return '\n'.join(lines)


DEFAULT_ENRICH_PROMPT = (
    'For each email below, summarize the email and any successfully fetched linked '
    'content (web pages, YouTube/Instagram/TikTok transcripts via Apify, social posts '
    'from Instagram/Facebook/LinkedIn/X/TikTok, image descriptions). '
    'Clearly separate what came from the email body vs linked content. '
    'If a link failed to fetch, mention it briefly. '
    'Do not invent facts that are not in the provided material.'
)
