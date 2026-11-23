"""Which time zone each day and item is in.

The zone runs through the trip in itinerary order: it starts at the trip's zone, a day may
set its own, and each travel item switches it to the travel's arrival zone for everything
after it. An item's own zone overrides only that item. Mirrored in the frontend's
`resolveTripZones`; keep the two in step.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo, available_timezones

from .models import TripStop


@lru_cache(maxsize=1)
def _zones():
    return frozenset(available_timezones())


def is_zone(name):
    return name in _zones()


@dataclass
class StopZone:
    zone: str | None
    arrive_zone: str | None = None
    arrive_time: object = None
    arrive_day_offset: int = 0
    after_overnight: bool = False


@dataclass
class DayZones:
    zones: list = field(default_factory=list)
    stops: dict = field(default_factory=dict)


def arrival(day_date, stop, zone, arrive_zone):
    """Arrival wall time in `arrive_zone` and its day offset from `day_date`, or (None, 0)."""
    if stop.start_time is None or not stop.duration_minutes:
        return None, 0
    if zone and arrive_zone:
        start = datetime.combine(day_date, stop.start_time, tzinfo=ZoneInfo(zone))
        end = (start + timedelta(minutes=stop.duration_minutes)).astimezone(ZoneInfo(arrive_zone))
    else:
        end = datetime.combine(day_date, stop.start_time) + timedelta(minutes=stop.duration_minutes)
    return end.time().replace(tzinfo=None), (end.date() - day_date).days


def resolve(trip, days, stops_by_day):
    """{day_id: DayZones} for days in date order; stops_by_day lists each day's stops in order."""
    zone = trip.timezone or None
    out = {}
    for day in days:
        if day.timezone:
            zone = day.timezone
        info = DayZones(zones=[zone])
        overnight = False
        for stop in stops_by_day.get(day.id, []):
            own = stop.timezone or zone
            item = StopZone(zone=own, after_overnight=overnight)
            if stop.kind == TripStop.KIND_TRAVEL:
                item.arrive_zone = stop.arrive_timezone or own
                item.arrive_time, item.arrive_day_offset = arrival(day.date, stop, own, item.arrive_zone)
                overnight = overnight or item.arrive_day_offset > 0
                zone = item.arrive_zone
            for z in (own, item.arrive_zone):
                if z and z not in info.zones:
                    info.zones.append(z)
            info.stops[stop.id] = item
        info.zones = [z for z in info.zones if z] or [None]
        out[day.id] = info
    return out


# Same names the frontend's zoneAbbr shows: US abbreviations (what browsers print in en-US),
# a few well-known ones, otherwise GMT±offset.
_US_NAMES = {
    'PST', 'PDT', 'MST', 'MDT', 'CST', 'CDT', 'EST', 'EDT', 'AKST', 'AKDT', 'HST', 'HDT', 'AST', 'ADT',
}
_KNOWN_ZONES = {
    'Europe/London', 'Europe/Dublin', 'Asia/Kolkata', 'Asia/Tokyo', 'Asia/Seoul', 'Asia/Shanghai',
    'Asia/Hong_Kong', 'Europe/Paris', 'Europe/Berlin', 'Europe/Rome', 'Europe/Madrid', 'Europe/Amsterdam',
    'Australia/Sydney', 'Australia/Melbourne', 'Pacific/Auckland',
}


def abbreviation(zone, on_date):
    """'PST', 'GMT', 'JST', or 'GMT+7' / 'GMT+5:30'."""
    if not zone:
        return ''
    when = datetime.combine(on_date or date.today(), datetime.min.time().replace(hour=12), tzinfo=ZoneInfo(zone))
    name = when.tzname() or ''
    if (name in _US_NAMES and zone.startswith(('America/', 'US/', 'Pacific/Honolulu'))) or zone in _KNOWN_ZONES:
        return name
    minutes = int(when.utcoffset().total_seconds() // 60)
    if minutes == 0:
        return 'GMT'
    sign = '-' if minutes < 0 else '+'
    h, m = divmod(abs(minutes), 60)
    return f'GMT{sign}{h}' + (f':{m:02d}' if m else '')
