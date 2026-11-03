"""Mini Google Contacts manager: search, bulk field update, bulk create (Google-only writes)."""
from __future__ import annotations

import time

from . import google_auth
from .engine.normalize import norm_email, phone_for_storage, union
from .engine.sources import google as google_src

PAGE_SIZE = 50
MAX_UPDATE = 100
MAX_CREATE = 50
UPDATE_FIELDS = frozenset({'labels', 'email', 'phone', 'city', 'state', 'country'})
READ_MASK = google_src.PERSON_FIELDS


class ManagerError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _svc(write=False):
    try:
        return google_auth.people_service(write=write)
    except ValueError as e:
        raise ManagerError(str(e), 400) from e


def _clean(s):
    return ' '.join(str(s or '').split())


def _as_list(raw):
    if isinstance(raw, (list, tuple)):
        return [_clean(x) for x in raw if _clean(x)]
    s = _clean(raw)
    if not s:
        return []
    return [_clean(x) for x in s.split(',') if _clean(x)]


def _primary_name(p):
    n = (p.get('names') or [{}])[0]
    display = _clean(n.get('displayName'))
    if display:
        return display
    return _clean(' '.join(filter(None, [n.get('givenName'), n.get('familyName')]))) or '(no name)'


def _emails(p):
    return [_clean(e.get('value')) for e in p.get('emailAddresses') or [] if _clean(e.get('value'))]


def _phones(p):
    out = []
    for x in p.get('phoneNumbers') or []:
        v = phone_for_storage(x.get('canonicalForm') or x.get('value')) or _clean(x.get('value'))
        if v:
            out.append(v)
    return out


def _addr(p):
    addrs = p.get('addresses') or []
    a = next((x for x in addrs if x.get('metadata', {}).get('primary')), addrs[0] if addrs else {})
    return {
        'address': _clean(a.get('formattedValue')) or None,
        'city': _clean(a.get('city')) or None,
        'state': _clean(a.get('region')) or None,
        'country': (_clean(a.get('country')) or _clean(a.get('countryCode')) or None),
    }


def _label_names(p, group_names):
    out = []
    for m in p.get('memberships') or []:
        rn = (m.get('contactGroupMembership') or {}).get('contactGroupResourceName')
        if rn in group_names:
            out.append(group_names[rn])
    return sorted(out)


def serialize_person(p, group_names):
    loc = _addr(p)
    return {
        'id': p.get('resourceName') or '',
        'etag': p.get('etag') or '',
        'name': _primary_name(p),
        'given_name': _clean(((p.get('names') or [{}])[0]).get('givenName')) or '',
        'family_name': _clean(((p.get('names') or [{}])[0]).get('familyName')) or '',
        'emails': _emails(p),
        'phones': _phones(p),
        'labels': _label_names(p, group_names),
        'city': loc['city'] or '',
        'state': loc['state'] or '',
        'country': loc['country'] or '',
        'address': loc['address'] or '',
        'link': (f"https://contacts.google.com/person/{(p.get('resourceName') or '').split('/')[-1]}"
                 if p.get('resourceName') else ''),
    }


def list_labels():
    """User contact groups for filters and bulk label assign."""
    svc = _svc(write=False)
    names, _ = google_src.load_groups(svc, ())
    return {'labels': [{'id': rn, 'name': nm} for rn, nm in sorted(names.items(), key=lambda x: x[1].lower())]}


def _group_map(svc):
    names, _ = google_src.load_groups(svc, ())
    return names, {nm.lower(): rn for rn, nm in names.items()}


def _fetch_people(svc, resource_names):
    people = []
    for i in range(0, len(resource_names), google_src.BATCH_GET_MAX):
        chunk = resource_names[i:i + google_src.BATCH_GET_MAX]
        if not chunk:
            continue
        resp = svc.people().getBatchGet(resourceNames=chunk, personFields=READ_MASK).execute()
        for r in resp.get('responses') or []:
            if r.get('person'):
                people.append(r['person'])
    return people


def list_contacts(*, q='', label='', page_token=''):
    """Search or page through Google contacts. Optional label filters the result set."""
    svc = _svc(write=False)
    group_names, by_label = _group_map(svc)
    label_rn = by_label.get(_clean(label).lower()) if label else None
    if label and not label_rn:
        raise ManagerError(f'Unknown label "{_clean(label)}".')

    q = _clean(q)
    next_token = None
    people = []

    if q:
        resp = svc.people().searchContacts(query=q, readMask=READ_MASK, pageSize=PAGE_SIZE).execute()
        people = [r['person'] for r in resp.get('results') or [] if r.get('person')]
        # searchContacts has no page token in older clients; keep None
    elif label_rn:
        # Members of one group (up to a few thousand), then page in memory via page_token index.
        g = svc.contactGroups().get(resourceName=label_rn, maxMembers=2000).execute()
        members = list(g.get('memberResourceNames') or [])
        start = int(page_token) if str(page_token).isdigit() else 0
        chunk = members[start:start + PAGE_SIZE]
        people = _fetch_people(svc, chunk)
        if start + PAGE_SIZE < len(members):
            next_token = str(start + PAGE_SIZE)
    else:
        kw = dict(resourceName='people/me', pageSize=PAGE_SIZE, personFields=READ_MASK,
                  sortOrder='LAST_MODIFIED_DESCENDING')
        if page_token:
            kw['pageToken'] = page_token
        resp = svc.people().connections().list(**kw).execute()
        people = list(resp.get('connections') or [])
        next_token = resp.get('nextPageToken') or None

    if label_rn and q:
        people = [p for p in people if any(
            (m.get('contactGroupMembership') or {}).get('contactGroupResourceName') == label_rn
            for m in p.get('memberships') or [])]

    return {
        'contacts': [serialize_person(p, group_names) for p in people],
        'next_page_token': next_token,
        'labels': [{'id': rn, 'name': nm} for rn, nm in sorted(group_names.items(), key=lambda x: x[1].lower())],
    }


def _resolve_label_ids(by_label, labels):
    ids, unknown = [], []
    for raw in labels:
        name = _clean(raw)
        if not name:
            continue
        rn = by_label.get(name.lower())
        if rn:
            ids.append(rn)
        else:
            unknown.append(name)
    return ids, unknown


def _get_person(svc, rid):
    people = _fetch_people(svc, [rid])
    if not people:
        raise ManagerError(f'Contact {rid} not found in Google.', 404)
    return people[0]


_ADDRESS_WRITE_KEYS = (
    'type', 'formattedValue', 'streetAddress', 'extendedAddress', 'city', 'region',
    'postalCode', 'poBox', 'country', 'countryCode',
)


def _format_address(addr):
    """Build the unstructured line Google Contacts UI shows for an address."""
    city_region = ', '.join(p for p in [_clean(addr.get('city')), _clean(addr.get('region'))] if p)
    parts = [
        _clean(addr.get('streetAddress')) or _clean(addr.get('extendedAddress')),
        city_region,
        _clean(addr.get('postalCode')),
        _clean(addr.get('country')) or _clean(addr.get('countryCode')),
    ]
    return ', '.join(p for p in parts if p)


def _set_address_fields(person, *, city=None, state=None, country=None):
    """Overwrite city/region/country on the primary (or first) address; create one if needed.

    Always refreshes formattedValue — Google Contacts displays that string, not the structured
    fields alone, so leaving a stale formattedValue makes edits look like they didn't stick.
    """
    addrs = list(person.get('addresses') or [])
    if addrs:
        idx = next((i for i, a in enumerate(addrs) if a.get('metadata', {}).get('primary')), 0)
        raw = addrs[idx]
        base = {k: raw[k] for k in _ADDRESS_WRITE_KEYS if raw.get(k) not in (None, '')}
    else:
        idx, base = 0, {}
    if city is not None:
        if city:
            base['city'] = city
        else:
            base.pop('city', None)
    if state is not None:
        if state:
            base['region'] = state
        else:
            base.pop('region', None)
    if country is not None:
        if country:
            base['country'] = country
            base.pop('countryCode', None)
        else:
            base.pop('country', None)
            base.pop('countryCode', None)
    formatted = _format_address(base)
    if formatted:
        base['formattedValue'] = formatted
    else:
        base.pop('formattedValue', None)
    if not base:
        # Clearing everything: send empty list so Google drops the address.
        return []
    if addrs:
        cleaned = []
        for i, a in enumerate(addrs):
            if i == idx:
                cleaned.append(base)
            else:
                cleaned.append({k: a[k] for k in _ADDRESS_WRITE_KEYS if a.get(k) not in (None, '')})
        return cleaned
    return [base]


def _update_person(svc, person, update_fields, body_patch):
    rid = person['resourceName']
    body = {'etag': person['etag'], **body_patch}
    updated = svc.people().updateContact(
        resourceName=rid, updatePersonFields=','.join(update_fields), body=body, personFields=READ_MASK,
    ).execute()
    time.sleep(0.35)  # soft-rate-limit People API writes
    return updated


def _add_labels(svc, ids, label_ids):
    for rn in label_ids:
        svc.contactGroups().members().modify(
            resourceName=rn, body={'resourceNamesToAdd': ids}).execute()
        time.sleep(0.35)


def _patch_location(svc, person, *, city=None, state=None, country=None):
    """city/state/country: None = leave alone, str (possibly '') = set/clear."""
    if city is None and state is None and country is None:
        return person, False
    addrs = _set_address_fields(person, city=city, state=state, country=country)
    return _update_person(svc, person, ['addresses'], {'addresses': addrs}), True


def bulk_update(body):
    """Update many Google contacts.

    Single-field (legacy): {ids, field, value} for labels|email|phone|city|state|country
    Multi-field: {ids, labels?: [...], city?, state?, country?} — filled keys apply together.
      labels add-only; city/state/country overwrite (empty string clears).
    """
    if not isinstance(body, dict):
        raise ManagerError('Expected a JSON object.')
    ids = list(dict.fromkeys(_clean(x) for x in (body.get('ids') or []) if _clean(x)))
    if not ids:
        raise ManagerError('Select at least one contact.')
    if len(ids) > MAX_UPDATE:
        raise ManagerError(f'At most {MAX_UPDATE} contacts per bulk update.')

    field = _clean(body.get('field')).lower()
    multi = not field and any(k in body for k in ('labels', 'city', 'state', 'country'))
    if field and field not in UPDATE_FIELDS:
        raise ManagerError(f'Unsupported field "{field}".')
    if not field and not multi:
        raise ManagerError('Provide field/value or labels/city/state/country.')

    svc = _svc(write=True)
    group_names, by_label = _group_map(svc)
    results = []

    if multi or field in ('labels', 'city', 'state', 'country'):
        want_labels = (multi and 'labels' in body) or field == 'labels'
        raw_labels = body.get('labels') if multi else body.get('value')
        label_ids, unknown = (_resolve_label_ids(by_label, _as_list(raw_labels))
                              if want_labels else ([], []))
        if unknown:
            raise ManagerError('Unknown label(s): ' + ', '.join(f'"{u}"' for u in unknown))
        if field == 'labels' and not label_ids:
            raise ManagerError('Pick at least one label.')

        city = state = country = None
        if multi:
            if 'city' in body:
                city = _clean(body['city'])
            if 'state' in body:
                state = _clean(body['state'])
            if 'country' in body:
                country = _clean(body['country'])
        elif field == 'city':
            city = _clean(body.get('value'))
        elif field == 'state':
            state = _clean(body.get('value'))
        elif field == 'country':
            country = _clean(body.get('value'))

        if multi and not label_ids and city is None and state is None and country is None:
            raise ManagerError('Pick a label or set city/state/country.')

        if label_ids:
            try:
                _add_labels(svc, ids, label_ids)
            except Exception as e:  # noqa: BLE001
                return _bulk_summary('bulk', [
                    {'id': tid, 'ok': False, 'error': str(e)[:300]} for tid in ids])

        if city is None and state is None and country is None:
            label_names = [group_names[r] for r in label_ids]
            return _bulk_summary('labels', [
                {'id': tid, 'ok': True, 'changed': True, 'labels_added': label_names} for tid in ids])

        for tid in ids:
            try:
                person = _get_person(svc, tid)
                changed = bool(label_ids)
                person, loc_changed = _patch_location(
                    svc, person, city=city, state=state, country=country)
                changed = changed or loc_changed
                results.append({'id': tid, 'ok': True, 'changed': changed})
            except ManagerError as e:
                results.append({'id': tid, 'ok': False, 'error': str(e), 'status': e.status})
            except Exception as e:  # noqa: BLE001
                results.append({'id': tid, 'ok': False, 'error': str(e)[:300]})
        return _bulk_summary('bulk' if multi else field, results)
    # email / phone add-only (single-field)
    value = body.get('value')
    for tid in ids:
        try:
            person = _get_person(svc, tid)
            if field == 'email':
                email = norm_email(_clean(value)) or _clean(value)
                if not email:
                    raise ManagerError('Email is required.')
                existing = _emails(person)
                if email.lower() in {e.lower() for e in existing}:
                    results.append({'id': tid, 'ok': True, 'changed': False, 'skipped': 'already has email'})
                    continue
                patch = {'emailAddresses': (
                    [{'value': e} for e in existing] + [{'value': email}])}
                _update_person(svc, person, ['emailAddresses'], patch)
                results.append({'id': tid, 'ok': True, 'changed': True})
            else:
                phone = phone_for_storage(_clean(value)) or _clean(value)
                if not phone:
                    raise ManagerError('Phone is required.')
                existing = _phones(person)
                if phone in existing:
                    results.append({'id': tid, 'ok': True, 'changed': False, 'skipped': 'already has phone'})
                    continue
                raw_existing = [
                    {'value': x.get('value')} for x in person.get('phoneNumbers') or [] if x.get('value')]
                patch = {'phoneNumbers': raw_existing + [{'value': phone}]}
                _update_person(svc, person, ['phoneNumbers'], patch)
                results.append({'id': tid, 'ok': True, 'changed': True})
        except ManagerError as e:
            results.append({'id': tid, 'ok': False, 'error': str(e), 'status': e.status})
        except Exception as e:  # noqa: BLE001
            results.append({'id': tid, 'ok': False, 'error': str(e)[:300]})

    return _bulk_summary(field, results)


def update_contact(resource_name, body):
    """Update one Google contact. Body may include first_name, last_name, emails, phones,
    labels (replace known user labels), city, state, country.
    """
    rid = _clean(resource_name)
    if not rid.startswith('people/'):
        raise ManagerError('Invalid contact id.')
    if not isinstance(body, dict):
        raise ManagerError('Expected a JSON object.')

    svc = _svc(write=True)
    group_names, by_label = _group_map(svc)
    person = _get_person(svc, rid)
    changed = False

    if any(k in body for k in ('first_name', 'last_name', 'given_name', 'family_name')):
        cur = (person.get('names') or [{}])[0]
        given = _clean(body['first_name'] if 'first_name' in body else body.get('given_name', cur.get('givenName')))
        family = _clean(body['last_name'] if 'last_name' in body else body.get('family_name', cur.get('familyName')))
        nm = google_src.name_parts(given_name=given, family_name=family)
        if not nm:
            raise ManagerError('Need a first or last name.')
        display = google_src.display_name(given_name=given, family_name=family)
        person = _update_person(svc, person, ['names'], {
            'names': [{**nm, 'displayName': display}],
        })
        changed = True

    if 'emails' in body or 'email' in body:
        emails = union([norm_email(e) or e for e in _as_list(body.get('emails') or body.get('email'))])
        person = _update_person(svc, person, ['emailAddresses'], {
            'emailAddresses': [{'value': e} for e in emails],
        })
        changed = True

    if 'phones' in body or 'phone' in body:
        phones = union([phone_for_storage(p) or p for p in _as_list(body.get('phones') or body.get('phone'))])
        person = _update_person(svc, person, ['phoneNumbers'], {
            'phoneNumbers': [{'value': p} for p in phones],
        })
        changed = True

    if any(k in body for k in ('city', 'state', 'country')):
        city = _clean(body['city']) if 'city' in body else None
        state = _clean(body['state']) if 'state' in body else None
        country = _clean(body['country']) if 'country' in body else None
        person, loc_changed = _patch_location(svc, person, city=city, state=state, country=country)
        changed = changed or loc_changed

    if 'labels' in body or 'groups' in body:
        want_ids, unknown = _resolve_label_ids(by_label, _as_list(body.get('labels') or body.get('groups')))
        if unknown:
            raise ManagerError('Unknown label(s): ' + ', '.join(f'"{u}"' for u in unknown))
        current = {
            (m.get('contactGroupMembership') or {}).get('contactGroupResourceName')
            for m in person.get('memberships') or []
            if (m.get('contactGroupMembership') or {}).get('contactGroupResourceName') in group_names
        }
        want = set(want_ids)
        to_add = want - current
        to_rem = current - want
        for rn in to_add:
            svc.contactGroups().members().modify(
                resourceName=rn, body={'resourceNamesToAdd': [rid]}).execute()
            time.sleep(0.35)
            changed = True
        for rn in to_rem:
            svc.contactGroups().members().modify(
                resourceName=rn, body={'resourceNamesToRemove': [rid]}).execute()
            time.sleep(0.35)
            changed = True
        if to_add or to_rem:
            person = _get_person(svc, rid)

    return {'changed': changed, 'contact': serialize_person(person, group_names)}


def _bulk_summary(op, results):
    return {
        'op': op,
        'results': results,
        'ok': sum(1 for r in results if r.get('ok') and r.get('changed')),
        'skipped': sum(1 for r in results if r.get('ok') and not r.get('changed')),
        'failed': sum(1 for r in results if not r.get('ok')),
    }


def bulk_create(body):
    """Create many Google contacts. Body: {contacts: [{first_name, last_name, ...}, ...]}."""
    if not isinstance(body, dict):
        raise ManagerError('Expected a JSON object.')
    rows = body.get('contacts')
    if not isinstance(rows, list) or not rows:
        raise ManagerError('Provide a contacts array.')
    if len(rows) > MAX_CREATE:
        raise ManagerError(f'At most {MAX_CREATE} contacts per bulk create.')

    svc = _svc(write=True)
    group_names, by_label = _group_map(svc)
    results = []

    for i, raw in enumerate(rows):
        if not isinstance(raw, dict):
            results.append({'index': i, 'ok': False, 'error': 'Each contact must be an object.'})
            continue
        given = _clean(raw.get('first_name') or raw.get('given_name'))
        family = _clean(raw.get('last_name') or raw.get('family_name'))
        emails = union([norm_email(e) or e for e in _as_list(raw.get('emails') or raw.get('email'))])
        phones = union([phone_for_storage(p) or p for p in _as_list(raw.get('phones') or raw.get('phone'))])
        city = _clean(raw.get('city')) or None
        state = _clean(raw.get('state')) or None
        country = _clean(raw.get('country')) or None
        labels = _as_list(raw.get('labels') or raw.get('groups'))
        name = google_src.display_name(given_name=given, family_name=family)
        if not name and not emails and not phones:
            results.append({'index': i, 'ok': False, 'error': 'Need a name, email or phone.'})
            continue
        label_ids, unknown = _resolve_label_ids(by_label, labels)
        if unknown:
            results.append({'index': i, 'ok': False,
                            'error': 'Unknown label(s): ' + ', '.join(f'"{u}"' for u in unknown)})
            continue
        memberships = [{'contactGroupMembership': {'contactGroupResourceName': rn}} for rn in label_ids]
        person = google_src.person_body(
            given_name=given, family_name=family, emails=emails, phones=phones,
            city=city, state=state, country=country, memberships=memberships)
        try:
            created = google_src.create_contact(svc, person)
            time.sleep(0.35)
            results.append({
                'index': i, 'ok': True, 'changed': True,
                'contact': serialize_person(created, group_names),
            })
        except Exception as e:  # noqa: BLE001
            results.append({'index': i, 'ok': False, 'error': str(e)[:300]})

    return {
        'op': 'create',
        'results': results,
        'ok': sum(1 for r in results if r.get('ok')),
        'failed': sum(1 for r in results if not r.get('ok')),
        'contacts': [r['contact'] for r in results if r.get('ok') and r.get('contact')],
    }
