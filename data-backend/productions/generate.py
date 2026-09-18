"""Turn a user prompt into a production rundown via LLM JSON."""

from __future__ import annotations

import json
import re
from decimal import Decimal

from django.db import transaction

from .constants import (
    DEFAULT_SCENE_DURATION_SECONDS,
    PRODUCTION_TYPE_LABELS,
    PRODUCTION_TYPE_REEL,
    PRODUCTION_TYPES,
    SCENE_TYPE_PRESETS,
)
from .llm import chat_completion
from .models import Production, Scene, SceneAsset
from .serializers import persist_scene_times
from .timing import TimecodeError, parse_timecode

_THINK_RE = re.compile(r'<think>.*?</think>', re.IGNORECASE | re.DOTALL)
_FENCE_RE = re.compile(r'```(?:json)?\s*([\s\S]*?)```', re.IGNORECASE)
_TYPE_VALUES = {value for value, _label in PRODUCTION_TYPES}
_SCENE_TYPE_LOOKUP = {name.casefold(): name for name in SCENE_TYPE_PRESETS}

MAX_SCENES = 24
MIN_DURATION = Decimal('1')
MAX_DURATION = Decimal('180')

SYSTEM_PROMPT = """You are a writer-director building a first-draft video rundown, not a trip itinerary.

Return JSON only, no markdown, matching this shape:
{
  "title": "string",
  "subtitle": "string",
  "type": "short_form_documentary" | "long_form_documentary" | "reel",
  "description": "one-paragraph logline: the idea, tension, or joke — not a plot summary",
  "tags": ["short", "labels"],
  "scenes": [
    {
      "title": "short scene name (mood or beat, not 'Day 1' or 'Arrive at X')",
      "scene_type": "Hook" | "Intro" | "Preparation" | "Anticipation" | "Body" | "Outro" | other short label,
      "duration_seconds": number,
      "visuals": "what we see. Prefer images that COMMENT on the line, contrast it, or withhold it — not a 1:1 illustration of the VO",
      "voiceover": "spoken words for this scene, teleprompter-ready. Specific, voiced, not a caption of the picture",
      "music": "optional music/sound note",
      "fx_cues": "optional FX",
      "notes": "optional: why this beat is here (callback, misdirect, pattern interrupt)",
      "assets": ["specific things to make or shoot"]
    }
  ]
}

Structure (do this unless the user explicitly wants a timeline):
- Do NOT tell the story in chronological order. No "we packed / we drove / we arrived / we hiked / we left".
- Open in medias res or with the oddest true detail. The hook should raise a question, not set the scene.
- Middle scenes should jump: contrast, callback, reversal, fake-out, intimate vs wide, now vs then, claim vs evidence.
- Withhold the obvious payoff until late. Let one early image return changed at the end.
- At least one scene should be a quiet or sideways beat (object, hands, a rule, a mistake) rather than another location.
- Voiceover is a point of view, not a tour guide. Cut any line that only names what is on screen.
- Visuals should sometimes contradict or complicate the VO (e.g. calm line over chaotic picture, or vice versa).
- scene_type labels are optional flavors, not a required order. Do not emit Hook, Intro, Preparation, Anticipation, Body, Outro in that sequence just because they exist.

Craft:
- Include EVERY scene's voiceover AND visuals. Do not leave those empty.
- duration_seconds is scene length, not clock time. Fit spoken length (~2.5 words/sec) plus a little picture hold. Vary lengths; do not make every scene the same.
- Reels: 4-8 scenes, total about 20-60 seconds. Short form: 6-12 scenes, ~2-8 minutes. Long form: 8-18 scenes, ~8-18 minutes.
- Prefer the requested type. If none, pick the best fit.
- Assets are names of things to create or capture, not file paths.
"""


class GenerateError(ValueError):
    pass


def extract_json(text: str) -> dict:
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
            raise GenerateError('The model did not return JSON.')
        data = json.loads(blob[start:end + 1])
    if not isinstance(data, dict):
        raise GenerateError('The model JSON is not an object.')
    return data


def _duration_seconds(raw) -> Decimal:
    if raw in (None, ''):
        return parse_timecode(DEFAULT_SCENE_DURATION_SECONDS)
    try:
        value = parse_timecode(raw)
    except TimecodeError:
        return parse_timecode(DEFAULT_SCENE_DURATION_SECONDS)
    if value < MIN_DURATION:
        return MIN_DURATION
    if value > MAX_DURATION:
        return MAX_DURATION
    return value


def normalize_script(raw: dict, requested_type: str = '') -> dict:
    if not isinstance(raw, dict):
        raise GenerateError('Script is not an object.')
    scenes_in = raw.get('scenes')
    if not isinstance(scenes_in, list) or not scenes_in:
        raise GenerateError('Script has no scenes.')

    production_type = str(raw.get('type') or requested_type or PRODUCTION_TYPE_REEL).strip()
    if production_type not in _TYPE_VALUES:
        production_type = requested_type if requested_type in _TYPE_VALUES else PRODUCTION_TYPE_REEL

    scenes = []
    for index, row in enumerate(scenes_in[:MAX_SCENES]):
        if not isinstance(row, dict):
            continue
        scene_type = str(row.get('scene_type') or row.get('type') or '').strip()
        scene_type = _SCENE_TYPE_LOOKUP.get(scene_type.casefold(), scene_type)
        if not scene_type:
            if index == 0:
                scene_type = 'Hook'
            elif index == len(scenes_in) - 1:
                scene_type = 'Outro'
            else:
                scene_type = 'Body'
        assets = row.get('assets') or []
        if isinstance(assets, str):
            assets = [part.strip() for part in assets.split(',') if part.strip()]
        elif not isinstance(assets, list):
            assets = []
        names = []
        for item in assets:
            name = str(item.get('name') if isinstance(item, dict) else item).strip()
            if name:
                names.append(name[:255])
        title = str(row.get('title') or scene_type).strip()[:255]
        scenes.append({
            'title': title,
            'scene_type': scene_type[:128],
            'duration_seconds': _duration_seconds(
                row.get('duration_seconds', row.get('duration')),
            ),
            'visuals': str(row.get('visuals') or '').strip(),
            'voiceover': str(row.get('voiceover') or row.get('dialogue') or '').strip(),
            'music': str(row.get('music') or '').strip(),
            'fx_cues': str(row.get('fx_cues') or row.get('fx') or '').strip(),
            'notes': str(row.get('notes') or '').strip(),
            'assets': names[:20],
        })

    if not scenes:
        raise GenerateError('Script has no usable scenes.')

    tags = raw.get('tags') or []
    if isinstance(tags, str):
        tags = [part.strip() for part in tags.split(',') if part.strip()]
    elif not isinstance(tags, list):
        tags = []
    tags = [str(tag).strip()[:64] for tag in tags if str(tag).strip()][:12]

    title = str(raw.get('title') or 'Untitled production').strip()[:255] or 'Untitled production'
    return {
        'title': title,
        'subtitle': str(raw.get('subtitle') or '').strip()[:255],
        'type': production_type,
        'description': str(raw.get('description') or '').strip(),
        'tags': tags,
        'scenes': scenes,
    }


def build_user_prompt(prompt: str, production_type: str = '') -> str:
    parts = [
        'Write an editorial first draft, not a chronological recap, from this brief:\n\n',
        prompt.strip(),
        '\n\nAvoid a beginning-to-end travelogue. Open late, jump time, and let picture and VO play against each other.',
    ]
    if production_type in _TYPE_VALUES:
        label = PRODUCTION_TYPE_LABELS.get(production_type, production_type)
        parts.append(f'\nUse type "{production_type}" ({label}).')
    parts.append('\nReturn the JSON object now, with visuals/b-roll, voiceover, and duration_seconds on every scene.')
    return ''.join(parts)


def generate_script(prompt: str, production_type: str = '') -> dict:
    brief = (prompt or '').strip()
    if not brief:
        raise GenerateError('Prompt is required.')
    raw_text = chat_completion(
        prompt=build_user_prompt(brief, production_type),
        system=SYSTEM_PROMPT,
        json_mode=True,
        temperature=0.85,
    )
    return normalize_script(extract_json(raw_text), requested_type=production_type)


@transaction.atomic
def create_production_from_script(user, script: dict) -> Production:
    production = Production.objects.create(
        user=user,
        title=script['title'],
        subtitle=script.get('subtitle') or '',
        production_type=script['type'],
        description=script.get('description') or '',
        tags=list(script.get('tags') or []),
    )
    for index, row in enumerate(script['scenes']):
        scene = Scene.objects.create(
            user=user,
            production=production,
            sort_order=index,
            title=row['title'],
            scene_type=row['scene_type'],
            duration_seconds=row['duration_seconds'],
            visuals=row['visuals'],
            voiceover=row['voiceover'],
            music=row['music'],
            fx_cues=row['fx_cues'],
            notes=row['notes'],
        )
        SceneAsset.objects.bulk_create([
            SceneAsset(scene=scene, name=name, sort_order=asset_index)
            for asset_index, name in enumerate(row.get('assets') or [])
        ])
    persist_scene_times(production)
    return production


def generate_production(*, user, prompt: str, production_type: str = '') -> Production:
    script = generate_script(prompt, production_type=production_type)
    return create_production_from_script(user, script)
