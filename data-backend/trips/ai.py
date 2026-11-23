"""Trip assistant: ask an LLM for recommendations and turn them into stops, events, or lodging.

The model only ever proposes. Its JSON is cleaned into ``TripSuggestion`` rows here, and
``apply_suggestion`` creates the real records through the normal serializers.
"""

import json
import re

from django.db.models import Max
from rest_framework.exceptions import ValidationError

from productions.llm import chat_completion

from . import zones
from .models import TripDay, TripLeg, TripStop, TripStopAttachment, TripSuggestion
from .serializers import TripLodgingSerializer, TripStopSerializer

SYSTEM_PROMPT = """You are a travel planner helping someone fill in their trip itinerary.
Reply with one JSON object: {"suggestions": [ ... ]} holding 3-8 suggestions unless the user asks for a different number.

Each suggestion is one of these shapes:
{"kind": "lodging", "name": str, "address": str, "url": str, "description": str, "why": str,
 "price_hint": "$" | "$$" | "$$$" | "$$$$", "check_in_time": "HH:MM", "check_out_time": "HH:MM", "day_ids": [int]}
{"kind": "stop", "name": str, "address": str, "url": str, "description": str, "why": str,
 "price_hint": str, "category": str, "day_id": int, "start_time": "HH:MM", "duration_minutes": int}
{"kind": "event", "name": str, "address": str, "url": str, "description": str, "why": str,
 "price_hint": str, "category": str, "day_id": int, "start_time": "HH:MM", "needs_booking": bool}

Rules:
- "stop" is a place visited at your own pace (sight, park, restaurant, neighborhood).
- "event" happens at a fixed time (tour, show, class, timed ticket, dinner reservation).
- "lodging" is a hotel, inn, or rental; day_ids are the nights it would cover.
- Only use day ids that appear in the trip context. Pick the day whose city fits; use null when none fits.
- Choose start times that fit the gaps in that day's schedule.
- Recommend only real places you are confident exist. Never invent phone numbers, confirmation codes, or exact prices.
- category is a short label such as Sight, Food, Nature, Museum, Shopping.
- Keep description under 300 characters and why under 160 characters."""

KIND_ALIASES = {
    'stop': TripSuggestion.KIND_STOP,
    'activity': TripSuggestion.KIND_STOP,
    'place': TripSuggestion.KIND_STOP,
    'sight': TripSuggestion.KIND_STOP,
    'restaurant': TripSuggestion.KIND_STOP,
    'event': TripSuggestion.KIND_EVENT,
    'tour': TripSuggestion.KIND_EVENT,
    'lodging': TripSuggestion.KIND_LODGING,
    'hotel': TripSuggestion.KIND_LODGING,
    'stay': TripSuggestion.KIND_LODGING,
}

STOP_FIELDS = ('day_id', 'leg_id', 'text', 'description', 'loc', 'cat', 'status', 'start_time', 'duration_minutes')
LODGING_FIELDS = (
    'name', 'address', 'phone', 'url', 'confirmation', 'notes', 'check_in_time', 'check_out_time', 'day_ids',
)

_TIME = re.compile(r'^(\d{1,2}):(\d{2})')
_THINK = re.compile(r'<think>.*?</think>', re.S)


def _hhmm(value):
    if value is None:
        return ''
    return str(value)[:5]


def build_context(trip, day=None):
    """Plain-text picture of the trip so suggestions can target real days and free time."""
    lines = [f'Trip: {trip.title}']
    if trip.start_date:
        lines.append(f'Dates: {trip.start_date} to {trip.end_date or trip.start_date}')
    if trip.description.strip():
        lines.append(f'About: {" ".join(trip.description.split())[:600]}')
    lodgings = list(trip.lodgings.all())
    if lodgings:
        lines.append('Lodging already booked: ' + '; '.join(
            f'{l.name}' + (f' ({l.address})' if l.address else '') for l in lodgings
        ))
    legs = list(trip.legs.order_by('sort_order', 'id'))
    if legs:
        lines.append('Legs: ' + ' -> '.join(
            f'{l.name}' + (f' ({l.location})' if l.location else '') for l in legs
        ))
    lines.append('')
    lines.append('Days (id, date, title, time zones, lodging, scheduled items). Times are local wall-clock times:')
    all_days = list(trip.days.select_related('lodging', 'leg').prefetch_related('stops').order_by('date'))
    day_zones = zones.resolve(trip, all_days, {d.id: list(d.stops.all()) for d in all_days})
    for d in all_days:
        head = f'- day_id={d.id} {d.date:%a %Y-%m-%d}'
        if d.leg_id:
            head += f' [{d.leg.name}]'
        if d.title:
            head += f' "{d.title}"'
        zone_names = [z for z in day_zones[d.id].zones if z]
        if zone_names:
            head += f'; time zone {" then ".join(zone_names)}'
        if d.lodging_id:
            head += f'; staying at {d.lodging.name}'
        lines.append(head)
        stops = sorted(d.stops.all(), key=lambda s: (s.start_time is None, s.start_time or 0, s.sort_order))
        for s in stops:
            when = _hhmm(s.start_time) or 'untimed'
            if s.start_time and s.duration_minutes:
                when += f' for {s.duration_minutes} min'
            where = s.loc + (f' -> {s.arrive_loc}' if s.arrive_loc else '')
            lines.append(f'    {when} [{s.kind}] {" ".join(s.text.split())[:120]}' + (f' @ {where}' if where else ''))
    ideas = list(trip.stops.filter(day__isnull=True).select_related('leg').order_by('sort_order', 'id')[:30])
    if ideas:
        lines.append('')
        lines.append('Unscheduled ideas already saved (avoid duplicating):')
        for idea in ideas:
            tag = f' [{idea.leg.name}]' if idea.leg_id else ''
            lines.append(f'- {" ".join(idea.text.split())[:100]}{tag}' + (f' @ {idea.loc}' if idea.loc else ''))
    if day is not None:
        lines.append('')
        lines.append(f'Focus on day_id={day.id} ({day.date}) unless the request says otherwise.')
    return '\n'.join(lines)


def _text(value, limit):
    return ' '.join(str(value or '').split())[:limit]


def _time(value):
    match = _TIME.match(str(value or '').strip())
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    return f'{hour:02d}:{minute:02d}' if hour < 24 and minute < 60 else None


def _int(value, low=None, high=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if (low is not None and number < low) or (high is not None and number > high):
        return None
    return number


def _url(value):
    url = str(value or '').strip()
    return url[:2000] if url.startswith(('http://', 'https://')) else ''


def clean_suggestion(raw, day_ids):
    """Coerce one model-produced dict into our suggestion shape, or None if it is unusable."""
    if not isinstance(raw, dict):
        return None
    kind = KIND_ALIASES.get(str(raw.get('kind') or '').strip().lower())
    name = _text(raw.get('name') or raw.get('title') or raw.get('text'), 255)
    if not kind or not name:
        return None
    item = {
        'name': name,
        'address': _text(raw.get('address') or raw.get('loc'), 255),
        'url': _url(raw.get('url')),
        'description': _text(raw.get('description'), 600),
        'why': _text(raw.get('why'), 300),
        'price_hint': _text(raw.get('price_hint'), 8),
    }
    if kind == TripSuggestion.KIND_LODGING:
        nights = raw.get('day_ids') if isinstance(raw.get('day_ids'), list) else []
        item['day_ids'] = sorted({n for n in (_int(v) for v in nights) if n in day_ids})
        item['check_in_time'] = _time(raw.get('check_in_time'))
        item['check_out_time'] = _time(raw.get('check_out_time'))
    else:
        day_id = _int(raw.get('day_id'))
        item['day_id'] = day_id if day_id in day_ids else None
        item['start_time'] = _time(raw.get('start_time'))
        item['category'] = _text(raw.get('category'), 64)
        if kind == TripSuggestion.KIND_STOP:
            item['duration_minutes'] = _int(raw.get('duration_minutes'), 5, 24 * 60)
        else:
            item['needs_booking'] = bool(raw.get('needs_booking'))
    return kind, item


def parse_suggestions(text, trip):
    """Turn raw model output into a list of (kind, data) pairs, dropping anything malformed."""
    text = _THINK.sub('', text or '').strip()
    try:
        payload = json.loads(text)
    except ValueError:
        match = re.search(r'\{.*\}', text, re.S)
        try:
            payload = json.loads(match.group(0)) if match else {}
        except ValueError:
            payload = {}
    rows = payload.get('suggestions') if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []

    day_ids = set(trip.days.values_list('id', flat=True))
    planned = {' '.join(t.lower().split()) for t in TripStop.objects.filter(trip=trip).values_list('text', flat=True)}
    planned |= {n.lower() for n in trip.lodgings.values_list('name', flat=True)}
    seen = set()
    out = []
    for raw in rows:
        cleaned = clean_suggestion(raw, day_ids)
        if not cleaned:
            continue
        kind, item = cleaned
        key = (kind, item['name'].lower())
        if key in seen:
            continue
        seen.add(key)
        item['already_planned'] = item['name'].lower() in planned
        out.append((kind, item))
    return out


def generate(batch):
    """Ask the model for suggestions for ``batch`` and store them. Raises on failure."""
    prompt = f'{build_context(batch.trip, batch.day)}\n\nRequest: {batch.prompt}'
    text = chat_completion(prompt=prompt, system=SYSTEM_PROMPT, json_mode=True, timeout=180, temperature=0.5)
    items = parse_suggestions(text, batch.trip)
    if not items:
        raise ValueError('The assistant did not return any usable suggestions. Try rephrasing the request.')
    TripSuggestion.objects.bulk_create([
        TripSuggestion(user=batch.user, batch=batch, kind=kind, data=data, sort_order=i)
        for i, (kind, data) in enumerate(items)
    ])


def map_query(data):
    """Name plus address finds the actual place; the address alone often lands on a street."""
    return ', '.join(p for p in (data.get('name', ''), data.get('address', '')) if p)


def _notes(data):
    parts = [data.get('description', '')]
    if data.get('why'):
        parts.append(f'*Why:* {data["why"]}')
    if data.get('price_hint'):
        parts.append(f'Price: {data["price_hint"]}')
    return '\n\n'.join(p for p in parts if p)


def draft_fields(suggestion):
    """The stop or lodging form fields a suggestion would create, before any user edits."""
    data = suggestion.data
    if suggestion.kind == TripSuggestion.KIND_LODGING:
        return {
            'name': data.get('name', ''),
            'address': data.get('address', ''),
            'url': data.get('url', ''),
            'notes': _notes(data),
            'check_in_time': data.get('check_in_time'),
            'check_out_time': data.get('check_out_time'),
            'day_ids': data.get('day_ids', []),
        }
    is_event = suggestion.kind == TripSuggestion.KIND_EVENT
    return {
        'day_id': data.get('day_id'),
        'kind': TripStop.KIND_EVENT if is_event else TripStop.KIND_ACTIVITY,
        'text': data.get('name', ''),
        'description': _notes(data),
        'loc': data.get('address', ''),
        'cat': data.get('category') or ('Event' if is_event else 'Sight'),
        'status': TripStop.STATUS_TOBOOK if data.get('needs_booking') else TripStop.STATUS_CONFIRMED,
        'start_time': data.get('start_time'),
        'duration_minutes': None if is_event else data.get('duration_minutes'),
    }


def apply_suggestion(suggestion, request, fields=None):
    """Create the stop/event or lodging for ``suggestion``.

    ``fields`` holds the user's edits from the stop or lodging form; anything omitted falls
    back to what the model suggested. Call inside a transaction.
    """
    if suggestion.status == TripSuggestion.STATUS_ADDED:
        raise ValidationError({'detail': 'This suggestion was already added.'})
    fields = fields if isinstance(fields, dict) else {}
    data = suggestion.data
    trip = suggestion.batch.trip
    context = {'request': request}
    payload = draft_fields(suggestion)

    if suggestion.kind == TripSuggestion.KIND_LODGING:
        payload.update({k: v for k, v in fields.items() if k in LODGING_FIELDS}, trip_id=trip.id)
        serializer = TripLodgingSerializer(data=payload, context=context)
        serializer.is_valid(raise_exception=True)
        suggestion.lodging = serializer.save(user=request.user)
    else:
        to_ideas = bool(fields.get('to_ideas')) or ('day_id' in fields and fields.get('day_id') is None)
        payload.update({k: v for k, v in fields.items() if k in STOP_FIELDS})
        payload['trip_id'] = trip.id
        if to_ideas:
            payload['day_id'] = None
            payload['start_time'] = None
            if 'status' not in fields:
                payload['status'] = TripStop.STATUS_OPTION
            leg_id = _int(payload.get('leg_id'))
            if leg_id is not None:
                leg = TripLeg.objects.filter(pk=leg_id, trip=trip, user=request.user).first()
                payload['leg_id'] = leg.id if leg else None
            else:
                # If the suggestion targeted a day that belongs to a leg, inherit that leg.
                orig_day = TripDay.objects.filter(pk=_int(data.get('day_id')), trip=trip, user=request.user).first()
                payload['leg_id'] = orig_day.leg_id if orig_day and orig_day.leg_id else None
            serializer = TripStopSerializer(data=payload, context=context)
            serializer.is_valid(raise_exception=True)
            last = TripStop.objects.filter(trip=trip, day__isnull=True).aggregate(m=Max('sort_order'))['m']
            stop = serializer.save(
                user=request.user,
                sort_order=0 if last is None else last + 1,
                extra={'ai_suggestion_id': suggestion.id},
            )
        else:
            day = TripDay.objects.filter(pk=_int(payload['day_id']), trip=trip, user=request.user).first()
            if day is None:
                raise ValidationError({'day_id': 'Choose a day on this trip.'})
            payload['day_id'] = day.id
            serializer = TripStopSerializer(data=payload, context=context)
            serializer.is_valid(raise_exception=True)
            last = day.stops.aggregate(m=Max('sort_order'))['m']
            stop = serializer.save(
                user=request.user,
                sort_order=0 if last is None else last + 1,
                extra={'ai_suggestion_id': suggestion.id},
            )
        if data.get('url'):
            TripStopAttachment.objects.create(
                user=request.user, stop=stop, kind=TripStopAttachment.KIND_URL, title='Website', url=data['url'],
            )
        location = TripStopAttachment(
            user=request.user, stop=stop, kind=TripStopAttachment.KIND_LOCATION, title='Map',
            address=map_query(data)[:500], sort_order=1,
        )
        location.fill_map_urls()
        location.save()
        suggestion.stop = stop

    suggestion.status = TripSuggestion.STATUS_ADDED
    suggestion.save(update_fields=['status', 'stop', 'lodging', 'modified_on'])
    return suggestion
