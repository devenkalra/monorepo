"""Create an entity from dropped text, HTML, URLs, or files."""

from __future__ import annotations

import html as html_lib
import ipaddress
import json
import mimetypes
import os
import re
import socket
from urllib.parse import unquote, urljoin, urlparse

import requests
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction

from .models import Asset, Book, Container, EntityRelation, Location, Movie, Note, Org, Person
from .serializers import (
    AssetSerializer,
    BookSerializer,
    ContainerSerializer,
    LocationSerializer,
    MovieSerializer,
    NoteSerializer,
    OrgSerializer,
    PersonSerializer,
)
from .utils import save_file_deduplicated


class DropIngestError(ValueError):
    pass


class DropSummary:
    def __init__(self):
        self.action = 'created'
        self.created = []
        self.reused = []
        self.relations = []
        self.photos = 0
        self.attachments = 0
        self.rebased = 0

    def created_entity(self, entity):
        self.action = 'created'
        self.created.append(_entity_ref(entity))

    def reused_entity(self, entity):
        self.action = 'reused'
        self.reused.append(_entity_ref(entity))

    def created_related(self, entity):
        self.created.append(_entity_ref(entity))

    def reused_related(self, entity):
        self.reused.append(_entity_ref(entity))

    def add_relation(self, relation_type, target, linked):
        self.relations.append({
            'relation_type': relation_type,
            'label': _relation_label(relation_type),
            'display': target.display or str(target.id),
            'linked': linked,
        })

    def as_dict(self):
        return {
            'action': self.action,
            'created': self.created,
            'reused': self.reused,
            'relations': self.relations,
            'photos': self.photos,
            'attachments': self.attachments,
            'rebased': self.rebased,
            'lines': self.lines(),
        }

    def lines(self):
        rows = []
        if self.action == 'reused' and self.reused:
            main = self.reused[0]
            rows.append(f'Reused existing {main["type"]} “{main["display"]}” instead of creating a duplicate.')
        for item in self.created:
            if self.action == 'created' and item == self.created[0]:
                rows.append(f'Created {item["type"]} “{item["display"]}”.')
            else:
                rows.append(f'Created related {item["type"]} “{item["display"]}”.')
        for item in self.reused[1 if self.action == 'reused' else 0:]:
            rows.append(f'Reused existing {item["type"]} “{item["display"]}”.')
        for rel in self.relations:
            verb = 'Linked' if rel['linked'] else 'Already linked'
            rows.append(f'{verb} {rel["display"]} as {rel["label"]}.')
        if self.photos:
            rows.append(f'Saved {self.photos} photo{"s" if self.photos != 1 else ""} locally.')
        if self.attachments:
            rows.append(f'Saved {self.attachments} document{"s" if self.attachments != 1 else ""} locally.')
        if self.rebased:
            rows.append(f'Rewrote {self.rebased} link{"s" if self.rebased != 1 else ""} to local copies.')
        return rows


def _entity_ref(entity):
    return {
        'id': str(entity.id),
        'type': entity.type,
        'display': entity.display or entity.type,
    }


def _relation_label(relation_type):
    from .constants import RELATION_SCHEMA
    for schema in RELATION_SCHEMA:
        if schema.get('key') == relation_type:
            return schema.get('name') or relation_type
    return relation_type.replace('_', ' ').title()


ENTITY_TYPES = (
    'Person', 'Note', 'Location', 'Movie', 'Book', 'Container', 'Asset', 'Org',
)
SERIALIZERS = {
    'Person': PersonSerializer,
    'Note': NoteSerializer,
    'Location': LocationSerializer,
    'Movie': MovieSerializer,
    'Book': BookSerializer,
    'Container': ContainerSerializer,
    'Asset': AssetSerializer,
    'Org': OrgSerializer,
}
RELATION_WHITELIST = {
    'HAS_DIRECTOR', 'HAS_ACTOR', 'HAS_MUS_DIRECTOR', 'HAS_AS_AUTHOR',
    'IS_RELATED_TO', 'LIVES_AT', 'WORKS_AT', 'IS_MEMBER_OF', 'IS_LOCATED_IN',
    'HAS', 'IS_CHILD_OF', 'IS_SPOUSE_OF', 'IS_FRIEND_OF', 'IS_COLLEAGUE_OF',
}
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg'}
DOC_EXTS = {
    '.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt', '.csv', '.xls', '.xlsx',
    '.ppt', '.pptx', '.md', '.epub',
}
IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp', 'image/svg+xml'}
MAX_DOWNLOAD_BYTES = 8_000_000
MAX_FILES = 12
MAX_URLS = 12
FETCH_TIMEOUT = 15
USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
)

_URL_RE = re.compile(r'https?://[^\s<>\"\']+', re.IGNORECASE)
_HREF_RE = re.compile(r'''href\s*=\s*["'](https?://[^"']+)["']''', re.IGNORECASE)
_SRC_RE = re.compile(r'''(?:src|data-src)\s*=\s*["'](https?://[^"']+)["']''', re.IGNORECASE)
_TITLE_RE = re.compile(r'<title[^>]*>(.*?)</title>', re.IGNORECASE | re.DOTALL)
_OG_IMAGE_RE = re.compile(
    r'''<meta[^>]+property=["']og:image["'][^>]+content=["']([^"']+)["']''',
    re.IGNORECASE,
)
_OG_TITLE_RE = re.compile(
    r'''<meta[^>]+property=["']og:title["'][^>]+content=["']([^"']+)["']''',
    re.IGNORECASE,
)
_OG_DESC_RE = re.compile(
    r'''<meta[^>]+property=["']og:description["'][^>]+content=["']([^"']+)["']''',
    re.IGNORECASE,
)
_DIRECTOR_RE = re.compile(r'(?:directed by|director)\s*[:\-]?\s*', re.IGNORECASE)
_AUTHOR_RE = re.compile(r'(?:written by|author)\s*[:\-]?\s*', re.IGNORECASE)
_NAME_PARTICLES = {'van', 'von', 'de', 'del', 'di', 'da', 'la', 'le', 'bin', 'al', 'jr', 'sr', 'ii', 'iii', 'iv'}
_EMAIL_RE = re.compile(r'[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}', re.IGNORECASE)
_PHONE_RE = re.compile(r'(?:\+?\d[\d\-\s().]{7,}\d)')
_YEAR_RE = re.compile(r'\b((?:19|20)\d{2})\b')
_WEAK_DISPLAYS = {
    'dropped item', 'untitled movie', 'untitled book', 'untitled container',
    'untitled organization', 'untitled asset', 'note', 'person', 'image', 'document',
}
ENTITY_MODELS = {
    'Person': Person,
    'Note': Note,
    'Location': Location,
    'Movie': Movie,
    'Book': Book,
    'Container': Container,
    'Asset': Asset,
    'Org': Org,
}


def ingest_drop(request):
    payload = _request_payload(request)
    if not payload['text'] and not payload['html'] and not payload['url'] and not payload['files']:
        raise DropIngestError('Drop text, a link, or a file to create an entity.')

    media = _collect_media(payload)
    parsed = _parse_content(payload, media, forced_type=payload.get('forced_type'))
    description = _rebase_description(parsed.get('description') or '', media['url_map'])
    photos = list(media['photos'])
    attachments = list(media['attachments'])
    photos.extend(parsed.get('extra_photos') or [])
    attachments.extend(parsed.get('extra_attachments') or [])
    photos, attachments = _dedupe_media(photos), _dedupe_media(attachments)

    entity_data = _entity_payload(parsed, description, photos, attachments, media['source_urls'])
    summary = DropSummary()
    summary.photos = len(photos)
    summary.attachments = len(attachments)
    summary.rebased = len(media.get('url_map') or {})
    with transaction.atomic():
        entity, created = _get_or_create_main(request.user, entity_data, request)
        if created:
            summary.created_entity(entity)
        else:
            summary.reused_entity(entity)
        _create_relations(request.user, entity, parsed.get('relations') or [], request, summary)
    return entity, summary.as_dict()


def _request_payload(request):
    data = request.data if hasattr(request, 'data') else {}
    files = []
    if hasattr(request, 'FILES'):
        files = list(request.FILES.getlist('files')) + list(request.FILES.getlist('file'))
    text = str(data.get('text') or '').strip()
    html = str(data.get('html') or '').strip()
    url = str(data.get('url') or '').strip()
    extra_text = []
    kept_files = []
    for uploaded in files[:MAX_FILES]:
        name = (getattr(uploaded, 'name', '') or '').lower()
        if name.endswith(('.txt', '.md', '.html', '.htm', '.csv', '.json')):
            try:
                raw = uploaded.read()
                uploaded.seek(0)
                extra_text.append(raw.decode('utf-8', errors='replace')[:20_000])
            except Exception:
                pass
        kept_files.append(uploaded)
    if extra_text:
        text = '\n\n'.join([part for part in [text, *extra_text] if part]).strip()
    return {
        'text': text,
        'html': html,
        'url': url,
        'files': kept_files,
        'forced_type': _resolve_forced_type(data.get('type') or data.get('entity_type')),
    }


def _collect_media(payload):
    photos = []
    attachments = []
    url_map = {}
    source_urls = []

    for uploaded in payload['files']:
        saved = _save_upload(uploaded)
        if not saved:
            continue
        if _is_image_name(uploaded.name) or _is_image_type(getattr(uploaded, 'content_type', '')):
            photos.append(saved)
        else:
            attachments.append(saved)

    found_urls = _extract_urls(payload['text'], payload['html'], payload['url'])
    page_bits = []
    for url in found_urls:
        kind = _url_kind(url)
        if kind == 'page':
            source_urls.append(url)
            meta = _fetch_page_meta(url)
            if meta:
                page_bits.append(meta['text'])
                for image_url in meta.get('images') or []:
                    if image_url not in found_urls:
                        found_urls.append(image_url)
        elif kind in ('image', 'document'):
            saved = _download_media(url, kind)
            if not saved:
                continue
            url_map[url] = saved['url']
            if kind == 'image':
                photos.append(saved)
            else:
                attachments.append(saved)
        if len(url_map) + len(photos) + len(attachments) >= MAX_URLS + MAX_FILES:
            break

    if page_bits:
        payload['text'] = '\n\n'.join([part for part in [payload['text'], *page_bits] if part]).strip()
    return {
        'photos': photos,
        'attachments': attachments,
        'url_map': url_map,
        'source_urls': source_urls or ([payload['url']] if payload['url'] else []),
    }


def _parse_content(payload, media, forced_type=None):
    heuristic = _heuristic_parse(payload, media, forced_type=forced_type)
    llm_data = llm_parse(payload, media, heuristic, forced_type=forced_type)
    if not llm_data:
        if not forced_type:
            heuristic['type'] = _coerce_type_from_relations(heuristic['type'], heuristic.get('relations') or [])
        heuristic['relations'] = _normalize_relations(heuristic.get('relations') or [], heuristic['type'])
        return heuristic
    merged = dict(heuristic)
    for key, value in llm_data.items():
        if value in (None, '', [], {}):
            continue
        merged[key] = value
    if forced_type:
        merged['type'] = forced_type
    else:
        merged['type'] = _normalize_type(merged.get('type') or heuristic.get('type'))
        merged['type'] = _coerce_type_from_relations(merged['type'], merged.get('relations') or [])
    merged['relations'] = _normalize_relations(merged.get('relations') or [], merged['type'])
    return merged


def llm_available():
    try:
        from productions.llm import llm_available as _available
        return _available()
    except Exception:
        return False


def llm_parse(payload, media, heuristic, forced_type=None):
    if not llm_available():
        return {}
    try:
        from productions.llm import chat_completion
        raw = chat_completion(
            prompt=_user_prompt(payload, media, heuristic, forced_type=forced_type),
            system=_system_prompt(forced_type),
            json_mode=True,
            temperature=0.2,
            timeout=45.0,
        )
        data = _extract_json(raw)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return _normalize_llm_fields(data)


_JSON_SHAPE = """Return JSON only:
{
  "type": "Person" | "Note" | "Location" | "Movie" | "Book" | "Container" | "Asset" | "Org",
  "display": "title or name",
  "description": "short HTML summary; keep useful quotes; do not dump the whole source",
  "tags": ["short", "labels"],
  "year": 1999,
  "language": "",
  "country": "",
  "summary": "book plot in a few sentences",
  "first_name": "",
  "last_name": "",
  "profession": "",
  "emails": [],
  "phones": [],
  "dob": "YYYY-MM-DD or empty",
  "address1": "",
  "city": "",
  "state": "",
  "postal_code": "",
  "name": "org name",
  "kind": "School" | "University" | "Company" | "NonProfit" | "Club" | "Unspecified",
  "value": null,
  "acquired_on": "",
  "relations": [
    {"relation_type": "HAS_DIRECTOR"|"HAS_AS_AUTHOR"|"HAS_ACTOR"|"HAS_MUS_DIRECTOR"|"WORKS_AT"|"LIVES_AT"|"IS_RELATED_TO", "display": "Name", "type": "Person"}
  ]
}"""

_TYPE_FIELD_HINTS = {
    'Movie': 'Fill year/language/country. Put director/actors in relations (HAS_DIRECTOR, HAS_ACTOR).',
    'Book': 'Fill year/summary. Put author in relations (HAS_AS_AUTHOR).',
    'Person': 'Split first/last name. Extract emails, phones, profession, and dob if present.',
    'Location': 'Fill address1/city/state/postal_code/country.',
    'Org': 'Fill name and kind (School, University, Company, NonProfit, Club, or Unspecified).',
    'Asset': 'Fill value and acquired_on if present.',
    'Container': 'Use display as the container title.',
    'Note': 'Use display as a short title and keep useful quotes in description.',
}

_SYSTEM_PROMPT = f"""You extract one primary record for a personal knowledge base.

{_JSON_SHAPE}

Pick the single best type for the dropped content.
If relations include HAS_ACTOR, HAS_DIRECTOR, or HAS_MUS_DIRECTOR, type MUST be Movie.
If relations include HAS_AS_AUTHOR, type MUST be Book.
Movie: fill year/language/country; put director/actors in relations (HAS_DIRECTOR, HAS_ACTOR).
Book: fill year/summary; put author in relations (HAS_AS_AUTHOR).
Person: split first/last name; emails and phones if present.
Location: address parts.
Org: name and kind.
Note: use when the drop is an article, chat, or miscellaneous text.
Do not invent facts that are not in the source.
"""


def _system_prompt(forced_type=None):
    if not forced_type:
        return _SYSTEM_PROMPT
    hint = _TYPE_FIELD_HINTS.get(forced_type, '')
    return f"""You extract one {forced_type} record for a personal knowledge base.

{_JSON_SHAPE}

The type is locked to {forced_type}. Do not pick another type.
{hint}
Only include relations that are valid starting from {forced_type}.
Do not invent facts that are not in the source.
"""


def _user_prompt(payload, media, heuristic, forced_type=None):
    if forced_type:
        parts = [f'Type is locked to {forced_type}. Extract fields for that type. display hint={heuristic.get("display")}']
    else:
        parts = [f'Heuristic guess: type={heuristic.get("type")} display={heuristic.get("display")}']
    parts.append(f'Dropped files: {len(media["photos"])} images, {len(media["attachments"])} documents.')
    if media['source_urls']:
        parts.append('Source URLs:\n' + '\n'.join(media['source_urls'][:8]))
    blob = (payload.get('text') or '')[:10_000]
    html = (payload.get('html') or '')[:4_000]
    if blob:
        parts.append('Plain text:\n' + blob)
    if html:
        parts.append('HTML excerpt:\n' + html)
    parts.append('Return the JSON object now.')
    return '\n\n'.join(parts)


def _heuristic_parse(payload, media, forced_type=None):
    text = ' '.join(part for part in [payload.get('text'), _strip_html(payload.get('html') or '')] if part)
    html = payload.get('html') or ''
    title = _first_title(html, text, media)
    entity_type = forced_type or _guess_type(text, html, media)
    relations = []
    director = _name_after(_DIRECTOR_RE, text)
    if director and entity_type == 'Movie':
        relations.append({'relation_type': 'HAS_DIRECTOR', 'display': director, 'type': 'Person'})
    author = _name_after(_AUTHOR_RE, text)
    if author and entity_type == 'Book':
        relations.append({'relation_type': 'HAS_AS_AUTHOR', 'display': author, 'type': 'Person'})
    year_match = _YEAR_RE.search(text)
    emails = _EMAIL_RE.findall(text)[:8]
    phones = [item.strip() for item in _PHONE_RE.findall(text)[:8]]
    description = html.strip() if html.strip() else _text_to_html(payload.get('text') or text)
    parsed = {
        'type': entity_type,
        'display': title[:255],
        'description': description,
        'tags': ['dropped'],
        'year': int(year_match.group(1)) if year_match else None,
        'emails': emails,
        'phones': phones,
        'relations': relations,
    }
    if entity_type == 'Person':
        first, last = _split_name(title)
        parsed['first_name'] = first
        parsed['last_name'] = last
        parsed['profession'] = ''
    if entity_type == 'Org':
        parsed['name'] = title
        parsed['kind'] = _guess_org_kind(text)
    if entity_type == 'Book':
        parsed['summary'] = (payload.get('text') or text)[:2000]
    if entity_type == 'Location':
        parsed.update(_guess_address(text))
    return parsed


def _guess_type(text, html, media):
    blob = f'{text}\n{html}'.lower()
    if re.search(r'\b(directed by|starring|imdb|filmography|runtime|box office)\b', blob) or 'imdb.com/title' in blob:
        return 'Movie'
    if re.search(r'\b(isbn|paperback|hardcover|publisher|goodreads)\b', blob) or 'author' in blob and 'book' in blob:
        return 'Book'
    if re.search(r'\b(university|inc\.|llc\b|non-?profit|foundation|company|school)\b', blob) and not re.search(r'\b(directed by|isbn)\b', blob):
        return 'Org'
    if re.search(r'\b(street|avenue|boulevard|suite|postal|zip code)\b', blob) or re.search(r'\b[A-Z]{2}\s+\d{5}\b', text):
        return 'Location'
    if _EMAIL_RE.search(text) and _looks_like_person_name(_first_line(text)):
        return 'Person'
    if re.search(r'\b(bought|acquired|appraised|\$\d)\b', blob) and media['attachments']:
        return 'Asset'
    if media['photos'] and len(text.split()) <= 12:
        return 'Note'
    if _looks_like_person_name(_first_line(text)) and len(text.split()) < 80:
        return 'Person'
    return 'Note'


def _first_title(html, text, media):
    og = _OG_TITLE_RE.search(html or '')
    if og:
        return html_lib.unescape(og.group(1)).strip()[:255]
    title = _TITLE_RE.search(html or '')
    if title:
        return html_lib.unescape(re.sub(r'\s+', ' ', title.group(1))).strip()[:255]
    line = _first_line(text)
    if line:
        return line[:255]
    if media['photos']:
        return os.path.splitext(media['photos'][0].get('filename') or 'Image')[0][:255]
    if media['attachments']:
        return os.path.splitext(media['attachments'][0].get('filename') or 'Document')[0][:255]
    if media['source_urls']:
        host = urlparse(media['source_urls'][0]).hostname or 'Link'
        return host[:255]
    return 'Dropped item'


def _entity_payload(parsed, description, photos, attachments, source_urls):
    entity_type = _normalize_type(parsed.get('type'))
    urls = []
    for url in source_urls:
        if url and url not in {item.get('url') for item in urls}:
            urls.append({'url': url, 'caption': 'Source'})
    referenced = []
    for item in photos + attachments:
        path = item.get('path')
        if path:
            referenced.append({'path': path, 'is_encrypted': False})
    payload = {
        'display': (parsed.get('display') or 'Dropped item')[:255],
        'description': description,
        'tags': _clean_tags(parsed.get('tags')),
        'urls': urls,
        'photos': photos,
        'attachments': attachments,
        'referenced_files': referenced,
    }
    if entity_type == 'Person':
        first, last = parsed.get('first_name'), parsed.get('last_name')
        if not first and not last:
            first, last = _split_name(payload['display'])
        payload.update({
            'first_name': first or '',
            'last_name': last or '',
            'profession': parsed.get('profession') or '',
            'emails': list(parsed.get('emails') or [])[:8],
            'phones': list(parsed.get('phones') or [])[:8],
        })
        dob = str(parsed.get('dob') or '').strip()
        if re.match(r'\d{4}-\d{2}-\d{2}$', dob):
            payload['dob'] = dob
    elif entity_type in ('Movie', 'Book'):
        year = parsed.get('year')
        try:
            payload['year'] = int(year) if year not in (None, '') else None
        except (TypeError, ValueError):
            payload['year'] = None
        payload['language'] = str(parsed.get('language') or '')[:100]
        payload['country'] = str(parsed.get('country') or '')[:100]
        if entity_type == 'Book':
            payload['summary'] = str(parsed.get('summary') or '')[:8000]
    elif entity_type == 'Location':
        payload.update({
            'address1': str(parsed.get('address1') or '')[:255],
            'address2': str(parsed.get('address2') or '')[:255],
            'city': str(parsed.get('city') or '')[:100],
            'state': str(parsed.get('state') or '')[:100],
            'postal_code': str(parsed.get('postal_code') or '')[:20],
            'country': str(parsed.get('country') or '')[:100],
        })
    elif entity_type == 'Org':
        payload['name'] = str(parsed.get('name') or payload['display'])[:255]
        kind = str(parsed.get('kind') or 'Unspecified')
        payload['kind'] = kind if kind in {
            'School', 'University', 'Company', 'NonProfit', 'Club', 'Unspecified',
        } else 'Unspecified'
    elif entity_type == 'Asset':
        try:
            payload['value'] = float(parsed['value']) if parsed.get('value') not in (None, '') else None
        except (TypeError, ValueError):
            payload['value'] = None
        payload['acquired_on'] = str(parsed.get('acquired_on') or '')[:255]
    payload['_type'] = entity_type
    return payload


def _create_entity(user, entity_data, request):
    entity_type = entity_data.pop('_type')
    entity_data = {key: value for key, value in entity_data.items() if value is not None}
    serializer_cls = SERIALIZERS[entity_type]
    serializer = serializer_cls(data=entity_data, context={'request': request})
    if not serializer.is_valid():
        raise DropIngestError(_format_errors(serializer.errors))
    return serializer.save(user=user)


def _find_duplicate(user, entity_data):
    entity_type = entity_data.get('_type')
    display = (entity_data.get('display') or '').strip()
    model = ENTITY_MODELS.get(entity_type)
    if not model:
        return None
    match = None
    if display and display.casefold() not in _WEAK_DISPLAYS:
        qs = model.objects.filter(user=user, display__iexact=display)
        year = entity_data.get('year')
        if year not in (None, '') and entity_type in ('Movie', 'Book'):
            match = qs.filter(year=year).first() or qs.first()
        elif entity_type == 'Person':
            first = (entity_data.get('first_name') or '').strip()
            last = (entity_data.get('last_name') or '').strip()
            match = qs.first()
            if not match and first:
                match = model.objects.filter(user=user, first_name__iexact=first, last_name__iexact=last).first()
        else:
            match = qs.first()
    if match:
        return match
    for url in entity_data.get('urls') or []:
        href = url.get('url') if isinstance(url, dict) else str(url or '')
        href = href.strip()
        if not href:
            continue
        hit = model.objects.filter(user=user, urls__icontains=href).first()
        if hit:
            return hit
    return None


def _merge_media(entity, entity_data):
    changed = False
    for field in ('photos', 'attachments', 'urls'):
        incoming = entity_data.get(field) or []
        if not incoming:
            continue
        current = list(getattr(entity, field) or [])
        seen = set()
        for item in current:
            key = item.get('url') if isinstance(item, dict) else str(item)
            if key:
                seen.add(key)
        for item in incoming:
            key = item.get('url') if isinstance(item, dict) else str(item)
            if not key or key in seen:
                continue
            current.append(item)
            seen.add(key)
            changed = True
        if changed:
            setattr(entity, field, current)
    if changed:
        entity.save()
    return entity


def _get_or_create_main(user, entity_data, request):
    existing = _find_duplicate(user, entity_data)
    if existing:
        return _merge_media(existing, entity_data), False
    created = _create_entity(user, dict(entity_data), request)
    return created, True


def _create_relations(user, entity, relations, request, summary=None):
    for row in _normalize_relations(relations, entity.type):
        target, person_created = _get_or_create_person(user, row['display'], request)
        if not target or target.id == entity.id:
            continue
        if summary:
            if person_created:
                summary.created_related(target)
            else:
                summary.reused_related(target)
        try:
            _rel, linked = EntityRelation.objects.get_or_create(
                from_entity=entity,
                to_entity=target,
                relation_type=row['relation_type'],
            )
        except Exception:
            continue
        if summary:
            summary.add_relation(row['relation_type'], target, linked)


def _get_or_create_person(user, display, request):
    name = (display or '').strip()
    if not name:
        return None, False
    existing = Person.objects.filter(user=user, display__iexact=name).first()
    if existing:
        return existing, False
    first, last = _split_name(name)
    serializer = PersonSerializer(
        data={'display': name, 'first_name': first, 'last_name': last, 'tags': ['dropped']},
        context={'request': request},
    )
    if not serializer.is_valid():
        return None, False
    return serializer.save(user=user), True


def _extract_urls(text, html, explicit_url):
    found = []
    if explicit_url:
        found.extend(_split_uri_list(explicit_url))
    for match in _HREF_RE.findall(html or ''):
        found.append(match)
    for match in _SRC_RE.findall(html or ''):
        found.append(match)
    for match in _URL_RE.findall(text or ''):
        found.append(match.rstrip(').,;]>\'\"'))
    unique = []
    seen = set()
    for url in found:
        url = html_lib.unescape((url or '').strip())
        if not url or url in seen:
            continue
        seen.add(url)
        unique.append(url)
        if len(unique) >= MAX_URLS:
            break
    return unique


def _split_uri_list(value):
    urls = []
    for line in str(value or '').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and line.lower().startswith('http'):
            urls.append(line)
    return urls


def _url_kind(url):
    path = unquote(urlparse(url).path or '').lower()
    ext = os.path.splitext(path)[1]
    if ext in IMAGE_EXTS:
        return 'image'
    if ext in DOC_EXTS:
        return 'document'
    return 'page'


def _download_media(url, kind):
    resp = _http_get(url, stream=True)
    if resp is None:
        return None
    content_type = (resp.headers.get('Content-Type') or '').split(';')[0].strip().lower()
    if kind == 'image' and content_type and content_type not in IMAGE_TYPES and not content_type.startswith('image/'):
        return None
    body = _read_limited(resp)
    if not body:
        return None
    filename = _filename_from_url(url, content_type, kind)
    uploaded = SimpleUploadedFile(filename, body, content_type=content_type or None)
    return _save_upload(uploaded)


def _save_upload(uploaded):
    try:
        result = save_file_deduplicated(uploaded)
    except Exception:
        return None
    name = getattr(uploaded, 'name', '') or os.path.basename(result.get('path') or 'file')
    item = {
        'url': result.get('url'),
        'filename': os.path.basename(name),
        'caption': '',
        'path': result.get('path'),
    }
    if result.get('thumbnail_url'):
        item['thumbnail_url'] = result['thumbnail_url']
    if result.get('preview_url'):
        item['preview_url'] = result['preview_url']
    return item


def _fetch_page_meta(url):
    resp = _http_get(url, stream=False)
    if resp is None:
        return None
    content_type = (resp.headers.get('Content-Type') or '').split(';')[0].strip().lower()
    if content_type in IMAGE_TYPES or content_type.startswith('image/'):
        return None
    if content_type and 'html' not in content_type and 'text' not in content_type:
        return None
    html = (resp.content or b'')[:200_000].decode('utf-8', errors='replace')
    title = ''
    og_title = _OG_TITLE_RE.search(html)
    if og_title:
        title = html_lib.unescape(og_title.group(1)).strip()
    elif _TITLE_RE.search(html):
        title = html_lib.unescape(re.sub(r'\s+', ' ', _TITLE_RE.search(html).group(1))).strip()
    desc = ''
    og_desc = _OG_DESC_RE.search(html)
    if og_desc:
        desc = html_lib.unescape(og_desc.group(1)).strip()
    images = []
    og_image = _OG_IMAGE_RE.search(html)
    if og_image:
        images.append(urljoin(url, html_lib.unescape(og_image.group(1).strip())))
    text_parts = [part for part in [title, desc, _strip_html(html)[:4000]] if part]
    return {'text': '\n'.join(text_parts), 'images': images}


def _request_headers(url, referer=None):
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    headers = {
        'User-Agent': USER_AGENT,
        'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    if referer:
        headers['Referer'] = referer
    elif 'amazon' in host or host.endswith('ssl-images-amazon.com'):
        headers['Referer'] = 'https://www.amazon.com/'
    elif parsed.scheme and parsed.netloc:
        headers['Referer'] = f'{parsed.scheme}://{parsed.netloc}/'
    return headers


def _http_get(url, stream=False):
    current = url
    referer = None
    for _ in range(4):
        if not _is_safe_to_fetch(current):
            return None
        try:
            resp = requests.get(
                current,
                timeout=FETCH_TIMEOUT,
                stream=stream,
                allow_redirects=False,
                headers=_request_headers(current, referer=referer),
            )
        except requests.RequestException:
            return None
        if resp.is_redirect or resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get('Location')
            if not location:
                return None
            current = urljoin(current, location)
            continue
        if resp.status_code == 403 and referer is None:
            host = (urlparse(current).hostname or '').lower()
            referer = 'https://www.amazon.com/' if 'amazon' in host else 'https://www.google.com/'
            continue
        if resp.status_code >= 400:
            return None
        return resp
    return None


def _is_safe_to_fetch(url):
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return False
    host = (parsed.hostname or '').lower()
    if not host or host in {'localhost', 'metadata.google.internal'}:
        return False
    if host.endswith('.local') or host.endswith('.internal'):
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
            or ip.is_unspecified
        ):
            return False
    return True


def _read_limited(resp):
    chunks = []
    total = 0
    try:
        for chunk in resp.iter_content(64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_DOWNLOAD_BYTES:
                return b''
            chunks.append(chunk)
    except requests.RequestException:
        return b''
    return b''.join(chunks)


def _filename_from_url(url, content_type, kind):
    path = unquote(urlparse(url).path or '')
    name = os.path.basename(path) or kind
    name = re.sub(r'[^A-Za-z0-9._-]+', '-', name).strip('-') or kind
    if '.' not in name:
        ext = mimetypes.guess_extension(content_type or '') or ('.jpg' if kind == 'image' else '.bin')
        name = f'{name}{ext}'
    return name[:180]


def _rebase_description(description, url_map):
    html = description or ''
    for original, local in sorted(url_map.items(), key=lambda item: len(item[0]), reverse=True):
        html = html.replace(original, local)
    return html


def _dedupe_media(items):
    seen = set()
    result = []
    for item in items:
        key = item.get('url') or item.get('path')
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _coerce_type_from_relations(entity_type, relations):
    rels = {
        str(row.get('relation_type') or '').strip().upper()
        for row in (relations or [])
        if isinstance(row, dict)
    }
    if rels & {'HAS_ACTOR', 'HAS_DIRECTOR', 'HAS_MUS_DIRECTOR'}:
        return 'Movie'
    if rels & {'HAS_AS_AUTHOR'} and entity_type in ('Note', 'Person'):
        return 'Book'
    return entity_type


def _relation_allowed(relation_type, entity_type):
    from .constants import RELATION_SCHEMA
    for schema in RELATION_SCHEMA:
        if schema.get('key') != relation_type:
            continue
        expected = schema.get('fromEntity')
        if expected in ('*', 'ANY', entity_type):
            return True
    return False


def _normalize_type(value):
    text = str(value or '').strip()
    lookup = {name.casefold(): name for name in ENTITY_TYPES}
    return lookup.get(text.casefold(), 'Note')


def _resolve_forced_type(value):
    if value in (None, ''):
        return None
    text = str(value).strip()
    lookup = {name.casefold(): name for name in ENTITY_TYPES}
    resolved = lookup.get(text.casefold())
    if not resolved:
        raise DropIngestError(f'Unknown entity type "{text}".')
    return resolved


def _normalize_relations(rows, entity_type):
    if not isinstance(rows, list):
        return []
    cleaned = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        rel = str(row.get('relation_type') or '').strip().upper()
        display = str(row.get('display') or row.get('name') or '').strip()
        if not display or rel not in RELATION_WHITELIST:
            continue
        if not _relation_allowed(rel, entity_type):
            continue
        key = (rel, display.casefold())
        if key in seen:
            continue
        seen.add(key)
        cleaned.append({'relation_type': rel, 'display': display[:255], 'type': 'Person'})
        if len(cleaned) >= 8:
            break
    return cleaned


def _normalize_llm_fields(data):
    out = {}
    if data.get('type'):
        out['type'] = _normalize_type(data.get('type'))
    for key in (
        'display', 'description', 'language', 'country', 'summary', 'first_name',
        'last_name', 'profession', 'address1', 'address2', 'city', 'state',
        'postal_code', 'name', 'kind', 'acquired_on', 'dob',
    ):
        if key in data and data[key] not in (None, ''):
            out[key] = data[key]
    if isinstance(data.get('tags'), list):
        out['tags'] = _clean_tags(data.get('tags'))
    if isinstance(data.get('emails'), list):
        out['emails'] = [str(item).strip() for item in data['emails'] if str(item).strip()][:8]
    if isinstance(data.get('phones'), list):
        out['phones'] = [str(item).strip() for item in data['phones'] if str(item).strip()][:8]
    if data.get('year') not in (None, ''):
        out['year'] = data.get('year')
    if data.get('value') not in (None, ''):
        out['value'] = data.get('value')
    if data.get('relations'):
        out['relations'] = data.get('relations')
    return out


def _extract_json(text):
    blob = (text or '').strip()
    fence = _FENCE_RE.search(blob)
    if fence:
        blob = fence.group(1).strip()
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        start, end = blob.find('{'), blob.rfind('}')
        if start < 0 or end <= start:
            return {}
        try:
            return json.loads(blob[start:end + 1])
        except json.JSONDecodeError:
            return {}


def _clean_tags(value):
    tags = []
    if isinstance(value, str):
        value = [part.strip() for part in value.split(',')]
    if not isinstance(value, list):
        value = []
    for item in value:
        name = str(item).strip()[:64]
        if name and name not in tags:
            tags.append(name)
    if 'dropped' not in tags:
        tags.append('dropped')
    return tags[:12]


def _strip_html(value):
    text = re.sub(r'(?is)<script[^>]*>.*?</script>', ' ', value or '')
    text = re.sub(r'(?is)<style[^>]*>.*?</style>', ' ', text)
    text = re.sub(r'(?s)<[^>]+>', ' ', text)
    return html_lib.unescape(re.sub(r'\s+', ' ', text)).strip()


def _text_to_html(text):
    escaped = html_lib.escape((text or '').strip())
    if not escaped:
        return ''
    return '<p>' + escaped.replace('\n\n', '</p><p>').replace('\n', '<br>') + '</p>'


def _first_line(text):
    for line in (text or '').splitlines():
        line = re.sub(r'\s+', ' ', line).strip()
        if line:
            return line
    return ''


def _name_after(pattern, text):
    match = pattern.search(text or '')
    if not match:
        return ''
    tokens = re.findall(r"[A-Z][\w.'\-]+", text[match.end():match.end() + 80])
    names = []
    real = 0
    for tok in tokens:
        particle = tok.casefold() in _NAME_PARTICLES
        if real >= 2 and not particle:
            break
        names.append(tok)
        if not particle:
            real += 1
        if real >= 3:
            break
    return ' '.join(names).strip()


def _split_name(display):
    parts = [part for part in str(display or '').strip().split() if part]
    if not parts:
        return '', ''
    if len(parts) == 1:
        return parts[0], ''
    return parts[0], ' '.join(parts[1:])


def _looks_like_person_name(value):
    parts = [part for part in str(value or '').split() if part]
    if not 1 <= len(parts) <= 4:
        return False
    return all(re.match(r"^[A-Z][\w.'\-]+$", part) for part in parts)


def _guess_org_kind(text):
    blob = (text or '').lower()
    if 'university' in blob:
        return 'University'
    if 'school' in blob:
        return 'School'
    if 'nonprofit' in blob or 'non-profit' in blob:
        return 'NonProfit'
    if 'club' in blob:
        return 'Club'
    if re.search(r'\b(inc\.|llc|corp|company)\b', blob):
        return 'Company'
    return 'Unspecified'


def _guess_address(text):
    city = state = postal = ''
    match = re.search(r'\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)?),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\b', text or '')
    if match:
        city, state, postal = match.group(1), match.group(2), match.group(3)
    line = _first_line(text)
    return {
        'address1': line if re.search(r'\d', line) else '',
        'city': city,
        'state': state,
        'postal_code': postal,
        'country': 'USA' if state else '',
    }


def _is_image_name(name):
    return os.path.splitext((name or '').lower())[1] in IMAGE_EXTS


def _is_image_type(content_type):
    kind = (content_type or '').split(';')[0].strip().lower()
    return kind in IMAGE_TYPES or kind.startswith('image/')


def _format_errors(errors):
    if isinstance(errors, dict):
        parts = []
        for key, value in errors.items():
            parts.append(f'{key}: {value}')
        return '; '.join(parts)[:400]
    return str(errors)[:400]
