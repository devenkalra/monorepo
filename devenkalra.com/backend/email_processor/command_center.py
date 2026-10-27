"""Interactive Command Center: NL → Gmail search → numbered select → batch action.

PRD §5 Prompt-to-Select. Session number→gmail_id mapping is stored in SQLite
(`CommandSession`) with a TTL instead of Redis (stack stays SQLite / in-process).
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from . import gmail as gmail_api
from .models import CommandSession, MailboxAccount
from .sync import get_active_mailbox, service_for

logger = logging.getLogger(__name__)

PROMPT_SCHEMA = {
    'name': 'email_command',
    'strict': True,
    'schema': {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'mode': {'type': 'string', 'enum': ['search', 'action', 'clarify']},
            'explanation': {'type': 'string'},
            'gmail_query': {'type': 'string'},
            'max_results': {'type': 'integer'},
            'action': {
                'type': 'string',
                'enum': [
                    'archive', 'trash', 'mark_read', 'mark_unread',
                    'label_processed', 'none',
                ],
            },
            'selection': {
                'type': 'string',
                'enum': ['all', 'indices', 'all_except', 'none'],
            },
            'indices': {
                'type': 'array',
                'items': {'type': 'integer'},
            },
            'needs_confirm': {'type': 'boolean'},
            'clarify_question': {'type': 'string'},
        },
        'required': [
            'mode', 'explanation', 'gmail_query', 'max_results',
            'action', 'selection', 'indices', 'needs_confirm', 'clarify_question',
        ],
    },
}

SYSTEM_PROMPT = """You are the Email Processor Command Center interpreter.
The user either searches Gmail or acts on a numbered result list from the previous search.

If the user is finding/listing/showing mail → mode=search.
Build a Gmail search query string (same syntax as Gmail UI), e.g.:
- newsletters today → category:promotions newer_than:1d OR subject:(newsletter OR digest) newer_than:1d
- unread from amazon → from:amazon is:unread
Prefer in:inbox unless they ask for all mail / archived / trash.
max_results default 25 (cap 50).

If there is an active numbered list and the user gives a batch command → mode=action.
Expand ranges in indices (1-based display numbers). "1,2,3-6" → indices=[1,2,3,4,5,6].
Examples:
- "Delete all except 3 and 5" → action=trash, selection=all_except, indices=[3,5]
- "Archive 1, 2, and 4" → action=archive, selection=indices, indices=[1,2,4]
- "Trash 1,2,3-6" → action=trash, selection=indices, indices=[1,2,3,4,5,6]
- "Archive 3-6 except keep none" → action=archive, selection=indices, indices=[3,4,5,6]
- "Mark all as read" → action=mark_read, selection=all
- "Trash everything" → action=trash, selection=all, needs_confirm=true
- "Mark 2-4 as processed" → action=label_processed, selection=indices, indices=[2,3,4]

Supported actions only: archive, trash, mark_read, mark_unread, label_processed.
Use action=trash for delete/remove (moves to Gmail Trash). Permanent delete is not supported.
label_processed applies the Processed label and archives (remove INBOX).
If the request is ambiguous or asks for an unsupported action → mode=clarify with clarify_question.
When mode=search leave action=none selection=none indices=[].
When mode=action leave gmail_query="" unless also starting a new search (prefer action alone).
"""


def session_ttl_seconds():
    return int(getattr(settings, 'EMAIL_COMMAND_SESSION_TTL', 3600) or 3600)


def purge_expired_sessions():
    CommandSession.objects.filter(expires_at__lt=timezone.now()).delete()


def get_active_session(user_id) -> CommandSession | None:
    purge_expired_sessions()
    return (
        CommandSession.objects
        .filter(user_id=user_id, expires_at__gte=timezone.now())
        .order_by('-updated_at')
        .first()
    )


def serialize_session(session: CommandSession | None):
    if not session:
        return None
    items = []
    for row in session.items or []:
        items.append({
            'n': row.get('n'),
            'gmail_id': row.get('gmail_id'),
            'thread_id': row.get('thread_id') or '',
            'subject': row.get('subject') or '',
            'from_address': row.get('from_address') or '',
            'snippet': row.get('snippet') or '',
            'received_at': row.get('received_at') or '',
            'label_ids': row.get('label_ids') or [],
        })
    return {
        'id': session.session_key,
        'prompt': session.prompt,
        'gmail_query': session.gmail_query,
        'explanation': session.explanation,
        'items': items,
        'expires_at': session.expires_at.isoformat() if session.expires_at else None,
        'last_action': session.last_action or '',
        'updated_at': session.updated_at.isoformat() if session.updated_at else None,
    }


def _renumber_session_items(session: CommandSession, remove_thread_ids=None, remove_gmail_ids=None):
    remove_threads = set(remove_thread_ids or [])
    remove_msgs = set(remove_gmail_ids or [])
    remaining = []
    for row in session.items or []:
        tid = row.get('thread_id') or ''
        mid = row.get('gmail_id') or ''
        if tid and tid in remove_threads:
            continue
        if mid and mid in remove_msgs:
            continue
        remaining.append(row)
    for i, row in enumerate(remaining, start=1):
        row['n'] = i
    session.items = remaining
    session.expires_at = timezone.now() + timedelta(seconds=session_ttl_seconds())
    session.save(update_fields=['items', 'expires_at', 'updated_at', 'last_action'])


SUMMARY_MAX_MESSAGES = 10
SUMMARY_BODY_CHARS = 4000

SUMMARY_SCHEMA = {
    'name': 'email_selection_summary',
    'strict': True,
    'schema': {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'brief_summary': {'type': 'string'},
            'key_points': {
                'type': 'array',
                'items': {'type': 'string'},
            },
            'detailed_summary': {'type': 'string'},
        },
        'required': ['brief_summary', 'key_points', 'detailed_summary'],
    },
}


def _resolve_selected_rows(session: CommandSession, *, thread_ids=None, gmail_ids=None) -> list[dict]:
    """Map requested thread/message ids onto active session rows (message-level)."""
    by_thread = {}
    by_gmail = {}
    for row in session.items or []:
        tid = row.get('thread_id') or ''
        mid = row.get('gmail_id') or ''
        if tid:
            by_thread.setdefault(tid, []).append(row)
        if mid:
            by_gmail[mid] = row

    requested_threads = [t for t in (thread_ids or []) if t]
    requested_msgs = [m for m in (gmail_ids or []) if m]
    rows = []
    seen = set()

    for mid in requested_msgs:
        row = by_gmail.get(mid)
        if not row:
            raise RuntimeError(f'Message {mid} is not in the active list.')
        if mid in seen:
            continue
        seen.add(mid)
        rows.append(row)

    for tid in requested_threads:
        if tid not in by_thread:
            raise RuntimeError(f'Thread {tid} is not in the active list.')
        for row in by_thread[tid]:
            mid = row.get('gmail_id') or ''
            if not mid or mid in seen:
                continue
            seen.add(mid)
            rows.append(row)

    if not rows:
        raise RuntimeError('Select at least one message/thread.')
    return rows


def summarize_selection(user_id, *, thread_ids=None, gmail_ids=None) -> dict:
    """Fetch full bodies for selected list messages and summarize with OpenAI."""
    mailbox = get_active_mailbox()
    if not mailbox or not mailbox.refresh_token:
        raise RuntimeError('Connect Gmail first.')

    session = get_active_session(user_id)
    if not session or not session.items:
        raise RuntimeError('No active numbered list. Run a search first.')

    rows = _resolve_selected_rows(session, thread_ids=thread_ids, gmail_ids=gmail_ids)
    if len(rows) > SUMMARY_MAX_MESSAGES:
        raise RuntimeError(
            f'Summarize supports up to {SUMMARY_MAX_MESSAGES} messages at a time '
            f'({len(rows)} selected). Narrow the selection and try again.'
        )

    service = service_for(mailbox)
    packed = []
    for row in rows:
        mid = row.get('gmail_id') or ''
        try:
            raw = gmail_api.fetch_message(service, mid)
            headers = gmail_api.header_map(raw.get('payload') or {})
            plain, html = gmail_api.get_text_bodies(raw.get('payload') or {})
            body = (plain or html or row.get('snippet') or '').strip()
            subject = headers.get('subject') or row.get('subject') or '(no subject)'
            from_address = headers.get('from') or row.get('from_address') or ''
        except Exception as exc:
            logger.warning('Failed to fetch message %s for summarize: %s', mid, exc)
            subject = row.get('subject') or '(no subject)'
            from_address = row.get('from_address') or ''
            body = (row.get('snippet') or '').strip() or f'(Could not fetch body: {exc})'
        packed.append({
            'n': row.get('n'),
            'gmail_id': mid,
            'thread_id': row.get('thread_id') or '',
            'subject': subject,
            'from_address': from_address,
            'body': body[:SUMMARY_BODY_CHARS],
        })

    client, model = _openai_client()
    blocks = []
    for item in packed:
        blocks.append(
            f"gmail_id: {item['gmail_id']}\n"
            f"n: {item.get('n')}\n"
            f"From: {item['from_address']}\n"
            f"Subject: {item['subject']}\n"
            f"Body:\n{item['body']}"
        )
    user_content = (
        f'Summarize these {len(packed)} email(s) for the user.\n\n'
        + '\n\n----- EMAIL -----\n\n'.join(blocks)
    )
    resp = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {
                'role': 'system',
                'content': (
                    'You summarize selected Gmail messages for a busy user. '
                    'Be concrete: asks, deadlines, money, links, decisions, action needed. '
                    'Avoid fluff and marketing filler.\n'
                    'Return three sections:\n'
                    '- brief_summary: 1–3 sentences, scannable overview.\n'
                    '- key_points: 3–8 short bullets covering the most important facts '
                    'across the selection (actions, dates, amounts, who/what).\n'
                    '- detailed_summary: a fuller narrative (a short paragraph or two) '
                    'covering context and nuances; mention individual emails when useful '
                    '(by subject/from).'
                ),
            },
            {'role': 'user', 'content': user_content},
        ],
        response_format={'type': 'json_schema', 'json_schema': SUMMARY_SCHEMA},
    )
    data = json.loads(resp.choices[0].message.content or '{}')
    brief_summary = (data.get('brief_summary') or '').strip()
    key_points = [
        str(point).strip()
        for point in (data.get('key_points') or [])
        if str(point).strip()
    ]
    detailed_summary = (data.get('detailed_summary') or '').strip()
    sources = [
        {
            'n': item.get('n'),
            'gmail_id': item['gmail_id'],
            'thread_id': item.get('thread_id') or '',
            'subject': item['subject'],
            'from_address': item['from_address'],
        }
        for item in packed
    ]

    session.last_action = json.dumps({
        'action': 'summarize',
        'count': len(sources),
        'source': 'selection',
        'model': model,
    })
    session.expires_at = timezone.now() + timedelta(seconds=session_ttl_seconds())
    session.save(update_fields=['last_action', 'expires_at', 'updated_at'])

    return {
        'type': 'summary',
        'action': 'summarize',
        'brief_summary': brief_summary,
        'key_points': key_points,
        'detailed_summary': detailed_summary,
        # Backward-compatible alias for older clients
        'summary': brief_summary,
        'items': sources,
        'model': model,
        'session': serialize_session(session),
        'explanation': f'Summarized {len(sources)} selected message(s).',
    }


def apply_selection_action(
    user_id,
    *,
    action: str,
    thread_ids=None,
    gmail_ids=None,
    label_id=None,
    label_name=None,
    confirm: bool = False,
) -> dict:
    """Deterministic bulk action on selected list rows via Gmail thread ids."""
    mailbox = get_active_mailbox()
    if not mailbox or not mailbox.refresh_token:
        raise RuntimeError('Connect Gmail first.')

    session = get_active_session(user_id)
    if not session or not session.items:
        raise RuntimeError('No active numbered list. Run a search first.')

    action = (action or '').strip().lower()
    if action == 'summarize':
        return summarize_selection(user_id, thread_ids=thread_ids, gmail_ids=gmail_ids)

    allowed = {'archive', 'trash', 'mark_read', 'mark_unread', 'label', 'label_processed'}
    if action not in allowed:
        raise RuntimeError(f'Unsupported action: {action}')

    by_thread = {}
    by_gmail = {}
    for row in session.items or []:
        tid = row.get('thread_id') or ''
        mid = row.get('gmail_id') or ''
        if tid:
            by_thread.setdefault(tid, []).append(row)
        if mid:
            by_gmail[mid] = row

    requested_threads = [t for t in (thread_ids or []) if t]
    requested_msgs = [m for m in (gmail_ids or []) if m]

    # Prefer thread ids; fall back to mapping message ids → thread ids from session
    resolved_threads = []
    for tid in requested_threads:
        if tid not in by_thread:
            raise RuntimeError(f'Thread {tid} is not in the active list.')
        resolved_threads.append(tid)
    for mid in requested_msgs:
        row = by_gmail.get(mid)
        if not row:
            raise RuntimeError(f'Message {mid} is not in the active list.')
        tid = row.get('thread_id') or ''
        if tid:
            resolved_threads.append(tid)
        else:
            raise RuntimeError(f'Message {mid} has no thread_id; cannot act deterministically.')

    resolved_threads = list(dict.fromkeys(resolved_threads))
    if not resolved_threads:
        raise RuntimeError('Select at least one message/thread.')

    if action == 'trash' and not confirm:
        targets = []
        for tid in resolved_threads:
            row = (by_thread.get(tid) or [{}])[0]
            targets.append({
                'thread_id': tid,
                'n': row.get('n'),
                'subject': row.get('subject'),
                'from_address': row.get('from_address'),
            })
        return {
            'type': 'confirm',
            'action': action,
            'target_count': len(resolved_threads),
            'thread_ids': resolved_threads,
            'targets': targets,
            'session': serialize_session(session),
            'detail': (
                f'Confirm trash on {len(resolved_threads)} thread(s). '
                'Resubmit with confirm=true.'
            ),
        }

    if action == 'label' and not (label_id or label_name):
        raise RuntimeError('Assign label requires label_id or label_name.')

    service = service_for(mailbox)
    result = gmail_api.batch_thread_action(
        service,
        resolved_threads,
        action,
        label_id=label_id,
        label_name=label_name,
    )

    session.last_action = json.dumps({
        'action': action,
        'thread_ids': resolved_threads,
        'label_id': label_id,
        'label_name': label_name,
        'result': result,
        'source': 'selection',
    })
    # Remove acted threads from the list (archive/trash/processed); keep for label-only
    if action in ('archive', 'trash', 'label_processed'):
        _renumber_session_items(session, remove_thread_ids=resolved_threads)
    else:
        session.expires_at = timezone.now() + timedelta(seconds=session_ttl_seconds())
        session.save(update_fields=['last_action', 'expires_at', 'updated_at'])

    return {
        'type': 'action',
        'action': action,
        'affected': result.get('affected', 0),
        'thread_ids': resolved_threads,
        'result': result,
        'session': serialize_session(session),
        'explanation': f'{action} applied to {len(resolved_threads)} thread(s).',
    }


def _openai_client():
    from openai import OpenAI
    api_key = getattr(settings, 'EMAIL_OPENAI_API_KEY', '') or getattr(settings, 'OPENAI_API_KEY', '')
    if not api_key:
        raise RuntimeError('EMAIL_OPENAI_API_KEY (or OPENAI_API_KEY) is not configured')
    return OpenAI(api_key=api_key), getattr(settings, 'EMAIL_OPENAI_MODEL', 'gpt-4.1-mini')


def interpret_prompt(prompt: str, session: CommandSession | None) -> dict:
    client, model = _openai_client()
    context = 'No active numbered list.'
    if session and session.items:
        preview = []
        for row in session.items[:40]:
            preview.append(
                f"{row.get('n')}. {row.get('subject') or '(no subject)'} "
                f"— from {row.get('from_address') or '?'}"
            )
        context = (
            f"Active list ({len(session.items)} items), query={session.gmail_query!r}:\n"
            + '\n'.join(preview)
        )

    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {
                'role': 'user',
                'content': f'Context:\n{context}\n\nUser prompt:\n{prompt}',
            },
        ],
        response_format={
            'type': 'json_schema',
            'json_schema': PROMPT_SCHEMA,
        },
    )
    raw = resp.choices[0].message.content or '{}'
    data = json.loads(raw)
    data['model'] = model
    return data


def _heuristic_interpret(prompt: str, session: CommandSession | None) -> dict | None:
    """Cheap fallback when OpenAI is unavailable for common patterns."""
    text = (prompt or '').strip()
    lower = text.lower()
    if not text:
        return None

    # Action patterns when a session exists
    if session and session.items:
        m = re.search(
            r'(?:delete|trash|remove)\s+(?:all\s+)?except\s+([\d,\s\-and]+)',
            lower,
        )
        if m:
            indices = parse_index_text(m.group(1))
            return {
                'mode': 'action',
                'explanation': 'Trash all listed messages except the given numbers.',
                'gmail_query': '',
                'max_results': 25,
                'action': 'trash',
                'selection': 'all_except',
                'indices': indices,
                'needs_confirm': True,
                'clarify_question': '',
                'model': 'heuristic',
            }
        m = re.search(r'(?:archive)\s+(?:all\s+)?except\s+([\d,\s\-and]+)', lower)
        if m:
            indices = parse_index_text(m.group(1))
            return {
                'mode': 'action',
                'explanation': 'Archive all listed messages except the given numbers.',
                'gmail_query': '',
                'max_results': 25,
                'action': 'archive',
                'selection': 'all_except',
                'indices': indices,
                'needs_confirm': False,
                'clarify_question': '',
                'model': 'heuristic',
            }
        m = re.search(
            r'(?:archive|trash|delete|mark\s+read|mark\s+as\s+read|mark\s+processed|'
            r'label\s+processed)\s+([\d,\s\-and]+)$',
            lower,
        )
        if m and re.search(r'\d', m.group(1)):
            action = 'archive'
            if 'trash' in lower or 'delete' in lower:
                action = 'trash'
            elif 'mark read' in lower or 'mark as read' in lower:
                action = 'mark_read'
            elif 'processed' in lower:
                action = 'label_processed'
            indices = parse_index_text(m.group(1))
            return {
                'mode': 'action',
                'explanation': f'{action} selected numbers.',
                'gmail_query': '',
                'max_results': 25,
                'action': action,
                'selection': 'indices',
                'indices': indices,
                'needs_confirm': action == 'trash',
                'clarify_question': '',
                'model': 'heuristic',
            }
        if re.search(r'^(archive|trash|delete)\s+all\b', lower):
            action = 'trash' if ('trash' in lower or 'delete' in lower) else 'archive'
            return {
                'mode': 'action',
                'explanation': f'{action} entire list.',
                'gmail_query': '',
                'max_results': 25,
                'action': action,
                'selection': 'all',
                'indices': [],
                'needs_confirm': action == 'trash',
                'clarify_question': '',
                'model': 'heuristic',
            }

    # Simple search heuristics
    if re.search(r'\b(find|show|list|search)\b', lower) or not session:
        q_parts = ['in:inbox']
        if 'newsletter' in lower or 'promotion' in lower:
            q_parts.append('(category:promotions OR unsubscribe OR newsletter OR digest)')
        if 'today' in lower:
            q_parts.append('newer_than:1d')
        elif 'this week' in lower or 'past week' in lower:
            q_parts.append('newer_than:7d')
        if 'unread' in lower:
            q_parts.append('is:unread')
        return {
            'mode': 'search',
            'explanation': 'Heuristic Gmail search from prompt keywords.',
            'gmail_query': ' '.join(q_parts),
            'max_results': 25,
            'action': 'none',
            'selection': 'none',
            'indices': [],
            'needs_confirm': False,
            'clarify_question': '',
            'model': 'heuristic',
        }
    return None


def expand_index_tokens(raw_indices) -> list[int]:
    """Expand display numbers and ranges. Accepts [1,2,3] or ['1','2','3-6'] or '1,2,3-6'."""
    if raw_indices is None:
        return []
    if isinstance(raw_indices, int):
        return [raw_indices]
    if isinstance(raw_indices, str):
        tokens = re.split(r'[\s,;]+', raw_indices.strip())
    else:
        tokens = list(raw_indices)

    out = []
    for token in tokens:
        if token is None or token == '':
            continue
        if isinstance(token, int):
            out.append(token)
            continue
        text = str(token).strip()
        # Bare number that may have been split from a range already
        if re.fullmatch(r'\d+', text):
            out.append(int(text))
            continue
        m = re.fullmatch(r'(\d+)\s*-\s*(\d+)', text)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a > b:
                a, b = b, a
            out.extend(range(a, b + 1))
            continue
        # Fallback: pull integers (does not expand ranges embedded without hyphen token)
        out.extend(int(x) for x in re.findall(r'\d+', text))

    # Dedupe preserving order
    seen = set()
    ordered = []
    for n in out:
        if n in seen:
            continue
        seen.add(n)
        ordered.append(n)
    return ordered


def parse_index_text(text: str) -> list[int]:
    """Parse '1, 2, 3-6 and 8' into a flat index list."""
    if not text:
        return []
    tokens = re.findall(r'\d+\s*-\s*\d+|\d+', text)
    return expand_index_tokens(tokens)


def resolve_indices(session: CommandSession, selection: str, indices) -> list[str]:
    by_n = {int(row['n']): row['gmail_id'] for row in (session.items or []) if row.get('n')}
    all_ids = [row['gmail_id'] for row in (session.items or []) if row.get('gmail_id')]
    wanted = {i for i in expand_index_tokens(indices) if i in by_n}

    if selection == 'all':
        return all_ids
    if selection == 'indices':
        return [by_n[i] for i in sorted(wanted)]
    if selection == 'all_except':
        return [by_n[n] for n in sorted(by_n) if n not in wanted]
    return []


def run_search(mailbox: MailboxAccount, user_id, prompt: str, plan: dict) -> dict:
    service = service_for(mailbox)
    query = (plan.get('gmail_query') or 'in:inbox').strip()
    max_results = max(1, min(int(plan.get('max_results') or 25), 50))
    metas = gmail_api.list_messages_metadata(service, query=query, max_results=max_results)

    items = []
    for i, meta in enumerate(metas, start=1):
        items.append({
            'n': i,
            'gmail_id': meta['id'],
            'thread_id': meta.get('thread_id') or '',
            'subject': meta.get('subject') or '',
            'from_address': meta.get('from_address') or '',
            'snippet': meta.get('snippet') or '',
            'received_at': meta.get('received_at') or '',
            'label_ids': meta.get('label_ids') or [],
        })

    # Replace prior sessions for this user (single active list)
    CommandSession.objects.filter(user_id=user_id).delete()
    session = CommandSession.objects.create(
        session_key=uuid.uuid4().hex,
        user_id=user_id,
        mailbox=mailbox,
        prompt=prompt,
        gmail_query=query,
        explanation=plan.get('explanation') or '',
        items=items,
        expires_at=timezone.now() + timedelta(seconds=session_ttl_seconds()),
        last_action='',
    )
    return {
        'type': 'search',
        'explanation': plan.get('explanation') or '',
        'gmail_query': query,
        'count': len(items),
        'session': serialize_session(session),
        'model': plan.get('model') or '',
    }


def run_action(
    mailbox: MailboxAccount,
    session: CommandSession,
    plan: dict,
    *,
    confirm: bool = False,
) -> dict:
    action = plan.get('action') or 'none'
    selection = plan.get('selection') or 'none'
    indices = plan.get('indices') or []
    needs_confirm = bool(plan.get('needs_confirm')) or action == 'trash'

    if action in ('none', '') or selection in ('none', ''):
        raise RuntimeError('No actionable selection in that command.')

    gmail_ids = resolve_indices(session, selection, indices)
    if not gmail_ids:
        raise RuntimeError('No messages matched those numbers. Refresh the list and try again.')

    if needs_confirm and not confirm:
        return {
            'type': 'confirm',
            'explanation': plan.get('explanation') or '',
            'action': action,
            'selection': selection,
            'indices': indices,
            'target_count': len(gmail_ids),
            'targets': [
                {
                    'n': row.get('n'),
                    'subject': row.get('subject'),
                    'from_address': row.get('from_address'),
                }
                for row in (session.items or [])
                if row.get('gmail_id') in set(gmail_ids)
            ][:50],
            'session': serialize_session(session),
            'model': plan.get('model') or '',
            'detail': (
                f'Confirm {action} on {len(gmail_ids)} message(s). '
                'Resubmit the same prompt with confirm=true.'
            ),
        }

    service = service_for(mailbox)
    result = gmail_api.batch_mailbox_action(service, gmail_ids, action)

    session.last_action = json.dumps({
        'action': action,
        'selection': selection,
        'indices': indices,
        'count': len(gmail_ids),
        'result': result,
    })
    # Drop acted-on messages from the numbered list so numbers stay meaningful
    acted = set(gmail_ids)
    remaining = []
    for row in session.items or []:
        if row.get('gmail_id') in acted:
            continue
        remaining.append(row)
    for i, row in enumerate(remaining, start=1):
        row['n'] = i
    session.items = remaining
    session.expires_at = timezone.now() + timedelta(seconds=session_ttl_seconds())
    session.save(update_fields=['items', 'last_action', 'expires_at', 'updated_at'])

    return {
        'type': 'action',
        'explanation': plan.get('explanation') or '',
        'action': action,
        'affected': len(gmail_ids),
        'gmail_ids': gmail_ids,
        'result': result,
        'session': serialize_session(session),
        'model': plan.get('model') or '',
    }


def handle_command(user_id, prompt: str, *, confirm: bool = False, force_search: bool = False) -> dict:
    mailbox = get_active_mailbox()
    if not mailbox or not mailbox.refresh_token:
        raise RuntimeError('Connect Gmail first.')

    prompt = (prompt or '').strip()
    if not prompt:
        raise RuntimeError('Prompt is required.')

    session = get_active_session(user_id)
    try:
        plan = interpret_prompt(prompt, None if force_search else session)
    except Exception as exc:
        logger.warning('Command NL parse failed (%s); trying heuristic', exc)
        plan = _heuristic_interpret(prompt, None if force_search else session)
        if not plan:
            raise RuntimeError(f'Could not interpret prompt: {exc}') from exc

    mode = plan.get('mode') or 'clarify'
    if mode == 'clarify':
        return {
            'type': 'clarify',
            'explanation': plan.get('explanation') or '',
            'question': plan.get('clarify_question') or plan.get('explanation') or 'Please clarify.',
            'session': serialize_session(session),
            'model': plan.get('model') or '',
        }

    if mode == 'search' or force_search:
        return run_search(mailbox, user_id, prompt, plan)

    if mode == 'action':
        if not session or not session.items:
            # Treat as search if they spoke like a finder
            if plan.get('gmail_query'):
                return run_search(mailbox, user_id, prompt, plan)
            raise RuntimeError(
                'No active numbered list. Run a search first '
                '(e.g. "Find all newsletters from today").'
            )
        return run_action(mailbox, session, plan, confirm=confirm)

    raise RuntimeError(f'Unknown command mode: {mode}')
