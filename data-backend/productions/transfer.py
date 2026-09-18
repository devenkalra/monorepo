"""Portable JSON export/import for productions."""

from __future__ import annotations

from django.db import transaction
from django.utils.text import slugify

from .constants import (
    ASSET_STATUSES,
    ASSET_STATUS_TODO,
    DEFAULT_SCENE_DURATION_SECONDS,
    PRODUCTION_TYPE_SHORT_FORM,
    PRODUCTION_TYPES,
)
from .models import Production, ProductionAssetStatus, Scene, SceneAsset
from .serializers import persist_scene_times
from .timing import TimecodeError, asset_name_key, format_timecode, parse_timecode


EXPORT_FORMAT = 'bldrdojo.productions'
EXPORT_VERSION = 1
MAX_IMPORT_PRODUCTIONS = 100
MAX_IMPORT_SCENES = 500

_TYPE_VALUES = {value for value, _label in PRODUCTION_TYPES}
_ASSET_STATUS_VALUES = {value for value, _label in ASSET_STATUSES}


class TransferError(ValueError):
    pass


def export_filename(production=None):
    if production is None:
        return 'productions.json'
    slug = slugify(production.title) or 'production'
    return f'{slug}.json'


def production_export_dict(production):
    scenes = production.scenes.all()
    if not any(
        hasattr(scene, '_prefetched_objects_cache') and 'assets' in scene._prefetched_objects_cache
        for scene in scenes
    ):
        scenes = production.scenes.prefetch_related('assets').all()
    return {
        'title': production.title,
        'subtitle': production.subtitle,
        'type': production.production_type,
        'description': production.description,
        'tags': list(production.tags or []),
        'is_archived': bool(production.is_archived),
        'scenes': [scene_export_dict(scene) for scene in scenes],
        'asset_statuses': [
            {'name': row.display_name, 'status': row.status}
            for row in production.asset_statuses.all()
        ],
    }


def scene_export_dict(scene):
    return {
        'title': scene.title,
        'scene_type': scene.scene_type,
        'duration': format_timecode(scene.duration_seconds),
        'duration_seconds': float(scene.duration_seconds),
        'visuals': scene.visuals,
        'voiceover': scene.voiceover,
        'music': scene.music,
        'fx_cues': scene.fx_cues,
        'notes': scene.notes,
        'assets': [asset.name for asset in scene.assets.all()],
    }


def export_document(productions):
    return {
        'format': EXPORT_FORMAT,
        'version': EXPORT_VERSION,
        'productions': [production_export_dict(production) for production in productions],
    }


def parse_import_document(data):
    if isinstance(data, list):
        rows = data
    elif not isinstance(data, dict):
        raise TransferError('Expected a JSON object or array.')
    elif isinstance(data.get('productions'), list):
        rows = data['productions']
    elif 'title' in data or data.get('scenes') is not None:
        rows = [data]
    else:
        raise TransferError('No productions found in file.')
    if not rows:
        raise TransferError('No productions found in file.')
    if len(rows) > MAX_IMPORT_PRODUCTIONS:
        raise TransferError(f'Import is limited to {MAX_IMPORT_PRODUCTIONS} productions.')
    return rows


def _clean_tags(value):
    if value is None:
        return []
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(',')]
        return [part for part in parts if part][:12]
    if not isinstance(value, list):
        return []
    tags = []
    for item in value:
        name = str(item).strip()
        if name:
            tags.append(name[:64])
    return tags[:12]


def _clean_assets(value):
    if value is None:
        return []
    if isinstance(value, str):
        items = [part.strip() for part in value.split(',') if part.strip()]
        return items[:40]
    if not isinstance(value, list):
        return []
    names = []
    for item in value:
        if isinstance(item, dict):
            name = str(item.get('name') or '').strip()
        else:
            name = str(item).strip()
        if name:
            names.append(name[:255])
    return names[:40]


def _parse_duration(row):
    if not isinstance(row, dict):
        return parse_timecode(DEFAULT_SCENE_DURATION_SECONDS)
    raw = row.get('duration_seconds', row.get('duration'))
    if raw in (None, ''):
        return parse_timecode(DEFAULT_SCENE_DURATION_SECONDS)
    try:
        value = parse_timecode(raw)
    except TimecodeError as exc:
        raise TransferError(f'Invalid scene duration: {raw}') from exc
    if value < 0:
        raise TransferError('Scene duration cannot be negative.')
    return value


def _normalize_type(value):
    production_type = str(value or '').strip()
    if production_type in _TYPE_VALUES:
        return production_type
    return PRODUCTION_TYPE_SHORT_FORM


def _normalize_scene(row, index):
    if not isinstance(row, dict):
        raise TransferError(f'Scene {index + 1} is not an object.')
    assets = _clean_assets(row.get('assets'))
    title = str(row.get('title') or '').strip()[:255]
    scene_type = str(row.get('scene_type') or row.get('type') or '').strip()[:128]
    return {
        'title': title,
        'scene_type': scene_type,
        'duration_seconds': _parse_duration(row),
        'visuals': str(row.get('visuals') or '').strip(),
        'voiceover': str(row.get('voiceover') or row.get('dialogue') or '').strip(),
        'music': str(row.get('music') or '').strip(),
        'fx_cues': str(row.get('fx_cues') or row.get('fx') or '').strip(),
        'notes': str(row.get('notes') or '').strip(),
        'assets': assets,
    }


def _normalize_asset_statuses(value):
    if not isinstance(value, list):
        return []
    rows = []
    seen = set()
    for item in value:
        if isinstance(item, dict):
            name = str(item.get('name') or item.get('display_name') or '').strip()
            status_value = str(item.get('status') or ASSET_STATUS_TODO).strip()
        else:
            continue
        key = asset_name_key(name)
        if not key or key in seen:
            continue
        if status_value not in _ASSET_STATUS_VALUES:
            status_value = ASSET_STATUS_TODO
        seen.add(key)
        rows.append({'name': name[:255], 'name_key': key, 'status': status_value})
    return rows


def normalize_production(raw):
    if not isinstance(raw, dict):
        raise TransferError('Each production must be a JSON object.')
    title = str(raw.get('title') or '').strip()[:255]
    if not title:
        raise TransferError('Title is required.')
    scenes_in = raw.get('scenes') or []
    if scenes_in is None:
        scenes_in = []
    if not isinstance(scenes_in, list):
        raise TransferError('Scenes must be a list.')
    if len(scenes_in) > MAX_IMPORT_SCENES:
        raise TransferError(f'Import is limited to {MAX_IMPORT_SCENES} scenes per production.')
    scenes = [_normalize_scene(row, index) for index, row in enumerate(scenes_in)]
    return {
        'title': title,
        'subtitle': str(raw.get('subtitle') or '').strip()[:255],
        'type': _normalize_type(raw.get('type') or raw.get('production_type')),
        'description': str(raw.get('description') or '').strip(),
        'tags': _clean_tags(raw.get('tags')),
        'is_archived': bool(raw.get('is_archived')),
        'scenes': scenes,
        'asset_statuses': _normalize_asset_statuses(
            raw.get('asset_statuses') or raw.get('asset_todos'),
        ),
    }


def create_production_from_export(user, payload) -> Production:
    script = normalize_production(payload)
    production = Production.objects.create(
        user=user,
        title=script['title'],
        subtitle=script['subtitle'],
        production_type=script['type'],
        description=script['description'],
        tags=list(script['tags']),
        is_archived=script['is_archived'],
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
    ProductionAssetStatus.objects.bulk_create([
        ProductionAssetStatus(
            production=production,
            name_key=row['name_key'],
            display_name=row['name'],
            status=row['status'],
        )
        for row in script['asset_statuses']
    ])
    return production


@transaction.atomic
def import_productions(user, data):
    rows = parse_import_document(data)
    created = []
    for row in rows:
        created.append(create_production_from_export(user, row))
    return created
