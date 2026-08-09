"""Gmail API helpers (OAuth user mailbox) for gmail_assistant."""

from __future__ import annotations

import base64
import json
import logging
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

GMAIL_SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.labels',
]

_HTML_TAG_RE = re.compile(r'<[^>]+>')
_WS_RE = re.compile(r'\s+')


def _client_config() -> tuple[str, str]:
    client_id = getattr(settings, 'GOOGLE_CLIENT_ID', '') or ''
    client_secret = getattr(settings, 'GOOGLE_CLIENT_SECRET', '') or ''
    if not client_id:
        import os

        client_id = os.environ.get('GOOGLE_CLIENT_ID', '')
        client_secret = os.environ.get('GOOGLE_CLIENT_SECRET', '')
    return client_id, client_secret


def oauth_redirect_uri() -> str:
    return getattr(settings, 'GMAIL_OAUTH_REDIRECT_URI', '') or (
        'http://localhost:8000/api/gmail/oauth/callback/'
    )


def oauth_authorize_url(state: str = '') -> str:
    client_id, _ = _client_config()
    # Do not set include_granted_scopes=true: restricted Gmail scopes reject
    # incremental auth and Google returns Error 400: invalid_request.
    params = {
        'client_id': client_id,
        'redirect_uri': oauth_redirect_uri(),
        'response_type': 'code',
        'scope': ' '.join(GMAIL_SCOPES),
        'access_type': 'offline',
        'prompt': 'consent',
    }
    if state:
        params['state'] = state
    return 'https://accounts.google.com/o/oauth2/v2/auth?' + urllib.parse.urlencode(
        params
    )


def exchange_code(code: str) -> dict[str, Any]:
    client_id, client_secret = _client_config()
    data = urllib.parse.urlencode(
        {
            'code': code,
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': oauth_redirect_uri(),
            'grant_type': 'authorization_code',
        }
    ).encode()
    req = urllib.request.Request(
        'https://oauth2.googleapis.com/token',
        data=data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    client_id, client_secret = _client_config()
    data = urllib.parse.urlencode(
        {
            'client_id': client_id,
            'client_secret': client_secret,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token',
        }
    ).encode()
    req = urllib.request.Request(
        'https://oauth2.googleapis.com/token',
        data=data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def build_gmail_service(refresh_token: str) -> Any:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    client_id, client_secret = _client_config()
    token_data = refresh_access_token(refresh_token)
    creds = Credentials(
        token=token_data['access_token'],
        refresh_token=refresh_token,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=client_id,
        client_secret=client_secret,
        scopes=GMAIL_SCOPES,
    )
    return build('gmail', 'v1', credentials=creds, cache_discovery=False)


def get_profile_email(service: Any) -> str:
    return service.users().getProfile(userId='me').execute().get('emailAddress', '')


def list_message_ids(service: Any, *, query: str, max_results: int = 200) -> list[str]:
    ids: list[str] = []
    request = service.users().messages().list(
        userId='me', q=query, maxResults=min(100, max_results)
    )
    while request is not None and len(ids) < max_results:
        response = request.execute()
        for item in response.get('messages') or []:
            mid = item.get('id')
            if mid:
                ids.append(mid)
            if len(ids) >= max_results:
                break
        token = response.get('nextPageToken')
        if not token or len(ids) >= max_results:
            break
        request = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=min(100, max_results - len(ids)),
            pageToken=token,
        )
    return ids


def header_map(payload: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for h in payload.get('headers') or []:
        name = (h.get('name') or '').strip().lower()
        if name:
            out[name] = h.get('value') or ''
    return out


def fetch_message_metadata(service: Any, gmail_id: str) -> dict[str, Any]:
    msg = (
        service.users()
        .messages()
        .get(
            userId='me',
            id=gmail_id,
            format='metadata',
            metadataHeaders=['From', 'Subject', 'Date'],
        )
        .execute()
    )
    payload = msg.get('payload') or {}
    headers = header_map(payload)
    date_hdr = headers.get('date') or ''
    date_iso = ''
    if date_hdr:
        try:
            date_iso = (
                parsedate_to_datetime(date_hdr).astimezone(timezone.utc).isoformat()
            )
        except (TypeError, ValueError, IndexError):
            date_iso = ''
    internal = int(msg.get('internalDate') or 0)
    if not date_iso and internal:
        date_iso = datetime.fromtimestamp(internal / 1000, tz=timezone.utc).isoformat()
    return {
        'gmail_id': msg['id'],
        'thread_id': msg.get('threadId') or '',
        'subject': headers.get('subject') or '(no subject)',
        'from_addr': headers.get('from') or '',
        'date_iso': date_iso,
        'internal_date_ms': internal,
        'snippet': msg.get('snippet') or '',
        'label_ids': list(msg.get('labelIds') or []),
    }


def _decode_part_body(data: str | None) -> str:
    if not data:
        return ''
    raw = base64.urlsafe_b64decode(data.encode('utf-8'))
    return raw.decode('utf-8', errors='replace')


def _walk_parts(payload: dict[str, Any]) -> tuple[str, str]:
    mime = (payload.get('mimeType') or '').lower()
    body = payload.get('body') or {}
    text_plain = ''
    text_html = ''
    if mime == 'text/plain' and body.get('data'):
        text_plain = _decode_part_body(body.get('data'))
    elif mime == 'text/html' and body.get('data'):
        text_html = _decode_part_body(body.get('data'))
    for part in payload.get('parts') or []:
        p, h = _walk_parts(part)
        if p and not text_plain:
            text_plain = p
        if h and not text_html:
            text_html = h
    if not text_plain and not text_html and body.get('data') and mime.startswith('text/'):
        decoded = _decode_part_body(body.get('data'))
        if 'html' in mime:
            text_html = decoded
        else:
            text_plain = decoded
    return text_plain, text_html


def html_to_text(html: str) -> str:
    cleaned = _HTML_TAG_RE.sub(' ', html or '')
    return _WS_RE.sub(' ', cleaned).strip()


def fetch_message(service: Any, gmail_id: str) -> dict[str, Any]:
    msg = (
        service.users()
        .messages()
        .get(userId='me', id=gmail_id, format='full')
        .execute()
    )
    payload = msg.get('payload') or {}
    headers = header_map(payload)
    text_plain, text_html = _walk_parts(payload)
    body = (text_plain or html_to_text(text_html) or msg.get('snippet') or '').strip()
    date_hdr = headers.get('date') or ''
    date_iso = ''
    if date_hdr:
        try:
            date_iso = (
                parsedate_to_datetime(date_hdr).astimezone(timezone.utc).isoformat()
            )
        except (TypeError, ValueError, IndexError):
            date_iso = ''
    internal = int(msg.get('internalDate') or 0)
    if not date_iso and internal:
        date_iso = datetime.fromtimestamp(internal / 1000, tz=timezone.utc).isoformat()
    return {
        'gmail_id': msg['id'],
        'thread_id': msg.get('threadId') or '',
        'subject': headers.get('subject') or '(no subject)',
        'from_addr': headers.get('from') or '',
        'to_addr': headers.get('to') or '',
        'date_iso': date_iso,
        'internal_date_ms': internal,
        'snippet': msg.get('snippet') or '',
        'body_text': body[:20000],
        'label_ids': list(msg.get('labelIds') or []),
    }


def list_labels(service: Any) -> list[dict[str, str]]:
    result = service.users().labels().list(userId='me').execute()
    labels = []
    for item in result.get('labels') or []:
        labels.append(
            {
                'id': item.get('id') or '',
                'name': item.get('name') or '',
                'type': item.get('type') or '',
            }
        )
    labels.sort(key=lambda x: (x['type'] != 'user', x['name'].casefold()))
    return labels


def trash_message(service: Any, gmail_id: str) -> None:
    service.users().messages().trash(userId='me', id=gmail_id).execute()


def archive_message(service: Any, gmail_id: str) -> list[str]:
    result = (
        service.users()
        .messages()
        .modify(userId='me', id=gmail_id, body={'removeLabelIds': ['INBOX']})
        .execute()
    )
    return list(result.get('labelIds') or [])


def modify_labels(
    service: Any,
    gmail_id: str,
    *,
    add: list[str] | None = None,
    remove: list[str] | None = None,
) -> list[str]:
    body: dict[str, Any] = {}
    if add:
        body['addLabelIds'] = add
    if remove:
        body['removeLabelIds'] = remove
    if not body:
        msg = (
            service.users()
            .messages()
            .get(userId='me', id=gmail_id, format='minimal')
            .execute()
        )
        return list(msg.get('labelIds') or [])
    result = (
        service.users()
        .messages()
        .modify(userId='me', id=gmail_id, body=body)
        .execute()
    )
    return list(result.get('labelIds') or [])
