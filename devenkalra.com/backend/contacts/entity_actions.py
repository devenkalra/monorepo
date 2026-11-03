"""Named bulk actions on People & Orgs entities (ClickUp).

Each action plans changes (dry-run friendly) then optionally applies them. Keep this
list small and explicit — add a function + registry entry per action.
"""
from __future__ import annotations

import re

from . import entities, google_auth, runner
from .engine import WriteGuard
from .engine.errors import ConfigError
from .engine.fields import MERGED
from .engine.normalize import norm_email, phone_for_storage
from .engine.sources import google as google_src
from .engine.transfer import task_record
from .models import EntityCache, EntityEdit

PSALUTATION_FIELD = 'PSalutation'
MAX_ACTION_IDS = 500

# Leading courtesy titles stripped before taking a first name from a display name.
_TITLES = frozenset({
    'dr', 'mr', 'mrs', 'ms', 'miss', 'prof', 'professor', 'sir', 'lady', 'lord',
    'rev', 'reverend', 'fr', 'father', 'hon', 'honorable',
})
_INITIAL_RE = re.compile(r'^[A-Za-z]\.?$')
_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


class ActionError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


# ---- first-name helpers -------------------------------------------------------------------
def _clean(s):
    return ' '.join(str(s or '').split())


def looks_like_email_or_phone(name):
    s = _clean(name)
    if not s:
        return True
    if _EMAIL_RE.match(s) or norm_email(s):
        return True
    # Digits-heavy / E.164-ish — treat as phone, not a person name.
    digits = sum(c.isdigit() for c in s)
    if digits >= 7 and phone_for_storage(s):
        return True
    if s.startswith('+') and digits >= 8:
        return True
    return False


def first_name_from_display(name):
    """First name from a ClickUp/LinkedIn/WhatsApp display name, or None if unusable.

    - "Kalra, Deven" → Deven
    - "Dr. Raj Kalra" → Raj
    - "J. Robert Smith" → Robert
    - email / phone-shaped names → None
    """
    s = _clean(name)
    if not s or looks_like_email_or_phone(s):
        return None
    if ',' in s:
        after = _clean(s.split(',', 1)[1])
        if after:
            s = after
    tokens = s.split()
    while tokens and tokens[0].lower().rstrip('.') in _TITLES:
        tokens.pop(0)
    if len(tokens) >= 2 and _INITIAL_RE.match(tokens[0]):
        tokens = tokens[1:]
    if not tokens:
        return None
    first = tokens[0].strip('.,;:')
    if not first or looks_like_email_or_phone(first):
        return None
    return first


def _google_given_names(resource_names):
    """resourceName -> givenName (missing keys = not found / no given name)."""
    if not resource_names:
        return {}
    try:
        svc = google_auth.people_service(write=False)
    except ValueError as e:
        raise ActionError(str(e), 400) from e
    out = {}
    for i in range(0, len(resource_names), google_src.BATCH_GET_MAX):
        chunk = resource_names[i:i + google_src.BATCH_GET_MAX]
        resp = svc.people().getBatchGet(
            resourceNames=chunk,
            personFields='names',
        ).execute()
        for r in resp.get('responses') or []:
            person = r.get('person') or {}
            rid = person.get('resourceName') or r.get('requestedResourceName')
            if not rid:
                continue
            given = _clean(((person.get('names') or [{}])[0]).get('givenName'))
            out[rid] = given or None
    return out


def resolve_first_name(row, google_given):
    """(first_name_or_None, source, skip_reason).

    Google-linked: use Google given name only (skip if absent).
    Otherwise: parse the ClickUp task name.
    """
    gid = _clean(row.get('google_id'))
    if gid:
        if google_given:
            return google_given, 'google', None
        return None, 'google', 'Google contact has no given name'
    first = first_name_from_display(row.get('name') or '')
    if not first:
        return None, 'name', 'no usable first name from display name'
    return first, 'name', None


# ---- action: fill_psalutation -------------------------------------------------------------
def _psalutation_field(fields):
    return next((f for f in fields if f['name'].strip().lower() == PSALUTATION_FIELD.lower()), None)


def _cf_value(task, field_id):
    for cf in task.get('custom_fields') or []:
        if cf.get('id') == field_id:
            v = cf.get('value')
            if v is None:
                return ''
            return _clean(v) if not isinstance(v, (list, dict)) else str(v)
    return ''


def plan_fill_psalutation(ids, *, overwrite=False):
    """Plan PSalutation fills for People tasks. Returns {action, changes, summary}."""
    ids = list(dict.fromkeys(_clean(x) for x in (ids or []) if _clean(x)))
    if not ids:
        raise ActionError('Select at least one person.')
    if len(ids) > MAX_ACTION_IDS:
        raise ActionError(f'At most {MAX_ACTION_IDS} contacts per action.')

    token, list_ids = entities.configured_lists()
    people_id = list_ids['people']
    cu = entities._client(people_id)
    _, fields = entities._list_meta(cu, people_id)
    psal = _psalutation_field(fields)
    if not psal:
        raise ActionError(f'People list has no "{PSALUTATION_FIELD}" field.')

    # Prefer cache for google_id / archived / name; confirm live for apply path later.
    cache = {c.task_id: c.row for c in EntityCache.objects.filter(task_id__in=ids)}
    rows = []
    for tid in ids:
        row = cache.get(tid)
        if not row:
            # Fall back to a live read so selection still works after a stale cache.
            try:
                t = entities._get_task(cu, tid)
            except entities.EditError:
                rows.append({'id': tid, 'name': tid, 'skip_reason': 'not found', 'would_change': False})
                continue
            if entities._kind(t, list_ids) != 'people':
                rows.append({'id': tid, 'name': t.get('name') or tid, 'skip_reason': 'not a person',
                             'would_change': False})
                continue
            row = entities.build_row('people', task_record(t), {f['id']: f for f in fields})
        rows.append(row)

    google_ids = [_clean(r.get('google_id')) for r in rows
                  if isinstance(r, dict) and r.get('google_id') and not r.get('skip_reason')]
    given_by_gid = _google_given_names(google_ids) if google_ids else {}

    changes = []
    for row in rows:
        if row.get('skip_reason'):
            changes.append(row)
            continue
        tid = row['id']
        name = row.get('name') or tid
        if row.get('archived'):
            changes.append({'id': tid, 'name': name, 'skip_reason': 'archived', 'would_change': False})
            continue
        if _clean(row.get('match')).lower() == MERGED:
            changes.append({'id': tid, 'name': name, 'skip_reason': 'merged', 'would_change': False})
            continue

        gid = _clean(row.get('google_id'))
        google_given = given_by_gid.get(gid) if gid else None
        if gid and gid not in given_by_gid:
            changes.append({'id': tid, 'name': name, 'skip_reason': 'Google contact not found',
                            'would_change': False})
            continue

        first, source, skip = resolve_first_name(row, google_given)
        if skip:
            changes.append({'id': tid, 'name': name, 'skip_reason': skip, 'would_change': False,
                            'source': source})
            continue

        # Live current PSalutation (cache may not include it).
        try:
            t = entities._get_task(cu, tid)
        except entities.EditError:
            changes.append({'id': tid, 'name': name, 'skip_reason': 'not found', 'would_change': False})
            continue
        before = _cf_value(t, psal['id'])
        if before and not overwrite:
            changes.append({
                'id': tid, 'name': name, 'before': before, 'after': first, 'source': source,
                'skip_reason': 'PSalutation already set', 'would_change': False,
            })
            continue
        if before == first:
            changes.append({
                'id': tid, 'name': name, 'before': before, 'after': first, 'source': source,
                'skip_reason': 'already correct', 'would_change': False,
            })
            continue
        changes.append({
            'id': tid, 'name': name, 'before': before, 'after': first, 'source': source,
            'skip_reason': None, 'would_change': True, 'field_id': psal['id'],
        })

    return {
        'action': 'fill_psalutation',
        'overwrite': bool(overwrite),
        'field': PSALUTATION_FIELD,
        'changes': changes,
        'summary': {
            'selected': len(ids),
            'would_change': sum(1 for c in changes if c.get('would_change')),
            'skipped': sum(1 for c in changes if c.get('skip_reason')),
        },
    }


def apply_fill_psalutation(plan, *, user='', max_writes=None):
    """Write planned PSalutation changes. `plan` from plan_fill_psalutation."""
    if not runner.writes_enabled():
        raise ActionError('Live ClickUp writes are disabled on this server '
                          '(set CONTACTS_CLICKUP_WRITES_ENABLED=1).', 409)
    todo = [c for c in plan.get('changes') or [] if c.get('would_change') and c.get('field_id')]
    if not todo:
        return {'action': 'fill_psalutation', 'ok': 0, 'failed': 0, 'results': [], 'rows': []}

    budget = max_writes if max_writes is not None else plan.get('max_writes')
    if budget is None:
        budget = max(20, len(todo) + 5)
    if len(todo) > budget:
        raise ActionError(f'Need {len(todo)} writes but max_writes is {budget}.')

    _, list_ids = entities.configured_lists()
    edit = EntityEdit(task_id='(action:fill_psalutation)', task_name='Fill PSalutation', edited_by=user)
    edit.save()
    cu = entities._client(
        list_ids['people'],
        WriteGuard(dry=False, writes_enabled=True, max_ops=budget,
                   journal=entities.EditJournal(edit.changes)),
    )
    results, touched = [], []
    try:
        for c in todo:
            try:
                entities._write(
                    cu, 'POST', f'/task/{c["id"]}/field/{c["field_id"]}', {'value': c['after']},
                    op='set_field', task_id=c['id'], task_name=c['name'], field=PSALUTATION_FIELD,
                    before=c.get('before') or None, after=c['after'],
                )
                results.append({'id': c['id'], 'ok': True, 'name': c['name'], 'after': c['after']})
                touched.append(c['id'])
            except Exception as e:  # noqa: BLE001
                results.append({'id': c['id'], 'ok': False, 'name': c['name'], 'error': str(e)[:300]})
        edit.ok = all(r.get('ok') for r in results)
        edit.save()
    except Exception as e:
        edit.error = str(e)[:1000]
        edit.save()
        raise ActionError(f'Stopped part-way: {e}', 502) from e

    entities.invalidate_details(touched)
    rows = entities._refresh_rows(cu, touched, list_ids)
    return {
        'action': 'fill_psalutation',
        'ok': sum(1 for r in results if r.get('ok')),
        'failed': sum(1 for r in results if not r.get('ok')),
        'results': results,
        'rows': rows,
    }


# ---- registry -----------------------------------------------------------------------------
ACTIONS = {
    'fill_psalutation': {
        'label': 'Fill PSalutation from first name',
        'plan': plan_fill_psalutation,
        'apply': apply_fill_psalutation,
    },
}


def list_actions():
    return [{'id': k, 'label': v['label']} for k, v in ACTIONS.items()]


def run_action(action_id, ids, *, dry_run=True, overwrite=False, user='', max_writes=None):
    spec = ACTIONS.get(action_id)
    if not spec:
        raise ActionError(f'Unknown action "{action_id}".')
    try:
        plan = spec['plan'](ids, overwrite=overwrite)
    except ConfigError as e:
        raise ActionError(str(e), 400) from e
    if dry_run:
        return {'dry_run': True, **plan}
    try:
        applied = spec['apply'](plan, user=user, max_writes=max_writes)
    except ConfigError as e:
        raise ActionError(str(e), 400) from e
    return {'dry_run': False, **plan, **applied}
