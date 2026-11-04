"""People & Orgs editor: list, read, create and edit ClickUp contacts and the relationships between them.

The list view reads a local copy of both lists (EntityCache) because reading ~4,000 tasks from ClickUp takes
a minute. Detail payloads are cached in EntityDetailCache and invalidated when that entity is updated
(editor save, create, live sync) or when the list is refreshed. A save is refused if the task changed in
ClickUp after the editor loaded it. Fields the sync owns are locked here and on the server.

New people are created in Google Contacts first, then mirrored into the ClickUp People list with google_id
set so the next sync updates them instead of duplicating.
"""
import re
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from . import google_auth, runner
from .engine import ClickUp, WriteGuard
from .engine import relations as rel
from .engine.clickup import TEXT_TYPES
from .engine.errors import ConfigError
from .engine.fields import ACTIVE, EXTRA, FIELDS, INTRODUCED_BY_FIELD, SOURCE_LABEL, task_url
from .engine.normalize import norm_email, phone_for_storage, split_list, union
from .engine.sources import google as google_src
from .engine.sync import now_ms
from .engine.transfer import LISTS, NUMBER_TYPES, TransferLog, read_list, task_record
from .models import ContactsState, EntityCache, EntityDetailCache, EntityEdit, GoogleAccount, SyncRun

META_KEY = 'entities_meta'
EDITABLE_TYPES = TEXT_TYPES + NUMBER_TYPES + ('date', 'checkbox', 'drop_down', 'labels')
LINK_TYPES = ('tasks', 'list_relationship')
MAX_EDIT_WRITES = 300
NAME_KEY = {name.lower(): key for key, name in FIELDS.items()}

# People fields only the sync may change: source keys, change hashes and bookkeeping.
SYNC_OWNED = {'google_id', 'google_link', 'google_hash', 'linkedin_url', 'linkedin_hash', 'whatsapp',
              'whatsapp_hash', 'sources', 'status', 'dup_of', 'last_synced', 'connected_on', 'last_li_msg',
              'last_wa_msg', 'relationship_data'}
# People fields a sync overwrites when the contact is linked to one of these sources.
FROM_SOURCE = {'company': ('google_id', 'linkedin_url'), 'title': ('google_id', 'linkedin_url'),
               'birthday': ('google_id',), 'address': ('google_id',), 'city': ('google_id',),
               'country': ('google_id',), 'website': ('google_id',),
               # Google is master for these; LinkedIn/WhatsApp syncs only add when no Google link.
               'emails': ('google_id',), 'email': ('google_id',), 'phones': ('google_id',),
               'groups': ('google_id',)}
SOURCE_NAME = {'google_id': 'Google', 'linkedin_url': 'LinkedIn'}
ADD_ONLY = {'emails', 'phones', 'groups'}
# Edited only via the Relationships UI (structured field + legacy Introduced by).
RELATION_UI_FIELDS = {rel.DATA_FIELD.lower(), INTRODUCED_BY_FIELD.lower()}
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
        raw_s = str(raw).strip()
        raw_i = None
        try:
            raw_i = int(float(raw))
        except (TypeError, ValueError):
            pass
        for o in _options(f):
            if raw == o.get('id') or raw_s == str(o.get('id') or ''):
                return o['id']
            if raw_i is not None and o.get('orderindex') is not None and raw_i == int(o['orderindex']):
                return o['id']
            if _option_name(o).strip().lower() == raw_s.lower():
                return o['id']
        return None
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
        name = next((_option_name(o) for o in _options(f) if o.get('id') == v), '')
        if name or _empty(raw):
            return name
        # Last resort: show the raw value rather than dropping the filter chip entirely.
        return str(raw).strip()
    if f.get('type') == 'labels':
        names = {o.get('id'): _option_name(o) for o in _options(f)}
        return [names.get(x, x) for x in v]
    if f.get('type') in LINK_TYPES:
        return [x['name'] or x['id'] for x in v]
    return v


def field_option_names(fields, name):
    """Display names of every option on a drop_down/labels field, or [] if missing."""
    want = name.strip().lower()
    f = next((x for x in fields if (x.get('name') or '').strip().lower() == want), None)
    if not f or f.get('type') not in ('drop_down', 'labels'):
        return []
    out = []
    for o in _options(f):
        n = _option_name(o).strip()
        if n:
            out.append(n)
    return out


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


def _field_def(fields, name):
    want = name.strip().lower()
    return next((f for f in fields if f['name'].strip().lower() == want), None)


def _cf_raw(task, fields, name):
    return rel.field_value(task, name, fields=fields)


def field_specs(kind, fields, task):
    """Every custom field of the task's list with its value and, for sync-owned fields, why it's locked."""
    raw = {cf['id']: cf.get('value') for cf in task.get('custom_fields', [])}
    by_key = {NAME_KEY[f['name'].strip().lower()]: raw.get(f['id'])
              for f in fields if f['name'].strip().lower() in NAME_KEY}
    specs = []
    for f in fields:
        fname = f['name'].strip().lower()
        key = NAME_KEY.get(fname) if kind == 'people' else (
            'relationship_data' if fname == rel.DATA_FIELD.lower() else None)
        locked = hint = None
        linked = [SOURCE_NAME[s] for s in FROM_SOURCE.get(key, ()) if not _empty(by_key.get(s))]
        if fname in RELATION_UI_FIELDS:
            locked = 'Edit relationships in the Relationships section (stored in Relationship data).'
        elif f.get('type') not in EDITABLE_TYPES:
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

    data_raw = next((cf.get('value') for cf in rec['custom_fields']
                     if (fields_by_id.get(cf['field_id']) or cf).get('name', '').strip().lower()
                     == rel.DATA_FIELD.lower()), None)
    intro_raw = next((cf.get('value') for cf in rec['custom_fields']
                      if (fields_by_id.get(cf['field_id']) or cf).get('name', '').strip().lower()
                      == INTRODUCED_BY_FIELD.lower()), None)
    lines, _, _ = rel.load_lines(rec.get('description') or '', data_raw, intro_raw)
    # Outreach is a People list dropdown or labels field (not sync-owned); always expose as a list
    # of option names so the UI can filter like Groups.
    return {
        'id': rec['id'], 'list': kind, 'name': rec['name'], 'status': rec['status'] or '',
        'archived': rec['archived'], 'updated': int(rec['date_updated'] or 0), 'url': rec['url'],
        'company': text('company'), 'title': text('title'), 'emails': text('emails') or text('email'),
        'phones': text('phones'), 'groups': items('groups'), 'sources': items('sources'),
        'outreach': items('outreach'),
        'psalutation': text('psalutation'), 'fsalutation': text('fsalutation'),
        'match': text('match status'), 'relationships': len(lines),
        'google_id': text('google id'), 'google_link': text('google link'),
    }


def _outreach_options(lists_meta):
    """Union of Outreach dropdown/label options cached on each list during refresh."""
    seen, out = set(), []
    for info in (lists_meta or {}).values():
        for name in info.get('outreach_options') or []:
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(name)
    return out


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
        meta['lists'][kind] = {
            'id': list_id,
            'name': info.get('name', '') or LISTS[kind],
            'outreach_options': field_option_names(fields, 'Outreach'),
        }
    with transaction.atomic():
        EntityCache.objects.all().delete()
        EntityCache.objects.bulk_create([EntityCache(task_id=r['id'], list_key=r['list'], row=r) for r in rows],
                                        batch_size=500)
        EntityDetailCache.objects.all().delete()
        ContactsState.put(META_KEY, meta)
    return listing()


def listing():
    _, ids = configured_lists()
    meta = ContactsState.get(META_KEY) or {}
    if not meta or {k: v['id'] for k, v in meta.get('lists', {}).items()} != ids:
        return {'loaded': False, 'entities': [], 'lists': {}, 'refreshed_at': None, 'stale': False,
                'outreach_options': []}
    refreshed = datetime.fromisoformat(meta['refreshed_at'])
    return {
        'loaded': True,
        'refreshed_at': meta['refreshed_at'],
        'stale': SyncRun.objects.filter(mode=SyncRun.Mode.LIVE, finished_at__gt=refreshed).exists(),
        'lists': meta['lists'],
        'outreach_options': _outreach_options(meta.get('lists')),
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
            invalidate_details([tid])
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


# ---- detail cache -------------------------------------------------------------------------
def invalidate_details(task_ids=None):
    """Drop cached detail payloads. None clears every entry (list refresh / wholesale sync)."""
    if task_ids is None:
        EntityDetailCache.objects.all().delete()
        return
    ids = [str(t) for t in task_ids if t and not str(t).startswith('dry-run')]
    if ids:
        EntityDetailCache.objects.filter(task_id__in=ids).delete()


def _store_detail(payload):
    tid = str(payload.get('id') or '')
    if not tid:
        return payload
    EntityDetailCache.objects.update_or_create(
        task_id=tid,
        defaults={'payload': payload, 'date_updated': str(payload.get('date_updated') or '')},
    )
    return payload


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


def _read_relationships(task, fields, kind, cu, ids, cache):
    """Load relationship lines from Relationship data (preferred), else description + Introduced by."""
    data_raw = _cf_raw(task, fields, rel.DATA_FIELD)
    intro_raw = _cf_raw(task, fields, INTRODUCED_BY_FIELD)
    lines, unparsed, structured = rel.load_lines(_description(task), data_raw, intro_raw)

    enriched = []
    for ln in lines:
        tkind, tname = _target(ln['target_id'], cu, ids, cache)
        section = rel.section_for(kind, tkind) if tkind else ln.get('section')
        if tkind and not section:
            continue
        enriched.append(dict(ln, name=tname or ln.get('name') or '', target_list=tkind,
                             section=section or ln.get('section') or 'Relationships'))
    # Always editable when Relationship data exists on the list; legacy unparsed only blocks
    # stripping leftover description sections.
    has_data_field = _field_def(fields, rel.DATA_FIELD) is not None
    return enriched, unparsed, structured, has_data_field


def _build_detail(task_id, cu=None, ids=None):
    ids = ids or configured_lists()[1]
    cu = cu or _client()
    t = _get_task(cu, task_id)
    kind = _kind(t, ids)
    if not kind:
        raise EditError(404, f'{t.get("name") or task_id} is not in the People or Orgs list.')
    statuses, fields = _list_meta(cu, ids[kind])
    cache = {}
    relationships, unparsed, structured, has_data_field = _read_relationships(t, fields, kind, cu, ids, cache)
    notes = rel.notes_text(_description(t), structured=structured)
    return {
        'id': t['id'], 'list': kind, 'list_name': LISTS[kind], 'name': t.get('name', ''),
        'status': (t.get('status') or {}).get('status', ''), 'statuses': statuses,
        'url': t.get('url') or task_url(t['id']), 'archived': bool(t.get('archived')),
        'date_updated': t.get('date_updated'), 'notes': notes,
        'fields': field_specs(kind, fields, t),
        'relationships': relationships,
        'relationships_editable': has_data_field or not unparsed,
        'unparsed': unparsed[:5],
        'relationship_storage': 'field' if structured or has_data_field else 'description',
        'suggestions': {other: rel.SUGGESTIONS.get((kind, other), []) for other in ('people', 'orgs')
                        if rel.section_for(kind, other)},
    }


def detail(task_id, *, force=False):
    """Return the People & Orgs detail payload, from cache unless force=True or missing."""
    tid = str(task_id)
    if not force:
        hit = EntityDetailCache.objects.filter(task_id=tid).first()
        if hit and hit.payload:
            return hit.payload
    return _store_detail(_build_detail(tid))


# ---- create (Google first) ----------------------------------------------------------------
def _as_list(raw):
    if isinstance(raw, (list, tuple)):
        return [str(x).strip() for x in raw if str(x).strip()]
    return split_list(raw)


def _parse_birthday(raw):
    if not raw:
        return None
    if isinstance(raw, dict):
        m, d = raw.get('month'), raw.get('day')
        if m and d:
            y = raw.get('year')
            return (int(y) if y else None, int(m), int(d))
        return None
    s = str(raw).strip()
    m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})$', s)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    m = re.match(r'^(\d{1,2})-(\d{1,2})$', s)
    if m:
        return None, int(m.group(1)), int(m.group(2))
    raise ValueError('Birthday must be YYYY-MM-DD or MM-DD.')


def _create_blocked():
    if not runner.writes_enabled():
        raise EditError(409, 'Live ClickUp writes are disabled on this server '
                             '(set CONTACTS_CLICKUP_WRITES_ENABLED=1 to allow creates).')
    if SyncRun.objects.filter(mode=SyncRun.Mode.LIVE,
                              status__in=[SyncRun.Status.QUEUED, SyncRun.Status.RUNNING]).exists():
        raise EditError(409, 'A live sync is running. Create again when it has finished.')
    account = GoogleAccount.objects.order_by('id').first()
    if not account or not account.refresh_token:
        raise EditError(400, 'Connect Google first (Overview tab).')
    if not account.can_write:
        raise EditError(400, 'Creating contacts needs write access to Google Contacts; '
                             'grant it from the Overview tab.')
    return account


def create_person(body, user=''):
    """Create a Google contact, then a linked ClickUp People task. Returns entity + cache rows."""
    _create_blocked()
    if not isinstance(body, dict):
        raise EditError(400, 'Expected a JSON object.')

    given = ' '.join(str(body.get('first_name') or body.get('given_name') or '').split())
    family = ' '.join(str(body.get('last_name') or body.get('family_name') or '').split())
    # Legacy single-name payloads still work.
    legacy_name = ' '.join(str(body.get('name') or '').split())
    name = google_src.display_name(given_name=given, family_name=family, name=legacy_name)
    emails = union([norm_email(e) or e for e in _as_list(body.get('emails'))])
    phones = union([phone_for_storage(p) for p in _as_list(body.get('phones'))])
    company = ' '.join(str(body.get('company') or '').split()) or None
    title = ' '.join(str(body.get('title') or '').split()) or None
    address = ' '.join(str(body.get('address') or '').split()) or None
    website = ' '.join(str(body.get('website') or '').split()) or None
    groups = list(dict.fromkeys(_as_list(body.get('groups'))))
    try:
        birthday = _parse_birthday(body.get('birthday'))
    except ValueError as e:
        raise EditError(400, str(e))
    if not name and not emails and not phones:
        raise EditError(400, 'Need a first or last name, email or phone.')
    if not name:
        name = emails[0] if emails else phones[0]

    # Soft duplicate guard against the local People cache (exact email or phone).
    listing_data = listing()
    if listing_data.get('loaded'):
        want_emails = {e.lower() for e in emails}
        want_phones = {p for p in phones}
        for row in listing_data['entities']:
            if row.get('list') != 'people' or row.get('archived'):
                continue
            row_emails = {x.strip().lower() for x in (row.get('emails') or '').split(',') if x.strip()}
            row_phones = {x.strip() for x in (row.get('phones') or '').split(',') if x.strip()}
            hit = (want_emails & row_emails) or (want_phones & row_phones)
            if hit:
                raise EditError(409, f'"{row["name"]}" already has {", ".join(sorted(hit))}. '
                                     'Open that person instead, or clear the overlapping email/phone.')

    try:
        svc = google_auth.people_service(write=True)
    except ValueError as e:
        raise EditError(400, str(e))

    group_names, _ = google_src.load_groups(svc, ())
    by_label = {n.lower(): rn for rn, n in group_names.items()}
    memberships, unknown_groups = [], []
    for g in groups:
        rn = by_label.get(g.lower())
        if rn:
            memberships.append({'contactGroupMembership': {'contactGroupResourceName': rn}})
        else:
            unknown_groups.append(g)

    person = google_src.person_body(given_name=given, family_name=family, name=legacy_name or name,
                                    emails=emails, phones=phones, company=company, title=title,
                                    birthday=birthday, address=address, website=website,
                                    memberships=memberships)
    try:
        created = google_src.create_contact(svc, person)
    except Exception as e:  # noqa: BLE001
        raise EditError(502, f'Google Contacts create failed: {e}')

    c = google_src.google_contact(created, group_names)
    # Prefer the values we just wrote when Google returns a sparse person.
    c['name'] = c['name'] if c['name'] and c['name'] != '(no name)' else name
    c['emails'] = c['emails'] or list(emails)
    c['phones'] = c['phones'] or list(phones)
    c['company'] = c.get('company') or company
    c['title'] = c.get('title') or title
    extra = c.setdefault('extra', {})
    extra['birthday'] = extra.get('birthday') or birthday
    extra['address'] = extra.get('address') or address
    extra['website'] = extra.get('website') or website

    warnings = []
    if unknown_groups:
        warnings.append('Google has no label named '
                        + ', '.join(f'"{g}"' for g in unknown_groups)
                        + '; skipped those groups.')
    task_id, rows, more = mirror_to_clickup(svc, created, c, user=user,
                                            failed_hint='Run a Google sync to pull it into People.')
    return {'entity': detail(task_id), 'rows': rows, 'warnings': warnings + more,
            'google_link': c.get('link') or '', 'google_id': c['key']}


def mirror_to_clickup(svc, person, c, *, user='', failed_hint=''):
    """Create a People task linked to an existing Google contact, then write the task id back to Google.

    `c` is google_contact(person). Returns (task_id, refreshed cache rows, warnings).
    """
    token, ids = configured_lists()
    edit = EntityEdit(task_id='(new)', task_name=c['name'], edited_by=user)
    cu = ClickUp(token, ids['people'], WriteGuard(dry=False, writes_enabled=True, max_ops=MAX_EDIT_WRITES,
                                                  journal=EditJournal(edit.changes)))
    missing = cu.load_fields()
    if missing:
        raise EditError(400, f'People list is missing required fields: {", ".join(missing)}.')

    vals = {
        'google_id': c['key'], 'google_hash': c['hash'], 'google_link': c.get('link'),
        'emails': ', '.join(c['emails']) or None,
        'email': c['emails'][0] if c['emails'] else None,
        'phones': ', '.join(c['phones']) or None,
        'company': c.get('company'), 'title': c.get('title'),
        'status': ACTIVE, 'last_synced': now_ms(),
    }
    for k in EXTRA:
        vals[k] = cu.prep(k, c.get('extra', {}).get(k))
    src_opts = cu.label_options('sources')
    google_label = SOURCE_LABEL['google']
    if 'sources' in cu.fields and google_label.lower() in src_opts:
        vals['sources'] = [google_label]
    grp_opts = cu.label_options('groups')
    wanted = [(grp_opts[g.lower()].get('label') or grp_opts[g.lower()].get('name') or '').strip()
              for g in c.get('groups', []) if g.lower() in grp_opts]
    if wanted:
        vals['groups'] = wanted

    edit.save()
    warnings = []
    try:
        task = cu.create(c['name'], vals)
    except Exception as e:
        edit.error = str(e)[:1000]
        edit.save()
        raise EditError(502, f'Google contact {c.get("link") or c["key"]} is fine, but creating it in ClickUp '
                             f'failed: {e}. {failed_hint}'.strip())

    task_id = task['id']
    edit.task_id = task_id
    try:
        google_src.writeback(type('Ctx', (), {'cu': cu, 'dry': False})(), svc, person,
                             {'id': task_id, 'name': c['name']})
    except Exception as e:  # noqa: BLE001
        warnings.append(f'ClickUp task created, but writing the task id back to Google failed: {e}')
        edit.changes.append({'op': 'google_writeback', 'ok': False, 'error': str(e)[:300],
                             'task_id': task_id, 'task_name': c['name']})

    edit.ok = True
    edit.save()
    rows = _refresh_rows(_client(), [task_id], ids)
    return task_id, rows, warnings


# ---- save ---------------------------------------------------------------------------------
def _write(cu, method, path, body, *, op, task_id, task_name, field='', before=None, after=None):
    handle = cu.guard.begin(op, task_id=task_id, task_name=task_name, field=field, before=before, after=after)
    try:
        cu._req(method, path, **({'json': body} if body is not None else {}))
    except Exception as e:
        cu.guard.done(handle, str(e))
        raise
    cu.guard.done(handle)


def _display_lines_from_data(raw, own_kind, cu, ids, cache, *, name_overrides=None):
    """Decode Relationship data JSON into sectioned lines with resolved names for the description block."""
    overrides = name_overrides or {}
    out = []
    for ln in rel.decode_data(raw):
        tid = ln['target_id']
        tkind, tname = _target(tid, cu, ids, cache)
        section = rel.section_for(own_kind, tkind) if tkind else ln.get('section')
        if tkind and not section:
            continue
        out.append({
            'label': ln['label'], 'target_id': tid, 'note': ln.get('note') or '',
            'name': overrides.get(tid) or tname or ln.get('name') or tid,
            'section': section or 'Relationships', 'target_list': tkind,
        })
    return out


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
    cache = {}
    current, unparsed, structured, has_data_field = _read_relationships(t, fields, kind, cu, ids, cache)
    notes = rel.notes_text(old_md, structured=structured)
    new_notes = str(body['notes']) if body.get('notes') is not None else notes
    desired = current
    if body.get('relationships') is not None:
        desired = _desired_relationships(kind, task_id, body['relationships'], current, cu, ids, cache, errors)
    if rel.HEADER_RE.search(new_notes):
        errors.append('Notes can\'t contain a line that is only **Relationships**, **Organizations** or **People**.')
    if any(rel.MARKER_LINE_RE.match(ln) for ln in new_notes.splitlines()):
        errors.append('Notes can\'t contain the "Do Not Change Between Lines" markers '
                      '(those wrap the auto-updated relationship block at the top of the description).')

    data_field = _field_def(fields, rel.DATA_FIELD)
    intro_field = _field_def(fields, INTRODUCED_BY_FIELD)
    if body.get('relationships') is not None and not has_data_field:
        errors.append(f'Add a "{rel.DATA_FIELD}" text field on the {LISTS[kind]} list before editing relationships.')

    # Structured mode: Relationship data is authoritative; description gets a managed display block
    # at the top (ClickUp panel links) plus user notes below.
    use_structured = has_data_field
    notes_changed = body.get('notes') is not None and new_notes != notes
    rels_in_body = body.get('relationships') is not None
    if use_structured:
        if unparsed and notes_changed:
            errors.append('The relationship sections of this description contain text the editor doesn\'t '
                          'understand, so notes can only be changed in ClickUp (or after migrating '
                          'relationships into Relationship data).')
        elif notes_changed or rels_in_body:
            # Rebuild the managed ### block from scratch. Use editor notes only when they were
            # edited cleanly; otherwise derive notes from the live description so orphan/hand-edited
            # markers are stripped instead of stacked.
            if notes_changed and not unparsed:
                new_md = rel.compose_description(desired, new_notes)
            else:
                new_md = rel.compose_description_over(old_md, desired)
            if new_md != (old_md or '').rstrip():
                task_body['markdown_content'] = new_md
    else:
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

    new_payload = rel.encode_data(desired) if use_structured else None
    old_payload = rel.encode_data(current) if use_structured else None
    rel_changed = use_structured and rels_in_body and new_payload != old_payload
    clear_intro = bool(intro_field and use_structured and rels_in_body
                       and _cf_raw(t, fields, INTRODUCED_BY_FIELD))

    if errors:
        raise EditError(400, ' '.join(dict.fromkeys(errors)))

    new_name = task_body.get('name', t.get('name', ''))
    old_by_key = {rel.key(ln): ln for ln in current}
    new_by_key = {rel.key(ln): ln for ln in desired}
    other = [(ln, True) for k, ln in old_by_key.items() if k not in new_by_key]
    other += [(ln, False) for k, ln in new_by_key.items()
              if k not in old_by_key or old_by_key[k]['note'] != ln['note'] or 'name' in task_body]

    if not task_body and not field_writes and not other and not rel_changed and not clear_intro:
        return {'changed': False, 'warnings': [], 'rows': [], 'entity': detail(task_id)}

    edit.task_name = t.get('name', '')
    edit.save()
    warnings, touched = [], [task_id]
    # Name isn't stored in Relationship data JSON; still invalidate partners so their labels refresh.
    if 'name' in task_body:
        touched += [ln['target_id'] for ln in desired if ln.get('target_id')]
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
        if rel_changed and data_field:
            _write(cu, 'POST', f'/task/{task_id}/field/{data_field["id"]}', {'value': new_payload},
                   op='set_relationships', task_id=task_id, task_name=edit.task_name, field=rel.DATA_FIELD,
                   before=old_payload, after=new_payload)
        if clear_intro:
            _write(cu, 'DELETE', f'/task/{task_id}/field/{intro_field["id"]}', None, op='clear_introduced_by',
                   task_id=task_id, task_name=edit.task_name, field=INTRODUCED_BY_FIELD,
                   before=_cf_raw(t, fields, INTRODUCED_BY_FIELD))
        for ln, remove in other:
            tkind = ln.get('target_list') or _target(ln['target_id'], cu, ids, cache)[0]
            if not tkind:
                continue
            target = _get_task(cu, ln['target_id'])
            tfields = cu._req('GET', f'/list/{ids[tkind]}/field').get('fields', [])
            inv = rel.inverse(ln['label'], kind, tkind)
            if use_structured and _field_def(tfields, rel.DATA_FIELD):
                t_lines, t_unparsed, _, _ = _read_relationships(target, tfields, tkind, cu, ids, cache)
                prior_raw = _cf_raw(target, tfields, rel.DATA_FIELD)
                prior = prior_raw if isinstance(prior_raw, str) else rel.encode_data(rel.decode_data(prior_raw))
                seed = rel.encode_data(t_lines)
                new_raw, _ = rel.upsert_data(seed, inv, task_id, new_name, ln['note'], remove=remove)
                data_wrote = new_raw != (prior or '')
                # Write when the edge set changes, or when folding legacy description into an empty field.
                if data_wrote:
                    fid = _field_def(tfields, rel.DATA_FIELD)['id']
                    _write(cu, 'POST', f'/task/{target["id"]}/field/{fid}', {'value': new_raw},
                           op='update_relationship', task_id=target['id'], task_name=target.get('name', ''),
                           field=rel.DATA_FIELD, before=prior or '', after=new_raw)
                    touched.append(target['id'])
                # Refresh description block when edges change or this task was renamed.
                if data_wrote or 'name' in task_body:
                    disp_lines = _display_lines_from_data(
                        new_raw, tkind, cu, ids, cache, name_overrides={task_id: new_name})
                    md = _description(target)
                    new_md = rel.compose_description_over(md, disp_lines)
                    if new_md != (md or '').rstrip():
                        _write(cu, 'PUT', f'/task/{target["id"]}', {'markdown_content': new_md},
                               op='set_description_relationships', task_id=target['id'],
                               task_name=target.get('name', ''), field='description',
                               before=md, after=new_md)
                    if target['id'] not in touched:
                        touched.append(target['id'])
                tintro = _field_def(tfields, INTRODUCED_BY_FIELD)
                if tintro and _cf_raw(target, tfields, INTRODUCED_BY_FIELD):
                    # Fold Introduced by into Relationship data on the other task too.
                    _write(cu, 'DELETE', f'/task/{target["id"]}/field/{tintro["id"]}', None,
                           op='clear_introduced_by', task_id=target['id'],
                           task_name=target.get('name', ''), field=INTRODUCED_BY_FIELD)
            else:
                md = _description(target)
                if rel.parse(md)[2]:
                    warnings.append(f'{target.get("name")} wasn\'t updated: its relationship sections contain text '
                                    'the editor doesn\'t understand. Update it in ClickUp.')
                    continue
                new_target_md, changed = rel.upsert_line(md, rel.section_for(tkind, kind), inv, task_id, new_name,
                                                         ln['note'], remove=remove)
                if changed:
                    _write(cu, 'PUT', f'/task/{target["id"]}', {'markdown_content': new_target_md},
                           op='update_relationship', task_id=target['id'], task_name=target.get('name', ''),
                           field='description', before=md, after=new_target_md)
                    touched.append(target['id'])
    except Exception as e:
        edit.error = str(e)[:1000]
        edit.save()
        invalidate_details(touched)
        _refresh_rows(_client(), touched, ids)
        raise EditError(502, f'Stopped part-way through saving: {e}. Reload to see what was saved.')
    edit.ok = True
    edit.save()
    invalidate_details(touched)
    rows = _refresh_rows(_client(), touched, ids)
    return {'changed': True, 'warnings': warnings, 'rows': rows, 'entity': detail(task_id)}


# ---- bulk -------------------------------------------------------------------------------
MAX_BULK = 100


def _bulk_add_groups(task_id, group_names, user):
    """Add ClickUp Groups labels to one person (by option name)."""
    d = detail(task_id, force=True)
    if d['list'] != 'people':
        raise EditError(400, f'{d["name"]} is an organization; groups only apply to people.')
    gfield = next((f for f in d['fields']
                   if f.get('key') == 'groups' or f['name'].strip().lower() == 'groups'), None)
    if not gfield:
        raise EditError(400, 'No Groups field on the People list.')
    if gfield.get('locked'):
        raise EditError(400, f'Groups on {d["name"]} can\'t be edited here.')
    by_name = {_option_name(o).strip().lower(): o['id'] for o in gfield.get('options') or []}
    add_ids = []
    for raw in group_names:
        name = ' '.join(str(raw or '').split())
        if not name:
            continue
        oid = by_name.get(name.lower())
        if not oid:
            raise EditError(400, f'Unknown group "{name}".')
        add_ids.append(oid)
    if not add_ids:
        raise EditError(400, 'Pick at least one group.')
    current = list(gfield.get('value') or [])
    merged = list(dict.fromkeys([*current, *add_ids]))
    if merged == current:
        return {'changed': False, 'warnings': [], 'rows': [], 'entity': d, 'skipped': 'already has those groups'}
    return save(task_id, {'date_updated': d['date_updated'], 'fields': {gfield['id']: merged}}, user=user)


def _bulk_add_relationship(task_id, label, target_id, note, user):
    """Append one relationship edge to an entity (no-op if that edge already exists)."""
    lab = ' '.join(str(label or '').split())
    tid = str(target_id or '').strip()
    if not lab or not tid:
        raise EditError(400, 'Relationship needs a type and a target.')
    d = detail(task_id, force=True)
    if tid == str(task_id):
        return {'changed': False, 'warnings': [], 'rows': [], 'entity': d, 'skipped': 'self-link'}
    if not d.get('relationships_editable'):
        raise EditError(400, f'Relationships on {d["name"]} can\'t be edited here.')
    rels = [{'label': r['label'], 'target_id': r['target_id'], 'note': r.get('note') or ''}
            for r in d.get('relationships') or []]
    if any(r['target_id'] == tid and r['label'].strip().lower() == lab.lower() for r in rels):
        return {'changed': False, 'warnings': [], 'rows': [], 'entity': d,
                'skipped': f'already has "{lab}"'}
    rels.append({'label': lab, 'target_id': tid, 'note': ' '.join(str(note or '').split())})
    return save(task_id, {'date_updated': d['date_updated'], 'relationships': rels}, user=user)


def bulk(body, user=''):
    """Apply one op to many entities. Returns {results, rows, ok, failed, skipped}.

    Ops:
      add_groups:       {ids, groups: [name, ...]}  — people only
      add_relationship: {ids, label, target_id, note?}
    """
    ids = [str(x).strip() for x in (body.get('ids') or []) if str(x).strip()]
    ids = list(dict.fromkeys(ids))
    op = str(body.get('op') or '').strip()
    if not ids:
        raise EditError(400, 'Select at least one person or organization.')
    if len(ids) > MAX_BULK:
        raise EditError(400, f'At most {MAX_BULK} entities per bulk action.')
    if op not in ('add_groups', 'add_relationship'):
        raise EditError(400, f'Unknown bulk op "{op}".')

    results, row_by_id = [], {}
    for tid in ids:
        try:
            if op == 'add_groups':
                out = _bulk_add_groups(tid, body.get('groups') or [], user)
            else:
                out = _bulk_add_relationship(
                    tid, body.get('label'), body.get('target_id'), body.get('note') or '', user)
            entry = {'id': tid, 'ok': True, 'changed': bool(out.get('changed')),
                     'name': (out.get('entity') or {}).get('name') or tid}
            if out.get('skipped'):
                entry['skipped'] = out['skipped']
            results.append(entry)
            for r in out.get('rows') or []:
                row_by_id[r['id']] = r
        except EditError as e:
            results.append({'id': tid, 'ok': False, 'error': str(e), 'status': e.status})
        except Exception as e:  # noqa: BLE001
            results.append({'id': tid, 'ok': False, 'error': str(e)[:300], 'status': 502})

    return {
        'op': op,
        'results': results,
        'rows': list(row_by_id.values()),
        'ok': sum(1 for r in results if r.get('ok') and r.get('changed')),
        'skipped': sum(1 for r in results if r.get('ok') and not r.get('changed')),
        'failed': sum(1 for r in results if not r.get('ok')),
    }
