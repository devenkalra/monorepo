"""Workflow implementations: ClickUp writing ideas + StaticFile image ingest."""

from __future__ import annotations

import io
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from email.utils import parseaddr

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone

logger = logging.getLogger(__name__)


def _clickup_token():
    return getattr(settings, 'CLICKUP_API_TOKEN', '') or ''


def _clickup_request(method, path, body=None):
    token = _clickup_token()
    if not token:
        raise RuntimeError('CLICKUP_API_TOKEN is not configured')
    url = f'https://api.clickup.com/api/v2{path}'
    data = None
    headers = {
        'Authorization': token,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }
    if body is not None:
        data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode('utf-8')
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(f'ClickUp {method} {path} failed ({exc.code}): {detail}') from exc


def create_writing_idea_task(message, classification):
    list_id = getattr(settings, 'EMAIL_CLICKUP_LIST_ID', '') or ''
    field_id = getattr(settings, 'EMAIL_CLICKUP_SENDER_FIELD_ID', '') or ''
    if not list_id:
        raise RuntimeError('EMAIL_CLICKUP_LIST_ID is not configured')

    extracted = classification.get('extracted') or {}
    title = (extracted.get('title') or message.subject or 'Writing idea').strip()[:200]
    urls = extracted.get('urls') or []
    summary = classification.get('summary') or message.snippet or ''
    lines = [summary.strip(), '']
    if urls:
        lines.append('## Links')
        for u in urls:
            lines.append(f'- {u}')
    lines.append('')
    lines.append(f'_Source email from {message.from_address}_')
    markdown = '\n'.join(lines).strip()

    task = _clickup_request(
        'POST',
        f'/list/{list_id}/task',
        {
            'name': title,
            'markdown_content': markdown,
            'status': 'to do',
        },
    )
    task_id = task.get('id')
    if field_id and task_id:
        _, sender_email = parseaddr(message.from_address)
        sender_email = sender_email or message.from_address
        try:
            _clickup_request(
                'POST',
                f'/task/{task_id}/field/{field_id}',
                {'value': sender_email},
            )
        except Exception as exc:
            logger.warning('Failed to set ClickUp sender field: %s', exc)
    return {'clickup_task_id': task_id, 'clickup_url': task.get('url') or ''}


def _openai_describe_image(image_bytes, filename=''):
    import base64
    from openai import OpenAI

    api_key = getattr(settings, 'EMAIL_OPENAI_API_KEY', '') or getattr(settings, 'OPENAI_API_KEY', '')
    model = getattr(settings, 'EMAIL_OPENAI_MODEL', 'gpt-4.1-mini')
    if not api_key:
        return ''
    client = OpenAI(api_key=api_key)
    b64 = base64.b64encode(image_bytes).decode('ascii')
    # Prefer vision-capable call; fall back silently
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{
                'role': 'user',
                'content': [
                    {
                        'type': 'text',
                        'text': f'Describe this image briefly for a personal media archive. Filename: {filename}',
                    },
                    {
                        'type': 'image_url',
                        'image_url': {'url': f'data:image/jpeg;base64,{b64}'},
                    },
                ],
            }],
            max_tokens=200,
        )
        return (resp.choices[0].message.content or '').strip()
    except Exception as exc:
        logger.warning('Image description failed: %s', exc)
        return ''


def _passes_image_gate(image_bytes):
    from PIL import Image

    if len(image_bytes) < 10 * 1024:
        return False
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            w, h = img.size
            if w < 100 or h < 100:
                return False
    except Exception:
        return False
    return True


def _save_static_file(image_bytes, filename, title, description=''):
    from core.models import StaticFile

    safe_name = re.sub(r'[^\w.\-]+', '_', filename or 'image.jpg')[:80]
    if '.' not in safe_name:
        safe_name += '.jpg'
    sf = StaticFile(
        title=(title or safe_name)[:200],
        filename=safe_name,
        make_local_copy=True,
    )
    # Put description into title suffix if model has no description field
    if description and not sf.title:
        sf.title = description[:200]
    elif description and description not in sf.title:
        sf.title = f'{sf.title} — {description}'[:200]
    sf.file.save(safe_name, ContentFile(image_bytes), save=False)
    sf.save()
    return {
        'static_file_id': sf.id,
        'media_url': f'/api/media/{sf.file.name}' if sf.file else '',
        'title': sf.title,
    }


def ingest_images_from_message(service, message, classification, gmail_payload):
    from . import gmail as gmail_api

    saved = []
    payload = gmail_payload.get('payload') or {}

    # MIME walk
    for mime, filename, content, part, attachment_id in gmail_api.walk_parts(payload):
        if not mime.startswith('image/'):
            continue
        data = content
        if data is None and attachment_id:
            data = gmail_api.download_attachment(service, message.gmail_id, attachment_id)
        if not data or not _passes_image_gate(data):
            continue
        desc = _openai_describe_image(data, filename)
        meta = _save_static_file(
            data,
            filename or f'{message.gmail_id}.jpg',
            title=filename or message.subject or 'Email image',
            description=desc,
        )
        meta['description'] = desc
        saved.append(meta)

    # HTML remote images
    _plain, html = gmail_api.get_text_bodies(payload)
    if html:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        for img in soup.find_all('img'):
            src = (img.get('src') or '').strip()
            if not src.startswith('http'):
                continue
            try:
                req = urllib.request.Request(src, headers={'User-Agent': 'devenkalra-email-processor/1.0'})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = resp.read()
                    ctype = resp.headers.get('Content-Type', 'image/jpeg')
            except Exception as exc:
                logger.info('Skip remote image %s: %s', src, exc)
                continue
            if not ctype.startswith('image/') or not _passes_image_gate(data):
                continue
            path = urllib.parse.urlparse(src).path
            fname = path.rsplit('/', 1)[-1] or 'remote.jpg'
            desc = _openai_describe_image(data, fname)
            meta = _save_static_file(data, fname, title=fname, description=desc)
            meta['source_url'] = src
            meta['description'] = desc
            saved.append(meta)

    if not saved:
        raise RuntimeError('No qualifying images found in message')
    return {'images': saved, 'count': len(saved)}


def run_workflow(kind, service, message, classification, gmail_payload=None):
    from .models import WorkflowRun

    run = WorkflowRun.objects.create(
        message=message,
        kind=kind,
        status=WorkflowRun.Status.RUNNING,
        started_at=timezone.now(),
    )
    try:
        if kind == WorkflowRun.Kind.WRITING_IDEA:
            result = create_writing_idea_task(message, classification)
        elif kind == WorkflowRun.Kind.IMAGE_INGEST:
            if gmail_payload is None:
                gmail_payload = gmail_api_fetch(service, message.gmail_id)
            result = ingest_images_from_message(service, message, classification, gmail_payload)
        elif kind in (WorkflowRun.Kind.IGNORE, WorkflowRun.Kind.NEWSLETTER):
            result = {'action': 'archive_only'}
        else:
            raise RuntimeError(f'Unsupported workflow kind: {kind}')

        run.status = WorkflowRun.Status.SUCCESS
        run.external_ids = result
        run.finished_at = timezone.now()
        run.save(update_fields=['status', 'external_ids', 'finished_at'])
        return run
    except Exception as exc:
        run.status = WorkflowRun.Status.FAILED
        run.error = str(exc)[:2000]
        run.finished_at = timezone.now()
        run.save(update_fields=['status', 'error', 'finished_at'])
        raise


def gmail_api_fetch(service, gmail_id):
    from . import gmail as gmail_api
    return gmail_api.fetch_message(service, gmail_id)
