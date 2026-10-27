"""People & Orgs editor: list, read and edit ClickUp contacts and the relationships between them.

The list view reads a local copy of both lists (EntityCache) because reading ~4,000 tasks from ClickUp takes
a minute. Details are always read live, and a save is refused if the task changed in ClickUp after the
editor loaded it. Fields the sync owns are locked here and on the server.
"""
import re
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from . import runner
from .engine import ClickUp, WriteGuard
from .engine import relations as rel
from .engine.clickup import TEXT_TYPES
from .engine.errors import ConfigError
from .engine.fields import FIELDS, task_url
from .engine.transfer import LISTS, NUMBER_TYPES, TransferLog, read_list, task_record
from .models import ContactsState, EntityCache, EntityEdit, SyncRun

META_KEY = 'entities_meta'
EDITABLE_TYPES = TEXT_TYPES + NUMBER_TYPES + ('date', 'checkbox', 'drop_down', 'labels')
LINK_TYPES = ('tasks', 'list_relationship')
MAX_EDIT_WRITES = 300
NAME_KEY = {name.lower(): key for key, name in FIELDS.items()}

# People fields only the sync may change: source keys, change hashes and bookkeeping.
SYNC_OWNED = {'google_id', 'google_link', 'google_hash', 'linkedin_url', 'linkedin_hash', 'whatsapp',
              'whatsapp_hash', 'sources', 'status', 'dup_of', 'last_synced', 'connected_on', 'last_li_msg',
              'last_wa_msg'}
# People fields a sync overwrites when the contact is linked to one of these sources.
FROM_SOURCE = {'company': ('google_id', 'linkedin_url'), 'title': ('google_id', 'linkedin_url'),
               'birthday': ('google_id',), 'address': ('google_id',), 'website': ('google_id',)}
SOURCE_NAME = {'google_id': 'Google', 'linkedin_url': 'LinkedIn'}
ADD_ONLY = {'emails', 'phones', 'groups'}
LABEL_RE = re.compile(r'^[^\[\]\n]+$')


class EditError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class EditJournal:
    """Collects the writes of one save for EntityEdit.changes (the WriteGuard journal interface)."""

    def __init__(self, entries):
        self.entries = entries

    def record(self, **entry):
        entry['ok'] = False
        self.entries.append(entry)
        return entry

    def finish(self, handle, error=None):
        handle['ok'] = error is None
        if error:
            handle['error'] = str(error)[:300]


# ---- configuration ------------------------------------------------------------------------
def configured_lists():
    token, people = runner.clickup_config()
    if not token or not people:
        raise ConfigError('Set CONTACTS_CLICKUP_LIST_ID and a ClickUp token (CLICKUP_API_TOKEN).')
    ids = {'people': str(people)}
    if runner.orgs_list_id():
        ids['orgs'] = str(runner.orgs_list_id())
    return token, ids


def _client(list_id='', guard=None):
    token, _ = configured_lists()
    return ClickUp(token, list_id, guard or WriteGuard(dry=True))


def _kind(task, ids):
    list_id = str((task.get('list') or {}).get('id') or '')
    return next((k for k, v in ids.items() if v == list_id), None)


def _get_task(cu, task_id):
    try:
        return cu._req('GET', f'/task/{task_id}', params={'include_markdown_description': 'true'})
    except RuntimeError as e:
        if '-> 404' in str(e) or '-> 401' in str(e):
            raise EditError(404, f'ClickUp task {task_id} was not found.')
        raise


def _list_meta(cu, list_id):
    info = cu._req('GET', f'/list/{list_id}')
    fields = cu._req('GET', f'/list/{list_id}/field').get('fields', [])
    return [s['status'] for s in info.get('statuses', [])], fields


def _description(task):
    return task.get('markdown_description') or task.get('description') or ''


# ---- field values -------------------------------------------------------------------------
def _options(f):
    return (f.get('type_config') or {}).get('options') or []


def _option_name(o):
    return o.get('name') or o.get('label') or ''


def _empty(v):
    return v is None or v == '' or v == []


def form_value(f, raw):
    """ClickUp's value -> the editor's: option IDs for dropdowns and labels, milliseconds for dates."""
    t = f.get('type')
    if t == 'checkbox':
        return raw in (True, 'true', 1, '1')
    if _empty(raw):
        return [] if t in ('labels',) + LINK_TYPES else None
    if t == 'drop_down':
        return next((o['id'] for o in _options(f)
                     if raw == o.get('id') or str(raw) == str(o.get('orderindex'))), None)
    if t == 'labels':
        return [x.get('id') if isinstance(x, dict) else x for x in raw]
    if t == 'date':
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            return None
    if t in NUMBER_TYPES:
        try:
            n = float(raw)
        except (TypeError, ValueError):
            return None
        return int(n) if n.is_integer() else n
    if t in TEXT_TYPES:
        return str(raw)
    if t in LINK_TYPES:
        return [{'id': x.get('id'), 'name': x.get('name', '')} for x in raw if isinstance(x, dict)]
    if t == 'users':
        return [x.get('username') or x.get('email') or '' for x in raw if isinstance(x, dict)]
    return raw if isinstance(raw, (str, int, float)) else str(raw)


def display_value(f, raw):
    v = form_value(f, raw)
    if f.get('type') == 'drop_down':
        return next((_option_name(o) for o in _options(f) if o.get('id') == v), '')
    if f.get('type') == 'labels':
        names = {o.get('id'): _option_name(o) for o in _options(f)}
        return [names.get(x, x) for x in v]
    if f.get('type') in LINK_TYPES:
        return [x['name'] or x['id'] for x in v]
    return v


def encode(f, v):
    """The editor's value -> what ClickUp accepts, or None to clear the field. Raises ValueError."""
    t = f.get('type')
    if t == 'checkbox':
        return bool(v)
    if _empty(v):
        return None
    if t in TEXT_TYPES:
        return str(v).strip() or None
    if t in NUMBER_TYPES:
        try:
            n = float(v)
        except (TypeError, ValueError):
            raise ValueError('must be a number')
        return int(n) if n.is_integer() else n
    if t == 'date':
        try:
            return int(float(v))
        except (TypeError, ValueError):
            raise ValueError('must be a date')
    ids = {o.get('id') for o in _options(f)}
    if t == 'drop_down':
        if v not in ids:
            raise ValueError('is not one of the options')
        return v
    if t == 'labels':
        if not isinstance(v, list) or any(x not in ids for x in v):
            raise ValueError('has a label that is not one of the options')
        return list(dict.fromkeys(v))
    raise ValueError('can only be edited in ClickUp')


def _same(f, old, new):
    t = f.get('type')
    if t == 'checkbox':
        return bool(old) == bool(new)
    if _empty(old) and _empty(new):
        return True
    if t == 'labels':
        return sorted(old or []) == sorted(new or [])
    if t in TEXT_TYPES:
        return str(old or '').strip() == str(new or '').strip()
    return old == new


def field_specs(kind, fields, task):
    """Every custom field of the task's list with its value and, for sync-owned fields, why it's locked."""
    raw = {cf['id']: cf.get('value') for cf in task.get('custom_fields', [])}
    by_key = {NAME_KEY[f['name'].strip().lower()]: raw.get(f['id'])
              for f in fields if f['name'].strip().lower() in NAME_KEY}
    specs = []
    for f in fields:
        key = NAME_KEY.get(f['name'].strip().lower()) if kind == 'people' else None
        locked = hint = None
        linked = [SOURCE_NAME[s] for s in FROM_SOURCE.get(key, ()) if not _empty(by_key.get(s))]
        if f.get('type') not in EDITABLE_TYPES:
            locked = 'This kind of field can only be edited in ClickUp.'
        elif key in SYNC_OWNED:
            locked = 'Set by the sync. Changing it here could break matching with Google, LinkedIn or WhatsApp.'
        elif linked:
            locked = (f'Filled in from {" and ".join(linked)} on every sync, so a change made here would be '
                      'overwritten. Change it in the source instead.')
        elif key in ADD_ONLY:
            hint = ('Syncs only add to this. Anything you remove that is still in Google, LinkedIn or WhatsApp '
                    'comes back on the next sync.')
        specs.append({
            'id': f['id'], 'name': f['name'], 'type': f.get('type'), 'key': key,
            'options': [{'id': o.get('id'), 'name': _option_name(o), 'color': o.get('color')} for o in _options(f)],
            'value': form_value(f, raw.get(f['id'])), 'locked': locked, 'hint': hint,
        })
    return specs


# ---- the list -----------------------------------------------------------------------------
def build_row(kind, rec, fields_by_id):
    vals = {}
    for cf in rec['custom_fields']:
        f = fields_by_id.get(cf['field_id']) or {'name': cf['name'], 'type': cf['type']}
        vals[f['name'].strip().lower()] = display_value(f, cf['value'])

    def text(name):
        v = vals.get(name)
        return ', '.join(map(str, v)) if isinstance(v, list) else ('' if v is None else str(v))

    def items(name):
        v = vals.get(name)
        return v if isinstance(v, list) else ([v] if v else [])

    lines = rel.split(rec['description'])[1]
    return {
        'id': rec['id'], 'list': kind, 'name': rec['name'], 'status': rec['status'] or '',
        'archived': rec['archived'], 'updated': int(rec['date_updated'] or 0), 'url': rec['url'],
        'company': text('company'), 'title': text('title'), 'emails': text('emails') or text('email'),
        'phones': text('phones'), 'groups': items('groups'), 'sources': items('sources'),
        'match': text('match status'), 'relationships': len(lines),
    }


def refresh(reporter=None):
    """Re-read both lists from ClickUp into the local copy. Read-only on ClickUp."""
    _, ids = configured_lists()
    log = TransferLog(reporter)
    meta = {'refreshed_at': timezone.now().isoformat(), 'lists': {}}
    rows = []
    for kind, list_id in ids.items():
        info, fields, tasks = read_list(_client(list_id), log, LISTS[kind])
        by_id = {f['id']: f for f in fields}
        rows += [build_row(kind, task_record(t), by_id) for t in tasks]
        meta['lists'][kind] = {'id': list_id, 'name': info.get('name', '') or LISTS[kind]}
    with transaction.atomic():
        EntityCache.objects.all().delete()
        EntityCache.objects.bulk_create([EntityCache(task_id=r['id'], list_key=r['list'], row=r) for r in rows],
                                        batch_size=500)
        ContactsState.put(META_KEY, meta)
    return listing()


def listing():
    _, ids = configured_lists()
    meta = ContactsState.get(META_KEY) or {}
    if not meta or {k: v['id'] for k, v in meta.get('lists', {}).items()} != ids:
        return {'loaded': False, 'entities': [], 'lists': {}, 'refreshed_at': None, 'stale': False}
    refreshed = datetime.fromisoformat(meta['refreshed_at'])
    return {
        'loaded': True,
        'refreshed_at': meta['refreshed_at'],
        'stale': SyncRun.objects.filter(mode=SyncRun.Mode.LIVE, finished_at__gt=refreshed).exists(),
        'lists': meta['lists'],
        'entities': [c.row for c in EntityCache.objects.all()],
    }


def _refresh_rows(cu, task_ids, ids):
    fields = {}
    out = []
    for tid in task_ids:
        try:
            t = _get_task(cu, tid)
        except EditError:
            EntityCache.objects.filter(task_id=tid).delete()
            continue
        kind = _kind(t, ids)
        if not kind:
            continue
        if kind not in fields:
            fields[kind] = {f['id']: f for f in cu._req('GET', f'/list/{ids[kind]}/field').get('fields', [])}
        row = build_row(kind, task_record(t), fields[kind])
        EntityCache.objects.update_or_create(task_id=tid, defaults={'list_key': kind, 'row': row})
        out.append(row)
    return out


# ---- detail -------------------------------------------------------------------------------
def _target(tid, cu, ids, cache):
    """(kind, current name) of a relationship target, or (None, None) if it isn't in either list."""
    if tid in cache:
        return cache[tid]
    row = EntityCache.objects.filter(task_id=tid).first()
    if row:
        cache[tid] = (row.list_key, row.row.get('name', ''))
    else:
        try:
            t = _get_task(cu, tid)
            cache[tid] = (_kind(t, ids), t.get('name', ''))
        except EditError:
            cache[tid] = (None, None)
    return cache[tid]


def detail(task_id):
    _, ids = configured_lists()
    cu = _client()
    t = _get_task(cu, task_id)
    kind = _kind(t, ids)
    if not kind:
        raise EditError(404, f'{t.get("name") or task_id} is not in the People or Orgs list.')
    statuses, fields = _list_meta(cu, ids[kind])
    notes, lines, unparsed = rel.parse(_description(t))
    cache = {}
    relationships = []
    for ln in lines:
        tkind, tname = _target(ln['target_id'], cu, ids, cache)
        relationships.append(dict(ln, name=tname or ln['name'], target_list=tkind))
    return {
        'id': t['id'], 'list': kind, 'list_name': LISTS[kind], 'name': t.get('name', ''),
        'status': (t.get('status') or {}).get('status', ''), 'statuses': statuses,
        'url': t.get('url') or task_url(t['id']), 'archived': bool(t.get('archived')),
        'date_updated': t.get('date_updated'), 'notes': notes,
        'fields': field_specs(kind, fields, t),
        'relationships': relationships,
        'relationships_editable': not unparsed,
        'unparsed': unparsed[:5],
        'suggestions': {other: rel.SUGGESTIONS.get((kind, other), []) for other in ('people', 'orgs')
                        if rel.section_for(kind, other)},
    }


# ---- save ---------------------------------------------------------------------------------
def _write(cu, method, path, body, *, op, task_id, task_name, field='', before=None, after=None):
    handle = cu.guard.begin(op, task_id=task_id, task_name=task_name, field=field, before=before, after=after)
    try:
        cu._req(method, path, **({'json': body} if body is not None else {}))
    except Exception as e:
        cu.guard.done(handle, str(e))
        raise
    cu.guard.done(handle)


def _desired_relationships(kind, task_id, items, current, cu, ids, cache, errors):
    out, seen = [], set()
    current_sections = {ln['target_id']: ln['section'] for ln in current}
    for it in items:
        tid = str(it.get('target_id') or '').strip()
        lab = ' '.join(str(it.get('label') or '').split())
        note = ' '.join(str(it.get('note') or '').split())
        if not tid or not lab:
            errors.append('Every relationship needs a type and a person or organization.')
            continue
        if not LABEL_RE.match(lab):
            errors.append(f'Relationship type "{lab}" can\'t contain square brackets.')
            continue
        if tid == task_id:
            errors.append('An entity can\'t be related to itself.')
            continue
        tkind, tname = _target(tid, cu, ids, cache)
        if tkind:
            section = rel.section_for(kind, tkind)
            if not section:
                errors.append(f'{tname}: organizations can only be linked to people.')
                continue
        elif tid in current_sections:
            section = current_sections[tid]
            tname = next(ln['name'] for ln in current if ln['target_id'] == tid)
        else:
            errors.append(f'Task {tid} is not in the People or Orgs list.')
            continue
        if (tid, lab.lower()) in seen:
            errors.append(f'{tname} is listed twice as "{lab}".')
            continue
        seen.add((tid, lab.lower()))
        out.append({'section': section, 'label': lab, 'name': tname, 'target_id': tid, 'note': note,
                    'target_list': tkind})
    return out


def save(task_id, body, user=''):
    """Apply one explicit save from the editor. Returns {'changed', 'warnings', 'rows', 'entity'}."""
    if not runner.writes_enabled():
        raise EditError(409, 'Live ClickUp writes are disabled on this server '
                             '(set CONTACTS_CLICKUP_WRITES_ENABLED=1 to allow edits).')
    if SyncRun.objects.filter(mode=SyncRun.Mode.LIVE,
                              status__in=[SyncRun.Status.QUEUED, SyncRun.Status.RUNNING]).exists():
        raise EditError(409, 'A live sync is running. Save again when it has finished.')
    _, ids = configured_lists()
    edit = EntityEdit(task_id=task_id, edited_by=user)
    cu = _client('', WriteGuard(dry=False, writes_enabled=True, max_ops=MAX_EDIT_WRITES,
                                journal=EditJournal(edit.changes)))
    t = _get_task(cu, task_id)
    kind = _kind(t, ids)
    if not kind:
        raise EditError(404, f'{t.get("name") or task_id} is not in the People or Orgs list.')
    if str(body.get('date_updated') or '') != str(t.get('date_updated') or ''):
        raise EditError(409, f'{t.get("name")} was changed in ClickUp after you opened it. '
                             'Reload it and make your changes again.')
    statuses, fields = _list_meta(cu, ids[kind])
    specs = {s['id']: s for s in field_specs(kind, fields, t)}
    fdefs = {f['id']: f for f in fields}
    errors, task_body = [], {}

    if 'name' in body:
        name = ' '.join(str(body['name'] or '').split())
        if not name:
            errors.append('Name can\'t be empty.')
        elif name != t.get('name'):
            task_body['name'] = name
    status = (t.get('status') or {}).get('status', '')
    if body.get('status') and body['status'] != status:
        if body['status'] not in statuses:
            errors.append(f'"{body["status"]}" is not a status of this list.')
        else:
            task_body['status'] = body['status']

    old_md = _description(t)
    notes, current, unparsed = rel.parse(old_md)
    new_notes = str(body['notes']) if body.get('notes') is not None else notes
    cache = {}
    desired = current
    if body.get('relationships') is not None:
        desired = _desired_relationships(kind, task_id, body['relationships'], current, cu, ids, cache, errors)
    if rel.HEADER_RE.search(new_notes):
        errors.append('Notes can\'t contain a line that is only **Relationships**, **Organizations** or **People**.')
    new_md = rel.render(new_notes, desired)
    if new_md != rel.render(notes, current):
        if unparsed:
            errors.append('The relationship sections of this description contain text the editor doesn\'t '
                          'understand, so notes and relationships can only be changed in ClickUp.')
        else:
            task_body['markdown_content'] = new_md

    field_writes = []
    for fid, value in (body.get('fields') or {}).items():
        spec = specs.get(fid)
        if not spec:
            errors.append(f'Unknown field {fid}.')
            continue
        try:
            new = encode(fdefs[fid], value)
        except ValueError as e:
            errors.append(f'{spec["name"]} {e}.')
            continue
        if _same(fdefs[fid], spec['value'], new):
            continue
        if spec['locked']:
            errors.append(f'{spec["name"]} is managed by the sync and can\'t be changed here.')
            continue
        field_writes.append((spec, new))
    if errors:
        raise EditError(400, ' '.join(dict.fromkeys(errors)))

    new_name = task_body.get('name', t.get('name', ''))
    old_by_key = {rel.key(ln): ln for ln in current}
    new_by_key = {rel.key(ln): ln for ln in desired}
    other = [(ln, True) for k, ln in old_by_key.items() if k not in new_by_key]
    other += [(ln, False) for k, ln in new_by_key.items()
              if k not in old_by_key or old_by_key[k]['note'] != ln['note'] or 'name' in task_body]

    if not task_body and not field_writes and not other:
        return {'changed': False, 'warnings': [], 'rows': [], 'entity': detail(task_id)}

    edit.task_name = t.get('name', '')
    edit.save()
    warnings, touched = [], [task_id]
    try:
        if task_body:
            _write(cu, 'PUT', f'/task/{task_id}', task_body, op='update_task', task_id=task_id,
                   task_name=edit.task_name, field=', '.join(sorted(task_body)),
                   before={'name': t.get('name'), 'status': status, 'description': old_md}, after=task_body)
        for spec, new in field_writes:
            if new is None:
                _write(cu, 'DELETE', f'/task/{task_id}/field/{spec["id"]}', None, op='clear_field',
                       task_id=task_id, task_name=edit.task_name, field=spec['name'], before=spec['value'])
            else:
                _write(cu, 'POST', f'/task/{task_id}/field/{spec["id"]}', {'value': new}, op='set_field',
                       task_id=task_id, task_name=edit.task_name, field=spec['name'], before=spec['value'],
                       after=new)
        for ln, remove in other:
            tkind = ln.get('target_list') or _target(ln['target_id'], cu, ids, cache)[0]
            if not tkind:
                continue
            target = _get_task(cu, ln['target_id'])
            md = _description(target)
            if rel.parse(md)[2]:
                warnings.append(f'{target.get("name")} wasn\'t updated: its relationship sections contain text the '
                                'editor doesn\'t understand. Update it in ClickUp.')
                continue
            new_target_md, changed = rel.upsert_line(md, rel.section_for(tkind, kind),
                                                     rel.inverse(ln['label'], kind, tkind), task_id, new_name,
                                                     ln['note'], remove=remove)
            if changed:
                _write(cu, 'PUT', f'/task/{target["id"]}', {'markdown_content': new_target_md},
                       op='update_relationship', task_id=target['id'], task_name=target.get('name', ''),
                       field='description', before=md, after=new_target_md)
                touched.append(target['id'])
    except Exception as e:
        edit.error = str(e)[:1000]
        edit.save()
        _refresh_rows(_client(), touched, ids)
        raise EditError(502, f'Stopped part-way through saving: {e}. Reload to see what was saved.')
    edit.ok = True
    edit.save()
    return {'changed': True, 'warnings': warnings, 'rows': _refresh_rows(_client(), touched, ids),
            'entity': detail(task_id)}
