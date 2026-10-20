"""Match related entities for import: reuse exact hits, create misses, flag ambiguity."""

from __future__ import annotations

from django.db.models import Q

from .constants import RELATION_SCHEMA
from .from_drop import ENTITY_TYPES, _split_name
from .import_v2_executor import ENTITY_MODELS
from .models import Person

_NAME_ALIASES = {
    'al': 'albert',
    'alex': 'alexander',
    'andy': 'andrew',
    'ben': 'benjamin',
    'bill': 'william',
    'bob': 'robert',
    'chris': 'christopher',
    'dan': 'daniel',
    'ed': 'edward',
    'jim': 'james',
    'joe': 'joseph',
    'jon': 'jonathan',
    'mike': 'michael',
    'nick': 'nicholas',
    'rob': 'robert',
    'sam': 'samuel',
    'steve': 'steven',
    'ted': 'theodore',
    'tim': 'timothy',
    'tom': 'thomas',
    'will': 'william',
}


def _first_name_aliases(first):
    key = (first or '').strip().casefold()
    aliases = {key} if key else set()
    full = _NAME_ALIASES.get(key)
    if full:
        aliases.add(full)
    for nick, canonical in _NAME_ALIASES.items():
        if key == canonical:
            aliases.add(nick)
    return aliases


def relation_name(relation_type):
    key = str(relation_type or '').strip().upper()
    for schema in RELATION_SCHEMA:
        if schema.get('key') == key:
            return schema.get('name') or key.replace('_', ' ').title()
        if schema.get('reverseKey') == key:
            return schema.get('reverseName') or key.replace('_', ' ').title()
    return key.replace('_', ' ').title()


def target_type_for_relation(relation_type, from_type):
    key = str(relation_type or '').strip().upper()
    for schema in RELATION_SCHEMA:
        if schema.get('key') != key:
            continue
        expected = schema.get('fromEntity')
        if expected in ('*', 'ANY', from_type):
            to_type = schema.get('toEntity') or 'Person'
            return to_type if to_type in ENTITY_TYPES else 'Person'
    return 'Person'


def serialize_candidate(entity):
    return {
        'id': str(entity.id),
        'display': entity.display or '',
        'type': entity.type,
        'profession': getattr(entity, 'profession', None) or '',
        'year': getattr(entity, 'year', None),
    }


def find_related_candidates(user, display, entity_type='Person', limit=8):
    name = (display or '').strip()
    if not name or not user:
        return []
    if entity_type not in ENTITY_MODELS:
        return []

    model = ENTITY_MODELS[entity_type]
    qs = model.objects.filter(user=user)
    matches = list(qs.filter(display__iexact=name)[:limit])

    if entity_type == 'Person':
        first, last = _split_name(name)
        person_qs = Person.objects.filter(user=user)
        if first and last:
            matches.extend(person_qs.filter(first_name__iexact=first, last_name__iexact=last)[:limit])
            aliases = _first_name_aliases(first)
            if aliases:
                alias_q = Q()
                for alias in aliases:
                    alias_q |= Q(first_name__iexact=alias)
                matches.extend(person_qs.filter(alias_q, last_name__iexact=last)[:limit])
            matches.extend(person_qs.filter(last_name__iexact=last)[:limit])
        elif last:
            matches.extend(person_qs.filter(last_name__iexact=last)[:limit])
        elif first:
            matches.extend(person_qs.filter(
                Q(first_name__iexact=first) | Q(last_name__iexact=first) | Q(display__iexact=first)
            )[:limit])
        if last and len(last) >= 3:
            matches.extend(qs.filter(display__icontains=last)[:limit])
    else:
        matches.extend(qs.filter(display__icontains=name)[:limit])

    seen = set()
    unique = []
    for entity in matches:
        key = str(entity.id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(entity)
        if len(unique) >= limit:
            break
    return unique


def classify_match(display, entity_type, candidates):
    name = (display or '').strip()
    exact_display = [
        item for item in candidates
        if (item.display or '').casefold() == name.casefold()
    ]
    if len(exact_display) == 1:
        return 'exact', exact_display[0]
    if len(exact_display) > 1:
        return 'ambiguous', None

    if entity_type == 'Person':
        first, last = _split_name(name)
        if first and last:
            aliases = _first_name_aliases(first)
            exact_name = [
                item for item in candidates
                if (getattr(item, 'first_name', None) or '').casefold() in aliases
                and (getattr(item, 'last_name', None) or '').casefold() == last.casefold()
            ]
            if len(exact_name) == 1:
                return 'exact', exact_name[0]
            if len(exact_name) > 1:
                return 'ambiguous', None

    if not candidates:
        return 'none', None
    return 'ambiguous', None


def resolve_related(user, display, entity_type='Person'):
    candidates = find_related_candidates(user, display, entity_type)
    status, entity = classify_match(display, entity_type, candidates)
    return {
        'status': status,
        'entity': entity,
        'candidates': [serialize_candidate(item) for item in candidates],
    }
