"""Create Notes pages from dropped URLs or text (YouTube, public web, plain text)."""

from __future__ import annotations

import ipaddress
import json
import logging
import re
import socket
from html.parser import HTMLParser
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils.text import slugify

from .models import MenuItem, NoteNode, Page

logger = logging.getLogger(__name__)

TEMP_FOLDER_TITLE = '_Temp'
USER_AGENT = 'devenkalra-notes-capture/1.0'
FETCH_TIMEOUT = 20
MAX_WEB_CHARS = 12_000
MAX_TRANSCRIPT_CHARS = 80_000
MAX_LLM_CHARS = 40_000

_YT_ID_RE = re.compile(
    r'(?:youtu\.be/|youtube(?:-nocookie)?\.com/(?:watch\?(?:[^#]*&)?v=|embed/|v/|shorts/|live/))'
    r'([A-Za-z0-9_-]{11})',
    re.IGNORECASE,
)
_URL_RE = re.compile(r'https?://[^\s<>\"\']+', re.IGNORECASE)
_PRIVATE_NETS = (
    ipaddress.ip_network('127.0.0.0/8'),
    ipaddress.ip_network('10.0.0.0/8'),
    ipaddress.ip_network('172.16.0.0/12'),
    ipaddress.ip_network('192.168.0.0/16'),
    ipaddress.ip_network('169.254.0.0/16'),
    ipaddress.ip_network('::1/128'),
    ipaddress.ip_network('fc00::/7'),
)


class _TitleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._in_title = False
        self.title = ''

    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'title':
            self._in_title = True

    def handle_endtag(self, tag):
        if tag.lower() == 'title':
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def youtube_video_id(url: str) -> str | None:
    match = _YT_ID_RE.search(url or '')
    return match.group(1) if match else None


def first_url(text: str) -> str | None:
    match = _URL_RE.search(text or '')
    if not match:
        return None
    url = match.group(0).rstrip(').,;]>\'\"')
    return url or None


def ensure_temp_folder() -> NoteNode:
    folder = NoteNode.objects.filter(
        title=TEMP_FOLDER_TITLE,
        parent__isnull=True,
        page__isnull=True,
    ).first()
    if folder:
        return folder
    return NoteNode.objects.create(
        title=TEMP_FOLDER_TITLE,
        parent=None,
        page=None,
        order=0,
    )


def ensure_notes_shell() -> Page:
    """Create the Notes CMS page and Notebook → Notes menu if they are missing."""
    page, _ = Page.objects.get_or_create(
        slug='notes',
        defaults={
            'title': 'Notes',
            'category': 'Notebook',
            'content': (
                '# Notes\n\n'
                'Browse selected pages in a multi-level folder tree. '
                'Use the left panel to navigate folders and pages; '
                'the right panel shows a live preview.\n'
            ),
            'roles_with_access': '',
        },
    )
    notebook, _ = MenuItem.objects.get_or_create(
        title='Notebook',
        parent=None,
        defaults={'page': None, 'order': 5, 'show_in_menu': True},
    )
    notes_menu = MenuItem.objects.filter(title='Notes', parent=notebook).order_by('id').first()
    if notes_menu is None:
        MenuItem.objects.create(
            title='Notes',
            parent=notebook,
            page=page,
            order=1,
            show_in_menu=True,
        )
    elif notes_menu.page_id != page.id:
        notes_menu.page = page
        notes_menu.save(update_fields=['page'])
    return page


def unique_slug(title: str) -> str:
    base = slugify(title)[:80] or 'note'
    slug = base
    n = 2
    while Page.objects.filter(slug=slug).exists():
        slug = f'{base}-{n}'[:200]
        n += 1
    return slug


def _emit(on_progress, message: str) -> None:
    if on_progress:
        on_progress(message)


def capture_dropped(*, text: str = '', url: str = '', on_progress=None) -> dict:
    """Classify dropped content and create a Page + NoteNode under _Temp."""
    raw_text = (text or '').strip()
    raw_url = (url or '').strip() or first_url(raw_text) or ''
    if not raw_text and not raw_url:
        raise ValueError('Drop some text or a URL to create a note.')

    _emit(on_progress, 'Looking at dropped content…')
    if raw_url and youtube_video_id(raw_url):
        title, content, kind = _build_youtube_note(raw_url, on_progress=on_progress)
    elif raw_url and _is_http_url(raw_url) and _looks_like_url_drop(raw_text, raw_url):
        title, content, kind = _build_web_note(raw_url, on_progress=on_progress)
    else:
        _emit(on_progress, 'Creating a text note…')
        title, content, kind = _build_text_note(raw_text or raw_url)

    _emit(on_progress, 'Saving note in _Temp…')
    page = Page.objects.create(
        title=title[:200],
        slug=unique_slug(title),
        category='Notebook',
        content=content,
        roles_with_access='',
        render_as_html=False,
    )
    folder = ensure_temp_folder()
    node = NoteNode.objects.create(
        title=page.title,
        parent=folder,
        page=page,
        order=0,
    )
    _emit(on_progress, 'Done')
    return {
        'kind': kind,
        'temp_folder_id': folder.id,
        'page': {
            'id': page.id,
            'title': page.title,
            'slug': page.slug,
            'content': page.content,
            'category': page.category,
            'render_as_html': page.render_as_html,
        },
        'node': {
            'id': node.id,
            'title': node.title,
            'parent': folder.id,
            'page': page.id,
            'page_slug': page.slug,
            'page_title': page.title,
            'is_folder': False,
            'order': node.order,
        },
    }


def _looks_like_url_drop(text: str, url: str) -> bool:
    """Treat as a URL drop when the payload is mostly just the URL (plus optional title)."""
    stripped = (text or '').strip()
    if not stripped or stripped == url:
        return True
    # Browser often drops "Title\nhttps://..."
    lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
    if len(lines) <= 2 and any(_is_http_url(ln) for ln in lines):
        return True
    return bool(re.fullmatch(r'https?://\S+', stripped, re.IGNORECASE))


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value or '')
    return parsed.scheme in ('http', 'https') and bool(parsed.netloc)


def _build_youtube_note(url: str, on_progress=None) -> tuple[str, str, str]:
    video_id = youtube_video_id(url)
    watch_url = f'https://www.youtube.com/watch?v={video_id}'
    _emit(on_progress, 'Fetching YouTube title…')
    title = _youtube_title(watch_url) or f'YouTube {video_id}'
    _emit(on_progress, f'Downloading transcript for “{title}”…')
    transcript = _youtube_transcript(video_id)
    if transcript:
        _emit(on_progress, 'Transcript downloaded; generating summary…')
    else:
        _emit(on_progress, 'No transcript available for this video')
    embed = (
        f'<iframe width="560" height="315" '
        f'src="https://www.youtube.com/embed/{video_id}" '
        f'title="{_escape_attr(title)}" frameborder="0" '
        f'referrerpolicy="strict-origin-when-cross-origin" '
        f'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" '
        f'allowfullscreen></iframe>'
    )
    processed = (
        _process_youtube_transcript(title, watch_url, transcript, on_progress=on_progress)
        if transcript
        else ''
    )
    body = processed or (
        '## Transcript\n\n'
        + (transcript or '_Transcript was not available for this video._')
    )
    parts = [
        f'# {title}',
        '',
        f'Source: [{watch_url}]({watch_url})',
        '',
        embed,
        '',
        body.strip(),
        '',
    ]
    return title, '\n'.join(parts).strip() + '\n', 'youtube'


def _build_web_note(url: str, on_progress=None) -> tuple[str, str, str]:
    _emit(on_progress, f'Fetching {urlparse(url).netloc or "page"}…')
    page_title, page_text = _fetch_web_page(url)
    title = page_title or urlparse(url).netloc or 'Web page'
    _emit(on_progress, f'Summarizing “{title}”…')
    summary = _summarize_page(title, url, page_text, on_progress=on_progress)
    if not summary:
        excerpt = (page_text or '').strip()
        summary = excerpt[:4000] if excerpt else '_Could not fetch a summary for this page._'
        _emit(on_progress, 'Using a page excerpt (no LLM summary)')
    content = '\n'.join(
        [
            f'# {title}',
            '',
            f'Source: [{url}]({url})',
            '',
            '## Summary',
            '',
            summary.strip(),
            '',
        ]
    )
    return title, content, 'web'


def _build_text_note(text: str) -> tuple[str, str, str]:
    first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), 'Dropped note')
    title = first_line[:80]
    if len(first_line) > 80:
        title = title.rstrip() + '…'
    content = f'# {title}\n\n{text.strip()}\n'
    return title, content, 'text'


def _youtube_title(watch_url: str) -> str:
    oembed = f'https://www.youtube.com/oembed?url={quote(watch_url, safe="")}&format=json'
    try:
        raw = _http_get(oembed, timeout=10)
        data = json.loads(raw.decode('utf-8', errors='replace'))
        return (data.get('title') or '').strip()
    except Exception as exc:  # noqa: BLE001
        logger.info('YouTube oEmbed failed: %s', exc)
        return ''


def _youtube_transcript(video_id: str) -> str:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        logger.warning('youtube-transcript-api is not installed')
        return ''

    api = YouTubeTranscriptApi()
    fetched = None
    try:
        fetched = api.fetch(video_id, languages=['en', 'en-US', 'en-GB', 'en-IN'])
    except Exception as exc:  # noqa: BLE001
        logger.info('YouTube transcript fetch() failed: %s', exc)

    if fetched is None:
        try:
            transcript_list = api.list(video_id)
            transcript = None
            try:
                transcript = transcript_list.find_transcript(['en', 'en-US', 'en-GB', 'en-IN'])
            except Exception:
                transcript = next(iter(transcript_list), None)
            if transcript is None:
                return ''
            if (
                getattr(transcript, 'language_code', '').split('-')[0] != 'en'
                and getattr(transcript, 'is_translatable', False)
            ):
                try:
                    transcript = transcript.translate('en')
                except Exception as exc:  # noqa: BLE001
                    logger.info('YouTube transcript translate failed: %s', exc)
            fetched = transcript.fetch()
        except Exception as exc:  # noqa: BLE001
            logger.warning('YouTube transcript list/fetch failed for %s: %s', video_id, exc)
            return ''

    parts = [
        getattr(s, 'text', None) or (s.get('text') if isinstance(s, dict) else '')
        for s in fetched
    ]
    text = ' '.join(p.replace('\n', ' ') for p in parts if p).strip()
    return text[:MAX_TRANSCRIPT_CHARS]


def _fetch_web_page(url: str) -> tuple[str, str]:
    _assert_public_url(url)
    raw = _http_get(url)
    html = raw.decode('utf-8', errors='replace')
    title = ''
    try:
        parser = _TitleParser()
        parser.feed(html)
        title = re.sub(r'\s+', ' ', parser.title).strip()
    except Exception:  # noqa: BLE001
        title = ''

    text = html
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup(['script', 'style', 'noscript', 'svg', 'iframe']):
            tag.decompose()
        if not title and soup.title and soup.title.string:
            title = soup.title.string.strip()
        root = soup.find('article') or soup.find('main') or soup.body or soup
        text = root.get_text('\n', strip=True) if root else ''
    except Exception:  # noqa: BLE001
        text = re.sub(r'<[^>]+>', ' ', html)

    text = re.sub(r'\n{3,}', '\n\n', text).strip()[:MAX_WEB_CHARS]
    return title, text


def _process_youtube_transcript(title: str, url: str, transcript: str, on_progress=None) -> str:
    """Turn a raw caption dump into summary, key points, and a readable transcript."""
    source = (transcript or '').strip()
    if not source:
        return ''
    markdown = _openai_chat(
        system=(
            'You write personal notebook entries from YouTube transcripts. '
            'Return GitHub-flavored markdown only, with exactly these headings in this order:\n\n'
            '## Summary\n'
            '## Key points\n'
            '## Transcript\n\n'
            'Rules:\n'
            '- Summary: 2–4 short paragraphs covering what the video is about and the main takeaway.\n'
            '- Key points: a bullet list of the most important facts, claims, steps, or quotes. Be specific.\n'
            '- Transcript: a readable version of the captions. Add punctuation and paragraph breaks, '
            'use **Speaker:** labels when speakers are clear, drop filler (um, uh, you know) and stutters, '
            'and keep meaning and important quotes. Do not invent content.\n'
            '- Do not include a top-level title. Do not wrap the whole answer in a code fence.'
        ),
        user=f'Title: {title}\nURL: {url}\n\nTranscript:\n{source[:MAX_LLM_CHARS]}',
        temperature=0.2,
        on_progress=on_progress,
    )
    if not markdown:
        return ''
    markdown = markdown.strip()
    if markdown.startswith('```'):
        markdown = re.sub(r'^```(?:markdown|md)?\s*', '', markdown)
        markdown = re.sub(r'\s*```$', '', markdown).strip()
    if '## Summary' not in markdown and '## Transcript' not in markdown:
        return (
            '## Summary\n\n'
            f'{markdown}\n\n'
            '## Transcript\n\n'
            f'{source[:MAX_TRANSCRIPT_CHARS]}'
        )
    return markdown


def _summarize_page(title: str, url: str, page_text: str, on_progress=None) -> str:
    return _openai_chat(
        system=(
            'Summarize the web page for a personal notebook. '
            'Write 2–5 short paragraphs in markdown. Include key facts. '
            'Do not invent details that are not in the source.'
        ),
        user=f'Title: {title}\nURL: {url}\n\n{page_text[:8000]}',
        temperature=0.2,
        on_progress=on_progress,
    )


def _openai_chat(*, system: str, user: str, temperature: float = 0.2, on_progress=None) -> str:
    if not (user or '').strip():
        return ''
    messages = [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': user},
    ]
    local_url = (getattr(settings, 'LOCALAI_URL', '') or '').rstrip('/')
    if local_url:
        local_model = getattr(settings, 'LOCALAI_MODEL', 'qwen3-32b')
        _emit(on_progress, f'Asking LocalAI ({local_model})…')
        try:
            text = _chat_once(
                api_key=getattr(settings, 'LOCALAI_API_KEY', '') or 'local',
                base_url=_localai_base_url(local_url),
                model=local_model,
                messages=messages,
                temperature=temperature,
                timeout=60,
            )
            if text:
                logger.info('Note capture LLM used LocalAI')
                _emit(on_progress, 'LocalAI finished')
                return text
            logger.warning('LocalAI returned empty content; trying OpenAI')
            _emit(on_progress, 'LocalAI returned nothing; trying OpenAI…')
        except Exception as exc:  # noqa: BLE001
            logger.warning('LocalAI note capture failed, trying OpenAI: %s', exc)
            _emit(on_progress, 'LocalAI failed; trying OpenAI…')

    api_key = getattr(settings, 'EMAIL_OPENAI_API_KEY', '') or getattr(settings, 'OPENAI_API_KEY', '')
    if not api_key:
        _emit(on_progress, 'No OpenAI key configured; skipping summary')
        return ''
    openai_model = getattr(settings, 'EMAIL_OPENAI_MODEL', 'gpt-4.1-mini')
    _emit(on_progress, f'Asking OpenAI ({openai_model})…')
    try:
        text = _chat_once(
            api_key=api_key,
            base_url=None,
            model=openai_model,
            messages=messages,
            temperature=temperature,
            timeout=60,
        )
        if text:
            logger.info('Note capture LLM used OpenAI')
            _emit(on_progress, 'OpenAI finished')
        return text
    except Exception as exc:  # noqa: BLE001
        logger.warning('OpenAI note capture failed: %s', exc)
        _emit(on_progress, 'OpenAI failed')
        return ''


def _localai_base_url(url: str) -> str:
    url = (url or '').rstrip('/')
    if url.endswith('/v1'):
        return url
    return f'{url}/v1'


def _strip_think(text: str) -> str:
    cleaned = re.sub(r'<think>[\s\S]*?</think>', '', text or '', flags=re.IGNORECASE)
    return cleaned.strip()


def _chat_once(*, api_key: str, base_url: str | None, model: str, messages: list, temperature: float, timeout: int) -> str:
    from openai import OpenAI

    kwargs = {'api_key': api_key or 'local', 'timeout': timeout}
    if base_url:
        kwargs['base_url'] = base_url
    client = OpenAI(**kwargs)
    resp = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=messages,
    )
    return _strip_think((resp.choices[0].message.content or '').strip())


def _assert_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        raise ValueError('Only http(s) URLs can be captured.')
    host = parsed.hostname or ''
    if not host or host.lower() in ('localhost',):
        raise ValueError('That URL is not a public page.')
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise ValueError(f'Could not resolve host: {host}') from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if any(ip in net for net in _PRIVATE_NETS):
            raise ValueError('That URL is not a public page.')


def _http_get(url: str, timeout: int = FETCH_TIMEOUT) -> bytes:
    req = Request(url, headers={'User-Agent': USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read(2_000_000)


def _escape_attr(value: str) -> str:
    return (
        (value or '')
        .replace('&', '&amp;')
        .replace('"', '&quot;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
    )
