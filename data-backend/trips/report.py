"""Markdown trip reports: overview, day-by-day, to dos and expenses, in any combination.

Running text rather than tables, so it pastes cleanly into email and reads on a phone.
"""
import re
from datetime import date, datetime, timedelta

from . import zones
from .models import DEFAULT_CURRENCY_SYMBOL, TripStop

SECTIONS = ('overview', 'days', 'todos', 'expenses')
KINDS = {
    'full': ('overview', 'days', 'todos'),
    'summary': ('overview',),
    'expenses': ('expenses',),
}


def _day(d):
    return f'{d:%a} {d:%b} {d.day}'


def _time(t):
    return t.strftime('%I:%M %p').lstrip('0')


_LIST_MARKER = re.compile(r'^(?:[-*+]|\d+[.)])\s+')


def _is_bold(text):
    return len(text) > 4 and text[:2] == text[-2:] and text[:2] in ('**', '__')


def _bold(text):
    text = ' '.join(text.split())
    return text if not text or _is_bold(text) else f'**{text}**'


def _plain(text):
    """Single-line title for headings, where wrapping bold markers would be redundant."""
    text = ' '.join(str(text or '').split())
    return text[2:-2].strip() if _is_bold(text) else text


def _block(text, indent=''):
    """Notes are typed line by line, so consecutive lines become markdown hard breaks."""
    lines = [line.rstrip() for line in str(text or '').strip().splitlines()]
    out = []
    for i, line in enumerate(lines):
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ''
        if line and nxt and not _LIST_MARKER.match(nxt):
            line += '  '
        out.append(f'{indent}{line}' if line else '')
    return '\n'.join(out)


def _day_offset(days):
    return f' ({"+" if days > 0 else "−"}{abs(days)})' if days else ''


def _stop_time(stop, day=None, where=None, labelled=False):
    """'7:30 PM', '1:00 PM - 2:30 PM', or for travel across zones '1:00 PM PST → 7:10 PM GMT+7 (+1)'."""
    if not stop.start_time:
        return ''
    on = day.date if day else None
    tag = (lambda z: f' {zones.abbreviation(z, on)}' if z else '') if labelled else (lambda z: '')
    start = _time(stop.start_time) + tag(where.zone if where else None)
    if not stop.duration_minutes:
        return start
    if where and where.arrive_time is not None:
        end, offset = where.arrive_time, _day_offset(where.arrive_day_offset)
        if where.arrive_zone != where.zone:
            return f'{start} → {_time(end)}{tag(where.arrive_zone)}{offset}'
        return f'{start} - {_time(end)}{tag(where.arrive_zone)}{offset}'
    end = datetime.combine(date.min, stop.start_time) + timedelta(minutes=stop.duration_minutes)
    return f'{start} - {_time(end.time())}' + tag(where.zone if where else None)


def _stop_location(stop):
    if stop.kind == TripStop.KIND_TRAVEL and stop.arrive_loc:
        return f'{stop.loc} → {stop.arrive_loc}' if stop.loc else stop.arrive_loc
    return stop.loc


def _day_locations(day, stops):
    places = []
    for stop in stops:
        for place in (stop.loc, stop.arrive_loc):
            if place and place not in places:
                places.append(place)
    if not places and day.lodging_id:
        places.append(day.lodging.name)
    return ', '.join(places)


def _list_item(line, body):
    """A bullet with free text indented beneath it."""
    body = body.strip()
    if not body:
        return f'- {line}'
    if not _LIST_MARKER.match(body):
        line += '  '
    return f'- {line}\n{_block(body, indent="  ")}'


def _overview_item(day):
    title = _plain(day.title)
    return _list_item(f'**{_day(day.date)}**' + (f' — {title}' if title else ''), day.notes)


def _money(amount, currency=''):
    text = f'{amount:,.2f}'.removesuffix('.00')
    if amount < 0:
        text = text[1:]
    sign = '-' if amount < 0 else ''
    return f'{sign}{currency} {text}' if currency else f'{sign}{DEFAULT_CURRENCY_SYMBOL}{text}'


def _totals(stops):
    """Per-currency totals, default currency first: '$1,200 · THB 3,500'."""
    sums = {}
    for s in stops:
        sums[s.currency] = sums.get(s.currency, 0) + s.price
    return ' · '.join(_money(sums[c], c) for c in sorted(sums, key=lambda c: (c != '', c)))


def _stop_line(stop, day=None, where=None, labelled=False):
    price = _money(stop.price, stop.currency) if stop.price is not None else ''
    when = _stop_time(stop, day, where, labelled or (where is not None and where.arrive_zone not in (None, where.zone)))
    opt = '(option)' if stop.status == TripStop.STATUS_OPTION else ''
    conf = f'Conf: {stop.confirmation}' if stop.confirmation else ''
    parts = (when, _bold(stop.text), opt, _stop_location(stop), conf, price, stop.person)
    return _list_item(' · '.join(p for p in parts if p), stop.description)


def _day_zones(day, info, trip_zone):
    """' · GMT+7' or ' · PST → GMT+7' when the day isn't simply in the trip's zone."""
    if info is None or info.zones in ([trip_zone], [None]):
        return ''
    return ' · ' + ' → '.join(zones.abbreviation(z, day.date) for z in info.zones if z)


def _day_section(day, stops, info=None, trip_zone=None):
    title = _plain(day.title)
    out = ['', f'### {_day(day.date)}' + (f' — {title}' if title else '') + _day_zones(day, info, trip_zone)]
    places = _day_locations(day, stops)
    if places:
        out += ['', '*' + places.replace('*', '\\*') + '*']
    if stops:
        multi = info is not None and len(info.zones) > 1
        lines = []
        for s in stops:
            where = info.stops.get(s.id) if info else None
            labelled = multi or (where is not None and where.zone != info.zones[0])
            lines.append(_stop_line(s, day, where, labelled))
        out += ['', *lines]
    return out


def filename(trip, kind='full'):
    slug = re.sub(r'[^A-Za-z0-9]+', '-', trip.title).strip('-').lower() or 'trip'
    return f'{slug}-report.md' if kind == 'full' else f'{slug}-{kind}.md'


def _grouped_totals(priced, key, blank):
    """'- **Food** — $120 · THB 900' per group, A–Z with the blank group last."""
    groups = {}
    for s in priced:
        name = key(s)
        groups.setdefault(name.lower(), (name, []))[1].append(s)
    return [
        f'- **{groups[k][0] or blank}** — {_totals(groups[k][1])}'
        for k in sorted(groups, key=lambda k: (k == '', k))
    ]


def _expense_line(day, stop):
    who = ' · '.join(p for p in (stop.cat, stop.person) if p)
    flag = ' (option)' if stop.status == TripStop.STATUS_OPTION else (' (to book)' if stop.status == TripStop.STATUS_TOBOOK else '')
    return (f'- **{_day(day.date)}** · {" ".join(stop.text.split())}' + (f' · {who}' if who else '')
            + f' — {_money(stop.price, stop.currency)}{flag}')


def _expense_section(trip, days, stops_by_day):
    class _ExpenseItem:
        def __init__(self, label, title, cat, person, price, currency, status):
            self.label = label
            self.title = title
            self.cat = cat
            self.person = person
            self.price = price
            self.currency = currency
            self.status = status

    items = []
    for l in trip.lodgings.all():
        if l.price is None:
            continue
        stay_days = [d for d in days if d.lodging_id == l.id]
        span = f'{_day(stay_days[0].date)} ({len(stay_days)}n)' if stay_days else 'Lodging'
        items.append(_ExpenseItem(span, l.name, 'Lodging', l.person, l.price, l.currency, l.status))
    for d in days:
        for s in stops_by_day[d.id]:
            if s.price is None:
                continue
            items.append(_ExpenseItem(_day(d.date), ' '.join(s.text.split()), s.cat, s.person, s.price, s.currency, s.status))

    out = ['', '## Expenses']
    if not items:
        return out + ['', 'No prices entered yet.']
    out += ['', f'**Total:** {_totals(items)}']
    out += ['', '### By category', '', *_grouped_totals(items, lambda s: s.cat, 'Uncategorized')]
    if any(s.person for s in items):
        out += ['', '### By person', '', *_grouped_totals(items, lambda s: s.person, 'Unassigned')]
    lines = []
    for it in items:
        who = ' · '.join(p for p in (it.cat, it.person) if p)
        flag = (
            ' (option)' if it.status == TripStop.STATUS_OPTION
            else (' (to book)' if it.status == TripStop.STATUS_TOBOOK else '')
        )
        lines.append(
            f'- **{it.label}** · {it.title}'
            + (f' · {who}' if who else '')
            + f' — {_money(it.price, it.currency)}{flag}'
        )
    out += ['', '### Items', '', *lines]
    return out


def _todos(trip, days, stops_by_day, hide_done):
    """Trip to-dos in plan order: trip-level first, then each day's, then each stop's within the day."""
    day_rank = {d.id: i for i, d in enumerate(days)}
    stop_rank = {s.id: i for d in days for i, s in enumerate(stops_by_day[d.id])}
    todos = [t for t in trip.todos.select_related('day', 'stop') if not (hide_done and t.done)]
    return sorted(todos, key=lambda t: (
        t.day_id is not None,
        day_rank.get(t.day_id, 0),
        t.stop_id is not None,
        stop_rank.get(t.stop_id, 0),
        t.sort_order,
        t.id,
    ))


def _todo_line(todo):
    context = []
    if todo.day_id:
        context.append(_day(todo.day.date))
    if todo.stop_id:
        context.append(' '.join(todo.stop.text.split()))
    text = ' '.join(todo.text.split())
    suffix = f' ({" · ".join(context)})' if context else ''
    return f'- [{"x" if todo.done else " "}] {text}{suffix}'


def _todo_sections(todos):
    """One flat list, or one sub-section per category (A–Z, uncategorized last) once any to-do has one."""
    if not any(t.category for t in todos):
        return ['', *(_todo_line(t) for t in todos)]
    groups = {}
    for t in todos:
        groups.setdefault(t.category.lower(), (t.category, []))[1].append(t)
    out = []
    for key in sorted(groups, key=lambda k: (k == '', k)):
        name, items = groups[key]
        out += ['', f'### {name or "Other"}', '', *(_todo_line(t) for t in items)]
    return out


def build(trip, today=None, hide_done=False, sections=KINDS['full']):
    today = today or date.today()
    days = list(trip.days.select_related('lodging').prefetch_related('stops').order_by('date', 'sort_order', 'id'))
    stops_by_day = {d.id: list(d.stops.order_by('sort_order', 'id')) for d in days}

    out = [f'# {trip.title}', '', f'{today:%b} {today.day}, {today.year} · @{trip.user.get_username()}']
    if trip.description.strip():
        out += ['', trip.description.strip()]

    if days and 'overview' in sections:
        out += ['', '## Overview', '', *(_overview_item(d) for d in days)]
    if days and 'days' in sections:
        resolved = zones.resolve(trip, days, stops_by_day)
        out += ['', '## Day by day']
        for d in days:
            out += _day_section(d, stops_by_day[d.id], resolved[d.id], trip.timezone or None)

    if 'todos' in sections:
        todos = _todos(trip, days, stops_by_day, hide_done)
        if todos or trip.notes.strip():
            out += ['', '## To Dos']
            out += _todo_sections(todos) if todos else ['', 'Nothing to do.']
            if trip.notes.strip():
                out += ['', 'Notes:', '', trip.notes.strip()]

    if 'expenses' in sections:
        out += _expense_section(trip, days, stops_by_day)
    return '\n'.join(out) + '\n'
