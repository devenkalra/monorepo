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
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.dateparse import parse_date, parse_datetime, parse_time

from gallery.models import Gallery, UserMedia
from vacation_list.models import VacList

from .models import (
    Trip,
    TripComment,
    TripDay,
    TripLeg,
    TripLodging,
    TripMedia,
    TripShare,
    TripStop,
    TripStopAttachment,
    TripTodo,
)

FORMAT_VERSION = 2

_LIST_MARKER = re.compile(r'^(?:[-*+]|\d+[.)])(?:\s+|$)(?:\[[ xX]\](?:\s+|$))?')

_VALID_STOP_STATUSES = {c[0] for c in TripStop.STATUS_CHOICES}
_LEGACY_STOP_STATUSES = {
    'planned': TripStop.STATUS_NO_BOOKING,
    'tentative': TripStop.STATUS_OPTION,
}
_VALID_LODGING_STATUSES = {c[0] for c in TripLodging.STATUS_CHOICES}
_VALID_SHARE_ROLES = {c[0] for c in TripShare.ROLE_CHOICES}


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


def _normalize_stop_status(value):
    if value in _VALID_STOP_STATUSES:
        return value
    if value in _LEGACY_STOP_STATUSES:
        return _LEGACY_STOP_STATUSES[value]
    return TripStop.STATUS_NO_BOOKING


def _normalize_lodging_status(value, confirmation=''):
    if value in _VALID_LODGING_STATUSES:
        return value
    if value in _LEGACY_STOP_STATUSES:
        return _LEGACY_STOP_STATUSES[value]
    return TripLodging.STATUS_CONFIRMED if confirmation else TripLodging.STATUS_TOBOOK


# ---------------------------------------------------------------- export

def export_trip(trip, *, include_sharing=True):
    packing = trip.packing_list
    gallery = trip.gallery
    out = {
        'pk': trip.pk,
        'title': trip.title,
        'description': trip.description,
        'notes': trip.notes,
        'timezone': trip.timezone,
        'start_date': _iso(trip.start_date),
        'end_date': _iso(trip.end_date),
        'packing_list_name': packing.name if packing else None,
        'gallery_slug': gallery.slug if gallery else None,
        'public_enabled': bool(trip.public_enabled) if include_sharing else False,
        'share_token': (trip.share_token or '') if include_sharing else '',
        'created_at': _iso(trip.created_at),
        'modified_on': _iso(trip.modified_on),
        'legs': [_export_leg(row) for row in trip.legs.all()],
        'lodgings': [_export_lodging(row) for row in trip.lodgings.all()],
        'days': [_export_day(day) for day in trip.days.all()],
        'ideas': [_export_stop(stop) for stop in trip.stops.filter(day__isnull=True).order_by('sort_order', 'id')],
        'media': [_export_media(row) for row in trip.media.select_related('asset').filter(day=None, stop=None)],
        'todos': [_export_todo(row) for row in trip.todos.all()],
        'shares': [_export_share(row) for row in trip.shares.all()] if include_sharing else [],
        'comments': [
            _export_comment(row)
            for row in trip.comments.select_related('author', 'resolved_by').order_by('created_at', 'id')
        ],
    }
    return out


def _export_share(row):
    return {
        'email': row.email,
        'role': row.role,
        'created_at': _iso(row.created_at),
        'modified_on': _iso(row.modified_on),
    }


def _export_comment(row):
    return {
        'pk': row.pk,
        'parent_pk': row.parent_id,
        'leg_pk': row.leg_id,
        'day_pk': row.day_id,
        'stop_pk': row.stop_id,
        'lodging_pk': row.lodging_id,
        'body': row.body,
        'author_email': (getattr(row.author, 'email', '') or '').strip().lower() if row.author_id else '',
        'resolved': bool(row.resolved),
        'resolved_at': _iso(row.resolved_at),
        'resolved_by_email': (getattr(row.resolved_by, 'email', '') or '').strip().lower() if row.resolved_by_id else '',
        'created_at': _iso(row.created_at),
        'modified_on': _iso(row.modified_on),
    }


def _export_todo(row):
    return {
        'text': row.text,
        'category': row.category,
        'done': row.done,
        'sort_order': row.sort_order,
        'day_pk': row.day_id,
        'stop_pk': row.stop_id,
        'created_at': _iso(row.created_at),
        'modified_on': _iso(row.modified_on),
    }


def _export_leg(row):
    return {
        'pk': row.pk,
        'name': row.name,
        'location': row.location,
        'timezone': row.timezone,
        'notes': row.notes,
        'sort_order': row.sort_order,
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
        'status': row.status,
        'price': str(row.price) if row.price is not None else None,
        'currency': row.currency,
        'person': row.person,
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
        'timezone': day.timezone,
        'lodging_pk': day.lodging_id,
        'leg_pk': day.leg_id,
        'sort_order': day.sort_order,
        'created_at': _iso(day.created_at),
        'modified_on': _iso(day.modified_on),
        'stops': [_export_stop(stop) for stop in day.stops.all()],
        'media': [_export_media(row) for row in day.media.select_related('asset').filter(stop=None)],
    }


def _export_stop(stop):
    return {
        'pk': stop.pk,
        'leg_pk': stop.leg_id,
        'text': stop.text,
        'kind': stop.kind,
        'travel_mode': stop.travel_mode,
        'description': stop.description,
        'loc': stop.loc,
        'arrive_loc': stop.arrive_loc,
        'cat': stop.cat,
        'price': str(stop.price) if stop.price is not None else None,
        'currency': stop.currency,
        'person': stop.person,
        'confirmation': stop.confirmation,
        'status': stop.status,
        'done': stop.done,
        'start_time': _iso(stop.start_time),
        'duration_minutes': stop.duration_minutes,
        'timezone': stop.timezone,
        'arrive_timezone': stop.arrive_timezone,
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
        yield from trip.get('media') or []
        for lodging in trip.get('lodgings') or []:
            yield from lodging.get('attachments') or []
        for day in trip.get('days') or []:
            yield from day.get('media') or []
            for stop in day.get('stops') or []:
                yield from stop.get('attachments') or []
                yield from stop.get('media') or []
        for idea in trip.get('ideas') or []:
            yield from idea.get('attachments') or []
            yield from idea.get('media') or []

    for trip in trips:
        for row in rows(trip):
            note(row.get('asset_url'), row.get('asset_filename'))
            note(row.get('url'))
    return refs


def export_zip(trips, *, include_sharing=True):
    """Zip of trip.json plus every referenced uploaded file under files/."""
    data = [export_trip(t, include_sharing=include_sharing) for t in trips]
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
    counts = {
        'trips': 0,
        'legs': 0,
        'lodgings': 0,
        'days': 0,
        'stops': 0,
        'attachments': 0,
        'media': 0,
        'todos': 0,
        'shares': 0,
        'comments': 0,
        'files': 0,
    }
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
        self._user_cache = {}

    def _url(self, url):
        return self.urls.get(url, url or '')

    def _asset(self, url):
        if not url:
            return None
        return UserMedia.objects.filter(owner=self.user, url=self._url(url)).first()

    def _user_by_email(self, email):
        cleaned = (email or '').strip().lower()
        if not cleaned:
            return None
        if cleaned not in self._user_cache:
            User = get_user_model()
            self._user_cache[cleaned] = User.objects.filter(email__iexact=cleaned).first()
        return self._user_cache[cleaned]

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

    def _stop(self, stop_data, *, trip, day, leg):
        stop = TripStop.objects.create(
            user=self.user,
            trip=trip,
            day=day,
            leg=leg,
            text=stop_data['text'],
            kind=stop_data.get('kind') or TripStop.KIND_ACTIVITY,
            travel_mode=stop_data.get('travel_mode') or '',
            description=stop_data.get('description') or '',
            loc=stop_data.get('loc') or '',
            arrive_loc=stop_data.get('arrive_loc') or '',
            cat=stop_data.get('cat') or '',
            price=_decimal(stop_data.get('price')),
            currency=stop_data.get('currency') or '',
            person=stop_data.get('person') or '',
            confirmation=stop_data.get('confirmation') or '',
            status=_normalize_stop_status(stop_data.get('status')),
            done=bool(stop_data.get('done', False)),
            start_time=_time(stop_data.get('start_time')),
            duration_minutes=stop_data.get('duration_minutes'),
            timezone=stop_data.get('timezone') or '',
            arrive_timezone=stop_data.get('arrive_timezone') or '',
            extra=stop_data.get('extra') or {},
            sort_order=stop_data.get('sort_order') or 0,
        )
        self._stamp(TripStop, stop.pk, stop_data)
        self.counts['stops'] += 1
        for att in stop_data.get('attachments') or []:
            self._attachment(att, stop=stop)
        return stop

    def trip(self, data):
        user = self.user
        packing_name = data.get('packing_list_name')
        gallery_slug = data.get('gallery_slug')
        public_enabled = bool(data.get('public_enabled', False))
        raw_token = (data.get('share_token') or '').strip()
        share_token = None
        if raw_token and not Trip.objects.filter(share_token=raw_token).exists():
            share_token = raw_token

        trip = Trip.objects.create(
            user=user,
            title=data['title'],
            description=data.get('description') or '',
            notes=data.get('notes') or '',
            timezone=data.get('timezone') or '',
            start_date=_date(data.get('start_date')),
            end_date=_date(data.get('end_date')),
            packing_list=VacList.objects.filter(user=user, name=packing_name).first() if packing_name else None,
            gallery=Gallery.objects.filter(owner=user, slug=gallery_slug).first() if gallery_slug else None,
            public_enabled=public_enabled,
            share_token=share_token,
        )
        if public_enabled and not trip.share_token:
            trip.ensure_share_token()
            trip.save(update_fields=['share_token'])
        self._stamp(Trip, trip.pk, data)
        self.counts['trips'] += 1

        leg_map = {}
        for row in data.get('legs') or []:
            leg = TripLeg.objects.create(
                user=user,
                trip=trip,
                name=row['name'],
                location=row.get('location') or '',
                timezone=row.get('timezone') or '',
                notes=row.get('notes') or '',
                sort_order=row.get('sort_order') or 0,
            )
            self._stamp(TripLeg, leg.pk, row)
            leg_map[row['pk']] = leg
            self.counts['legs'] += 1

        lodging_map = {}
        for row in data.get('lodgings') or []:
            confirmation = row.get('confirmation') or ''
            lodging = TripLodging.objects.create(
                user=user,
                trip=trip,
                name=row['name'],
                address=row.get('address') or '',
                phone=row.get('phone') or '',
                url=row.get('url') or '',
                confirmation=confirmation,
                status=_normalize_lodging_status(row.get('status'), confirmation),
                price=_decimal(row.get('price')),
                currency=row.get('currency') or '',
                person=row.get('person') or '',
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
                timezone=day_data.get('timezone') or '',
                lodging=lodging_map.get(day_data.get('lodging_pk')),
                leg=leg_map.get(day_data.get('leg_pk')),
                sort_order=day_data.get('sort_order') or 0,
            )
            self._stamp(TripDay, day.pk, day_data)
            day_map[day_data['pk']] = day
            self.counts['days'] += 1
            pending_media.extend(day_data.get('media') or [])

            for stop_data in day_data.get('stops') or []:
                stop = self._stop(stop_data, trip=trip, day=day, leg=leg_map.get(stop_data.get('leg_pk')))
                stop_map[stop_data['pk']] = stop
                pending_media.extend(stop_data.get('media') or [])

        for stop_data in data.get('ideas') or []:
            stop = self._stop(stop_data, trip=trip, day=None, leg=leg_map.get(stop_data.get('leg_pk')))
            stop_map[stop_data['pk']] = stop
            pending_media.extend(stop_data.get('media') or [])

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
                category=(row.get('category') or '')[:60],
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

        owner_email = (getattr(user, 'email', '') or '').strip().lower()
        for row in data.get('shares') or []:
            email = (row.get('email') or '').strip().lower()
            if not email or (owner_email and email == owner_email):
                continue
            role = row.get('role') if row.get('role') in _VALID_SHARE_ROLES else TripShare.ROLE_VIEWER
            share, created = TripShare.objects.get_or_create(
                trip=trip,
                email=email,
                defaults={
                    'user': self._user_by_email(email),
                    'role': role,
                    'invited_by': user,
                },
            )
            if created:
                self._stamp(TripShare, share.pk, row)
                self.counts['shares'] += 1

        raw_comments = list(data.get('comments') or [])
        roots = [c for c in raw_comments if not c.get('parent_pk')]
        replies = [c for c in raw_comments if c.get('parent_pk')]
        comment_map = {}
        for row in roots + replies:
            body = (row.get('body') or '').strip()
            if not body:
                continue
            parent = comment_map.get(row.get('parent_pk'))
            author = self._user_by_email(row.get('author_email')) or user
            resolved = bool(row.get('resolved', False))
            resolved_at = _dt(row.get('resolved_at')) if resolved else None
            resolved_by = (self._user_by_email(row.get('resolved_by_email')) or user) if resolved else None
            if parent is not None:
                leg, day, stop, lodging = parent.leg, parent.day, parent.stop, parent.lodging
            else:
                leg = leg_map.get(row.get('leg_pk'))
                day = day_map.get(row.get('day_pk'))
                stop = stop_map.get(row.get('stop_pk'))
                lodging = lodging_map.get(row.get('lodging_pk'))
            comment = TripComment.objects.create(
                trip=trip,
                author=author,
                parent=parent,
                leg=leg,
                day=day,
                stop=stop,
                lodging=lodging,
                body=body,
                resolved=resolved,
                resolved_at=resolved_at,
                resolved_by=resolved_by,
            )
            self._stamp(TripComment, comment.pk, row)
            if row.get('pk') is not None:
                comment_map[row['pk']] = comment
            self.counts['comments'] += 1

        return trip
