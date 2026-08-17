import json
import sys
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_date, parse_datetime, parse_time

from gallery.models import Gallery, UserMedia
from trips.models import Trip, TripDay, TripLodging, TripMedia, TripStop, TripStopAttachment
from vacation_list.models import VacList


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


class Command(BaseCommand):
    help = (
        'Import a trip fixture and assign every row to one user. '
        'Primary keys are remapped so existing production rows are not overwritten.'
    )

    def add_arguments(self, parser):
        parser.add_argument('fixture', help='Path to trip JSON (use - for stdin)')
        parser.add_argument('--email', required=True, help='Production owner email')
        parser.add_argument(
            '--replace',
            action='store_true',
            help="Delete this user's existing trips before import",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        email = options['email']
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist as exc:
            raise CommandError(f'No user with email {email}') from exc

        path = options['fixture']
        if path == '-':
            raw = sys.stdin.read()
        else:
            with open(path, encoding='utf-8') as fh:
                raw = fh.read()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CommandError(f'Invalid JSON fixture: {exc}') from exc
        if isinstance(payload, list):
            raise CommandError('Fixture must be an object with a "trips" list')
        trips = payload.get('trips')
        if not isinstance(trips, list):
            raise CommandError('Fixture must contain a "trips" list')

        with transaction.atomic():
            if options['replace']:
                deleted = Trip.objects.filter(user=user).delete()[0]
                self.stdout.write(f'Removed {deleted} existing trip row(s) for {user.email}')

            counts = {'trips': 0, 'lodgings': 0, 'days': 0, 'stops': 0, 'attachments': 0, 'media': 0}
            for trip_data in trips:
                self._import_trip(user, trip_data, counts)

        self.stdout.write(self.style.SUCCESS(
            f'Imported for {user.email}: '
            f'{counts["trips"]} trips, {counts["lodgings"]} lodgings, '
            f'{counts["days"]} days, {counts["stops"]} stops, '
            f'{counts["attachments"]} attachments, {counts["media"]} media'
        ))

    def _stamp(self, model, pk, data):
        updates = {}
        created = _dt(data.get('created_at'))
        modified = _dt(data.get('modified_on'))
        if created:
            updates['created_at'] = created
        if modified:
            updates['modified_on'] = modified
        if updates:
            model.objects.filter(pk=pk).update(**updates)

    def _packing_list(self, user, name):
        if not name:
            return None
        return VacList.objects.filter(user=user, name=name).first()

    def _gallery(self, user, slug):
        if not slug:
            return None
        return Gallery.objects.filter(owner=user, slug=slug).first()

    def _asset(self, user, url):
        if not url:
            return None
        return UserMedia.objects.filter(owner=user, url=url).first()

    def _import_trip(self, user, data, counts):
        trip = Trip.objects.create(
            user=user,
            title=data['title'],
            start_date=_date(data.get('start_date')),
            end_date=_date(data.get('end_date')),
            packing_list=self._packing_list(user, data.get('packing_list_name')),
            gallery=self._gallery(user, data.get('gallery_slug')),
        )
        self._stamp(Trip, trip.pk, data)
        counts['trips'] += 1

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
            counts['lodgings'] += 1
            for att in row.get('attachments') or []:
                obj = TripStopAttachment.objects.create(
                    user=user,
                    lodging=lodging,
                    kind=att['kind'],
                    title=att.get('title') or '',
                    url=att.get('url') or '',
                    osm_url=att.get('osm_url') or '',
                    address=att.get('address') or '',
                    lat=_decimal(att.get('lat')),
                    lng=_decimal(att.get('lng')),
                    asset=self._asset(user, att.get('asset_url')),
                    sort_order=att.get('sort_order') or 0,
                )
                self._stamp(TripStopAttachment, obj.pk, att)
                counts['attachments'] += 1

        day_map = {}
        stop_map = {}
        pending_media = list(data.get('media') or [])
        for day_data in data.get('days') or []:
            day = TripDay.objects.create(
                user=user,
                trip=trip,
                date=_date(day_data['date']),
                title=day_data.get('title') or '',
                journal=day_data.get('journal') or '',
                lodging=lodging_map.get(day_data.get('lodging_pk')),
                sort_order=day_data.get('sort_order') or 0,
            )
            self._stamp(TripDay, day.pk, day_data)
            day_map[day_data['pk']] = day
            counts['days'] += 1
            pending_media.extend(day_data.get('media') or [])

            for stop_data in day_data.get('stops') or []:
                stop = TripStop.objects.create(
                    user=user,
                    day=day,
                    text=stop_data['text'],
                    description=stop_data.get('description') or '',
                    loc=stop_data.get('loc') or '',
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
                counts['stops'] += 1
                pending_media.extend(stop_data.get('media') or [])

                for att in stop_data.get('attachments') or []:
                    obj = TripStopAttachment.objects.create(
                        user=user,
                        stop=stop,
                        kind=att['kind'],
                        title=att.get('title') or '',
                        url=att.get('url') or '',
                        osm_url=att.get('osm_url') or '',
                        address=att.get('address') or '',
                        lat=_decimal(att.get('lat')),
                        lng=_decimal(att.get('lng')),
                        asset=self._asset(user, att.get('asset_url')),
                        sort_order=att.get('sort_order') or 0,
                    )
                    self._stamp(TripStopAttachment, obj.pk, att)
                    counts['attachments'] += 1

        for row in pending_media:
            asset = self._asset(user, row.get('asset_url'))
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
            counts['media'] += 1
