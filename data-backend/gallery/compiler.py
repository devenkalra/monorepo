"""Compile a shot list into GalleryShow.config.

All clips sit on channel A. Crossfades between consecutive A clips would need
a ping-pong onto B plus a reverse blend (B out, A in). Phase 0 uses fade-in /
fade-out on each clip instead, which works for slide 2, 3, … without reverse
blend.
"""

from __future__ import annotations

import uuid

from .analyze import item_subject
from .presets import DEFAULT_STYLE, MAX_SHOTS, MAX_TARGET, MIN_CLIP, MIN_TARGET, PRESETS


def round2(n):
    return round(float(n) * 100) / 100


def new_clip_id():
    return str(uuid.uuid4())


def _view(*, name, time, zoom, x, y, crop_top=0.0, crop_bottom=0.0):
    return {
        'name': name,
        'time': round2(time),
        'zoom': zoom,
        'zoomX': zoom,
        'zoomY': zoom,
        'x': x,
        'y': y,
        'rotation': 0,
        'opacity': 1,
        'pitch': 0,
        'yaw': 0,
        'anchorX': x,
        'anchorY': y,
        'cropLeft': 0,
        'cropRight': 0,
        'cropTop': crop_top,
        'cropBottom': crop_bottom,
    }


def ken_burns_views(duration, zoom_end=1.15, x=0.5, y=0.5, crop_top=0.0, crop_bottom=0.0):
    d = max(MIN_CLIP, float(duration))
    return [
        _view(name='Start', time=0, zoom=1.0, x=x, y=y, crop_top=crop_top, crop_bottom=crop_bottom),
        _view(name='End', time=d, zoom=zoom_end, x=x, y=y, crop_top=crop_top, crop_bottom=crop_bottom),
    ]


def compile_show(plan, items_by_id, style=None, target_seconds=None):
    """Return (config, warnings). items_by_id maps str(id) -> object with optional .id."""
    warnings = []
    style_key = (style or (plan or {}).get('style') or DEFAULT_STYLE).lower()
    if style_key not in PRESETS:
        warnings.append(f'Unknown style {style_key}; using {DEFAULT_STYLE}.')
        style_key = DEFAULT_STYLE
    preset = PRESETS[style_key]

    shots = []
    for shot in (plan or {}).get('shots') or []:
        if shot.get('skip'):
            continue
        item_id = str(shot.get('item_id') or '')
        if not item_id:
            continue
        if item_id not in items_by_id:
            warnings.append(f'Dropped unknown item {item_id}.')
            continue
        shots.append({**shot, 'item_id': item_id})
        if len(shots) >= MAX_SHOTS:
            warnings.append(f'Trimmed to {MAX_SHOTS} shots.')
            break

    if not shots:
        raise ValueError('Select at least one image.')

    raw = []
    for shot in shots:
        sec = shot.get('seconds')
        try:
            sec = float(sec) if sec is not None else preset['seconds']
        except (TypeError, ValueError):
            sec = preset['seconds']
        raw.append(max(MIN_CLIP, sec))

    total = sum(raw)
    target = total
    if target_seconds is not None:
        try:
            target = float(target_seconds)
        except (TypeError, ValueError):
            target = total
        target = min(MAX_TARGET, max(MIN_TARGET, target))
    scale = (target / total) if total else 1.0

    slides = []
    effects = []
    cursor = 0.0
    fade = float(preset['fade'] or 0)

    for shot, raw_dur in zip(shots, raw):
        dur = round2(max(MIN_CLIP, raw_dur * scale))
        fade_i = min(fade, max(0.0, dur * 0.4)) if fade else 0.0
        x, y = _focus_xy(shot, items_by_id.get(shot['item_id']))
        slides.append({
            'clip_id': new_clip_id(),
            'item_id': shot['item_id'],
            'start': round2(cursor),
            'duration': dur,
            'channel': 0,
            'muted': True,
            'transitions': [],
            'views': ken_burns_views(
                dur,
                zoom_end=preset['zoom_end'],
                x=x,
                y=y,
                crop_top=preset['crop_top'],
                crop_bottom=preset['crop_bottom'],
            ),
        })
        if fade_i:
            effects.append(_fx('fade-in', cursor, fade_i))
            effects.append(_fx('fade-out', round2(cursor + dur - fade_i), fade_i))
        cursor = round2(cursor + dur)

    return (
        {
            'version': 1,
            'loop': True,
            'defaults': {'duration': preset['seconds'], 'transition': fade or 0},
            'style': style_key,
            'slides': slides,
            'effects': effects,
        },
        warnings,
    )


def _focus_xy(shot, item):
    focus = str((shot or {}).get('focus') or 'subject').lower()
    if focus == 'center':
        return 0.5, 0.5
    return item_subject(item)


def _fx(kind, start, duration):
    return {
        'id': new_clip_id(),
        'type': kind,
        'start': round2(max(0, start)),
        'duration': round2(max(MIN_CLIP, duration)),
    }
