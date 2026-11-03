"""Throttled, restartable Gmail mail merge over People contacts.

Audience is frozen into MailCampaignRecipient rows at create time. A background
tick claims pending rows under daily/per-minute caps and creates Gmail drafts
or sends. Server restarts resume from remaining pending rows.
"""
from __future__ import annotations

import base64
import html
import logging
import re
from datetime import timedelta
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from django.db import transaction
from django.db.models import Count, F
from django.utils import timezone

from . import entity_actions, google_auth
from .engine.normalize import norm_email
from .models import EntityCache, GoogleAccount, MailCampaign, MailCampaignRecipient

logger = logging.getLogger(__name__)

# {{token}} (preferred); also tolerate Gmail inserting tags inside the braces.
TOKEN_RE = re.compile(
    r'\{\{(?:<[^>]+>|\s|&nbsp;)*([a-zA-Z_][a-zA-Z0-9_]*)(?:<[^>]+>|\s|&nbsp;)*\}\}',
    re.I,
)
# Single-brace {token} — common when composing in Gmail (must not eat {{token}}).
SINGLE_TOKEN_RE = re.compile(
    r'(?<!\{)\{(?:<[^>]+>|\s|&nbsp;)*([a-zA-Z_][a-zA-Z0-9_]*)(?:<[^>]+>|\s|&nbsp;)*\}(?!\})',
    re.I,
)
TAG_RE = re.compile(r'<[^>]+>')
MAX_CREATE_IDS = 5000
STALE_SENDING = timedelta(minutes=15)
MAX_ATTEMPTS = 3
DEFAULT_DAILY_LIMIT = 1200
DEFAULT_PER_MINUTE = 20
HARD_DAILY_CAP = 1400  # leave headroom under Gmail's ~1500/day
DRAFT_LIST_MAX = 40
# Gmail accepts ~25MB messages; leave headroom for bodies/headers.
MAX_ATTACHMENTS_BYTES = 20 * 1024 * 1024


class MailMergeError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def render(template, data, *, escape_html=False):
    """Replace {{token}} / {token} with merge_data values; unknown tokens stay unchanged.

    Double braces are preferred. Single braces are also accepted (Gmail drafts often
    use {PSalutation}); unknown single-brace names are left as-is so normal {1} text
    is not wiped.
    """
    data = data or {}

    def repl_known(m, require_known):
        key = m.group(1)
        # Case-sensitive first, then case-insensitive fallback for PSalutation etc.
        if key in data:
            val = data[key]
        else:
            lower = {str(k).lower(): v for k, v in data.items()}
            if key.lower() not in lower:
                return m.group(0) if require_known else ''
            val = lower[key.lower()]
        text = '' if val is None else str(val)
        return html.escape(text, quote=True) if escape_html else text

    text = template or ''
    text = TOKEN_RE.sub(lambda m: repl_known(m, require_known=False), text)
    text = SINGLE_TOKEN_RE.sub(lambda m: repl_known(m, require_known=True), text)
    return text


def _decode_b64(data):
    if not data:
        return b''
    pad = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _walk_parts(payload):
    if not payload:
        return
    parts = payload.get('parts') or []
    if parts:
        for p in parts:
            yield from _walk_parts(p)
        return
    mime = payload.get('mimeType') or ''
    body = payload.get('body') or {}
    data = body.get('data')
    content = _decode_b64(data) if data else None
    yield mime, content


def _bodies_from_payload(payload):
    text_plain, text_html = '', ''
    # Single-part message
    if payload and not payload.get('parts') and (payload.get('body') or {}).get('data'):
        mime = payload.get('mimeType') or ''
        raw = _decode_b64(payload['body']['data']).decode('utf-8', errors='replace')
        if mime.startswith('text/html'):
            text_html = raw
        else:
            text_plain = raw
    for mime, content in _walk_parts(payload):
        if not content:
            continue
        decoded = content.decode('utf-8', errors='replace')
        if mime.startswith('text/plain') and not text_plain:
            text_plain = decoded
        elif mime.startswith('text/html') and not text_html:
            text_html = decoded
    return text_plain, text_html


def _header(payload, name):
    want = name.lower()
    for h in (payload or {}).get('headers') or []:
        if (h.get('name') or '').lower() == want:
            return h.get('value') or ''
    return ''


def _part_headers(part):
    return {(h.get('name') or '').lower(): (h.get('value') or '')
            for h in (part or {}).get('headers') or []}


def _payload_has_attachments(payload):
    """True if the MIME tree looks like it has file/inline attachments (no download)."""
    if not payload:
        return False
    filename = (payload.get('filename') or '').strip()
    mime = payload.get('mimeType') or ''
    body = payload.get('body') or {}
    headers = _part_headers(payload)
    content_id = (headers.get('content-id') or '').strip()
    disposition = (headers.get('content-disposition') or '').lower()
    if filename or body.get('attachmentId'):
        return True
    if content_id and not mime.startswith(('multipart/', 'text/')):
        return True
    if 'attachment' in disposition:
        return True
    return any(_payload_has_attachments(p) for p in payload.get('parts') or [])


def _fetch_part_bytes(service, message_id, body):
    data = body.get('data')
    if data:
        return _decode_b64(data)
    att_id = body.get('attachmentId')
    if not att_id or not message_id or service is None:
        return b''
    try:
        att = service.users().messages().attachments().get(
            userId='me', messageId=message_id, id=att_id).execute()
    except Exception as e:
        raise MailMergeError(f'Could not download draft attachment: {e}', 502) from e
    return _decode_b64(att.get('data'))


def _attachments_from_payload(service, message_id, payload):
    """Download file/inline parts from a Gmail message payload into storage dicts."""
    out = []
    total = 0

    def walk(part):
        nonlocal total
        if not part:
            return
        for child in part.get('parts') or []:
            walk(child)
        mime = part.get('mimeType') or 'application/octet-stream'
        if mime.startswith('multipart/'):
            return
        filename = (part.get('filename') or '').strip()
        body = part.get('body') or {}
        headers = _part_headers(part)
        content_id = (headers.get('content-id') or '').strip().strip('<>')
        disposition = (headers.get('content-disposition') or '').lower()
        is_text_body = mime.startswith('text/') and not filename and not content_id \
            and 'attachment' not in disposition
        if is_text_body:
            return
        if not filename and not content_id and not body.get('attachmentId') \
                and 'attachment' not in disposition:
            return
        raw = _fetch_part_bytes(service, message_id, body)
        if not raw:
            return
        total += len(raw)
        if total > MAX_ATTACHMENTS_BYTES:
            raise MailMergeError(
                f'Draft attachments exceed {MAX_ATTACHMENTS_BYTES // (1024 * 1024)}MB; '
                'use a smaller file or fewer attachments.')
        inline = bool(content_id) and 'attachment' not in disposition
        out.append({
            'filename': filename or (f'inline-{content_id}' if content_id else 'attachment'),
            'mime_type': mime,
            'content_id': content_id,
            'inline': inline,
            'data_b64': base64.b64encode(raw).decode('ascii'),
        })

    walk(payload)
    return out


def _snippet_plain(text, html_body, limit=120):
    s = (text or '').strip()
    if not s and html_body:
        s = TAG_RE.sub(' ', html_body)
        s = re.sub(r'\s+', ' ', s).strip()
    return (s[:limit] + ('…' if len(s) > limit else '')) if s else ''


def list_gmail_drafts(max_results=DRAFT_LIST_MAX):
    """Return recent Gmail drafts as [{id, subject, snippet, has_html}]."""
    _require_mail_account()
    try:
        service = google_auth.gmail_service()
        listed = service.users().drafts().list(userId='me', maxResults=max_results).execute()
    except Exception as e:
        raise MailMergeError(f'Could not list Gmail drafts: {e}', 502) from e
    out = []
    for row in listed.get('drafts') or []:
        did = row.get('id') or ''
        if not did:
            continue
        try:
            full = service.users().drafts().get(userId='me', id=did, format='full').execute()
        except Exception:
            out.append({
                'id': did, 'subject': '(unavailable)', 'snippet': '',
                'has_html': False, 'has_attachments': False,
            })
            continue
        msg = full.get('message') or {}
        payload = msg.get('payload') or {}
        subject = _header(payload, 'Subject') or '(no subject)'
        plain, html_body = _bodies_from_payload(payload)
        out.append({
            'id': did,
            'subject': subject,
            'snippet': _snippet_plain(plain, html_body) or (msg.get('snippet') or ''),
            'has_html': bool(html_body),
            'has_attachments': _payload_has_attachments(payload),
        })
    return out


def list_send_as():
    """Verified Gmail send-as identities for the From picker."""
    _require_mail_account()
    try:
        service = google_auth.gmail_service()
        listed = service.users().settings().sendAs().list(userId='me').execute()
    except Exception as e:
        raise MailMergeError(f'Could not list Gmail send-as addresses: {e}', 502) from e
    out = []
    for row in listed.get('sendAs') or []:
        email = (row.get('sendAsEmail') or '').strip()
        if not email:
            continue
        # pending aliases are not safe to send as (triggers unauthorized-sender warnings).
        if row.get('verificationStatus') == 'pending':
            continue
        out.append({
            'email': email,
            'name': (row.get('displayName') or '').strip(),
            'is_primary': bool(row.get('isPrimary')),
            'is_default': bool(row.get('isDefault')),
            # True = "Send mail as" display alias on this Gmail login (often fails DMARC
            # for custom domains). False / primary = actually owned mailbox.
            'treat_as_alias': bool(row.get('treatAsAlias')),
            'verification_status': row.get('verificationStatus') or '',
        })
    out.sort(key=lambda x: (not x['is_default'], not x['is_primary'], x['email'].lower()))
    return out


def resolve_from_identity(preferred_email='', preferred_name=''):
    """Pick a verified send-as: preferred → Gmail default → primary → account email."""
    account = _require_mail_account()
    try:
        identities = list_send_as()
    except MailMergeError:
        identities = []
    by_email = {i['email'].lower(): i for i in identities}
    want = (preferred_email or '').strip().lower()
    if want and want in by_email:
        ident = by_email[want]
    elif want and not identities:
        # Caller passed an address and we couldn't list send-as (tests / missing scope).
        ident = {'email': preferred_email.strip(), 'name': '', 'is_primary': False, 'is_default': False}
    else:
        ident = next((i for i in identities if i['is_default']), None) \
            or next((i for i in identities if i['is_primary']), None)
        if not ident and account.email:
            ident = {'email': account.email, 'name': '', 'is_primary': True, 'is_default': True}
        if not ident:
            raise MailMergeError('No verified Gmail send-as address available.')
    name = (preferred_name or '').strip() or ident.get('name') or ''
    return {'email': ident['email'], 'name': name}


def format_from_header(email_addr, display_name=''):
    email_addr = (email_addr or '').strip()
    display_name = (display_name or '').strip()
    if not email_addr:
        return ''
    return formataddr((display_name, email_addr)) if display_name else email_addr


def load_draft_template(draft_id):
    """Load subject + plain + HTML bodies + attachments from a Gmail draft."""
    draft_id = (draft_id or '').strip()
    if not draft_id:
        raise MailMergeError('gmail_draft_id is required.')
    _require_mail_account()
    try:
        service = google_auth.gmail_service()
        full = service.users().drafts().get(userId='me', id=draft_id, format='full').execute()
    except Exception as e:
        raise MailMergeError(f'Could not read Gmail draft: {e}', 502) from e
    msg = full.get('message') or {}
    payload = msg.get('payload') or {}
    message_id = msg.get('id') or ''
    subject = _header(payload, 'Subject')
    plain, html_body = _bodies_from_payload(payload)
    attachments = _attachments_from_payload(service, message_id, payload)
    if not subject and not plain and not html_body:
        raise MailMergeError('That Gmail draft has no subject or body.')
    if not plain and html_body:
        plain = TAG_RE.sub(' ', html_body)
        plain = re.sub(r'\s+', ' ', plain).strip()
    return {
        'draft_id': draft_id,
        'subject': subject or '',
        'text': plain or '',
        'html': html_body or '',
        'has_html': bool(html_body),
        'snippet': _snippet_plain(plain, html_body),
        'attachments': attachments,
        'attachment_names': [a['filename'] for a in attachments],
    }


def _primary_email(row):
    raw = (row.get('emails') or row.get('email') or '').strip()
    if not raw:
        return ''
    first = raw.split(',')[0].strip()
    return norm_email(first) or first.lower()


def _merge_data(row, first_name):
    email = _primary_email(row)
    name = (row.get('name') or '').strip()
    psal = (row.get('psalutation') or '').strip()
    fsal = (row.get('fsalutation') or '').strip()
    return {
        'name': name,
        'first_name': first_name or '',
        'email': email,
        'company': (row.get('company') or '').strip(),
        'title': (row.get('title') or '').strip(),
        'phones': (row.get('phones') or '').strip(),
        'groups': ', '.join(row.get('groups') or []),
        'outreach': ', '.join(row.get('outreach') or []),
        # ClickUp field names (preferred in drafts) plus lowercase aliases.
        'PSalutation': psal,
        'FSalutation': fsal,
        'psalutation': psal,
        'fsalutation': fsal,
    }


def _build_recipients(task_ids):
    """Return (rows_for_create, skipped[{task_id,name,reason}])."""
    ids = [str(x).strip() for x in task_ids if str(x).strip()]
    if not ids:
        raise MailMergeError('Select at least one contact.')
    if len(ids) > MAX_CREATE_IDS:
        raise MailMergeError(f'At most {MAX_CREATE_IDS} contacts per campaign.')

    cache = {c.task_id: c.row for c in EntityCache.objects.filter(task_id__in=ids)}
    google_ids = []
    for tid in ids:
        row = cache.get(tid) or {}
        gid = (row.get('google_id') or '').strip()
        if gid and not row.get('archived'):
            google_ids.append(gid)
    given = {}
    if google_ids:
        try:
            given = entity_actions._google_given_names(list(dict.fromkeys(google_ids)))
        except entity_actions.ActionError:
            given = {}

    seen_email = set()
    create, skipped = [], []
    for tid in ids:
        row = cache.get(tid)
        if not row:
            skipped.append({'task_id': tid, 'name': '', 'reason': 'not in local People & Orgs list'})
            continue
        name = (row.get('name') or '').strip()
        if row.get('archived'):
            skipped.append({'task_id': tid, 'name': name, 'reason': 'archived'})
            continue
        if (row.get('match') or '').strip().lower() == 'merged':
            skipped.append({'task_id': tid, 'name': name, 'reason': 'merged'})
            continue
        if row.get('list') != 'people':
            skipped.append({'task_id': tid, 'name': name, 'reason': 'not a person'})
            continue
        email = _primary_email(row)
        if not email:
            skipped.append({'task_id': tid, 'name': name, 'reason': 'no email'})
            continue
        if email in seen_email:
            skipped.append({'task_id': tid, 'name': name, 'reason': f'duplicate email {email}'})
            continue
        seen_email.add(email)
        first, _, _ = entity_actions.resolve_first_name(row, given.get((row.get('google_id') or '').strip()))
        create.append({
            'task_id': tid,
            'email': email,
            'name': name,
            'merge_data': _merge_data(row, first),
        })
    return create, skipped


def create_campaign(*, ids, subject_template='', body_template='', body_html_template='',
                    gmail_draft_id='', name='', delivery='draft',
                    from_email='', from_name='',
                    daily_limit=DEFAULT_DAILY_LIMIT, per_minute=DEFAULT_PER_MINUTE, user=''):
    source_draft_id = (gmail_draft_id or '').strip()
    subject_template = (subject_template or '').strip()
    body_template = (body_template or '').strip()
    body_html_template = (body_html_template or '').strip()

    attachments = []
    if source_draft_id:
        tpl = load_draft_template(source_draft_id)
        if not subject_template:
            subject_template = (tpl.get('subject') or '').strip()
        if not body_html_template:
            body_html_template = tpl.get('html') or ''
        if not body_template:
            body_template = tpl.get('text') or ''
        source_draft_id = tpl['draft_id']
        attachments = tpl.get('attachments') or []

    if not subject_template:
        raise MailMergeError('Subject template is required (or pick a Gmail draft that has one).')
    if not body_template and not body_html_template:
        raise MailMergeError('Body is required — pick a Gmail draft or paste plain text.')
    delivery = (delivery or MailCampaign.Delivery.DRAFT).strip().lower()
    if delivery not in MailCampaign.Delivery.values:
        raise MailMergeError('delivery must be draft or send.')
    daily_limit = max(1, min(int(daily_limit or DEFAULT_DAILY_LIMIT), HARD_DAILY_CAP))
    per_minute = max(1, min(int(per_minute or DEFAULT_PER_MINUTE), 60))

    # Always bind From to a verified send-as (default is usually a custom domain like deven@kalra.com).
    # Using the raw Google login (…@gmail.com) while the draft looks like a kalra.com letter
    # commonly trips "unauthorized sender" / phishing banners.
    ident = resolve_from_identity(from_email, from_name)

    create, skipped = _build_recipients(ids)
    if not create:
        raise MailMergeError('No sendable contacts (need People with an email).')

    with transaction.atomic():
        campaign = MailCampaign.objects.create(
            name=(name or '').strip() or f'Mail merge ({len(create)})',
            subject_template=subject_template,
            body_template=body_template,
            body_html_template=body_html_template,
            source_draft_id=source_draft_id,
            attachments=attachments,
            from_email=ident['email'],
            from_name=ident['name'],
            delivery=delivery,
            status=MailCampaign.Status.READY,
            daily_limit=daily_limit,
            per_minute=per_minute,
            created_by=user or '',
        )
        MailCampaignRecipient.objects.bulk_create([
            MailCampaignRecipient(
                campaign=campaign,
                task_id=r['task_id'],
                email=r['email'],
                name=r['name'],
                merge_data=r['merge_data'],
            ) for r in create
        ], batch_size=500)
    return serialize_campaign(campaign, include_preview=True, skipped=skipped)


def preview_rows(campaign, limit=25):
    rows = []
    for r in campaign.recipients.order_by('id')[:limit]:
        plain = render(campaign.body_template, r.merge_data)
        html_body = render(campaign.body_html_template, r.merge_data, escape_html=True) \
            if campaign.body_html_template else ''
        rows.append({
            'id': r.id,
            'task_id': r.task_id,
            'email': r.email,
            'name': r.name,
            'status': r.status,
            'subject': render(campaign.subject_template, r.merge_data),
            'body': plain or _snippet_plain('', html_body, 400),
            'body_html': html_body,
            'merge_data': r.merge_data,
        })
    return rows


def counts(campaign):
    agg = campaign.recipients.values('status').annotate(n=Count('id'))
    by = {row['status']: row['n'] for row in agg}
    return {
        'total': sum(by.values()),
        'pending': by.get(MailCampaignRecipient.Status.PENDING, 0),
        'sending': by.get(MailCampaignRecipient.Status.SENDING, 0),
        'sent': by.get(MailCampaignRecipient.Status.SENT, 0),
        'drafted': by.get(MailCampaignRecipient.Status.DRAFTED, 0),
        'skipped': by.get(MailCampaignRecipient.Status.SKIPPED, 0),
        'failed': by.get(MailCampaignRecipient.Status.FAILED, 0),
        'done': (
            by.get(MailCampaignRecipient.Status.SENT, 0)
            + by.get(MailCampaignRecipient.Status.DRAFTED, 0)
        ),
    }


def sent_today(campaign=None):
    """Successful deliveries today (UTC date) across one campaign or all."""
    start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    qs = MailCampaignRecipient.objects.filter(
        status__in=(MailCampaignRecipient.Status.SENT, MailCampaignRecipient.Status.DRAFTED),
        sent_at__gte=start,
    )
    if campaign is not None:
        qs = qs.filter(campaign=campaign)
    return qs.count()


def serialize_campaign(campaign, *, include_preview=False, include_recipients=False, skipped=None):
    c = counts(campaign)
    today = sent_today(campaign)
    out = {
        'id': campaign.id,
        'name': campaign.name,
        'subject_template': campaign.subject_template,
        'body_template': campaign.body_template,
        'body_html_template': campaign.body_html_template,
        'source_draft_id': campaign.source_draft_id,
        'has_html': bool(campaign.body_html_template),
        'attachment_names': [
            a.get('filename') or 'attachment' for a in (campaign.attachments or [])
        ],
        'from_email': campaign.from_email,
        'from_name': campaign.from_name,
        'delivery': campaign.delivery,
        'status': campaign.status,
        'daily_limit': campaign.daily_limit,
        'per_minute': campaign.per_minute,
        'created_by': campaign.created_by,
        'error': campaign.error,
        'created_at': campaign.created_at.isoformat() if campaign.created_at else None,
        'started_at': campaign.started_at.isoformat() if campaign.started_at else None,
        'finished_at': campaign.finished_at.isoformat() if campaign.finished_at else None,
        'last_tick_at': campaign.last_tick_at.isoformat() if campaign.last_tick_at else None,
        'counts': c,
        'sent_today': today,
        'budget_today': max(0, campaign.daily_limit - today),
    }
    if skipped is not None:
        out['skipped_on_create'] = skipped
    if include_preview:
        out['preview'] = preview_rows(campaign)
    if include_recipients:
        out['recipients'] = [
            {
                'id': r.id, 'task_id': r.task_id, 'email': r.email, 'name': r.name,
                'status': r.status, 'attempts': r.attempts, 'last_error': r.last_error,
                'provider_message_id': r.provider_message_id,
                'sent_at': r.sent_at.isoformat() if r.sent_at else None,
            }
            for r in campaign.recipients.order_by('id')[:2000]
        ]
    return out


def _require_mail_account():
    account = GoogleAccount.objects.order_by('id').first()
    if not account or not account.refresh_token:
        raise MailMergeError('Connect Google first (Overview tab).', 400)
    if not account.can_mail:
        raise MailMergeError(
            'Grant Gmail access from Overview (Connect Google with mail), then retry.', 400)
    return account


def start_campaign(campaign_id):
    campaign = MailCampaign.objects.filter(pk=campaign_id).first()
    if not campaign:
        raise MailMergeError('Campaign not found.', 404)
    if campaign.status in (MailCampaign.Status.COMPLETED, MailCampaign.Status.CANCELLED):
        raise MailMergeError(f'Campaign is {campaign.status}; create a new one.')
    if campaign.status == MailCampaign.Status.RUNNING:
        return serialize_campaign(campaign)
    _require_mail_account()
    if campaign.delivery == MailCampaign.Delivery.SEND and not google_auth.account_can_send():
        raise MailMergeError('Sending needs the Gmail send scope; reconnect Google with mail access.')
    pending = campaign.recipients.filter(status=MailCampaignRecipient.Status.PENDING).exists()
    if not pending and not campaign.recipients.filter(status=MailCampaignRecipient.Status.SENDING).exists():
        # Only failed left — treat as needing retry
        if campaign.recipients.filter(status=MailCampaignRecipient.Status.FAILED).exists():
            raise MailMergeError('No pending recipients. Use Retry failed first.')
        campaign.status = MailCampaign.Status.COMPLETED
        campaign.finished_at = timezone.now()
        campaign.save(update_fields=['status', 'finished_at'])
        return serialize_campaign(campaign)
    campaign.status = MailCampaign.Status.RUNNING
    campaign.error = ''
    if not campaign.started_at:
        campaign.started_at = timezone.now()
    campaign.finished_at = None
    campaign.save(update_fields=['status', 'error', 'started_at', 'finished_at'])
    return serialize_campaign(campaign)


def pause_campaign(campaign_id):
    campaign = MailCampaign.objects.filter(pk=campaign_id).first()
    if not campaign:
        raise MailMergeError('Campaign not found.', 404)
    if campaign.status not in (MailCampaign.Status.RUNNING, MailCampaign.Status.WAITING_QUOTA):
        raise MailMergeError('Only a running campaign can be paused.')
    campaign.status = MailCampaign.Status.PAUSED
    campaign.save(update_fields=['status'])
    return serialize_campaign(campaign)


def cancel_campaign(campaign_id):
    campaign = MailCampaign.objects.filter(pk=campaign_id).first()
    if not campaign:
        raise MailMergeError('Campaign not found.', 404)
    if campaign.status == MailCampaign.Status.COMPLETED:
        raise MailMergeError('Campaign already completed.')
    with transaction.atomic():
        campaign.recipients.filter(status=MailCampaignRecipient.Status.PENDING).update(
            status=MailCampaignRecipient.Status.SKIPPED,
            last_error='Cancelled',
        )
        campaign.status = MailCampaign.Status.CANCELLED
        campaign.finished_at = timezone.now()
        campaign.save(update_fields=['status', 'finished_at'])
    return serialize_campaign(campaign)


def retry_failed(campaign_id):
    campaign = MailCampaign.objects.filter(pk=campaign_id).first()
    if not campaign:
        raise MailMergeError('Campaign not found.', 404)
    n = campaign.recipients.filter(status=MailCampaignRecipient.Status.FAILED).update(
        status=MailCampaignRecipient.Status.PENDING,
        last_error='',
        attempts=0,
        provider_message_id='',
        sent_at=None,
    )
    if campaign.status in (MailCampaign.Status.COMPLETED, MailCampaign.Status.FAILED,
                           MailCampaign.Status.CANCELLED, MailCampaign.Status.PAUSED,
                           MailCampaign.Status.WAITING_QUOTA):
        campaign.status = MailCampaign.Status.READY if n else campaign.status
        campaign.finished_at = None
        campaign.error = ''
        campaign.save(update_fields=['status', 'finished_at', 'error'])
    return serialize_campaign(campaign)


def _mime_attachment_part(att):
    """Build a MIME part from a frozen campaign attachment dict."""
    raw = base64.b64decode(att.get('data_b64') or '', validate=False)
    mime = (att.get('mime_type') or 'application/octet-stream').split(';', 1)[0].strip()
    main, _, sub = mime.partition('/')
    if not main or not sub:
        main, sub = 'application', 'octet-stream'
    part = MIMEBase(main, sub)
    part.set_payload(raw)
    encoders.encode_base64(part)
    filename = (att.get('filename') or 'attachment').replace('"', '')
    content_id = (att.get('content_id') or '').strip().strip('<>')
    inline = bool(att.get('inline') and content_id)
    if inline:
        part.add_header('Content-ID', f'<{content_id}>')
        part.add_header('Content-Disposition', 'inline', filename=filename)
    else:
        part.add_header('Content-Disposition', 'attachment', filename=filename)
    return part


def _mime_raw(to_email, subject, plain, html_body, from_header, attachments=None):
    plain = plain or ''
    html_body = html_body or ''
    attachments = attachments or []
    inline = [a for a in attachments if a.get('inline') and a.get('content_id')]
    files = [a for a in attachments if not (a.get('inline') and a.get('content_id'))]

    if html_body and plain:
        alt = MIMEMultipart('alternative')
        alt.attach(MIMEText(plain, 'plain', 'utf-8'))
        alt.attach(MIMEText(html_body, 'html', 'utf-8'))
        body = alt
    elif html_body:
        body = MIMEText(html_body, 'html', 'utf-8')
    else:
        body = MIMEText(plain, 'plain', 'utf-8')

    if inline:
        related = MIMEMultipart('related')
        related.attach(body)
        for att in inline:
            related.attach(_mime_attachment_part(att))
        body = related

    if files:
        msg = MIMEMultipart('mixed')
        msg.attach(body)
        for att in files:
            msg.attach(_mime_attachment_part(att))
    else:
        msg = body

    msg['To'] = to_email
    if from_header:
        msg['From'] = from_header
    msg['Subject'] = subject
    return base64.urlsafe_b64encode(msg.as_bytes()).decode().rstrip('=')


def _deliver(service, campaign, recipient, from_header):
    if recipient.provider_message_id:
        return recipient.provider_message_id
    subject = render(campaign.subject_template, recipient.merge_data)
    plain = render(campaign.body_template, recipient.merge_data)
    html_body = render(campaign.body_html_template, recipient.merge_data, escape_html=True) \
        if campaign.body_html_template else ''
    raw = _mime_raw(
        recipient.email, subject, plain, html_body, from_header,
        attachments=campaign.attachments or [],
    )
    if campaign.delivery == MailCampaign.Delivery.DRAFT:
        created = service.users().drafts().create(
            userId='me', body={'message': {'raw': raw}}).execute()
        return created.get('id') or created.get('message', {}).get('id') or ''
    sent = service.users().messages().send(userId='me', body={'raw': raw}).execute()
    return sent.get('id') or ''


def recover_stale_sending():
    cutoff = timezone.now() - STALE_SENDING
    for r in MailCampaignRecipient.objects.filter(
        status=MailCampaignRecipient.Status.SENDING,
    ).select_related('campaign'):
        camp = r.campaign
        tick = camp.last_tick_at
        if tick and tick >= cutoff and camp.status == MailCampaign.Status.RUNNING:
            continue
        if r.attempts >= MAX_ATTEMPTS:
            r.status = MailCampaignRecipient.Status.FAILED
            r.last_error = r.last_error or 'Stuck in sending; max attempts reached after restart.'
        else:
            r.status = MailCampaignRecipient.Status.PENDING
            r.last_error = 'Reset after server restart'
        r.save(update_fields=['status', 'last_error'])


def _claim_batch(campaign, n):
    """Mark up to n pending rows as sending; return claimed ids (atomic per row)."""
    claimed = []
    candidates = list(
        campaign.recipients.filter(status=MailCampaignRecipient.Status.PENDING)
        .order_by('id')
        .values_list('id', flat=True)[:n]
    )
    for rid in candidates:
        updated = MailCampaignRecipient.objects.filter(
            pk=rid, status=MailCampaignRecipient.Status.PENDING,
        ).update(
            status=MailCampaignRecipient.Status.SENDING,
            attempts=F('attempts') + 1,
        )
        if updated:
            claimed.append(rid)
    return claimed


def _finish_if_idle(campaign):
    left = campaign.recipients.filter(
        status__in=(MailCampaignRecipient.Status.PENDING, MailCampaignRecipient.Status.SENDING),
    ).exists()
    if left:
        return
    failed = campaign.recipients.filter(status=MailCampaignRecipient.Status.FAILED).exists()
    campaign.status = MailCampaign.Status.FAILED if failed and not campaign.recipients.filter(
        status__in=(MailCampaignRecipient.Status.SENT, MailCampaignRecipient.Status.DRAFTED),
    ).exists() else MailCampaign.Status.COMPLETED
    campaign.finished_at = timezone.now()
    campaign.save(update_fields=['status', 'finished_at'])


def tick_campaign(campaign):
    """Process one throttle slice for a running/waiting campaign. Returns # delivered this tick."""
    if campaign.status == MailCampaign.Status.WAITING_QUOTA:
        if sent_today(campaign) >= campaign.daily_limit:
            return 0
        campaign.status = MailCampaign.Status.RUNNING
        campaign.save(update_fields=['status'])

    if campaign.status != MailCampaign.Status.RUNNING:
        return 0

    budget = campaign.daily_limit - sent_today(campaign)
    if budget <= 0:
        campaign.status = MailCampaign.Status.WAITING_QUOTA
        campaign.last_tick_at = timezone.now()
        campaign.save(update_fields=['status', 'last_tick_at'])
        return 0

    n = min(budget, campaign.per_minute)
    ids = _claim_batch(campaign, n)
    campaign.last_tick_at = timezone.now()
    campaign.save(update_fields=['last_tick_at'])
    if not ids:
        _finish_if_idle(campaign)
        return 0

    try:
        account = _require_mail_account()
        service = google_auth.gmail_service(account)
        ident = resolve_from_identity(campaign.from_email, campaign.from_name)
        # Persist resolved From if the campaign was created before send-as support.
        if not campaign.from_email:
            campaign.from_email = ident['email']
            campaign.from_name = ident['name']
            campaign.save(update_fields=['from_email', 'from_name'])
        from_header = format_from_header(ident['email'], ident['name'])
    except MailMergeError as e:
        MailCampaignRecipient.objects.filter(pk__in=ids).update(
            status=MailCampaignRecipient.Status.PENDING, last_error=str(e))
        campaign.status = MailCampaign.Status.PAUSED
        campaign.error = str(e)
        campaign.save(update_fields=['status', 'error'])
        return 0

    done_status = (
        MailCampaignRecipient.Status.DRAFTED
        if campaign.delivery == MailCampaign.Delivery.DRAFT
        else MailCampaignRecipient.Status.SENT
    )
    delivered = 0
    for rid in ids:
        r = MailCampaignRecipient.objects.filter(pk=rid).first()
        if not r or r.status != MailCampaignRecipient.Status.SENDING:
            continue
        try:
            mid = _deliver(service, campaign, r, from_header)
            r.status = done_status
            r.provider_message_id = mid or r.provider_message_id
            r.sent_at = timezone.now()
            r.last_error = ''
            r.save(update_fields=['status', 'provider_message_id', 'sent_at', 'last_error'])
            delivered += 1
        except Exception as e:
            logger.exception('Mail merge deliver failed for %s', r.email)
            err = str(e)[:500]
            if r.attempts >= MAX_ATTEMPTS:
                r.status = MailCampaignRecipient.Status.FAILED
            else:
                r.status = MailCampaignRecipient.Status.PENDING
            r.last_error = err
            r.save(update_fields=['status', 'last_error'])
            # Quota / rate limit: pause the campaign for the day or a bit
            low = err.lower()
            if 'quota' in low or 'rate limit' in low or 'user-rate' in low:
                campaign.status = MailCampaign.Status.WAITING_QUOTA
                campaign.error = err
                campaign.save(update_fields=['status', 'error'])
                # put remaining claimed back
                MailCampaignRecipient.objects.filter(
                    campaign=campaign, status=MailCampaignRecipient.Status.SENDING,
                ).exclude(pk=r.pk).update(status=MailCampaignRecipient.Status.PENDING)
                break

    campaign = MailCampaign.objects.get(pk=campaign.pk)
    _finish_if_idle(campaign)
    campaign.refresh_from_db()
    if (campaign.status == MailCampaign.Status.RUNNING
            and campaign.recipients.filter(status=MailCampaignRecipient.Status.PENDING).exists()
            and sent_today(campaign) >= campaign.daily_limit):
        campaign.status = MailCampaign.Status.WAITING_QUOTA
        campaign.save(update_fields=['status'])
    return delivered


def tick_all():
    """Worker entry: recover stale rows, then tick active campaigns."""
    recover_stale_sending()
    active = list(MailCampaign.objects.filter(
        status__in=(MailCampaign.Status.RUNNING, MailCampaign.Status.WAITING_QUOTA),
    ).order_by('id'))
    total = 0
    for campaign in active:
        try:
            total += tick_campaign(campaign)
        except Exception:
            logger.exception('Mail merge tick failed for campaign %s', campaign.pk)
            MailCampaign.objects.filter(pk=campaign.pk).update(
                error='Worker tick failed; see server logs',
                status=MailCampaign.Status.PAUSED,
            )
    return total
