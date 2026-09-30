from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


QUANTUM = Decimal('0.001')
ZERO = Decimal('0')


class TimecodeError(ValueError):
    pass


def quantize_seconds(value):
    return Decimal(value).quantize(QUANTUM, rounding=ROUND_HALF_UP)


def parse_timecode(value):
    if value is None or value == '':
        raise TimecodeError('Timecode is required')
    if isinstance(value, bool):
        raise TimecodeError('Invalid timecode')
    if isinstance(value, (int, float, Decimal)):
        seconds = Decimal(str(value))
    else:
        text = str(value).strip()
        if not text:
            raise TimecodeError('Timecode is required')
        parts = text.split(':')
        if len(parts) > 3:
            raise TimecodeError('Invalid timecode')
        try:
            if len(parts) == 1:
                seconds = Decimal(parts[0])
            elif len(parts) == 2:
                minutes = Decimal(parts[0] or '0')
                seconds = Decimal(parts[1] or '0')
                seconds = minutes * 60 + seconds
            else:
                hours = Decimal(parts[0] or '0')
                minutes = Decimal(parts[1] or '0')
                seconds = Decimal(parts[2] or '0')
                seconds = hours * 3600 + minutes * 60 + seconds
        except InvalidOperation as exc:
            raise TimecodeError('Invalid timecode') from exc
    if seconds < 0:
        raise TimecodeError('Timecode cannot be negative')
    return quantize_seconds(seconds)


def _format_seconds_part(seconds, pad=True):
    seconds = quantize_seconds(seconds)
    whole = int(seconds)
    frac = seconds - whole
    if frac == 0:
        return f'{whole:02d}' if pad else str(whole)
    text = format(frac.normalize(), 'f').lstrip('0')
    if not text.startswith('.'):
        text = f'.{text}'
    body = f'{whole}{text}'
    if pad:
        return f'{whole:02d}{text}'
    return body


def format_timecode(seconds):
    seconds = quantize_seconds(seconds if seconds is not None else 0)
    if seconds < 0:
        seconds = ZERO
    hours = int(seconds // 3600)
    remainder = seconds - hours * 3600
    minutes = int(remainder // 60)
    secs = remainder - minutes * 60
    if hours:
        return f'{hours}:{minutes:02d}:{_format_seconds_part(secs, pad=True)}'
    if minutes:
        return f'{minutes}:{_format_seconds_part(secs, pad=True)}'
    if secs == 0:
        return '0:00'
    return _format_seconds_part(secs, pad=False)


def recompute_scene_times(scenes):
    start = ZERO
    for scene in scenes:
        duration = quantize_seconds(scene.duration_seconds or 0)
        if duration < 0:
            raise TimecodeError('Duration cannot be negative')
        scene.duration_seconds = duration
        scene.start_seconds = start
        start = quantize_seconds(start + duration)
    return scenes


def apply_duration_edit(scenes, index, duration):
    duration = parse_timecode(duration)
    scenes[index].duration_seconds = duration
    return recompute_scene_times(scenes)


def apply_end_edit(scenes, index, end):
    end = parse_timecode(end)
    start = quantize_seconds(scenes[index].start_seconds or 0)
    duration = quantize_seconds(end - start)
    if duration < 0:
        raise TimecodeError('End is before start')
    return apply_duration_edit(scenes, index, duration)


def teleprompter_text(scenes):
    blocks = []
    for scene in scenes:
        voiceover = (scene.voiceover or '').strip()
        if not voiceover:
            continue
        title = (getattr(scene, 'title', None) or '').strip()
        if not title:
            title = (getattr(scene, 'scene_type', None) or 'SCENE').strip() or 'SCENE'
        blocks.append(f'[{title}]\n{voiceover}')
    return '\n\n'.join(blocks)


def _text_value(scene, attr):
    return (getattr(scene, attr, None) or '').strip()


def _asset_names(scene):
    raw = getattr(scene, 'assets', None)
    if raw is None:
        return []
    items = raw.all() if hasattr(raw, 'all') else raw
    names = []
    for item in items:
        if isinstance(item, str):
            name = item.strip()
        elif isinstance(item, dict):
            name = str(item.get('name') or '').strip()
        else:
            name = str(getattr(item, 'name', '') or '').strip()
        if name:
            names.append(name)
    return names


def _scene_timecode(scene, formatted_attr, seconds_attr):
    formatted = getattr(scene, formatted_attr, None)
    if formatted not in (None, ''):
        return str(formatted)
    seconds = getattr(scene, seconds_attr, None)
    if seconds is None:
        return ''
    return format_timecode(seconds)


def flat_output_text(scenes):
    blocks = []
    for index, scene in enumerate(scenes, start=1):
        lines = [f'Scene {index}']
        fields = [
            ('Title', _text_value(scene, 'title')),
            ('Type', _text_value(scene, 'scene_type')),
            ('Start', _scene_timecode(scene, 'start', 'start_seconds')),
            ('Duration', _scene_timecode(scene, 'duration', 'duration_seconds')),
            ('End', _scene_timecode(scene, 'end', 'end_seconds')),
            ('Visuals & B-Roll', _text_value(scene, 'visuals')),
            ('Voiceover & Dialogue', _text_value(scene, 'voiceover')),
            ('Music / Sound', _text_value(scene, 'music')),
            ('FX Cues', _text_value(scene, 'fx_cues')),
            ('Notes', _text_value(scene, 'notes')),
        ]
        for label, value in fields:
            if value:
                lines.append(f'{label}: {value}')
        assets = _asset_names(scene)
        if assets:
            lines.append(f'Assets: {", ".join(assets)}')
        blocks.append('\n'.join(lines))
    return '\n\n'.join(blocks)


def asset_name_key(name):
    return (name or '').strip().casefold()
