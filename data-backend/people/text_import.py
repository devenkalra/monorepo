"""Import one entity per text line using the LLM, then import-v2 create."""

from __future__ import annotations

import json
import re

from .from_drop import (
    ENTITY_TYPES,
    _AUTHOR_RE,
    _DIRECTOR_RE,
    _JSON_SHAPE,
    _TYPE_FIELD_HINTS,
    _entity_payload,
    _name_after,
    _normalize_llm_fields,
    _normalize_relations,
    _split_name,
    llm_available,
)
from .import_v2_executor import ENTITY_MODELS, execute_import_v2
from .models import Entity
from .relate import (
    classify_match,
    find_related_candidates,
    relation_name,
    serialize_candidate,
    target_type_for_relation,
)


MAX_LINES = 100
MAX_CHARS = 20_000
IMPORT_TAG = 'imported/text'
DROP_KEYS = {
    '_type', 'referenced_files', 'photos', 'attachments', 'relations',
}
_FIELD_TO_REL = {
    'director': 'HAS_DIRECTOR',
    'directed_by': 'HAS_DIRECTOR',
    'directors': 'HAS_DIRECTOR',
    'actor': 'HAS_ACTOR',
    'actors': 'HAS_ACTOR',
    'cast': 'HAS_ACTOR',
    'starring': 'HAS_ACTOR',
    'composer': 'HAS_MUS_DIRECTOR',
    'music_director': 'HAS_MUS_DIRECTOR',
    'music': 'HAS_MUS_DIRECTOR',
    'score': 'HAS_MUS_DIRECTOR',
    'author': 'HAS_AS_AUTHOR',
    'authors': 'HAS_AS_AUTHOR',
    'written_by': 'HAS_AS_AUTHOR',
}
_REL_ALIASES = {
    'DIRECTOR': 'HAS_DIRECTOR',
    'HAS_DIRECTOR': 'HAS_DIRECTOR',
    'ACTOR': 'HAS_ACTOR',
    'HAS_ACTOR': 'HAS_ACTOR',
    'STARRING': 'HAS_ACTOR',
    'CAST': 'HAS_ACTOR',
    'COMPOSER': 'HAS_MUS_DIRECTOR',
    'MUSIC': 'HAS_MUS_DIRECTOR',
    'MUSIC_DIRECTOR': 'HAS_MUS_DIRECTOR',
    'HAS_MUS_DIRECTOR': 'HAS_MUS_DIRECTOR',
    'AUTHOR': 'HAS_AS_AUTHOR',
    'HAS_AS_AUTHOR': 'HAS_AS_AUTHOR',
}
_REQUIRED_RELATIONS = {
    'Movie': ('HAS_DIRECTOR', 'HAS_ACTOR', 'HAS_MUS_DIRECTOR'),
    'Book': ('HAS_AS_AUTHOR',),
}
_BOOK_AUTHOR_RE = re.compile(
    r'(?:^|[\s,;:|—–\-])(?:written\s+by|authored\s+by|author(?:ed)?\s*[:\-]|by)\s+',
    re.IGNORECASE,
)
_BOOK_AUTHOR_TAIL_RE = re.compile(
    r'\s[—–\-]\s+([A-Z][\w.\'\-]+(?:\s+[A-Z][\w.\'\-]+){0,3})\s*$',
)


class TextImportError(ValueError):
    pass


def split_lines(text):
    lines = []
    for raw in str(text or '').replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        line = raw.strip()
        if line:
            lines.append(line)
        if len(lines) >= MAX_LINES:
            break
    return lines


def resolve_entity_type(value):
    if value in (None, ''):
        return 'Note'
    resolved = {name.casefold(): name for name in ENTITY_TYPES}.get(str(value).strip().casefold())
    if not resolved:
        raise TextImportError(f'Unknown entity type "{value}".')
    return resolved


def _heuristic_item(line, entity_type):
    fields = {
        'type': entity_type,
        'display': line[:255],
        'description': line if entity_type == 'Note' else '',
        'tags': [IMPORT_TAG],
    }
    if entity_type == 'Person':
        first, last = _split_name(line)
        fields['first_name'] = first
        fields['last_name'] = last
    elif entity_type == 'Org':
        fields['name'] = line[:255]
    director = _name_after(_DIRECTOR_RE, line) if entity_type == 'Movie' else ''
    if director:
        fields['relations'] = [{'relation_type': 'HAS_DIRECTOR', 'display': director}]
    author = _author_from_line(line) if entity_type == 'Book' else ''
    if author:
        fields['author'] = author
        fields['relations'] = [{'relation_type': 'HAS_AS_AUTHOR', 'display': author}]
    return fields


def _system_prompt(entity_type):
    hint = _TYPE_FIELD_HINTS.get(entity_type, '')
    return f"""You convert a numbered list of topic lines into structured knowledge-base records.

{_JSON_SHAPE}

Override description: it must be a detailed HTML write-up, not a one-line copy of the input.
Use 2-4 <p> paragraphs (about 120-250 words). Cover what the subject is, key facts, and useful context from well-known public knowledge.
display is a short title derived from the line. description is the full body.

Return JSON only in this shape:
{{"items":[{{...one object per input line...}}]}}

The type is locked to {entity_type}. Do not pick another type.
{hint}
Create exactly one item per input line, in the same order.
The line is a seed/title, not the complete record. Fill supported fields from the line plus well-known public facts.
Do not invent private details (emails, phones, unpublished dates) that are not in the line or widely published.
For Note: display is a short title; description is the expanded note, not the raw line.
For Movie: relations is required. Always include HAS_DIRECTOR, 3-6 HAS_ACTOR names, and HAS_MUS_DIRECTOR (composer) from well-known public credits.
Do not omit actors or the composer just because the input line only mentions the director or title.
For Book: every item must include the author as HAS_AS_AUTHOR. Repeat the same author on every book that shares one.
Use full legal names in relation display fields (Christopher Nolan, not Chris Nolan; Freida McFadden, not Frieda).
"""


def _user_prompt(lines, entity_type):
    numbered = '\n'.join(f'{idx}. {line}' for idx, line in enumerate(lines, 1))
    extra = ''
    if entity_type == 'Movie':
        extra = (
            'For every movie, include relations for director, principal actors, and composer '
            'from public knowledge even if those names are not in the line.\n'
        )
    elif entity_type == 'Book':
        extra = (
            'For every book, include HAS_AS_AUTHOR (or author) from public knowledge even if '
            'the line is only a title. If several titles share an author, put that author on every item.\n'
        )
    return (
        f'Type is locked to {entity_type}. Return one JSON object per line.\n'
        'Write a detailed HTML description for each item; do not copy the line as the whole description.\n'
        f'{extra}\n'
        f'Lines:\n{numbered}\n\n'
        'Return {"items":[...]} now.'
    )


def _parse_json_blob(raw):
    blob = (raw or '').strip()
    fence = re.search(r'```(?:json)?\s*([\s\S]*?)```', blob, re.I)
    if fence:
        blob = fence.group(1).strip()
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        for start_char, end_char in (('{', '}'), ('[', ']')):
            start, end = blob.find(start_char), blob.rfind(end_char)
            if start >= 0 and end > start:
                try:
                    return json.loads(blob[start:end + 1])
                except json.JSONDecodeError:
                    continue
    return None


def _extract_items(raw):
    data = _parse_json_blob(raw)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ('items', 'entities', 'records'):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if any(data.get(key) for key in ('display', 'description', 'first_name', 'name')):
            return [data]
    return []


def _llm_items(lines, entity_type):
    if not llm_available():
        return []
    raw = ''
    try:
        from productions.llm import chat_completion
        raw = chat_completion(
            prompt=_user_prompt(lines, entity_type),
            system=_system_prompt(entity_type),
            json_mode=True,
            temperature=0.2,
            timeout=90.0,
        )
    except Exception:
        raw = ''
    items = _extract_items(raw)
    items = items[:len(lines)]
    while len(items) < len(lines):
        items.append(_heuristic_item(lines[len(items)], entity_type))
    if entity_type in _REQUIRED_RELATIONS:
        items = _enrich_relations(items, lines, entity_type)
    if entity_type == 'Book':
        items = _fill_shared_book_authors(items, lines)
    return items


def _author_from_line(line):
    name = _name_after(_AUTHOR_RE, line) or _name_after(_BOOK_AUTHOR_RE, line)
    if name:
        return name
    tail = _BOOK_AUTHOR_TAIL_RE.search(line or '')
    return (tail.group(1).strip() if tail else '')


def _names_from_value(value):
    if isinstance(value, str):
        parts = re.split(r'\s*(?:,|;|/|\band\b)\s*', value)
        return [part.strip() for part in parts if 1 < len(part.strip()) < 80]
    if isinstance(value, list):
        names = []
        for item in value:
            if isinstance(item, str):
                names.extend(_names_from_value(item))
            elif isinstance(item, dict):
                name = (item.get('display') or item.get('name') or '').strip()
                if name:
                    names.append(name)
        return names
    return []


def _alias_relation_type(value):
    key = re.sub(r'[\s\-]+', '_', str(value or '').strip().upper())
    return _REL_ALIASES.get(key)


def _raw_relation_rows(fields):
    rows = []
    if not isinstance(fields, dict):
        return rows
    raw = fields.get('relations')
    if isinstance(raw, list):
        for row in raw:
            if isinstance(row, dict):
                rel = _alias_relation_type(
                    row.get('relation_type') or row.get('role') or row.get('rel')
                )
                display = (row.get('display') or row.get('name') or '').strip()
                if rel and display:
                    rows.append({'relation_type': rel, 'display': display})
            elif isinstance(row, str) and row.strip():
                continue
    for key, rel in _FIELD_TO_REL.items():
        if key not in fields:
            continue
        for name in _names_from_value(fields.get(key)):
            rows.append({'relation_type': rel, 'display': name})
    return rows


def _relations_complete(fields, entity_type, source_line=''):
    present = {row['relation_type'] for row in _item_relations(fields, entity_type, source_line)}
    required = _REQUIRED_RELATIONS.get(entity_type) or ()
    return all(rel in present for rel in required)


def _book_author_names(fields, source_line=''):
    return [
        row['display']
        for row in _item_relations(fields, 'Book', source_line)
        if row['relation_type'] == 'HAS_AS_AUTHOR'
    ]


def _fill_shared_book_authors(items, lines):
    authors = []
    seen = set()
    for index, item in enumerate(items):
        line = lines[index] if index < len(lines) else ''
        for name in _book_author_names(item, line):
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            authors.append(name)
    if len(authors) != 1:
        return items
    author = authors[0]
    filled = []
    for index, item in enumerate(items):
        line = lines[index] if index < len(lines) else ''
        if _book_author_names(item, line):
            filled.append(item)
            continue
        current = list(item.get('relations') or [])
        current.append({'relation_type': 'HAS_AS_AUTHOR', 'display': author})
        filled.append({**item, 'author': author, 'relations': current})
    return filled


def _enrich_relations(items, lines, entity_type):
    if not items or not llm_available():
        return items
    missing = [
        index for index in range(len(items))
        if not _relations_complete(
            items[index],
            entity_type,
            lines[index] if index < len(lines) else '',
        )
    ]
    if not missing:
        return items
    # For books, send the whole list so a shared author can be applied to every title.
    needed = [
        (index, items[index], lines[index] if index < len(lines) else items[index].get('display') or '')
        for index in (range(len(items)) if entity_type == 'Book' else missing)
    ]
    numbered = '\n'.join(
        f'{offset + 1}. {item.get("display") or line}'
        for offset, (_index, item, line) in enumerate(needed)
    )
    required = ', '.join(_REQUIRED_RELATIONS[entity_type])
    if entity_type == 'Book':
        prompt = (
            'Type is Book. For each title, return the author from public knowledge.\n'
            'Required relation_type: HAS_AS_AUTHOR. You may also set author.\n'
            'If several titles share an author, repeat that author on every item.\n'
            'Use the full legal name (Freida McFadden, not Frieda).\n\n'
            f'Titles:\n{numbered}\n\n'
            'Return {"items":[{"display":"...","author":"...","relations":'
            '[{"relation_type":"HAS_AS_AUTHOR","display":"..."}]}]} now.'
        )
    else:
        prompt = (
            f'Type is {entity_type}. For each title, return public-credit relations.\n'
            f'Required relation_type values: {required}.\n'
            'Use full legal names. Include 3-6 actors for movies and the composer.\n\n'
            f'Titles:\n{numbered}\n\n'
            'Return {"items":[{"display":"...","relations":[{"relation_type":"HAS_DIRECTOR","display":"..."}]}]} now.'
        )
    try:
        from productions.llm import chat_completion
        raw = chat_completion(
            prompt=prompt,
            system='You fill missing movie/book credits from well-known public knowledge. JSON only.',
            json_mode=True,
            temperature=0.1,
            timeout=60.0,
        )
    except Exception:
        return items
    extra = _extract_items(raw)
    merged = list(items)
    for offset, (index, item, _line) in enumerate(needed):
        if offset >= len(extra):
            break
        add = extra[offset]
        current = list(item.get('relations') or [])
        current.extend(add.get('relations') or [])
        for key in _FIELD_TO_REL:
            if add.get(key) and not item.get(key):
                merged[index] = {**merged[index], key: add.get(key)}
        merged[index] = {**merged[index], 'relations': current}
    return merged


def _as_html_description(value):
    text = str(value or '').strip()
    if not text:
        return ''
    if re.search(r'</?(p|div|ul|ol|h[1-6]|br)\b', text, re.I):
        return text
    parts = [part.strip() for part in re.split(r'\n\s*\n', text) if part.strip()]
    if not parts:
        parts = [text]
    return ''.join(f'<p>{part}</p>' for part in parts)


def _to_import_entity(fields, entity_type, index, source_line):
    parsed = _normalize_llm_fields(fields if isinstance(fields, dict) else {})
    parsed['type'] = entity_type
    if not parsed.get('display'):
        parsed['display'] = (source_line or f'{entity_type} {index}')[:255]
    if entity_type == 'Note' and not parsed.get('description'):
        parsed['description'] = source_line
    if entity_type == 'Person' and not parsed.get('first_name') and not parsed.get('last_name'):
        parsed['first_name'], parsed['last_name'] = _split_name(parsed['display'])
    description = _as_html_description(parsed.get('description') or '')
    payload = _entity_payload(parsed, description, [], [], [])
    for key in DROP_KEYS:
        payload.pop(key, None)
    payload['type'] = entity_type
    payload['tags'] = [IMPORT_TAG]
    cleaned = {}
    for key, value in payload.items():
        if key == 'description':
            cleaned[key] = value or ''
            continue
        if value in (None, '', [], {}):
            continue
        cleaned[key] = value
    return {
        'import_op': 'create',
        'import_ref': f'line-{index}',
        **cleaned,
    }


def _as_year(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _match_main(user, main):
    if not user:
        return 'none', None, []
    display = main.get('display') or ''
    entity_type = main.get('type')
    candidates = find_related_candidates(user, display, entity_type)
    year = _as_year(main.get('year'))
    if entity_type in ('Movie', 'Book') and year is not None:
        year_hits = [item for item in candidates if _as_year(getattr(item, 'year', None)) == year]
        if len(year_hits) == 1:
            return 'exact', year_hits[0], candidates
        if len(year_hits) > 1:
            return 'ambiguous', None, year_hits
    status, entity = classify_match(display, entity_type, candidates)
    return status, entity, candidates


def _plain_text(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html or '')).strip().casefold()


def _heuristic_merge_descriptions(existing, incoming):
    existing = existing or ''
    incoming = incoming or ''
    if not incoming:
        return existing
    if not existing:
        return incoming
    incoming_plain = _plain_text(incoming)
    existing_plain = _plain_text(existing)
    if incoming_plain and incoming_plain in existing_plain:
        return existing
    if existing_plain and existing_plain in incoming_plain:
        return incoming
    return f'{existing}{incoming if incoming.lstrip().startswith("<") else _as_html_description(incoming)}'


def _merge_descriptions(existing, incoming, display='', entity_type='Note'):
    existing = existing or ''
    incoming = incoming or ''
    if not incoming:
        return existing
    if not existing or existing.strip() == incoming.strip():
        return incoming or existing
    if not llm_available():
        return _heuristic_merge_descriptions(existing, incoming)
    try:
        from productions.llm import chat_completion
        raw = chat_completion(
            prompt=(
                f'Merge two HTML descriptions of the same {entity_type} "{display}".\n'
                'Keep every unique fact, drop repeated sentences, and return one coherent write-up.\n'
                'Use 2-4 <p> tags. Do not add a title.\n\n'
                f'EXISTING:\n{existing}\n\nNEW:\n{incoming}\n\n'
                'Return {"description":"<p>...</p>"} now.'
            ),
            system='You merge knowledge-base descriptions. JSON only.',
            json_mode=True,
            temperature=0.1,
            timeout=60.0,
        )
        data = _parse_json_blob(raw)
        merged = data.get('description') if isinstance(data, dict) else None
        if merged and str(merged).strip():
            return _as_html_description(merged)
    except Exception:
        pass
    return _heuristic_merge_descriptions(existing, incoming)


def _apply_existing_main(main, entity, incoming=None, merged=None):
    incoming_description = incoming if incoming is not None else main.get('description') or ''
    if not merged:
        merged = _merge_descriptions(
            entity.description or '',
            incoming_description,
            display=entity.display or main.get('display') or '',
            entity_type=main.get('type') or entity.type,
        )
    main['import_op'] = 'update'
    main['id'] = str(entity.id)
    main['existing_id'] = str(entity.id)
    main['existing_display'] = entity.display or main.get('display')
    main['incoming_description'] = incoming_description
    main['description'] = merged
    main['merged'] = True
    main.pop('pending_main', None)
    return main


def _main_candidate(entity, incoming, entity_type, use_llm=False):
    existing = entity.description or ''
    if use_llm:
        merged = _merge_descriptions(
            existing,
            incoming,
            display=entity.display or '',
            entity_type=entity_type,
        )
    else:
        merged = _heuristic_merge_descriptions(existing, incoming)
    row = serialize_candidate(entity)
    row['description'] = existing
    row['merged_description'] = merged
    return row


def _pending_main_item(main, line, entity_type, candidates, match_status):
    incoming = main.get('description') or ''
    use_llm = len(candidates) <= 2
    return {
        'key': f'main-{main["import_ref"]}',
        'kind': 'main',
        'match': match_status,
        'from_import_ref': main['import_ref'],
        'from_display': main.get('display') or line,
        'relation_name': 'Existing entity',
        'query': main.get('display') or line,
        'target_type': entity_type,
        'incoming_description': incoming,
        'candidates': [
            _main_candidate(item, incoming, entity_type, use_llm=use_llm)
            for item in candidates
        ],
    }


def _item_relations(fields, entity_type, source_line=''):
    rows = list(_raw_relation_rows(fields))
    if entity_type == 'Movie':
        director = _name_after(_DIRECTOR_RE, source_line)
        if director:
            rows.append({'relation_type': 'HAS_DIRECTOR', 'display': director})
    elif entity_type == 'Book':
        author = _author_from_line(source_line)
        if author:
            rows.append({'relation_type': 'HAS_AS_AUTHOR', 'display': author})
    cleaned = _normalize_relations(rows, entity_type)
    out = []
    seen = set()
    for row in cleaned:
        target_type = target_type_for_relation(row['relation_type'], entity_type)
        display = (row.get('display') or '').strip()
        if not display:
            continue
        key = (row['relation_type'], display.casefold())
        if key in seen:
            continue
        seen.add(key)
        out.append({
            'relation_type': row['relation_type'],
            'display': display[:255],
            'type': target_type,
        })
    return out


def _create_tags(extra_tag=None):
    tags = [IMPORT_TAG]
    extras = extra_tag if isinstance(extra_tag, list) else [extra_tag]
    for item in extras:
        name = str(item or '').strip()[:64]
        if name and name not in tags:
            tags.append(name)
    return tags


def _related_create_entity(display, entity_type, import_ref, tags=None):
    fields = {
        'type': entity_type,
        'display': display[:255],
        'tags': list(tags or [IMPORT_TAG]),
    }
    if entity_type == 'Person':
        first, last = _split_name(display)
        fields['first_name'] = first
        fields['last_name'] = last
    elif entity_type == 'Org':
        fields['name'] = display[:255]
    return {
        'import_op': 'create',
        'import_ref': import_ref,
        **fields,
    }


def _in_flight_match(display, entity_type, entities):
    name = (display or '').strip().casefold()
    first, last = _split_name(display)
    matches = []
    for item in entities:
        if item.get('type') != entity_type:
            continue
        if (item.get('display') or '').strip().casefold() == name:
            matches.append(item)
            continue
        if (
            entity_type == 'Person'
            and first
            and last
            and (item.get('first_name') or '').casefold() == first.casefold()
            and (item.get('last_name') or '').casefold() == last.casefold()
        ):
            matches.append(item)
    if len(matches) == 1:
        return matches[0]
    return None


def _new_related_ref(used):
    index = 1
    while f'related-{index}' in used:
        index += 1
    ref = f'related-{index}'
    used.add(ref)
    return ref


def _used_plan_refs(plan):
    used = {
        item.get('import_ref')
        for item in (plan.get('entities') or [])
        if item.get('import_ref')
    }
    for link in plan.get('resolved') or []:
        if link.get('to_import_ref'):
            used.add(link['to_import_ref'])
    return used


def _build_plan(text, entity_type, user=None):
    entity_type = resolve_entity_type(entity_type)
    text = str(text or '')
    if len(text) > MAX_CHARS:
        raise TextImportError(f'Text is too long (max {MAX_CHARS} characters).')
    lines = split_lines(text)
    if not lines:
        raise TextImportError('Enter at least one non-empty line.')

    llm_items = _llm_items(lines, entity_type)
    if entity_type == 'Book':
        llm_items = _fill_shared_book_authors(llm_items, lines)
    mains = []
    pending = []
    resolved = []
    used_refs = set()
    create_refs = {}

    for index, line in enumerate(lines, 1):
        fields = llm_items[index - 1] if index <= len(llm_items) else _heuristic_item(line, entity_type)
        main = _to_import_entity(fields, entity_type, index, line)
        if user:
            status, entity, candidates = _match_main(user, main)
            if status == 'exact' and entity is not None:
                main['pending_main'] = True
                pending.append(_pending_main_item(main, line, entity_type, [entity], 'exact'))
            elif status == 'ambiguous' and candidates:
                main['pending_main'] = True
                pending.append(_pending_main_item(main, line, entity_type, candidates, 'ambiguous'))
        mains.append(main)
        used_refs.add(main['import_ref'])

        for rel_index, row in enumerate(_item_relations(fields, entity_type, line), 1):
            key = f'{main["import_ref"]}-{row["relation_type"]}-{rel_index}'
            in_flight = _in_flight_match(row['display'], row['type'], mains)
            if in_flight:
                resolved.append({
                    'key': key,
                    'from_import_ref': main['import_ref'],
                    'relation_type': row['relation_type'],
                    'to_import_ref': in_flight['import_ref'],
                })
                continue

            match = {
                'status': 'none',
                'entity': None,
                'candidates': [],
            }
            if user:
                candidates = find_related_candidates(user, row['display'], row['type'])
                status, entity = classify_match(row['display'], row['type'], candidates)
                match = {
                    'status': status,
                    'entity': entity,
                    'candidates': [serialize_candidate(item) for item in candidates],
                }

            if match['status'] == 'exact' and match['entity'] is not None:
                resolved.append({
                    'key': key,
                    'from_import_ref': main['import_ref'],
                    'relation_type': row['relation_type'],
                    'to_entity': str(match['entity'].id),
                    'found_display': match['entity'].display or row['display'],
                    'found_type': match['entity'].type,
                })
                continue

            if match['status'] == 'ambiguous':
                pending.append({
                    'key': key,
                    'from_import_ref': main['import_ref'],
                    'from_display': main.get('display') or line,
                    'relation_type': row['relation_type'],
                    'relation_name': relation_name(row['relation_type']),
                    'query': row['display'],
                    'target_type': row['type'],
                    'candidates': match['candidates'],
                })
                continue

            create_key = (row['type'], row['display'].casefold())
            to_ref = create_refs.get(create_key)
            if not to_ref:
                to_ref = _new_related_ref(used_refs)
                create_refs[create_key] = to_ref
            resolved.append({
                'key': key,
                'from_import_ref': main['import_ref'],
                'relation_type': row['relation_type'],
                'to_import_ref': to_ref,
                'create_display': row['display'],
                'create_type': row['type'],
            })

    return {
        'version': 1,
        'entity_type': entity_type,
        'entities': mains,
        'resolved': resolved,
        'pending': pending,
    }


def _validate_draft(draft):
    if not isinstance(draft, dict) or draft.get('version') != 1:
        raise TextImportError('Import draft is missing or invalid.')
    entities = draft.get('entities')
    if not isinstance(entities, list) or not entities:
        raise TextImportError('Import draft has no entities.')
    for item in entities:
        if not isinstance(item, dict) or item.get('import_op') not in {'create', 'update'}:
            raise TextImportError('Import draft has an invalid entity.')
        if item.get('type') not in ENTITY_MODELS:
            raise TextImportError('Import draft has an unknown entity type.')
    pending = draft.get('pending') or []
    resolved = draft.get('resolved') or []
    if not isinstance(pending, list) or not isinstance(resolved, list):
        raise TextImportError('Import draft has invalid relations.')
    return {
        'version': 1,
        'entity_type': resolve_entity_type(draft.get('entity_type') or 'Note'),
        'entities': entities,
        'resolved': [item for item in resolved if isinstance(item, dict)],
        'pending': [item for item in pending if isinstance(item, dict)],
    }


def _display_for_ref(plan, import_ref):
    for item in plan.get('entities') or []:
        if item.get('import_ref') == import_ref:
            return item.get('display') or import_ref
    return import_ref


def _plan_preview(plan, user=None):
    create = []
    update = []
    found = []
    relations = []
    seen_create = set()

    for item in plan.get('entities') or []:
        if item.get('pending_main'):
            continue
        if item.get('import_op') == 'update' or item.get('existing_id'):
            update.append({
                'id': item.get('existing_id') or item.get('id'),
                'display': item.get('existing_display') or item.get('display') or '',
                'type': item.get('type'),
                'role': 'Imported item',
                'merged': bool(item.get('merged')),
                'import_ref': item.get('import_ref'),
                'description': item.get('description') or '',
                'incoming_description': item.get('incoming_description') or '',
            })
            continue
        create.append({
            'display': item.get('display') or '',
            'type': item.get('type'),
            'role': 'Imported item',
            'import_ref': item.get('import_ref'),
            'description': item.get('description') or '',
        })
        seen_create.add((item.get('type'), (item.get('display') or '').casefold()))

    for link in plan.get('resolved') or []:
        from_display = _display_for_ref(plan, link.get('from_import_ref'))
        rel_label = relation_name(link.get('relation_type'))
        if link.get('to_entity'):
            entity = None
            if user and link.get('to_entity'):
                entity = Entity.objects.filter(id=link['to_entity'], user=user).first()
            target = {
                'id': str(link['to_entity']),
                'display': (entity.display if entity else link.get('found_display')) or '',
                'type': (entity.type if entity else link.get('found_type')) or 'Person',
                'role': rel_label,
                'from_display': from_display,
            }
            if not any(row.get('id') == target['id'] and row.get('role') == rel_label for row in found):
                found.append(target)
            relations.append({
                'from': from_display,
                'relation_name': rel_label,
                'to': target['display'],
                'status': 'found',
            })
            continue

        display = link.get('create_display') or ''
        target_type = link.get('create_type') or 'Person'
        create_key = (target_type, display.casefold())
        if display and create_key not in seen_create:
            seen_create.add(create_key)
            create.append({
                'display': display,
                'type': target_type,
                'role': rel_label,
                'from_display': from_display,
            })
        relations.append({
            'from': from_display,
            'relation_name': rel_label,
            'to': display or link.get('to_import_ref') or '',
            'status': 'create',
        })

    return {
        'create': create,
        'update': update,
        'found': found,
        'ambiguities': plan.get('pending') or [],
        'relations': relations,
        'create_count': len(create),
        'update_count': len(update),
        'found_count': len(found),
        'ambiguity_count': len(plan.get('pending') or []),
    }


def _apply_confirmations(draft, confirmations, user):
    plan = _validate_draft(draft)
    choices = confirmations if isinstance(confirmations, dict) else {}
    remaining = []
    skipped_refs = set()
    for item in plan['pending']:
        if item.get('from_import_ref') in skipped_refs:
            continue
        choice = choices.get(item['key'])
        if not isinstance(choice, dict):
            remaining.append(item)
            continue
        action = str(choice.get('action') or '').strip().lower()
        if item.get('kind') == 'main':
            ref = item.get('from_import_ref')
            if action == 'skip':
                skipped_refs.add(ref)
                plan['entities'] = [row for row in plan['entities'] if row.get('import_ref') != ref]
                plan['resolved'] = [row for row in plan['resolved'] if row.get('from_import_ref') != ref]
                continue
            if action == 'create':
                for row in plan['entities']:
                    if row.get('import_ref') == ref:
                        row.pop('pending_main', None)
                        row['import_op'] = 'create'
                continue
            if action == 'use':
                entity_id = str(choice.get('id') or '').strip()
                entity = Entity.objects.filter(
                    id=entity_id,
                    user=user,
                    type=item.get('target_type'),
                ).first() if entity_id else None
                target = next((row for row in plan['entities'] if row.get('import_ref') == ref), None)
                if not entity or not target:
                    remaining.append(item)
                    continue
                chosen = next(
                    (
                        row for row in (item.get('candidates') or [])
                        if str(row.get('id') or '') == entity_id
                    ),
                    None,
                )
                _apply_existing_main(
                    target,
                    entity,
                    incoming=item.get('incoming_description') or target.get('description'),
                    merged=(chosen or {}).get('merged_description'),
                )
                continue
            remaining.append(item)
            continue
        if action == 'skip':
            continue
        if action == 'create':
            plan['resolved'].append({
                'key': item['key'],
                'from_import_ref': item['from_import_ref'],
                'relation_type': item['relation_type'],
                'to_import_ref': _new_related_ref(_used_plan_refs(plan)),
                'create_display': item['query'],
                'create_type': item['target_type'],
            })
            continue
        if action == 'use':
            entity_id = str(choice.get('id') or '').strip()
            entity = Entity.objects.filter(
                id=entity_id,
                user=user,
                type=item['target_type'],
            ).first() if entity_id else None
            if not entity:
                remaining.append(item)
                continue
            plan['resolved'].append({
                'key': item['key'],
                'from_import_ref': item['from_import_ref'],
                'relation_type': item['relation_type'],
                'to_entity': str(entity.id),
            })
            continue
        remaining.append(item)
    plan['pending'] = remaining
    return plan


def _plan_to_payload(plan, extra_tag=None):
    tags = _create_tags(extra_tag)
    skip_keys = {
        'existing_id', 'existing_display', 'incoming_description', 'merged', 'pending_main',
    }
    mains = []
    for item in plan['entities']:
        entity = {key: value for key, value in item.items() if key not in skip_keys}
        if entity.get('import_op') == 'update' and entity.get('id'):
            mains.append({
                'import_op': 'update',
                'import_ref': entity.get('import_ref'),
                'id': entity['id'],
                'type': entity.get('type'),
                'description': entity.get('description') or '',
            })
            continue
        entity['import_op'] = 'create'
        entity['tags'] = tags
        mains.append(entity)

    used_refs = _used_plan_refs({'entities': mains, 'resolved': plan.get('resolved') or []})
    create_refs = {}
    related = []
    seen_related = set()
    relations = []

    for link in plan.get('resolved') or []:
        relation = {
            'import_op': 'create',
            'import_ref': link.get('key') or f'rel-{len(relations) + 1}',
            'from_import_ref': link['from_import_ref'],
            'relation_type': link['relation_type'],
        }
        source = next(
            (item for item in plan['entities'] if item.get('import_ref') == link.get('from_import_ref')),
            None,
        )
        if source and (source.get('existing_id') or source.get('id')) and source.get('import_op') == 'update':
            relation['from_entity'] = source.get('existing_id') or source.get('id')
        if link.get('to_entity'):
            relation['to_entity'] = link['to_entity']
            relations.append(relation)
            continue

        to_ref = link.get('to_import_ref')
        create_display = link.get('create_display')
        create_type = link.get('create_type')
        if create_display and create_type:
            create_key = (create_type, create_display.casefold())
            to_ref = create_refs.get(create_key) or to_ref
            if not to_ref:
                to_ref = _new_related_ref(used_refs)
            else:
                used_refs.add(to_ref)
            if create_key not in create_refs:
                create_refs[create_key] = to_ref
                if to_ref not in seen_related:
                    seen_related.add(to_ref)
                    related.append(_related_create_entity(create_display, create_type, to_ref, tags=tags))
        if to_ref:
            relation['to_import_ref'] = to_ref
            relations.append(relation)

    return {
        'import_version': '2.0',
        'entities': mains + related,
        'relations': relations,
        'tags': [],
    }


def prepare_text_import(text, entity_type='Note', user=None, confirmations=None, draft=None):
    if draft:
        plan = _apply_confirmations(draft, confirmations, user)
    else:
        plan = _build_plan(text, entity_type, user=user)
        if confirmations:
            plan = _apply_confirmations(plan, confirmations, user)
    if plan.get('pending'):
        return {
            'needs_confirmation': True,
            'draft': plan,
            'confirmations': plan['pending'],
            'payload': None,
            'preview': _plan_preview(plan, user),
        }
    return {
        'needs_confirmation': False,
        'draft': plan,
        'confirmations': [],
        'payload': _plan_to_payload(plan),
        'preview': _plan_preview(plan, user),
    }


def build_import_payload(text, entity_type='Note', user=None, confirmations=None, draft=None):
    built = prepare_text_import(
        text,
        entity_type=entity_type,
        user=user,
        confirmations=confirmations,
        draft=draft,
    )
    if built['needs_confirmation']:
        raise TextImportError('Related entities need confirmation.')
    return built['payload']


def _is_confirmed(value):
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes'}
    return bool(value)


def import_text(text, user, entity_type='Note', confirmations=None, draft=None, confirm=False, extra_tag=None):
    built = prepare_text_import(
        text,
        entity_type=entity_type,
        user=user,
        confirmations=confirmations,
        draft=draft,
    )
    preview = built.get('preview') or _plan_preview(built['draft'], user)
    if not _is_confirmed(confirm) or built['needs_confirmation']:
        return {
            'success': False,
            'needs_confirmation': True,
            'message': 'Review the import before creating entities',
            'confirmations': built['confirmations'],
            'draft': built['draft'],
            'preview': preview,
            'type': built['draft']['entity_type'],
            'default_tag': IMPORT_TAG,
        }

    if not built['draft'].get('entities'):
        return {
            'success': True,
            'needs_confirmation': False,
            'message': 'Imported 0 entities from text',
            'created': 0,
            'updated': 0,
            'related_created': 0,
            'relations_created': 0,
            'errors': [],
            'type': built['draft'].get('entity_type') or entity_type,
            'lines': 0,
            'tags': _create_tags(extra_tag),
        }

    payload = _plan_to_payload(built['draft'], extra_tag=extra_tag)
    stats = execute_import_v2(payload, user)
    created = stats.get('entities_created') or 0
    updated = stats.get('entities_updated') or 0
    related = max(0, created - sum(1 for item in built['draft']['entities'] if item.get('import_op') != 'update'))
    errors = stats.get('errors') or []
    parts = []
    if created:
        parts.append(f'{created} {"entity" if created == 1 else "entities"}')
    if updated:
        parts.append(f'{updated} updated')
    return {
        'success': True,
        'needs_confirmation': False,
        'message': f'Imported {", ".join(parts) or "0 entities"} from text',
        'created': created,
        'updated': updated,
        'related_created': related,
        'relations_created': stats.get('relations_created') or 0,
        'errors': errors,
        'type': built['draft']['entity_type'],
        'lines': len(built['draft']['entities']),
        'tags': _create_tags(extra_tag),
    }
