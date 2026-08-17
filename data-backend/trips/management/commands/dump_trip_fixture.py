import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from trips.models import Trip, TripDay, TripLodging, TripMedia, TripStop, TripStopAttachment


def _iso(value):
    return value.isoformat() if value else None


class Command(BaseCommand):
    help = 'Dump trips owned by one user as JSON for import_trip_fixture.'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True, help='Owner email to dump')
        parser.add_argument('-o', '--output', default='-', help='Output path, or - for stdout')

    def handle(self, *args, **options):
        User = get_user_model()
        email = options['email']
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist as exc:
            raise CommandError(f'No user with email {email}') from exc

        trips = []
        for trip in Trip.objects.filter(user=user).select_related('packing_list', 'gallery'):
            trips.append(self._trip(trip))

        payload = {
            'email': user.email,
            'trips': trips,
        }
        text = json.dumps(payload, indent=2, default=str)
        dest = options['output']
        if dest in ('', '-'):
            self.stdout.write(text)
        else:
            with open(dest, 'w', encoding='utf-8') as fh:
                fh.write(text)
            self.stdout.write(self.style.SUCCESS(
                f'Wrote {len(trips)} trip(s) for {user.email} to {dest}'
            ))

    def _trip(self, trip):
        packing = trip.packing_list
        gallery = trip.gallery
        return {
            'pk': trip.pk,
            'title': trip.title,
            'start_date': _iso(trip.start_date),
            'end_date': _iso(trip.end_date),
            'packing_list_name': packing.name if packing else None,
            'gallery_slug': gallery.slug if gallery else None,
            'created_at': _iso(trip.created_at),
            'modified_on': _iso(trip.modified_on),
            'lodgings': [self._lodging(row) for row in trip.lodgings.all()],
            'days': [self._day(day) for day in trip.days.all()],
            'media': [self._media(row) for row in trip.media.select_related('asset', 'day', 'stop')],
        }

    def _lodging(self, row):
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
            'attachments': [self._attachment(item) for item in row.attachments.select_related('asset')],
        }

    def _day(self, day):
        return {
            'pk': day.pk,
            'date': _iso(day.date),
            'title': day.title,
            'journal': day.journal,
            'lodging_pk': day.lodging_id,
            'sort_order': day.sort_order,
            'created_at': _iso(day.created_at),
            'modified_on': _iso(day.modified_on),
            'stops': [self._stop(stop) for stop in day.stops.all()],
            'media': [self._media(row) for row in day.media.select_related('asset', 'stop')],
        }

    def _stop(self, stop):
        return {
            'pk': stop.pk,
            'text': stop.text,
            'description': stop.description,
            'loc': stop.loc,
            'cat': stop.cat,
            'status': stop.status,
            'done': stop.done,
            'start_time': _iso(stop.start_time),
            'duration_minutes': stop.duration_minutes,
            'extra': stop.extra or {},
            'sort_order': stop.sort_order,
            'created_at': _iso(stop.created_at),
            'modified_on': _iso(stop.modified_on),
            'attachments': [self._attachment(row) for row in stop.attachments.select_related('asset')],
            'media': [self._media(row) for row in stop.media.select_related('asset')],
        }

    def _attachment(self, row):
        return {
            'kind': row.kind,
            'title': row.title,
            'url': row.url,
            'osm_url': row.osm_url,
            'address': row.address,
            'lat': str(row.lat) if row.lat is not None else None,
            'lng': str(row.lng) if row.lng is not None else None,
            'asset_url': row.asset.url if row.asset_id else None,
            'sort_order': row.sort_order,
            'created_at': _iso(row.created_at),
            'modified_on': _iso(row.modified_on),
        }

    def _media(self, row):
        return {
            'caption': row.caption,
            'sort_order': row.sort_order,
            'asset_url': row.asset.url if row.asset_id else None,
            'day_pk': row.day_id,
            'stop_pk': row.stop_id,
            'created_at': _iso(row.created_at),
            'modified_on': _iso(row.modified_on),
        }
