"""Markdown trip report: summary, day-by-day plan, to dos and open items."""
import re
from datetime import date, datetime, timedelta

from .models import TripStop


def _day(d):
    return f'{d:%a} {d:%b} {d.day}'


def _time(t):
    return t.strftime('%I:%M %p').lstrip('0')


_LIST_MARKER = re.compile(r'^(?:[-*+]|\d+[.)])\s+')


def _cell(text):
    """Keep inline markdown; plain tables can't hold line breaks or lists, so lines join with ' · '."""
    lines = []
    for line in str(text or '').splitlines():
        line = _LIST_MARKER.sub('', ' '.join(line.split()))
        if line:
            lines.append(line)
    return ' · '.join(lines).replace('|', '\\|')


def _bold(text):
    text = text.strip()
    if not text or (len(text) > 4 and text[:2] == text[-2:] and text[:2] in ('**', '__')):
        return text
    return f'**{text}**'


def _row(*cells):
    return '| ' + ' | '.join(_cell(c) for c in cells) + ' |'


def _table(headers, rows):
    return '\n'.join([_row(*headers), '| ' + ' | '.join('---' for _ in headers) + ' |', *rows])


def _stop_time(stop):
    if not stop.start_time:
        return ''
    start = _time(stop.start_time)
    if not stop.duration_minutes:
        return start
    end = datetime.combine(date.min, stop.start_time) + timedelta(minutes=stop.duration_minutes)
    return f'{start} - {_time(end.time())}'


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


def _day_note(day):
    return '\n'.join(part for part in (_bold(day.title), day.notes) if part.strip())


def filename(trip):
    slug = re.sub(r'[^A-Za-z0-9]+', '-', trip.title).strip('-').lower() or 'trip'
    return f'{slug}-report.md'


def build(trip, today=None):
    today = today or date.today()
    days = list(trip.days.select_related('lodging').prefetch_related('stops').order_by('date', 'sort_order', 'id'))
    stops_by_day = {d.id: list(d.stops.order_by('sort_order', 'id')) for d in days}

    out = [f'# {trip.title}', '', f'{today:%b} {today.day}, {today.year} · @{trip.user.get_username()}']
    if trip.description.strip():
        out += ['', trip.description.strip()]

    out += ['', '## Day by Day Summary', '']
    out.append(_table(['Date', 'Location(s)', 'Note (from Day)'],
                      [_row(_day(d.date), _day_locations(d, stops_by_day[d.id]), _day_note(d)) for d in days]))

    rows = []
    for d in days:
        stops = stops_by_day[d.id]
        if not stops:
            rows.append(_row(_day(d.date), '', _day_locations(d, stops), d.title or d.notes))
        for i, stop in enumerate(stops):
            activity = '\n'.join(part for part in (stop.text, stop.description) if part.strip())
            rows.append(_row(_day(d.date) if i == 0 else '', _stop_time(stop), _stop_location(stop), activity))
    out += ['', '## Day by day', '', _table(['Date', 'Time', 'Location(s)', 'Note (Activity From Day)'], rows)]

    todos = [f'- [ ] {" ".join(stop.text.split())} ({_day(d.date)})'
             for d in days for stop in stops_by_day[d.id]
             if stop.status == TripStop.STATUS_TOBOOK and not stop.done]
    if todos or trip.notes.strip():
        out += ['', '## To Dos', '']
        out += todos or ['Nothing left to book.']
        if trip.notes.strip():
            out += ['', 'Notes:', '', trip.notes.strip()]

    if trip.open_items.strip():
        out += ['', '## Open Items', '', 'Add a comment on anything you\'d change.', '', trip.open_items.strip()]
    return '\n'.join(out) + '\n'
