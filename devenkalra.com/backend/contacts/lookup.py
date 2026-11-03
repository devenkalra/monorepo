"""Check contacts against the ClickUp People list and Google Contacts, then act on the result one row at a time.

Comparing only reads: ClickUp from the People & Orgs local copy (EntityCache), Google from a cached index of
every contact. Nothing is written until an action is run on a row. Each action re-evaluates the row first,
re-reads the records it touches, and refuses if the row's outcome changed since the comparison.
"""
import csv
import difflib
import io
import re
from collections import Counter
from datetime import datetime, timedelta

from django.utils import timezone

from . import entities, google_auth
from .engine import WriteGuard
from .engine.fields import SOURCE_LABEL, task_url
from .engine.normalize import norm_email, norm_name, norm_phone, phone_for_storage, split_list, union
from .engine.sources import google as google_src
from .models import ContactsState, EntityCache, EntityEdit, Lookup

SYNC_LABEL = 'SyncDriven'  # Google label and ClickUp group on every contact an action creates or changes
GOOGLE_INDEX_KEY = 'lookup_google_index'
GOOGLE_INDEX_TTL = timedelta(minutes=10)
GOOGLE_INDEX_MAX_AGE_FOR_WRITES = timedelta(minutes=1)
GOOGLE_INDEX_FIELDS = 'names,emailAddresses,phoneNumbers,externalIds,metadata'
MAX_ROWS = 1000
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_ACTION_WRITES = 20
MAX_CANDIDATES = 5
ROUGH_NAME = 0.85  # name similarity that makes a record a candidate when email/phone don't match
SAME_NAME = 0.8    # below this, an exact email/phone match with a different name is a conflict

SIDES = {'clickup': 'ClickUp', 'google': 'Google'}
OUTCOMES = {
    'exists': 'Exists', 'unlinked': 'Exists, unlinked', 'clickup_only': 'ClickUp only',
    'google_only': 'Google only', 'not_found': 'Not found', 'review': 'Needs review', 'conflict': 'Conflict',
}
ACTIONS = {
    'link': ('unlinked', 'Link'),
    'create_google': ('clickup_only', 'Create in Google & link'),
    'import_clickup': ('google_only', 'Import into ClickUp'),
    'create_both': ('not_found', 'Create in Google & ClickUp'),
}
ACTION_FOR = {outcome: action for action, (outcome, _) in ACTIONS.items()}

HEADERS = {
    'name': ('name', 'full name', 'fullname', 'display name', 'contact', 'contact name'),
    'first_name': ('first name', 'firstname', 'first', 'given name', 'given'),
    'last_name': ('last name', 'lastname', 'last', 'surname', 'family name', 'family'),
    'email': ('email', 'emails', 'e mail', 'email address', 'e mail address', 'mail'),
    'phone': ('phone', 'phones', 'phone number', 'mobile', 'mobile phone', 'mobile number', 'cell', 'cell phone',
              'tel', 'telephone', 'whatsapp'),
}
HEADER_FIELD = {alias: field for field, aliases in HEADERS.items() for alias in aliases}
VALUE_SPLIT = re.compile(r'\s*(?::::|[;,|\n])\s*')


class LookupFailed(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


# ---- input ----------------------------------------------------------------------------------
def _values(raw):
    items = raw if isinstance(raw, (list, tuple)) else [raw]
    return [x for v in items for x in VALUE_SPLIT.split(str(v or '').strip()) if x]


def make_input(*, name='', first_name='', last_name='', emails=(), phones=()):
    """One contact to check, or None if it has nothing to match on."""
    full = ' '.join(str(name or '').split()) or google_src.display_name(given_name=first_name,
                                                                        family_name=last_name)
    em = union([norm_email(e) or e.lower() for e in _values(emails)])
    ph = union([phone_for_storage(p) for p in _values(phones)])
    if not (full or em or ph):
        return None
    return {'name': full, 'emails': em, 'phones': ph}


def header_field(header):
    """CSV header -> name / first_name / last_name / email / phone, or None. Accepts Google export headers."""
    key = re.sub(r'[^a-z0-9]+', ' ', (header or '').lower()).strip()
    key = re.sub(r'\s+\d+(\s+value)?$', '', key)  # "E-mail 1 - Value", "Phone 2 - Value"
    return HEADER_FIELD.get(key)


def _decode(data):
    for enc in ('utf-8-sig', 'cp1252'):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode('latin-1')


def parse_csv(data):
    """Returns (inputs, columns). Raises LookupFailed when no usable column or row is found."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise LookupFailed('The file is larger than 2 MB.')
    text = _decode(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=',;\t')
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    header = next(reader, None)
    if not header:
        raise LookupFailed('The file is empty.')
    mapping = [header_field(h) for h in header]
    recognized = {h.strip(): f for h, f in zip(header, mapping) if f}
    ignored = [h.strip() for h, f in zip(header, mapping) if not f and h.strip()]
    if not recognized:
        raise LookupFailed('No name, email or phone column found. Use headers such as Name, First name, '
                           'Last name, Email and Phone.')
    inputs = []
    for line, cells in enumerate(reader, start=2):
        got = {f: [] for f in HEADERS}
        for f, cell in zip(mapping, cells):
            if f and cell.strip():
                got[f].append(cell.strip())
        inp = make_input(name=(got['name'] or [''])[0], first_name=(got['first_name'] or [''])[0],
                         last_name=(got['last_name'] or [''])[0], emails=got['email'], phones=got['phone'])
        if inp is None:
            continue
        if len(inputs) >= MAX_ROWS:
            raise LookupFailed(f'The file has more than {MAX_ROWS} contacts; split it into smaller files.')
        inp['line'] = line
        inputs.append(inp)
    if not inputs:
        raise LookupFailed('The file has no rows with a name, email or phone.')
    return inputs, {'recognized': recognized, 'ignored': ignored}


def inputs_from_json(rows):
    if not isinstance(rows, list) or not rows:
        raise LookupFailed('Provide at least one contact.')
    if len(rows) > MAX_ROWS:
        raise LookupFailed(f'At most {MAX_ROWS} contacts per comparison.')
    out = []
    for raw in rows:
        if not isinstance(raw, dict):
            raise LookupFailed('Each contact must be an object.')
        inp = make_input(name=raw.get('name'), first_name=raw.get('first_name'), last_name=raw.get('last_name'),
                         emails=raw.get('emails') or raw.get('email'), phones=raw.get('phones') or raw.get('phone'))
        if inp:
            out.append(inp)
    if not out:
        raise LookupFailed('Enter a name, email or phone.')
    return out


# ---- indexes --------------------------------------------------------------------------------
def _tail(phone):
    digits = re.sub(r'\D', '', phone or '')
    return digits[-10:] if len(digits) >= 7 else None


class Side:
    """Every record of one source, indexed by normalized email, phone, phone tail and name token."""

    def __init__(self, kind):
        self.kind, self.label = kind, SIDES[kind]
        self.recs, self.names = {}, {}
        self.by_email, self.by_phone, self.by_tail, self.by_token, self.by_google = {}, {}, {}, {}, {}

    def add(self, rec):
        rid = rec['id']
        self.recs[rid] = rec
        self.names[rid] = norm_name(rec['name'])
        for e in rec['emails']:
            if norm_email(e):
                self.by_email.setdefault(norm_email(e), set()).add(rid)
        for p in rec['phones']:
            if norm_phone(p):
                self.by_phone.setdefault(norm_phone(p), set()).add(rid)
            if _tail(p):
                self.by_tail.setdefault(_tail(p), set()).add(rid)
        for t in self.names[rid].split():
            self.by_token.setdefault(t, set()).add(rid)
        if rec.get('google_id'):
            self.by_google.setdefault(rec['google_id'], set()).add(rid)


def clickup_side():
    data = entities.listing()
    side, outdated = Side('clickup'), False
    for row in data['entities']:
        if row.get('list') != 'people' or row.get('archived'):
            continue
        if 'google_id' not in row:
            outdated = True
        side.add({'id': row['id'], 'name': row.get('name') or '', 'emails': split_list(row.get('emails')),
                  'phones': split_list(row.get('phones')), 'link': row.get('url') or task_url(row['id']),
                  'google_id': row.get('google_id') or ''})
    meta = {'loaded': data['loaded'], 'refreshed_at': data.get('refreshed_at'), 'stale': data.get('stale', False),
            'outdated': outdated}
    return side, meta


def google_rec(person, clickup_id=None):
    rid = person['resourceName']
    name = ((person.get('names') or [{}])[0].get('displayName') or '').strip()
    ext = next((e.get('value') for e in person.get('externalIds') or [] if e.get('type') == 'clickup'), '')
    return {
        'id': rid, 'name': name,
        'emails': union([norm_email(e.get('value')) for e in person.get('emailAddresses') or []]),
        'phones': union([phone_for_storage(x.get('canonicalForm') or x.get('value'))
                         for x in person.get('phoneNumbers') or []]),
        'link': f"https://contacts.google.com/person/{rid.split('/')[-1]}",
        'clickup_id': clickup_id or ext or '',
    }


def _google_service(write=False):
    try:
        return google_auth.people_service(write=write)
    except ValueError as e:
        raise LookupFailed(str(e))


def refresh_google_index(svc=None):
    svc = svc or _google_service()
    contacts, page = [], None
    while True:
        kw = dict(resourceName='people/me', pageSize=1000, personFields=GOOGLE_INDEX_FIELDS)
        if page:
            kw['pageToken'] = page
        resp = svc.people().connections().list(**kw).execute()
        contacts += [google_rec(p) for p in resp.get('connections') or []
                     if not (p.get('metadata') or {}).get('deleted')]
        page = resp.get('nextPageToken')
        if not page:
            break
    data = {'fetched_at': timezone.now().isoformat(), 'contacts': contacts}
    ContactsState.put(GOOGLE_INDEX_KEY, data)
    return data


def _age(iso):
    try:
        return timezone.now() - datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None


def google_index(max_age=GOOGLE_INDEX_TTL):
    data = ContactsState.get(GOOGLE_INDEX_KEY)
    age = _age((data or {}).get('fetched_at'))
    if not data or age is None or age > max_age:
        data = refresh_google_index()
    return data


def _remember_google(rec):
    data = ContactsState.get(GOOGLE_INDEX_KEY)
    if not data:
        return
    data['contacts'] = [c for c in data['contacts'] if c['id'] != rec['id']] + [rec]
    ContactsState.put(GOOGLE_INDEX_KEY, data)


def cache_status():
    data = entities.listing()
    people = [r for r in data['entities'] if r.get('list') == 'people']
    google = ContactsState.get(GOOGLE_INDEX_KEY) or {}
    return {
        'clickup': {'loaded': data['loaded'], 'refreshed_at': data.get('refreshed_at'),
                    'stale': data.get('stale', False), 'people': len(people),
                    'outdated': any('google_id' not in r for r in people)},
        'google': {'fetched_at': google.get('fetched_at'), 'contacts': len(google.get('contacts') or [])},
    }


def load_sides(google_max_age=GOOGLE_INDEX_TTL):
    cu, meta = clickup_side()
    if not meta['loaded']:
        raise LookupFailed('The ClickUp cache is empty. Click "Refresh ClickUp cache" first.', 409)
    if meta['outdated']:
        raise LookupFailed('The ClickUp cache was saved before it kept Google links. Click '
                           '"Refresh ClickUp cache" first.', 409)
    gdata = google_index(google_max_age)
    g = Side('google')
    for rec in gdata['contacts']:
        g.add(rec)
    return cu, g, {'clickup_as_of': meta['refreshed_at'] or '', 'google_as_of': gdata['fetched_at']}


# ---- matching -------------------------------------------------------------------------------
def _sim(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()


def same_person_name(a, b):
    na, nb = norm_name(a), norm_name(b)
    if not na or not nb:
        return True
    ta, tb = set(na.split()), set(nb.split())
    return ta <= tb or tb <= ta or _sim(na, nb) >= SAME_NAME


def differences(side, rec, inp):
    """(conflicts, notes) between an input and the record it matched exactly."""
    conflicts, notes = [], []
    label = side.label
    if inp['name'] and rec['name'] and not same_person_name(inp['name'], rec['name']):
        conflicts.append(f'Name differs: "{inp["name"]}" here, "{rec["name"]}" in {label}.')
    have = {norm_email(e) or e.lower() for e in rec['emails']}
    for e in inp['emails']:
        if (norm_email(e) or e) in have:
            continue
        if have:
            conflicts.append(f'Email {e} isn\'t on the {label} record (it has {", ".join(sorted(have))}).')
        else:
            notes.append(f'The {label} record has no email; {e} isn\'t on it.')
    phones = {norm_phone(p) or p for p in rec['phones']}
    tails = {_tail(p) for p in rec['phones']} - {None}
    for p in inp['phones']:
        if (norm_phone(p) or p) in phones or (_tail(p) and _tail(p) in tails):
            continue
        if phones:
            conflicts.append(f'Phone {p} isn\'t on the {label} record (it has {", ".join(sorted(phones))}).')
        else:
            notes.append(f'The {label} record has no phone; {p} isn\'t on it.')
    return conflicts, notes


def _candidate(side, rid, reasons, score):
    r = side.recs[rid]
    return {'id': rid, 'name': r['name'], 'emails': r['emails'], 'phones': r['phones'], 'link': r['link'],
            'reasons': reasons, 'score': round(score, 2)}


def _result(status, rid=None, candidates=(), conflicts=(), notes=(), chosen=False):
    return {'status': status, 'id': rid, 'candidates': list(candidates), 'conflicts': list(conflicts),
            'notes': list(notes), 'chosen': chosen}


def exact(side, rid, inp, reasons, chosen=False):
    conflicts, notes = differences(side, side.recs[rid], inp)
    return _result('exact', rid, [_candidate(side, rid, reasons, 1.0)], conflicts, notes, chosen)


def _names(side, ids):
    return ', '.join(f'"{side.recs[i]["name"]}"' for i in sorted(ids))


def match_side(side, inp):
    """exact (one record by email/phone), conflict (several), rough (similar name / phone tail) or none."""
    emails = {e for e in (norm_email(x) for x in inp['emails']) if e}
    phones = {p for p in (norm_phone(x) for x in inp['phones']) if p}
    by_email = set().union(*(side.by_email.get(e, set()) for e in emails))
    by_phone = set().union(*(side.by_phone.get(p, set()) for p in phones))
    strong = by_email | by_phone

    def why(rid):
        return [r for r, hits in (('email', by_email), ('phone', by_phone)) if rid in hits]

    if len(strong) == 1:
        rid = next(iter(strong))
        return exact(side, rid, inp, why(rid))
    if strong:
        cands = [_candidate(side, rid, why(rid), 1.0) for rid in sorted(strong)][:MAX_CANDIDATES]
        if by_email and by_phone and not (by_email & by_phone):
            msg = (f'In {side.label}, the email matches {_names(side, by_email)} but the phone matches '
                   f'{_names(side, by_phone)}.')
        else:
            msg = (f'{len(strong)} {side.label} records share this email or phone: {_names(side, strong)}. '
                   'Merge or correct them.')
        return _result('conflict', candidates=cands, conflicts=[msg])

    found = {}

    def add(rid, reason, score):
        c = found.setdefault(rid, {'reasons': [], 'score': 0.0})
        c['reasons'].append(reason)
        c['score'] = max(c['score'], score)

    for t in {_tail(p) for p in inp['phones']} - {None}:
        for rid in side.by_tail.get(t, ()):
            add(rid, 'phone (last 10 digits)', 0.9)
    target = norm_name(inp['name'])
    if target:
        for rid in set().union(*(side.by_token.get(t, set()) for t in target.split())):
            sim = _sim(target, side.names[rid])
            if sim >= ROUGH_NAME:
                add(rid, 'same name' if sim == 1 else f'similar name ({sim:.2f})', sim)
    if not found:
        return _result('none')
    ranked = sorted(found.items(), key=lambda kv: (-kv[1]['score'], side.recs[kv[0]]['name']))[:MAX_CANDIDATES]
    return _result('rough', candidates=[_candidate(side, rid, v['reasons'], v['score']) for rid, v in ranked])


def side_result(side, inp, choice, reason='chosen by you'):
    if choice == 'new':
        return _result('none', notes=[f'You marked this as not in {side.label}.'], chosen=True)
    if choice and choice in side.recs:
        return exact(side, choice, inp, [reason], chosen=True)
    out = match_side(side, inp)
    if choice:
        out['notes'].append(f'The {side.label} record you chose no longer exists, so it was matched again.')
    return out


def evaluate(inp, choice, cu_side, g_side):
    """The row's outcome, with each side's match, conflicts, notes and the one action that applies."""
    choice = choice or {}
    reason = 'handled by this comparison' if choice.get('by') == 'action' else 'chosen by you'
    cu = side_result(cu_side, inp, choice.get('clickup'), reason)
    g = side_result(g_side, inp, choice.get('google'), reason)
    link_conflicts, notes = [], []
    outcome = 'conflict'

    if cu['status'] == 'exact':
        crec = cu_side.recs[cu['id']]
        gid = crec.get('google_id')
        if gid and gid not in g_side.recs:
            link_conflicts.append(f'ClickUp "{crec["name"]}" is linked to a Google contact that no longer exists. '
                                  'Run a Google sync (it marks the link deleted) or fix the Google ID in ClickUp.')
        elif gid:
            if g['status'] == 'exact' and g['id'] != gid:
                link_conflicts.append(
                    f'ClickUp "{crec["name"]}" is linked to Google contact "{g_side.recs[gid]["name"]}", '
                    f'but this row matches Google contact "{g_side.recs[g["id"]]["name"]}".')
            else:
                if g['id'] != gid:
                    g = exact(g_side, gid, inp, ['linked from ClickUp'])
                outcome = 'exists'
        elif g['status'] == 'exact':
            grec = g_side.recs[g['id']]
            others = cu_side.by_google.get(g['id'], set()) - {cu['id']}
            if others:
                link_conflicts.append(f'Google contact "{grec["name"]}" is already linked to ClickUp '
                                      f'{_names(cu_side, others)}.')
            elif grec.get('clickup_id') and grec['clickup_id'] != cu['id'] and grec['clickup_id'] in cu_side.recs:
                link_conflicts.append(f'Google contact "{grec["name"]}" points to ClickUp '
                                      f'"{cu_side.recs[grec["clickup_id"]]["name"]}", not "{crec["name"]}".')
            else:
                outcome = 'unlinked'
        elif g['status'] == 'rough':
            outcome = 'review'
        elif g['status'] == 'none':
            outcome = 'clickup_only'
    elif cu['status'] == 'none':
        if g['status'] == 'exact':
            linked = cu_side.by_google.get(g['id'], set())
            if len(linked) == 1:
                cu = exact(cu_side, next(iter(linked)), inp, ['linked from Google'])
                outcome = 'exists'
            elif linked:
                link_conflicts.append(f'Google contact "{g_side.recs[g["id"]]["name"]}" is linked from several '
                                      f'ClickUp tasks: {_names(cu_side, linked)}.')
            else:
                outcome = 'google_only'
        elif g['status'] == 'rough':
            outcome = 'review'
        elif g['status'] == 'none':
            outcome = 'not_found'
    elif cu['status'] == 'rough' and g['status'] != 'conflict':
        outcome = 'review'

    conflicts = link_conflicts + cu['conflicts'] + g['conflicts']
    notes += cu['notes'] + g['notes']
    final = 'conflict' if conflicts else outcome
    new_action = None
    if final == 'review':
        new_action = evaluate(inp, as_new(choice, cu, g), cu_side, g_side)['action']
    return {'outcome': final, 'base': outcome, 'action': ACTION_FOR.get(final), 'new_action': new_action,
            'clickup': cu, 'google': g, 'conflicts': conflicts, 'notes': notes}


def as_new(choice, cu, g):
    """The choice that treats every side with only possible matches as someone new."""
    out = dict(choice)
    for key, side in (('clickup', cu), ('google', g)):
        if side['status'] == 'rough':
            out[key] = 'new'
    return out


# ---- saved comparisons ----------------------------------------------------------------------
def _summary(rows):
    counts = Counter(r['result']['outcome'] for r in rows if r.get('result'))
    return {'total': len(rows), 'done': sum(1 for r in rows if r.get('done')), **counts}


def recheck(lk, sides=None, indexes=None):
    cu, g, meta = sides or load_sides()
    rows = lk.rows if indexes is None else [r for r in lk.rows if r['index'] in set(indexes)]
    for row in rows:
        row['result'] = evaluate(row['input'], row.get('choice') or {}, cu, g)
    lk.clickup_as_of, lk.google_as_of = meta['clickup_as_of'], meta['google_as_of']
    lk.checked_at = timezone.now()
    lk.summary = _summary(lk.rows)
    lk.save()
    return lk


def create(inputs, *, name='', columns=None, user=''):
    rows = [{'index': i, 'line': inp.pop('line', None), 'input': inp, 'choice': {}, 'done': None, 'result': None}
            for i, inp in enumerate(inputs)]
    lk = Lookup(name=(name or '')[:255], columns=columns or {}, rows=rows, created_by=user)
    return recheck(lk)


def payload(lk, rows=True):
    out = {'id': lk.pk, 'name': lk.name or f'Comparison #{lk.pk}', 'created_by': lk.created_by,
           'created_at': lk.created_at.isoformat() if lk.created_at else None,
           'checked_at': lk.checked_at.isoformat() if lk.checked_at else None,
           'clickup_as_of': lk.clickup_as_of, 'google_as_of': lk.google_as_of, 'columns': lk.columns,
           'summary': lk.summary}
    if rows:
        out['rows'] = lk.rows
    return out


def _row(lk, index):
    try:
        index = int(index)
    except (TypeError, ValueError):
        raise LookupFailed('row must be a row number.')
    row = next((r for r in lk.rows if r['index'] == index), None)
    if row is None:
        raise LookupFailed(f'No row {index} in this comparison.', 404)
    return row


def choose(lk, index, side, value):
    """Resolve a rough match: pick one of the side's candidates, 'new', or '' to undo the choice."""
    if side not in SIDES:
        raise LookupFailed('side must be clickup or google.')
    row = _row(lk, index)
    if row.get('done'):
        raise LookupFailed('This row was already handled.', 409)
    choice = row.setdefault('choice', {})
    value = str(value or '').strip()
    if not value:
        choice.pop(side, None)
    else:
        allowed = {c['id'] for c in (row.get('result') or {}).get(side, {}).get('candidates', [])}
        if value != 'new' and value not in allowed:
            raise LookupFailed('Choose one of the candidates shown for this row, or "new".')
        choice[side] = value
    return recheck(lk)


# ---- actions --------------------------------------------------------------------------------
def act(lk, index, action, user=''):
    """Run the one action that applies to a row, after re-checking it against fresh data.

    On a row that needs review, its new_action ignores the possible matches and creates the row as new
    wherever it has no exact match.
    """
    if action not in ACTIONS:
        raise LookupFailed(f'action must be one of: {", ".join(ACTIONS)}.')
    row = _row(lk, index)
    if row.get('done'):
        raise LookupFailed('This row was already handled.', 409)
    entities._create_blocked()
    sides = load_sides(GOOGLE_INDEX_MAX_AGE_FOR_WRITES)
    choice = row.get('choice') or {}
    result = evaluate(row['input'], choice, sides[0], sides[1])
    if result['outcome'] == 'review' and result['new_action'] == action:
        result = evaluate(row['input'], as_new(choice, result['clickup'], result['google']), sides[0], sides[1])
    if result['action'] != action:
        row['result'] = evaluate(row['input'], choice, sides[0], sides[1])
        recheck(lk, sides)
        raise LookupFailed(f'This row is now "{OUTCOMES[result["outcome"]]}", so "{ACTIONS[action][1]}" '
                           'no longer applies. Look at it again.', 409)

    done = {'link': _link, 'create_google': _create_google, 'import_clickup': _import_clickup,
            'create_both': _create_both}[action](row['input'], result, user)
    done['warnings'] += _clickup_label_missing(done['clickup_id'])
    row['done'] = {'action': action, 'at': timezone.now().isoformat(), 'by': user, **done}
    row['choice'] = {'clickup': done['clickup_id'], 'google': done['google_id'], 'by': 'action'}
    return recheck(lk, load_sides())


def _people_client(edit):
    token, ids = entities.configured_lists()
    cu = entities.ClickUp(token, ids['people'], WriteGuard(dry=False, writes_enabled=True, max_ops=MAX_ACTION_WRITES,
                                                           journal=entities.EditJournal(edit.changes)))
    missing = cu.load_fields()
    if missing:
        raise LookupFailed(f'People list is missing required fields: {", ".join(missing)}.')
    return cu, ids


def _read_task(cu, task_id):
    t = entities._get_task(cu, task_id)
    keys = ('google_id', 'google_link', 'google_hash', 'emails', 'email', 'phones', 'company', 'title',
            'sources', 'groups')
    return t, {k: cu.decode(t, k) for k in keys}


def _google_person(svc, rid):
    resp = svc.people().getBatchGet(resourceNames=[rid], personFields=google_src.PERSON_FIELDS).execute()
    person = next((r['person'] for r in resp.get('responses') or [] if r.get('person')), None)
    if not person:
        raise LookupFailed('That Google contact no longer exists. Re-check the comparison.', 409)
    return person


def _clickup_link_of(person):
    return next((e.get('value') for e in person.get('externalIds') or [] if e.get('type') == 'clickup'), '')


def _sync_label(svc, group_names):
    """resourceName of the SyncDriven Google label, creating it if needed (added to group_names)."""
    rn = next((rn for rn, n in group_names.items() if n.lower() == SYNC_LABEL.lower()), None)
    if not rn:
        group = svc.contactGroups().create(body={'contactGroup': {'name': SYNC_LABEL}}).execute()
        rn = group['resourceName']
        group_names[rn] = SYNC_LABEL
    return rn


def _label_in_google(svc, group_names, rid):
    rn = _sync_label(svc, group_names)
    svc.contactGroups().members().modify(resourceName=rn, body={'resourceNamesToAdd': [rid]}).execute()


def _clickup_label_missing(task_id):
    row = EntityCache.objects.filter(task_id=task_id).first()
    if row and SYNC_LABEL.lower() not in {g.lower() for g in row.row.get('groups') or []}:
        return [f'ClickUp Groups has no "{SYNC_LABEL}" option, so the task wasn\'t labeled. Add the option in '
                'ClickUp to label future ones.']
    return []


def _google_link_changes(cu, vals, c, with_hash):
    changes = {'google_id': c['key'], 'google_link': c['link']}
    if with_hash:
        changes['google_hash'] = c['hash']
    if 'sources' in cu.fields and SOURCE_LABEL['google'].lower() in cu.label_options('sources'):
        sources = union(vals.get('sources') or [], [SOURCE_LABEL['google']])
        if sources != (vals.get('sources') or []):
            changes['sources'] = sources
    opt = cu.label_options('groups').get(SYNC_LABEL.lower())
    if opt:
        groups = union(vals.get('groups') or [], [(opt.get('label') or opt.get('name')).strip()])
        if groups != (vals.get('groups') or []):
            changes['groups'] = groups
    return changes


def _write_link(cu, ids, svc, edit, t, vals, person, c, *, with_hash):
    """Store the Google link on the ClickUp task and the task id on the Google contact."""
    tid = t['id']
    edit.save()
    try:
        cu.set_fields(tid, _google_link_changes(cu, vals, c, with_hash), before=vals, task_name=t['name'])
    except Exception as e:  # noqa: BLE001
        edit.error = str(e)[:1000]
        edit.save()
        raise LookupFailed(f'Writing the Google link to ClickUp "{t["name"]}" failed: {e}', 502)
    warnings = []
    try:
        google_src.writeback(type('Ctx', (), {'cu': cu, 'dry': False})(), svc, person,
                             {'id': tid, 'name': t['name']})
    except Exception as e:  # noqa: BLE001
        warnings.append(f'Linked in ClickUp, but writing the task id back to Google failed: {e}')
    edit.ok = True
    edit.save()
    entities._refresh_rows(entities._client(), [tid], ids)
    entities.invalidate_details([tid])
    _remember_google(google_rec(person, clickup_id=tid))
    return warnings


def _link(inp, result, user):
    tid, gid = result['clickup']['id'], result['google']['id']
    svc = _google_service(write=True)
    person = _google_person(svc, gid)
    other = _clickup_link_of(person)
    if other and other != tid:
        raise LookupFailed(f'That Google contact already points to ClickUp task {other}. Fix it manually.', 409)
    edit = EntityEdit(task_id=tid, edited_by=user)
    cu, ids = _people_client(edit)
    t, vals = _read_task(cu, tid)
    edit.task_name = t['name']
    if vals['google_id']:
        raise LookupFailed(f'ClickUp "{t["name"]}" is already linked to {vals["google_id"]}. Re-check the '
                           'comparison.', 409)
    group_names, _ = google_src.load_groups(svc, ())
    c = google_src.google_contact(person, group_names)
    _label_in_google(svc, group_names, gid)
    # No hash: the next Google sync sees a change and fills the task in from Google, as for any new link.
    warnings = _write_link(cu, ids, svc, edit, t, vals, person, c, with_hash=False)
    return {'clickup_id': tid, 'google_id': gid, 'warnings': warnings}


def _create_google(inp, result, user):
    tid = result['clickup']['id']
    svc = _google_service(write=True)
    edit = EntityEdit(task_id=tid, edited_by=user)
    cu, ids = _people_client(edit)
    t, vals = _read_task(cu, tid)
    edit.task_name = t['name']
    if vals['google_id']:
        raise LookupFailed(f'ClickUp "{t["name"]}" is already linked to {vals["google_id"]}. Re-check the '
                           'comparison.', 409)
    group_names, _ = google_src.load_groups(svc, ())
    _sync_label(svc, group_names)
    by_label = {n.lower(): rn for rn, n in group_names.items()}
    memberships = [{'contactGroupMembership': {'contactGroupResourceName': by_label[g.lower()]}}
                   for g in union(vals['groups'] or [], [SYNC_LABEL]) if g.lower() in by_label]
    body = google_src.person_body(name=t['name'], emails=union(split_list(vals['emails']), [vals['email'] or '']),
                                  phones=split_list(vals['phones']), company=vals['company'], title=vals['title'],
                                  memberships=memberships)
    try:
        created = google_src.create_contact(svc, body)
    except Exception as e:  # noqa: BLE001
        raise LookupFailed(f'Google Contacts create failed: {e}', 502)
    c = google_src.google_contact(created, group_names)
    try:
        warnings = _write_link(cu, ids, svc, edit, t, vals, created, c, with_hash=True)
    except LookupFailed as e:
        raise LookupFailed(f'Created Google contact {c["link"]}, but {e} Link them manually.', e.status)
    return {'clickup_id': tid, 'google_id': c['key'], 'warnings': warnings}


def _import_clickup(inp, result, user):
    gid = result['google']['id']
    svc = _google_service(write=True)
    person = _google_person(svc, gid)
    if _clickup_link_of(person):
        raise LookupFailed(f'That Google contact already points to ClickUp task {_clickup_link_of(person)}. '
                           'Refresh the ClickUp cache and re-check.', 409)
    group_names, _ = google_src.load_groups(svc, ())
    _label_in_google(svc, group_names, gid)
    c = google_src.google_contact(person, group_names)
    c['groups'] = union(c['groups'], [SYNC_LABEL])
    task_id, _, warnings = entities.mirror_to_clickup(svc, person, c, user=user,
                                                      failed_hint='Re-check the row and try again.')
    _remember_google(google_rec(person, clickup_id=task_id))
    return {'clickup_id': task_id, 'google_id': gid, 'warnings': warnings}


def _create_both(inp, result, user):
    svc = _google_service(write=True)
    _sync_label(svc, google_src.load_groups(svc, ())[0])
    parts = google_src.name_parts(name=inp['name'])
    body = {'first_name': parts.get('givenName', ''), 'last_name': parts.get('familyName', ''),
            'emails': [e for e in inp['emails'] if norm_email(e)], 'phones': inp['phones'],
            'groups': [SYNC_LABEL]}
    out = entities.create_person(body, user=user)
    task_id = out['entity']['id']
    _remember_google({'id': out['google_id'], 'name': inp['name'], 'emails': body['emails'],
                      'phones': inp['phones'], 'link': out.get('google_link') or '', 'clickup_id': task_id})
    return {'clickup_id': task_id, 'google_id': out['google_id'], 'warnings': out.get('warnings') or []}
