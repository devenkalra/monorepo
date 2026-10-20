"""Parse vCard (VCF) files into Person field dicts."""

from __future__ import annotations

import quopri
import re
from datetime import date


_UNESCAPE = {
    r'\n': '\n',
    r'\N': '\n',
    r'\,': ',',
    r'\;': ';',
    r'\\': '\\',
}


def _unfold(text):
    return re.sub(r'\r?\n[ \t]', '', text.replace('\r\n', '\n').replace('\r', '\n'))


def _unescape(value):
    if not value:
        return ''
    def repl(match):
        token = match.group(0)
        return _UNESCAPE.get(token, token[1:])
    return re.sub(r'\\[nN,;\\]', repl, value)


def _decode_value(value, params):
    encoding = str(params.get('ENCODING') or '').upper()
    charset = str(params.get('CHARSET') or 'utf-8')
    if encoding in ('QUOTED-PRINTABLE', 'QP'):
        raw = quopri.decodestring(value.encode('ascii', 'replace'))
        try:
            return raw.decode(charset, errors='replace')
        except LookupError:
            return raw.decode('utf-8', errors='replace')
    return value


def _parse_line(line):
    if ':' not in line:
        return None
    name_params, value = line.split(':', 1)
    parts = name_params.split(';')
    name = parts[0].split('.')[-1].upper()
    params = {}
    for part in parts[1:]:
        if '=' in part:
            key, param_value = part.split('=', 1)
            params[key.upper()] = param_value
        elif part:
            params[part.upper()] = True
    return name, params, _decode_value(value, params)


def _parse_bday(value):
    text = (value or '').strip()
    if not text:
        return None
    if re.match(r'^\d{4}-\d{2}-\d{2}$', text):
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None
    digits = re.sub(r'\D', '', text)
    if len(digits) == 8:
        try:
            return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
        except ValueError:
            return None
    return None


def _map_gender(value):
    token = (value or '').split(';')[0].strip().upper()
    if token in ('M', 'MALE'):
        return 'Male'
    if token in ('F', 'FEMALE'):
        return 'Female'
    return 'Unspecified'


def _split_fn(full_name):
    parts = [part for part in re.split(r'\s+', (full_name or '').strip()) if part]
    if not parts:
        return '', ''
    if len(parts) == 1:
        return parts[0], ''
    return parts[0], ' '.join(parts[1:])


def parse_vcards(text):
    """Return a list of raw property maps, one per vCard."""
    cards = []
    current = None
    for line in _unfold(text).split('\n'):
        line = line.strip()
        if not line:
            continue
        parsed = _parse_line(line)
        if not parsed:
            continue
        name, params, value = parsed
        if name == 'BEGIN' and value.upper() == 'VCARD':
            current = []
            continue
        if name == 'END' and value.upper() == 'VCARD':
            if current is not None:
                cards.append(current)
            current = None
            continue
        if current is not None:
            current.append((name, params, value))
    return cards


def card_to_person_fields(properties):
    """Map one vCard's properties to Person model kwargs (without user)."""
    fields = {
        'first_name': '',
        'last_name': '',
        'display': '',
        'emails': [],
        'phones': [],
        'urls': [],
        'profession': '',
        'description': '',
        'gender': 'Unspecified',
        'dob': None,
        'tags': ['imported/vcf'],
    }
    org = ''
    title = ''
    notes = []

    for name, _params, value in properties:
        value = _unescape(value).strip()
        if not value:
            continue
        if name == 'N':
            parts = value.split(';')
            fields['last_name'] = (parts[0] if parts else '').strip()
            fields['first_name'] = (parts[1] if len(parts) > 1 else '').strip()
        elif name == 'FN' and not fields['display']:
            fields['display'] = value[:255]
        elif name == 'EMAIL':
            if value not in fields['emails']:
                fields['emails'].append(value)
        elif name == 'TEL':
            if value not in fields['phones']:
                fields['phones'].append(value)
        elif name == 'URL':
            if not any(item.get('url') == value for item in fields['urls']):
                fields['urls'].append({'url': value, 'caption': ''})
        elif name == 'TITLE':
            title = value
        elif name == 'ORG':
            org = value.split(';')[0].strip()
        elif name == 'NOTE':
            notes.append(value)
        elif name == 'BDAY':
            fields['dob'] = _parse_bday(value)
        elif name == 'GENDER':
            fields['gender'] = _map_gender(value)

    if not fields['first_name'] and not fields['last_name'] and fields['display']:
        fields['first_name'], fields['last_name'] = _split_fn(fields['display'])
    if not fields['display']:
        fields['display'] = f"{fields['first_name']} {fields['last_name']}".strip()
    fields['profession'] = (title or org)[:255]
    fields['description'] = '\n'.join(notes)
    fields['emails'] = fields['emails'][:20]
    fields['phones'] = fields['phones'][:20]
    return fields


def person_fields_from_vcf(text):
    """Parse a VCF document into a list of Person field dicts."""
    people = []
    for properties in parse_vcards(text):
        fields = card_to_person_fields(properties)
        if not (fields['display'] or fields['emails'] or fields['phones']):
            continue
        if not fields['display']:
            fields['display'] = fields['emails'][0] if fields['emails'] else 'Person'
        people.append(fields)
    return people
