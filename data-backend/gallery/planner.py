"""Shot list: heuristic order plus optional LocalAI plan (phase 2)."""

from __future__ import annotations

import json
import logging
import os
import re

from .analyze import BLUR_SKIP_THRESHOLD, item_blur
from .presets import DEFAULT_STYLE, MAX_SHOTS, PRESETS

logger = logging.getLogger(__name__)

ROLES = frozenset({'opener', 'hero', 'detail', 'pair', 'bridge', 'closer'})
FOCUSES = frozenset({'face', 'center', 'subject'})
LLM_TIMEOUT = 90.0
_THINK_RE = re.compile(r'<think>.*?</think>', re.IGNORECASE | re.DOTALL)
_FENCE_RE = re.compile(r'```(?:json)?\s*([\s\S]*?)```', re.IGNORECASE)

SYSTEM_PROMPT = """You are sequencing a slideshow. Return JSON only, matching:
{"title": "string", "style": "kenburns|punchy|documentary|cinematic", "shots": [
  {"item_id": "id from cards", "role": "opener|hero|detail|bridge|closer",
   "seconds": 1-20, "focus": "face|center|subject", "skip": false}
]}
Rules:
- Do not invent item ids. Only use ids from the cards.
- Keep the given card order unless the user prompt asks to reorder or skip.
- skip:true to drop a shot (very blurry, near-duplicate, or the user asked to skip it).
- faces / face_kind / face_boxes are analyzer results. Use them:
  - focus "face" when faces > 0 (Ken Burns aims at the face cluster).
  - focus "center" when faces is 0.
  - Prefer face_kind "group" or a clear "portrait" as opener when the user does not specify.
  - Hold shots with faces a bit longer; keep no-face details shorter.
- Do not emit "with" or overlapping pairs.
- First kept shot is opener; last kept shot is closer.
"""


def plan_from_item_ids(item_ids, title='', style='kenburns', items_by_id=None):
    items_by_id = items_by_id or {}
    ids = [str(i) for i in (item_ids or []) if i]
    kept = []
    skipped_blurry = []
    for item_id in ids:
        item = items_by_id.get(item_id)
        if item is not None and item_blur(item) > BLUR_SKIP_THRESHOLD:
            skipped_blurry.append(item_id)
            continue
        kept.append(item_id)

    n = len(kept)
    shots = []
    for i, item_id in enumerate(kept):
        item = items_by_id.get(item_id)
        faces = _item_faces(item)
        if i == 0:
            role = 'opener'
        elif i == n - 1:
            role = 'closer'
        else:
            role = 'hero'
        shots.append({
            'item_id': item_id,
            'role': role,
            'focus': 'face' if faces else 'subject',
            'skip': False,
        })
    return {
        'title': title or '',
        'style': style,
        'shots': shots,
        'chapters': [],
        'skipped_blurry': skipped_blurry,
        'planner': 'heuristic',
    }


def feature_card(item, item_id=None) -> dict:
    """Text card for the LocalAI planner. Includes detected faces, not pixels."""
    if isinstance(item, dict):
        analysis = item.get('analysis') or {}
        item_id = str(item_id or item.get('id') or '')
        filename = item.get('filename') or ''
        caption = item.get('title') or item.get('caption') or ''
    else:
        analysis = getattr(item, 'analysis', None) or {}
        item_id = str(item_id or getattr(item, 'id', '') or '')
        filename = getattr(item, 'filename', '') or ''
        caption = getattr(item, 'title', '') or getattr(item, 'caption', '') or ''

    raw_faces = analysis.get('faces') if isinstance(analysis, dict) else []
    if not isinstance(raw_faces, list):
        raw_faces = []
    boxes = []
    for face in raw_faces[:8]:
        if not isinstance(face, dict):
            continue
        try:
            boxes.append({
                'x': round(float(face.get('x', 0)), 3),
                'y': round(float(face.get('y', 0)), 3),
                'w': round(float(face.get('w', 0)), 3),
                'h': round(float(face.get('h', 0)), 3),
            })
        except (TypeError, ValueError):
            continue
    n = len(raw_faces)
    if n >= 3:
        face_kind = 'group'
    elif n == 2:
        face_kind = 'pair'
    elif n == 1:
        face_kind = 'portrait'
    else:
        face_kind = 'none'
    subject = analysis.get('subject') if isinstance(analysis, dict) else None
    if not isinstance(subject, dict):
        subject = {'x': 0.5, 'y': 0.5}
    try:
        blur = float((analysis or {}).get('blur') or 0)
    except (TypeError, ValueError):
        blur = 0.0
    return {
        'id': item_id,
        'filename': filename,
        'caption': str(caption)[:120],
        'taken_at': (analysis or {}).get('taken_at'),
        'aspect': (analysis or {}).get('aspect'),
        'orientation': (analysis or {}).get('orientation'),
        'blur': blur,
        'faces': n,
        'face_kind': face_kind,
        'face_boxes': boxes,
        'subject': {
            'x': round(float(subject.get('x', 0.5) or 0.5), 3),
            'y': round(float(subject.get('y', 0.5) or 0.5), 3),
        },
    }


def build_plan(
    item_ids,
    items_by_id=None,
    prompt='',
    title='',
    style='kenburns',
    target_seconds=None,
    on_log=None,
):
    """Heuristic plan, replaced by a validated LocalAI plan when available."""
    items_by_id = items_by_id or {}
    heuristic = plan_from_item_ids(
        item_ids, title=title, style=style, items_by_id=items_by_id
    )
    ids = [str(i) for i in (item_ids or []) if i]
    cards = []
    for item_id in ids:
        item = items_by_id.get(item_id)
        if item is None:
            continue
        cards.append(feature_card(item, item_id=item_id))
    with_faces = sum(1 for c in cards if c.get('faces'))
    _emit(
        on_log,
        'planning',
        (
            f'{len(cards)} feature card(s), {with_faces} with faces; '
            f'heuristic kept {len(heuristic.get("shots") or [])} after blur skip.'
        ),
        data={
            'cards': [
                {
                    'id': c['id'],
                    'filename': c.get('filename'),
                    'faces': c.get('faces'),
                    'face_kind': c.get('face_kind'),
                    'blur': c.get('blur'),
                }
                for c in cards
            ],
            'skipped_blurry': heuristic.get('skipped_blurry') or [],
        },
    )

    if not llm_available():
        _emit(on_log, 'planning', 'LocalAI is not configured; using your order.', level='warn')
        return heuristic
    if not cards:
        return heuristic

    user_prompt = _user_prompt(prompt, style, target_seconds, cards)
    _emit(
        on_log,
        'planning',
        f'Calling LocalAI (timeout {int(LLM_TIMEOUT)}s).',
        data={'prompt_chars': len(user_prompt), 'prompt': (prompt or '')[:400]},
    )
    try:
        raw_text = _chat_completion(
            prompt=user_prompt,
            system=SYSTEM_PROMPT,
            json_mode=True,
            timeout=LLM_TIMEOUT,
        )
        preview = _THINK_RE.sub('', raw_text or '').strip()
        _emit(
            on_log,
            'planning',
            f'LocalAI returned {len(raw_text or "")} chars.',
            data={'preview': preview[:2000]},
        )
        raw_plan = extract_plan_json(raw_text)
        plan, warnings = validate_plan(raw_plan, [c['id'] for c in cards], title=title, style=style)
    except Exception as exc:  # noqa: BLE001
        logger.warning('Gallery LocalAI plan failed: %s', exc)
        heuristic['planner_error'] = _short_err(exc)
        _emit(
            on_log,
            'planning',
            f'LocalAI plan unused; using your order. {_short_err(exc)}',
            level='warn',
        )
        return heuristic

    plan['skipped_blurry'] = heuristic.get('skipped_blurry') or []
    plan['planner'] = 'llm'
    plan['planner_warnings'] = warnings
    if title and title.strip().lower() not in {'', 'show'}:
        plan['title'] = title.strip()[:80]
    _emit(
        on_log,
        'planning',
        f'Using LocalAI shot list ({len(plan.get("shots") or [])} shots).',
        data={'shots': plan.get('shots'), 'warnings': warnings},
    )
    return plan


def _emit(on_log, step, message, level='info', data=None):
    if not on_log:
        return
    kwargs = {'level': level}
    if data is not None:
        kwargs['data'] = data
    on_log(step, message, **kwargs)


def llm_available() -> bool:
    try:
        from django.conf import settings
    except Exception:
        settings = None
    url = (
        (getattr(settings, 'LOCALAI_URL', '') if settings else '')
        or os.environ.get('LOCALAI_URL', '')
        or ''
    ).strip()
    openai_key = (
        (getattr(settings, 'OPENAI_API_KEY', '') if settings else '')
        or os.environ.get('OPENAI_API_KEY', '')
        or ''
    ).strip()
    return bool(url or openai_key)


def extract_plan_json(text: str) -> dict:
    blob = _THINK_RE.sub('', text or '').strip()
    fence = _FENCE_RE.search(blob)
    if fence:
        blob = fence.group(1).strip()
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        start = blob.find('{')
        end = blob.rfind('}')
        if start < 0 or end <= start:
            raise ValueError('LocalAI did not return JSON')
        data = json.loads(blob[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError('LocalAI JSON is not an object')
    return data


def validate_plan(raw, allowed_ids, title='', style='kenburns'):
    """Return (plan, warnings). Raises ValueError if nothing usable remains."""
    if not isinstance(raw, dict):
        raise ValueError('Plan is not an object')
    shots_in = raw.get('shots')
    if not isinstance(shots_in, list) or not shots_in:
        raise ValueError('Plan has no shots')

    allowed = {str(i) for i in allowed_ids}
    warnings = []
    shots = []
    for shot in shots_in:
        if not isinstance(shot, dict):
            continue
        if shot.get('skip'):
            continue
        item_id = str(shot.get('item_id') or '')
        if item_id not in allowed:
            warnings.append(f'Dropped unknown item {item_id}.')
            continue
        role = str(shot.get('role') or 'hero').lower()
        if role not in ROLES:
            role = 'hero'
        focus = str(shot.get('focus') or 'subject').lower()
        if focus not in FOCUSES:
            focus = 'subject'
        seconds = shot.get('seconds')
        try:
            seconds = float(seconds) if seconds is not None else None
        except (TypeError, ValueError):
            seconds = None
        if seconds is not None:
            seconds = min(20.0, max(1.0, seconds))
        entry = {
            'item_id': item_id,
            'role': role,
            'focus': focus,
            'skip': False,
        }
        if seconds is not None:
            entry['seconds'] = seconds
        shots.append(entry)
        if len(shots) >= MAX_SHOTS:
            warnings.append(f'Trimmed to {MAX_SHOTS} shots.')
            break

    if not shots:
        raise ValueError('Plan has no valid shots')
    shots[0]['role'] = 'opener'
    if len(shots) > 1:
        shots[-1]['role'] = 'closer'

    out_style = str(raw.get('style') or style or DEFAULT_STYLE).lower()
    if out_style not in PRESETS:
        out_style = style if style in PRESETS else DEFAULT_STYLE
    out_title = str(raw.get('title') or title or '')[:80]
    return (
        {
            'title': out_title,
            'style': out_style,
            'shots': shots,
            'chapters': [],
        },
        warnings,
    )


def _item_faces(item) -> list:
    if item is None:
        return []
    if isinstance(item, dict):
        analysis = item.get('analysis') or {}
    else:
        analysis = getattr(item, 'analysis', None) or {}
    faces = analysis.get('faces') if isinstance(analysis, dict) else []
    return faces if isinstance(faces, list) else []


def _user_prompt(prompt, style, target_seconds, cards) -> str:
    request = (prompt or '').strip() or (
        '(none — keep the given order; use faces to pick opener/closer and focus)'
    )
    target = target_seconds if target_seconds is not None else 'unset'
    return (
        f'User request: {request}\n'
        f'Style: {style}\n'
        f'Target seconds: {target}\n'
        'Cards in play order (faces are detector boxes in 0–1 image coords):\n'
        f'{json.dumps(cards, ensure_ascii=False)}'
    )


def _short_err(exc) -> str:
    return str(exc).replace('\n', ' ').strip()[:160]


def _chat_completion(*, prompt, system, json_mode=True, timeout=LLM_TIMEOUT):
    from gmail_assistant.llm import chat_completion

    return chat_completion(
        prompt=prompt, system=system, json_mode=json_mode, timeout=timeout
    )
