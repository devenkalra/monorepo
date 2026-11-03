"""One-time ClickUp migration: description sections + Introduced by -> Relationship data JSON.

Runs against the configured People and Orgs lists. Dry by default; live writes go through WriteGuard.
"""
from collections import defaultdict

from . import runner
from .engine import ClickUp, WriteGuard, open_list
from .engine import relations as rel
from .engine.errors import ConfigError
from .engine.fields import INTRODUCED_BY_FIELD
from .engine.transfer import LISTS, read_list, TransferLog


def _kind_maps(lists_tasks, list_ids):
    """task_id -> list key, task_id -> name."""
    kinds, names = {}, {}
    for kind, tasks in lists_tasks.items():
        for t in tasks:
            kinds[t['id']] = kind
            names[t['id']] = t.get('name') or t['id']
    return kinds, names


def _collect(lists_tasks, fields_by_kind):
    """Gather merged relationship lines per task from structured + legacy sources."""
    by_task = {}
    unparsed_by = {}
    for kind, tasks in lists_tasks.items():
        fields = fields_by_kind[kind]
        for t in tasks:
            data_raw = rel.field_value(t, rel.DATA_FIELD, fields=fields)
            intro_raw = rel.field_value(t, INTRODUCED_BY_FIELD, fields=fields)
            md = t.get('markdown_description') or t.get('description') or ''
            lines, unparsed, _ = rel.load_lines(md, data_raw, intro_raw)
            by_task[t['id']] = lines
            if unparsed:
                unparsed_by[t['id']] = unparsed
    return by_task, unparsed_by


def _ensure_inverses(by_task, kinds, names):
    extras = defaultdict(list)
    for tid, lines in by_task.items():
        own = kinds.get(tid)
        if not own:
            continue
        for ln in lines:
            other = ln['target_id']
            okind = kinds.get(other)
            if not okind:
                continue
            inv = rel.inverse(ln['label'], own, okind)
            extras[other].append({
                'label': inv, 'target_id': tid, 'name': names.get(tid, ''),
                'note': ln.get('note') or '',
            })
    for tid, extra in extras.items():
        by_task[tid] = rel.merge_lines(by_task[tid], extra)
    return by_task


def plan(lists_tasks, fields_by_kind):
    """Return {task_id: {name, kind, payload, notes, clear_intro, strip_desc, unparsed, skip_reason}}."""
    kinds, names = _kind_maps(lists_tasks, None)
    by_task, unparsed_by = _collect(lists_tasks, fields_by_kind)
    by_task = _ensure_inverses(by_task, kinds, names)
    out = {}
    for kind, tasks in lists_tasks.items():
        fields = fields_by_kind[kind]
        data_f = next((f for f in fields if f['name'].strip().lower() == rel.DATA_FIELD.lower()), None)
        intro_f = next((f for f in fields if f['name'].strip().lower() == INTRODUCED_BY_FIELD.lower()), None)
        for t in tasks:
            tid = t['id']
            md = t.get('markdown_description') or t.get('description') or ''
            notes, _, unparsed = rel.parse(md)
            data_raw = rel.field_value(t, rel.DATA_FIELD, fields=fields) or ''
            intro_raw = rel.field_value(t, INTRODUCED_BY_FIELD, fields=fields)
            payload = rel.encode_data(by_task.get(tid, []))
            has_intro = bool(intro_raw)
            has_sections = bool(rel.HEADER_RE.search(md or ''))
            already = (str(data_raw).strip() == payload and not has_intro
                       and (not has_sections or bool(unparsed)))
            skip = None
            if not data_f:
                skip = f'missing "{rel.DATA_FIELD}" field on {LISTS[kind]}'
            elif unparsed and has_sections:
                # Still write Relationship data + intro clear; leave description alone.
                pass
            out[tid] = {
                'id': tid, 'name': names[tid], 'kind': kind,
                'payload': payload, 'notes': notes,
                'clear_intro': bool(intro_f and has_intro),
                'strip_desc': has_sections and not unparsed,
                'unparsed': unparsed[:5],
                'data_field_id': data_f['id'] if data_f else None,
                'intro_field_id': intro_f['id'] if intro_f else None,
                'changed': not already and data_f is not None,
                'skip_reason': skip,
                'edge_count': len(by_task.get(tid, [])),
            }
    return out


def migrate(*, dry=True, max_ops=None, reporter=None):
    """Migrate both lists. Returns (plan_rows, guard, warnings)."""
    token, people = runner.clickup_config()
    orgs = runner.orgs_list_id()
    if not token or not people:
        raise ConfigError('Set CONTACTS_CLICKUP_LIST_ID and a ClickUp token.')
    if not orgs:
        raise ConfigError('Set CONTACTS_CLICKUP_ORGS_LIST_ID — Relationship data must exist on Orgs too.')
    if not dry and not runner.writes_enabled():
        raise ConfigError('Live ClickUp writes are disabled (CONTACTS_CLICKUP_WRITES_ENABLED).')

    guard = WriteGuard(dry=dry, writes_enabled=not dry, max_ops=max_ops)
    log = TransferLog(reporter)
    lists_tasks, fields_by_kind = {}, {}
    clients = {}
    for kind, lid in (('people', people), ('orgs', orgs)):
        cu, _missing = open_list(token, lid, guard)
        clients[kind] = cu
        info, fields, tasks = read_list(cu, log, LISTS[kind])
        if not any(f['name'].strip().lower() == rel.DATA_FIELD.lower() for f in fields):
            raise ConfigError(f'{LISTS[kind]} list "{info.get("name")}" is missing a "{rel.DATA_FIELD}" field.')
        lists_tasks[kind] = tasks
        fields_by_kind[kind] = fields

    planned = plan(lists_tasks, fields_by_kind)
    warnings = []
    for row in planned.values():
        if row['unparsed']:
            warnings.append(f'{row["name"]}: left description sections in place (unparsed: '
                            + '; '.join(row['unparsed']) + ')')
        if row['skip_reason']:
            warnings.append(f'{row["name"]}: skipped — {row["skip_reason"]}')

    for row in planned.values():
        if row['skip_reason'] or not row['changed']:
            continue
        cu = clients[row['kind']]
        tid, name = row['id'], row['name']
        handle = guard.begin('set_relationships', task_id=tid, task_name=name, field=rel.DATA_FIELD,
                             after=row['payload'])
        if handle is not None:
            try:
                cu._req('POST', f'/task/{tid}/field/{row["data_field_id"]}', json={'value': row['payload']})
            except Exception as e:
                guard.done(handle, error=str(e))
                raise
            guard.done(handle)
        if row['strip_desc']:
            handle = guard.begin('strip_description', task_id=tid, task_name=name, field='description',
                                 after=row['notes'])
            if handle is not None:
                try:
                    cu._req('PUT', f'/task/{tid}', json={'markdown_content': row['notes']})
                except Exception as e:
                    guard.done(handle, error=str(e))
                    raise
                guard.done(handle)
        if row['clear_intro'] and row['intro_field_id']:
            handle = guard.begin('clear_introduced_by', task_id=tid, task_name=name,
                                 field=INTRODUCED_BY_FIELD)
            if handle is not None:
                try:
                    cu._req('DELETE', f'/task/{tid}/field/{row["intro_field_id"]}')
                except Exception as e:
                    guard.done(handle, error=str(e))
                    raise
                guard.done(handle)

    return list(planned.values()), guard, warnings
