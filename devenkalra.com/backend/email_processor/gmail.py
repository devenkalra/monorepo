"""Gmail API helpers (OAuth user mailbox)."""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone as dt_timezone
from email.utils import parsedate_to_datetime

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
LABEL_PROCESSED = 'Processed'
LABEL_NEEDS_REVIEW = 'Needs-Review'


def _client_config():
    client_id = getattr(settings, 'EMAIL_GMAIL_CLIENT_ID', '') or settings.GOOGLE_CLIENT_ID
    client_secret = (
        getattr(settings, 'EMAIL_GMAIL_CLIENT_SECRET', '') or settings.GOOGLE_CLIENT_SECRET
    )
    return client_id, client_secret


def oauth_authorize_url(redirect_uri, state=''):
    from urllib.parse import urlencode
    client_id, _ = _client_config()
    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': ' '.join(GMAIL_SCOPES),
        'access_type': 'offline',
        'prompt': 'consent',
        'include_granted_scopes': 'true',
    }
    if state:
        params['state'] = state
    return 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode(params)


def exchange_code(code, redirect_uri):
    import json
    import urllib.parse
    import urllib.request

    client_id, client_secret = _client_config()
    data = urllib.parse.urlencode({
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code',
    }).encode()
    req = urllib.request.Request(
        'https://oauth2.googleapis.com/token',
        data=data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def refresh_access_token(refresh_token):
    import json
    import urllib.parse
    import urllib.request

    client_id, client_secret = _client_config()
    data = urllib.parse.urlencode({
        'client_id': client_id,
        'client_secret': client_secret,
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token',
    }).encode()
    req = urllib.request.Request(
        'https://oauth2.googleapis.com/token',
        data=data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def build_gmail_service(refresh_token):
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


def get_profile_email(service):
    return service.users().getProfile(userId='me').execute().get('emailAddress', '')


def ensure_label(service, name):
    existing = service.users().labels().list(userId='me').execute().get('labels', [])
    for label in existing:
        if label.get('name') == name:
            return label['id']
    created = service.users().labels().create(
        userId='me',
        body={
            'name': name,
            'labelListVisibility': 'labelShow',
            'messageListVisibility': 'show',
        },
    ).execute()
    return created['id']


def start_watch(service, topic_name):
    body = {
        'topicName': topic_name,
        'labelIds': ['INBOX'],
        'labelFilterBehavior': 'include',
    }
    return service.users().watch(userId='me', body=body).execute()


def list_history(service, start_history_id):
    """Yield message ids from messagesAdded since start_history_id."""
    page_token = None
    latest_history_id = str(start_history_id)
    while True:
        kwargs = {
            'userId': 'me',
            'startHistoryId': start_history_id,
            'historyTypes': ['messageAdded'],
        }
        if page_token:
            kwargs['pageToken'] = page_token
        try:
            resp = service.users().history().list(**kwargs).execute()
        except Exception as exc:
            # Invalid history id — caller should full-resync
            if 'historyId' in str(exc) or '404' in str(exc):
                raise
            raise
        latest_history_id = str(resp.get('historyId') or latest_history_id)
        for hist in resp.get('history', []) or []:
            for added in hist.get('messagesAdded', []) or []:
                msg = added.get('message') or {}
                mid = msg.get('id')
                if mid:
                    yield mid, latest_history_id
        page_token = resp.get('nextPageToken')
        if not page_token:
            break
    return latest_history_id


def fetch_message(service, message_id):
    return service.users().messages().get(
        userId='me', id=message_id, format='full',
    ).execute()


def header_map(payload):
    headers = {}
    for h in (payload or {}).get('headers') or []:
        name = (h.get('name') or '').lower()
        if name:
            headers[name] = h.get('value') or ''
    return headers


def parse_received_at(internal_date_ms, date_header=''):
    if internal_date_ms:
        try:
            ts = int(internal_date_ms) / 1000.0
            return datetime.fromtimestamp(ts, tz=dt_timezone.utc)
        except (TypeError, ValueError, OSError):
            pass
    if date_header:
        try:
            dt = parsedate_to_datetime(date_header)
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, dt_timezone.utc)
            return dt
        except (TypeError, ValueError, IndexError):
            pass
    return timezone.now()


def decode_body_data(data):
    if not data:
        return b''
    pad = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def walk_parts(payload):
    """Yield (mime_type, filename, bytes_or_None, part) for each part."""
    if not payload:
        return
    mime = payload.get('mimeType') or ''
    filename = ''
    for h in payload.get('headers') or []:
        if (h.get('name') or '').lower() == 'content-disposition':
            # crude filename extract
            cd = h.get('value') or ''
            if 'filename=' in cd:
                filename = cd.split('filename=', 1)[1].strip().strip('"')
    body = payload.get('body') or {}
    data = body.get('data')
    attachment_id = body.get('attachmentId')
    parts = payload.get('parts') or []
    if parts:
        for p in parts:
            yield from walk_parts(p)
    else:
        content = decode_body_data(data) if data else None
        yield mime, filename, content, payload, attachment_id


def get_text_bodies(payload):
    text_plain = ''
    text_html = ''
    for mime, _fn, content, _part, _aid in walk_parts(payload):
        if not content:
            continue
        try:
            decoded = content.decode('utf-8', errors='replace')
        except Exception:
            continue
        if mime.startswith('text/plain') and not text_plain:
            text_plain = decoded
        elif mime.startswith('text/html') and not text_html:
            text_html = decoded
    return text_plain, text_html


def download_attachment(service, message_id, attachment_id):
    att = service.users().messages().attachments().get(
        userId='me', messageId=message_id, id=attachment_id,
    ).execute()
    return decode_body_data(att.get('data'))


def modify_labels(service, message_id, add=None, remove=None):
    body = {}
    if add:
        body['addLabelIds'] = list(add)
    if remove:
        body['removeLabelIds'] = list(remove)
    if not body:
        return
    service.users().messages().modify(userId='me', id=message_id, body=body).execute()


def mark_processed_and_archive(service, message_id, processed_label_id):
    modify_labels(
        service,
        message_id,
        add=[processed_label_id],
        remove=['INBOX', 'UNREAD'],
    )


def apply_needs_review(service, message_id, review_label_id):
    modify_labels(service, message_id, add=[review_label_id])


def list_recent_inbox_ids(service, max_results=50):
    resp = service.users().messages().list(
        userId='me', labelIds=['INBOX'], maxResults=max_results,
    ).execute()
    return [m['id'] for m in resp.get('messages') or []]


def list_messages_metadata(service, query='', max_results=25):
    """List messages matching a Gmail query; return metadata for Prompt-to-Select."""
    kwargs = {
        'userId': 'me',
        'maxResults': max_results,
        'q': query or 'in:inbox',
    }
    resp = service.users().messages().list(**kwargs).execute()
    refs = resp.get('messages') or []
    out = []
    for ref in refs:
        mid = ref.get('id')
        if not mid:
            continue
        raw = service.users().messages().get(
            userId='me',
            id=mid,
            format='metadata',
            metadataHeaders=['Subject', 'From', 'Date'],
        ).execute()
        headers = header_map(raw.get('payload') or {})
        received = parse_received_at(raw.get('internalDate'), headers.get('date', ''))
        out.append({
            'id': mid,
            'thread_id': raw.get('threadId') or '',
            'subject': headers.get('subject', ''),
            'from_address': headers.get('from', ''),
            'snippet': raw.get('snippet') or '',
            'received_at': received.isoformat() if received else '',
            'label_ids': raw.get('labelIds') or [],
        })
    return out


def list_user_labels(service):
    """Return Gmail labels usable for assign-label UI."""
    resp = service.users().labels().list(userId='me').execute()
    out = []
    for label in resp.get('labels') or []:
        name = label.get('name') or ''
        lid = label.get('id') or ''
        ltype = label.get('type') or ''
        if not lid or not name:
            continue
        # Skip noisy system folders; keep user labels + our workflow labels
        if ltype == 'system' and name not in (LABEL_PROCESSED, LABEL_NEEDS_REVIEW, 'STARRED', 'IMPORTANT'):
            continue
        out.append({'id': lid, 'name': name, 'type': ltype})
    out.sort(key=lambda x: (0 if x['type'] == 'user' else 1, x['name'].lower()))
    return out


def resolve_label_id(service, label_id=None, label_name=None):
    if label_id:
        return label_id
    name = (label_name or '').strip()
    if not name:
        raise RuntimeError('label_id or label_name is required')
    return ensure_label(service, name)


def batch_mailbox_action(service, gmail_ids, action, label_id=None, label_name=None):
    """Apply archive/trash/read/label via Gmail batchModify (or trash)."""
    ids = [i for i in (gmail_ids or []) if i]
    if not ids:
        return {'affected': 0}

    # Gmail batchModify accepts up to 1000 ids
    chunk_size = 100
    affected = 0
    for i in range(0, len(ids), chunk_size):
        chunk = ids[i:i + chunk_size]
        if action == 'trash':
            # Prefer trash over permanent batchDelete
            for mid in chunk:
                service.users().messages().trash(userId='me', id=mid).execute()
                affected += 1
            continue

        add, remove = [], []
        if action == 'archive':
            remove = ['INBOX']
        elif action == 'mark_read':
            remove = ['UNREAD']
        elif action == 'mark_unread':
            add = ['UNREAD']
        elif action == 'label_processed':
            processed = ensure_label(service, LABEL_PROCESSED)
            add = [processed]
            remove = ['INBOX', 'UNREAD']
        elif action == 'label':
            add = [resolve_label_id(service, label_id=label_id, label_name=label_name)]
        else:
            raise RuntimeError(f'Unsupported mailbox action: {action}')

        body = {'ids': chunk}
        if add:
            body['addLabelIds'] = add
        if remove:
            body['removeLabelIds'] = remove
        service.users().messages().batchModify(userId='me', body=body).execute()
        affected += len(chunk)

    return {'affected': affected, 'action': action}


def batch_thread_action(service, thread_ids, action, label_id=None, label_name=None):
    """Deterministic bulk ops on Gmail threads (preferred over message ids)."""
    ids = list(dict.fromkeys([i for i in (thread_ids or []) if i]))
    if not ids:
        return {'affected': 0, 'thread_ids': [], 'action': action}

    affected = 0
    for tid in ids:
        if action == 'trash':
            service.users().threads().trash(userId='me', id=tid).execute()
            affected += 1
            continue

        add, remove = [], []
        if action == 'archive':
            remove = ['INBOX']
        elif action == 'mark_read':
            remove = ['UNREAD']
        elif action == 'mark_unread':
            add = ['UNREAD']
        elif action == 'label_processed':
            processed = ensure_label(service, LABEL_PROCESSED)
            add = [processed]
            remove = ['INBOX', 'UNREAD']
        elif action == 'label':
            add = [resolve_label_id(service, label_id=label_id, label_name=label_name)]
        else:
            raise RuntimeError(f'Unsupported thread action: {action}')

        body = {}
        if add:
            body['addLabelIds'] = add
        if remove:
            body['removeLabelIds'] = remove
        if not body:
            continue
        service.users().threads().modify(userId='me', id=tid, body=body).execute()
        affected += 1

    return {'affected': affected, 'thread_ids': ids, 'action': action}
