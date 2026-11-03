"""Rebuild task descriptions from authoritative Relationship data.

Wipes the current description and writes a fresh managed ### heading block generated from
Relationship data (ClickUp panel task links). Does not write Relationship display.

Dry by default; live writes go through WriteGuard. Safe to re-run.
"""
from . import runner
from .engine import WriteGuard, open_list
from .engine import relations as rel
from .engine.errors import ConfigError
from .engine.transfer import LISTS, read_list, TransferLog


def _names_and_kinds(lists_tasks):
    names, kinds = {}, {}
    for kind, tasks in lists_tasks.items():
        for t in tasks:
            kinds[t['id']] = kind
            names[t['id']] = t.get('name') or t['id']
    return names, kinds


def _lines_for_display(task, fields, kind, names, kinds):
    data_raw = rel.field_value(task, rel.DATA_FIELD, fields=fields)
    lines = rel.decode_data(data_raw)
    out = []
    for ln in lines:
        tid = ln['target_id']
        tkind = kinds.get(tid)
        section = rel.section_for(kind, tkind) if tkind else None
        if tkind and not section:
            continue
        out.append({
            'label': ln['label'], 'target_id': tid, 'note': ln.get('note') or '',
            'name': names.get(tid) or ln.get('name') or tid,
            'section': section or 'Relationships',
        })
    return out


def _description(task):
    return task.get('markdown_description') or task.get('description') or ''


def plan(lists_tasks, fields_by_kind):
    """Return plan rows keyed by task id. Description is replaced entirely from Relationship data."""
    names, kinds = _names_and_kinds(lists_tasks)
    out = {}
    for kind, tasks in lists_tasks.items():
        fields = fields_by_kind[kind]
        data_f = next((f for f in fields if f['name'].strip().lower() == rel.DATA_FIELD.lower()), None)
        for t in tasks:
            tid = t['id']
            skip = None if data_f else f'missing "{rel.DATA_FIELD}" field on {LISTS[kind]}'
            lines = _lines_for_display(t, fields, kind, names, kinds) if not skip else []
            # Wipe description; regenerate only the managed block from Relationship data.
            new_md = rel.compose_description(lines, '')
            md = _description(t)
            out[tid] = {
                'id': tid, 'name': names[tid], 'kind': kind,
                'description': new_md,
                'edge_count': len(lines),
                'update_description': not skip and new_md != (md or '').rstrip(),
                'changed': not skip and new_md != (md or '').rstrip(),
                'skip_reason': skip,
            }
    return out


def sync(*, dry=True, max_ops=None, reporter=None):
    """Replace descriptions from Relationship data. Returns (plan_rows, guard, warnings)."""
    token, people = runner.clickup_config()
    orgs = runner.orgs_list_id()
    if not token or not people:
        raise ConfigError('Set CONTACTS_CLICKUP_LIST_ID and a ClickUp token.')
    if not orgs:
        raise ConfigError('Set CONTACTS_CLICKUP_ORGS_LIST_ID.')
    if not dry and not runner.writes_enabled():
        raise ConfigError('Live ClickUp writes are disabled (CONTACTS_CLICKUP_WRITES_ENABLED).')

    guard = WriteGuard(dry=dry, writes_enabled=not dry, max_ops=max_ops)
    log = TransferLog(reporter)
    lists_tasks, fields_by_kind, clients = {}, {}, {}
    for kind, lid in (('people', people), ('orgs', orgs)):
        cu, _missing = open_list(token, lid, guard)
        clients[kind] = cu
        info, fields, tasks = read_list(cu, log, LISTS[kind])
        if not any(f['name'].strip().lower() == rel.DATA_FIELD.lower() for f in fields):
            raise ConfigError(f'{LISTS[kind]} list "{info.get("name")}" is missing a "{rel.DATA_FIELD}" field.')
        lists_tasks[kind] = tasks
        fields_by_kind[kind] = fields

    planned = plan(lists_tasks, fields_by_kind)
    warnings = [f'{r["name"]}: skipped — {r["skip_reason"]}' for r in planned.values() if r['skip_reason']]

    for row in planned.values():
        if row['skip_reason'] or not row['changed']:
            continue
        cu = clients[row['kind']]
        handle = guard.begin('set_description_relationships', task_id=row['id'], task_name=row['name'],
                             field='description', after=row['description'])
        if handle is not None:
            try:
                cu._req('PUT', f'/task/{row["id"]}', json={'markdown_content': row['description']})
            except Exception as e:
                guard.done(handle, error=str(e))
                raise
            guard.done(handle)

    return list(planned.values()), guard, warnings
