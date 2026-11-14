"""Trip export/import: JSON rows plus the uploaded files they reference, bundled as a zip.

Primary keys are remapped on import so existing rows on the target server are never overwritten.
"""
import io
import json
import re
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.dateparse import parse_date, parse_datetime, parse_time

from gallery.models import Gallery, UserMedia
from vacation_list.models import VacList

from .models import Trip, TripDay, TripLodging, TripMedia, TripStop, TripStopAttachment, TripTodo

FORMAT_VERSION = 1

_LIST_MARKER = re.compile(r'^(?:[-*+]|\d+[.)])(?:\s+|$)(?:\[[ xX]\](?:\s+|$))?')


def open_items_to_todos(text):
    """One to-do per non-blank line of the retired markdown open-items field."""
    lines = (_LIST_MARKER.sub('', line.strip()).strip() for line in text.splitlines())
    return [line for line in lines if line]


class TransferError(ValueError):
    pass


def _iso(value):
    return value.isoformat() if value else None


def _dt(value):
    if not value:
        return None
    if isinstance(value, str) and value.endswith('Z'):
        value = value[:-1] + '+00:00'
    return parse_datetime(value)


def _date(value):
    return parse_date(value) if value else None


def _time(value):
    return parse_time(value) if value else None


def _decimal(value):
    if value in (None, ''):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None


# ---------------------------------------------------------------- export

def export_trip(trip):
    packing = trip.packing_list
    gallery = trip.gallery
    return {
        'pk': trip.pk,
        'title': trip.title,
        'description': trip.description,
        'notes': trip.notes,
        'start_date': _iso(trip.start_date),
        'end_date': _iso(trip.end_date),
        'packing_list_name': packing.name if packing else None,
        'gallery_slug': gallery.slug if gallery else None,
        'created_at': _iso(trip.created_at),
        'modified_on': _iso(trip.modified_on),
        'lodgings': [_export_lodging(row) for row in trip.lodgings.all()],
        'days': [_export_day(day) for day in trip.days.all()],
        'media': [_export_media(row) for row in trip.media.select_related('asset').filter(day=None, stop=None)],
        'todos': [_export_todo(row) for row in trip.todos.all()],
    }


def _export_todo(row):
    return {
        'text': row.text,
        'done': row.done,
        'sort_order': row.sort_order,
        'day_pk': row.day_id,
        'stop_pk': row.stop_id,
        'created_at': _iso(row.created_at),
        'modified_on': _iso(row.modified_on),
    }


def _export_lodging(row):
    return {
        'pk': row.pk,
        'name': row.name,
        'address': row.address,
        'phone': row.phone,
        'url': row.url,
        'confirmation': row.confirmation,
        'notes': row.notes,
        'check_in_time': _iso(row.check_in_time),
        'check_out_time': _iso(row.check_out_time),
        'created_at': _iso(row.created_at),
        'modified_on': _iso(row.modified_on),
        'attachments': [_export_attachment(item) for item in row.attachments.select_related('asset')],
    }


def _export_day(day):
    return {
        'pk': day.pk,
        'date': _iso(day.date),
        'title': day.title,
        'notes': day.notes,
        'journal': day.journal,
        'lodging_pk': day.lodging_id,
        'sort_order': day.sort_order,
        'created_at': _iso(day.created_at),
        'modified_on': _iso(day.modified_on),
        'stops': [_export_stop(stop) for stop in day.stops.all()],
        'media': [_export_media(row) for row in day.media.select_related('asset').filter(stop=None)],
    }


def _export_stop(stop):
    return {
        'pk': stop.pk,
        'text': stop.text,
        'kind': stop.kind,
        'travel_mode': stop.travel_mode,
        'description': stop.description,
        'loc': stop.loc,
        'arrive_loc': stop.arrive_loc,
        'cat': stop.cat,
        'status': stop.status,
        'done': stop.done,
        'start_time': _iso(stop.start_time),
        'duration_minutes': stop.duration_minutes,
        'extra': stop.extra or {},
        'sort_order': stop.sort_order,
        'created_at': _iso(stop.created_at),
        'modified_on': _iso(stop.modified_on),
        'attachments': [_export_attachment(row) for row in stop.attachments.select_related('asset')],
        'media': [_export_media(row) for row in stop.media.select_related('asset')],
    }


def _export_attachment(row):
    return {
        'kind': row.kind,
        'title': row.title,
        'url': row.url,
        'osm_url': row.osm_url,
        'address': row.address,
        'lat': str(row.lat) if row.lat is not None else None,
        'lng': str(row.lng) if row.lng is not None else None,
        'asset_url': row.asset.url if row.asset_id else None,
        'asset_filename': row.asset.filename if row.asset_id else None,
        'sort_order': row.sort_order,
        'created_at': _iso(row.created_at),
        'modified_on': _iso(row.modified_on),
    }


def _export_media(row):
    return {
        'caption': row.caption,
        'sort_order': row.sort_order,
        'asset_url': row.asset.url if row.asset_id else None,
        'asset_filename': row.asset.filename if row.asset_id else None,
        'day_pk': row.day_id,
        'stop_pk': row.stop_id,
        'created_at': _iso(row.created_at),
        'modified_on': _iso(row.modified_on),
    }


def _media_path(url):
    """Local file behind a /media/ URL, or None for external or missing files."""
    prefix = settings.MEDIA_URL
    if not url or not url.startswith(prefix):
        return None
    root = Path(settings.MEDIA_ROOT).resolve()
    path = (root / url[len(prefix):]).resolve()
    if root not in path.parents or not path.is_file():
        return None
    return path


def _file_refs(trips):
    """Every /media/ URL the exported rows point at, with the best known original filename."""
    refs = {}

    def note(url, filename=None):
        if url and url.startswith(settings.MEDIA_URL) and (url not in refs or filename):
            refs[url] = filename or refs.get(url) or Path(url).name

    def rows(trip):
        yield from trip['media']
        for lodging in trip['lodgings']:
            yield from lodging['attachments']
        for day in trip['days']:
            yield from day['media']
            for stop in day['stops']:
                yield from stop['attachments']
                yield from stop['media']

    for trip in trips:
        for row in rows(trip):
            note(row.get('asset_url'), row.get('asset_filename'))
            note(row.get('url'))
    return refs


def export_zip(trips):
    """Zip of trip.json plus every referenced uploaded file under files/."""
    data = [export_trip(t) for t in trips]
    files = {}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for i, (url, filename) in enumerate(sorted(_file_refs(data).items())):
            path = _media_path(url)
            if not path:
                continue
            name = f'files/{i:04d}{path.suffix}'
            zf.write(path, name)
            files[url] = {'path': name, 'filename': filename}
        payload = {'version': FORMAT_VERSION, 'trips': data, 'files': files}
        zf.writestr('trip.json', json.dumps(payload, indent=2, default=str))
    return buf.getvalue()


def export_filename(trips):
    if len(trips) == 1:
        stem = ''.join(c if c.isalnum() else '-' for c in trips[0].title).strip('-').lower() or 'trip'
    else:
        stem = 'trips'
    return f'{stem}-export.zip'


# ---------------------------------------------------------------- import

def read_bundle(uploaded):
    """(payload, file loader) from an export zip or a bare JSON fixture."""
    raw = uploaded.read()
    if zipfile.is_zipfile(io.BytesIO(raw)):
        zf = zipfile.ZipFile(io.BytesIO(raw))
        try:
            payload = json.loads(zf.read('trip.json'))
        except KeyError as exc:
            raise TransferError('Zip has no trip.json.') from exc
        except json.JSONDecodeError as exc:
            raise TransferError(f'trip.json is not valid JSON: {exc}') from exc
        names = set(zf.namelist())
        return payload, (lambda name: zf.read(name) if name in names else None)
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise TransferError('Expected a trip export .zip or .json file.') from exc
    return payload, (lambda name: None)


def import_payload(user, payload, load_file=lambda name: None, replace=False):
    """Create the trips in payload for user. Returns (trips, counts)."""
    if not isinstance(payload, dict) or not isinstance(payload.get('trips'), list):
        raise TransferError('Export must contain a "trips" list.')
    counts = {'trips': 0, 'lodgings': 0, 'days': 0, 'stops': 0, 'attachments': 0, 'media': 0, 'todos': 0, 'files': 0}
    with transaction.atomic():
        if replace:
            Trip.objects.filter(user=user).delete()
        urls = _import_files(user, payload.get('files') or {}, load_file, counts)
        trips = [_Importer(user, urls, counts).trip(data) for data in payload['trips']]
    return trips, counts


def _import_files(user, files, load_file, counts):
    from gallery.views import _register_user_media
    from people.utils import save_file_deduplicated

    urls = {}
    for old_url, info in files.items():
        content = load_file(info.get('path') or '')
        if content is None:
            continue
        filename = info.get('filename') or Path(old_url).name
        saved = save_file_deduplicated(ContentFile(content, name=Path(old_url).name))
        new_url = saved['url'].replace('\\', '/')
        _register_user_media(
            user,
            url=new_url,
            thumbnail_url=(saved.get('thumbnail_url') or '').replace('\\', '/'),
            filename=filename,
            sha256=saved.get('sha256') or '',
        )
        urls[old_url] = new_url
        counts['files'] += 1
    return urls


class _Importer:
    def __init__(self, user, urls, counts):
        self.user = user
        self.urls = urls
        self.counts = counts

    def _url(self, url):
        return self.urls.get(url, url or '')

    def _asset(self, url):
        if not url:
            return None
        return UserMedia.objects.filter(owner=self.user, url=self._url(url)).first()

    @staticmethod
    def _stamp(model, pk, data):
        updates = {}
        created = _dt(data.get('created_at'))
        modified = _dt(data.get('modified_on'))
        if created:
            updates['created_at'] = created
        if modified:
            updates['modified_on'] = modified
        if updates:
            model.objects.filter(pk=pk).update(**updates)

    def _attachment(self, att, **parent):
        obj = TripStopAttachment.objects.create(
            user=self.user,
            kind=att['kind'],
            title=att.get('title') or '',
            url=self._url(att.get('url')),
            osm_url=att.get('osm_url') or '',
            address=att.get('address') or '',
            lat=_decimal(att.get('lat')),
            lng=_decimal(att.get('lng')),
            asset=self._asset(att.get('asset_url')),
            sort_order=att.get('sort_order') or 0,
            **parent,
        )
        self._stamp(TripStopAttachment, obj.pk, att)
        self.counts['attachments'] += 1

    def trip(self, data):
        user = self.user
        packing_name = data.get('packing_list_name')
        gallery_slug = data.get('gallery_slug')
        trip = Trip.objects.create(
            user=user,
            title=data['title'],
            description=data.get('description') or '',
            notes=data.get('notes') or '',
            start_date=_date(data.get('start_date')),
            end_date=_date(data.get('end_date')),
            packing_list=VacList.objects.filter(user=user, name=packing_name).first() if packing_name else None,
            gallery=Gallery.objects.filter(owner=user, slug=gallery_slug).first() if gallery_slug else None,
        )
        self._stamp(Trip, trip.pk, data)
        self.counts['trips'] += 1

        lodging_map = {}
        for row in data.get('lodgings') or []:
            lodging = TripLodging.objects.create(
                user=user,
                trip=trip,
                name=row['name'],
                address=row.get('address') or '',
                phone=row.get('phone') or '',
                url=row.get('url') or '',
                confirmation=row.get('confirmation') or '',
                notes=row.get('notes') or '',
                check_in_time=_time(row.get('check_in_time')),
                check_out_time=_time(row.get('check_out_time')),
            )
            self._stamp(TripLodging, lodging.pk, row)
            lodging_map[row['pk']] = lodging
            self.counts['lodgings'] += 1
            for att in row.get('attachments') or []:
                self._attachment(att, lodging=lodging)

        day_map = {}
        stop_map = {}
        pending_media = list(data.get('media') or [])
        for day_data in data.get('days') or []:
            day = TripDay.objects.create(
                user=user,
                trip=trip,
                date=_date(day_data['date']),
                title=day_data.get('title') or '',
                notes=day_data.get('notes') or '',
                journal=day_data.get('journal') or '',
                lodging=lodging_map.get(day_data.get('lodging_pk')),
                sort_order=day_data.get('sort_order') or 0,
            )
            self._stamp(TripDay, day.pk, day_data)
            day_map[day_data['pk']] = day
            self.counts['days'] += 1
            pending_media.extend(day_data.get('media') or [])

            for stop_data in day_data.get('stops') or []:
                stop = TripStop.objects.create(
                    user=user,
                    day=day,
                    text=stop_data['text'],
                    kind=stop_data.get('kind') or TripStop.KIND_ACTIVITY,
                    travel_mode=stop_data.get('travel_mode') or '',
                    description=stop_data.get('description') or '',
                    loc=stop_data.get('loc') or '',
                    arrive_loc=stop_data.get('arrive_loc') or '',
                    cat=stop_data.get('cat') or '',
                    status=stop_data.get('status') or TripStop.STATUS_CONFIRMED,
                    done=bool(stop_data.get('done', False)),
                    start_time=_time(stop_data.get('start_time')),
                    duration_minutes=stop_data.get('duration_minutes'),
                    extra=stop_data.get('extra') or {},
                    sort_order=stop_data.get('sort_order') or 0,
                )
                self._stamp(TripStop, stop.pk, stop_data)
                stop_map[stop_data['pk']] = stop
                self.counts['stops'] += 1
                pending_media.extend(stop_data.get('media') or [])
                for att in stop_data.get('attachments') or []:
                    self._attachment(att, stop=stop)

        for row in pending_media:
            asset = self._asset(row.get('asset_url'))
            if not asset:
                continue
            obj = TripMedia.objects.create(
                user=user,
                asset=asset,
                trip=trip,
                day=day_map.get(row.get('day_pk')),
                stop=stop_map.get(row.get('stop_pk')),
                caption=row.get('caption') or '',
                sort_order=row.get('sort_order') or 0,
            )
            self._stamp(TripMedia, obj.pk, row)
            self.counts['media'] += 1

        for row in data.get('todos') or []:
            stop = stop_map.get(row.get('stop_pk'))
            obj = TripTodo.objects.create(
                user=user,
                trip=trip,
                day=stop.day if stop else day_map.get(row.get('day_pk')),
                stop=stop,
                text=row.get('text') or '',
                done=bool(row.get('done', False)),
                sort_order=row.get('sort_order') or 0,
            )
            self._stamp(TripTodo, obj.pk, row)
            self.counts['todos'] += 1

        # Exports made before open items were folded into to-dos.
        base = len(data.get('todos') or [])
        for i, text in enumerate(open_items_to_todos(data.get('open_items') or '')):
            TripTodo.objects.create(user=user, trip=trip, text=text, sort_order=base + i)
            self.counts['todos'] += 1
        return trip
