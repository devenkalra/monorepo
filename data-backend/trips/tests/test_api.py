from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APITestCase

from gallery.models import Gallery
from trips.models import Trip, TripDay, TripLodging, TripStop, TripStopAttachment
from vacation_list.models import VacList


User = get_user_model()


class TripApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tripper', password='secret', email='trip@example.com')
        self.other = User.objects.create_user(username='other', password='secret', email='other@example.com')
        self.client.force_authenticate(self.user)

    def test_unauthenticated_rejected(self):
        self.client.force_authenticate(user=None)
        res = self.client.get('/api/trips/trips/')
        self.assertIn(res.status_code, (401, 403))

    def test_trips_are_isolated_per_user(self):
        Trip.objects.create(title='Mine', user=self.user)
        Trip.objects.create(title='Theirs', user=self.other)
        res = self.client.get('/api/trips/trips/')
        self.assertEqual([row['title'] for row in res.data], ['Mine'])
        self.client.force_authenticate(self.other)
        res = self.client.get('/api/trips/trips/')
        self.assertEqual([row['title'] for row in res.data], ['Theirs'])

    def test_cannot_fetch_other_users_trip(self):
        theirs = Trip.objects.create(title='Theirs', user=self.other)
        res = self.client.get(f'/api/trips/trips/{theirs.id}/')
        self.assertEqual(res.status_code, 404)

    def test_cannot_link_other_users_packing_list(self):
        theirs = VacList.objects.create(name='Other pack', user=self.other)
        res = self.client.post(
            '/api/trips/trips/',
            {'title': 'Trip', 'packing_list_id': theirs.id},
            format='json',
        )
        self.assertEqual(res.status_code, 400)

    def test_cannot_link_other_users_gallery(self):
        theirs = Gallery.objects.create(owner=self.other, title='G', slug='g')
        res = self.client.post(
            '/api/trips/trips/',
            {'title': 'Trip', 'gallery_id': str(theirs.id)},
            format='json',
        )
        self.assertEqual(res.status_code, 400)

    def test_seed_death_valley(self):
        res = self.client.post('/api/trips/trips/seed-death-valley/', {}, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['title'], 'Sierra & Death Valley')
        self.assertEqual(len(res.data['days']), 7)
        self.assertEqual(sum(len(d['stops']) for d in res.data['days']), 26)
        again = self.client.post('/api/trips/trips/seed-death-valley/', {}, format='json')
        self.assertEqual(again.status_code, 200)
        self.assertEqual(Trip.objects.filter(user=self.user).count(), 1)

    def test_cannot_add_day_to_other_users_trip(self):
        theirs = Trip.objects.create(title='Theirs', user=self.other)
        res = self.client.post(
            '/api/trips/days/',
            {'trip_id': theirs.id, 'date': '2026-09-01', 'title': 'Nope'},
            format='json',
        )
        self.assertEqual(res.status_code, 400)

    def test_new_day_sorts_by_date(self):
        trip = Trip.objects.create(title='Blank', user=self.user)
        self.client.post(
            '/api/trips/days/',
            {'trip_id': trip.id, 'date': '2026-10-05', 'title': 'Later'},
            format='json',
        )
        self.client.post(
            '/api/trips/days/',
            {'trip_id': trip.id, 'date': '2026-10-01', 'title': 'Earlier'},
            format='json',
        )
        res = self.client.get(f'/api/trips/trips/{trip.id}/')
        self.assertEqual([d['title'] for d in res.data['days']], ['Earlier', 'Later'])
        self.assertEqual([d['date'] for d in res.data['days']], ['2026-10-01', '2026-10-05'])

    def test_adding_day_sets_trip_dates(self):
        trip = Trip.objects.create(title='Blank', user=self.user)
        res = self.client.post(
            '/api/trips/days/',
            {'trip_id': trip.id, 'date': '2026-10-02', 'title': 'Day two'},
            format='json',
        )
        self.assertEqual(res.status_code, 201)
        trip.refresh_from_db()
        self.assertEqual(str(trip.start_date), '2026-10-02')
        self.assertEqual(str(trip.end_date), '2026-10-02')

    def test_stop_extra_and_custom_loc(self):
        trip = Trip.objects.create(title='Custom', user=self.user)
        day = TripDay.objects.create(user=self.user, trip=trip, date='2026-09-01', title='One')
        res = self.client.post(
            '/api/trips/stops/',
            {
                'day_id': day.id,
                'text': 'Custom stop',
                'description': 'Table on the patio',
                'loc': 'Panamint Springs',
                'cat': 'Food',
                'status': 'tobook',
                'extra': {'reservation': 'table for 2'},
            },
            format='json',
        )
        self.assertEqual(res.status_code, 201)
        stop = TripStop.objects.get(pk=res.data['id'])
        self.assertEqual(stop.user, self.user)
        self.assertEqual(stop.description, 'Table on the patio')
        self.assertEqual(stop.loc, 'Panamint Springs')
        self.assertEqual(stop.extra['reservation'], 'table for 2')

    def test_new_stop_appends_to_day(self):
        trip = Trip.objects.create(title='Order', user=self.user)
        day = TripDay.objects.create(user=self.user, trip=trip, date='2026-09-01', title='One')
        first = TripStop.objects.create(user=self.user, day=day, text='First', sort_order=0)
        res = self.client.post(
            '/api/trips/stops/',
            {
                'day_id': day.id,
                'text': 'Second',
                'start_time': '09:30',
                'duration_minutes': 45,
            },
            format='json',
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['sort_order'], 1)
        self.assertEqual(res.data['start_time'], '09:30:00')
        self.assertEqual(res.data['duration_minutes'], 45)
        detail = self.client.get(f'/api/trips/trips/{trip.id}/')
        self.assertEqual([s['text'] for s in detail.data['days'][0]['stops']], ['First', 'Second'])
        self.assertEqual(first.sort_order, 0)

    def test_move_stop_changes_order(self):
        trip = Trip.objects.create(title='Order', user=self.user)
        day = TripDay.objects.create(user=self.user, trip=trip, date='2026-09-01', title='One')
        a = TripStop.objects.create(user=self.user, day=day, text='A', sort_order=0)
        b = TripStop.objects.create(user=self.user, day=day, text='B', sort_order=1)
        res = self.client.post(f'/api/trips/stops/{b.id}/move/', {'direction': 'up'}, format='json')
        self.assertEqual(res.status_code, 200)
        detail = self.client.get(f'/api/trips/trips/{trip.id}/')
        self.assertEqual([s['text'] for s in detail.data['days'][0]['stops']], ['B', 'A'])
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(b.sort_order, 0)
        self.assertEqual(a.sort_order, 1)

    def test_cannot_attach_to_other_users_stop(self):
        trip = Trip.objects.create(title='Theirs', user=self.other)
        day = TripDay.objects.create(user=self.other, trip=trip, date='2026-09-01')
        stop = TripStop.objects.create(user=self.other, day=day, text='Hotel')
        res = self.client.post(
            '/api/trips/attachments/',
            {'stop_id': stop.id, 'kind': 'url', 'url': 'https://example.com', 'title': 'Nope'},
            format='json',
        )
        self.assertEqual(res.status_code, 400)

    def test_location_attachment_builds_map_links(self):
        trip = Trip.objects.create(title='Mine', user=self.user)
        day = TripDay.objects.create(user=self.user, trip=trip, date='2026-09-01')
        stop = TripStop.objects.create(user=self.user, day=day, text='Inn')
        res = self.client.post(
            '/api/trips/attachments/',
            {
                'stop_id': stop.id,
                'kind': 'location',
                'title': 'The Inn',
                'address': 'Furnace Creek, CA',
            },
            format='json',
        )
        self.assertEqual(res.status_code, 201)
        self.assertIn('google.com/maps', res.data['url'])
        self.assertIn('openstreetmap.org', res.data['osm_url'])
        self.assertIn('Furnace', res.data['url'])
        detail = self.client.get(f'/api/trips/trips/{trip.id}/')
        attachments = detail.data['days'][0]['stops'][0]['attachments']
        self.assertEqual(attachments[0]['kind'], 'location')

    def test_lodging_can_have_attachments(self):
        trip = Trip.objects.create(title='Stay', user=self.user)
        lodging = TripLodging.objects.create(user=self.user, trip=trip, name='The Inn')
        res = self.client.post(
            '/api/trips/attachments/',
            {
                'lodging_id': lodging.id,
                'kind': 'url',
                'title': 'Reservation',
                'url': 'https://example.com/booking',
            },
            format='json',
        )
        self.assertEqual(res.status_code, 201)
        picture = self.client.post(
            '/api/trips/attachments/',
            {
                'lodging_id': lodging.id,
                'kind': 'picture',
                'title': 'Room',
                'url': 'https://example.com/room.jpg',
            },
            format='json',
        )
        self.assertEqual(picture.status_code, 201)
        detail = self.client.get(f'/api/trips/trips/{trip.id}/')
        kinds = [a['kind'] for a in detail.data['lodgings'][0]['attachments']]
        self.assertEqual(kinds, ['url', 'picture'])
        both = self.client.post(
            '/api/trips/attachments/',
            {
                'stop_id': TripStop.objects.create(
                    user=self.user,
                    day=TripDay.objects.create(user=self.user, trip=trip, date='2026-09-10'),
                    text='Hike',
                ).id,
                'lodging_id': lodging.id,
                'kind': 'url',
                'url': 'https://example.com/both',
            },
            format='json',
        )
        self.assertEqual(both.status_code, 400)

    def test_lodging_shared_across_days(self):
        trip = Trip.objects.create(title='Stay', user=self.user)
        d1 = TripDay.objects.create(user=self.user, trip=trip, date='2026-09-10', title='One')
        d2 = TripDay.objects.create(user=self.user, trip=trip, date='2026-09-11', title='Two')
        d3 = TripDay.objects.create(user=self.user, trip=trip, date='2026-09-12', title='Three')
        res = self.client.post(
            '/api/trips/lodgings/',
            {
                'trip_id': trip.id,
                'name': 'The Inn at Death Valley',
                'address': 'Furnace Creek, CA',
                'confirmation': 'ABC123',
                'day_ids': [d1.id, d2.id],
            },
            format='json',
        )
        self.assertEqual(res.status_code, 201)
        lodging_id = res.data['id']
        self.assertIn('google.com/maps', res.data['maps_url'])
        detail = self.client.get(f'/api/trips/trips/{trip.id}/')
        by_date = {row['date']: row for row in detail.data['days']}
        self.assertEqual(by_date['2026-09-10']['lodging']['name'], 'The Inn at Death Valley')
        self.assertEqual(by_date['2026-09-11']['lodging_id'], lodging_id)
        self.assertIsNone(by_date['2026-09-12']['lodging'])
        self.assertEqual(len(detail.data['lodgings']), 1)

        patch = self.client.patch(
            f'/api/trips/lodgings/{lodging_id}/',
            {'day_ids': [d2.id, d3.id]},
            format='json',
        )
        self.assertEqual(patch.status_code, 200)
        detail = self.client.get(f'/api/trips/trips/{trip.id}/')
        by_date = {row['date']: row for row in detail.data['days']}
        self.assertIsNone(by_date['2026-09-10']['lodging'])
        self.assertEqual(by_date['2026-09-11']['lodging_id'], lodging_id)
        self.assertEqual(by_date['2026-09-12']['lodging_id'], lodging_id)

    def test_cannot_use_other_trips_lodging(self):
        mine = Trip.objects.create(title='Mine', user=self.user)
        theirs = Trip.objects.create(title='Theirs', user=self.other)
        lodging = theirs.lodgings.create(user=self.other, name='Other hotel')
        day = TripDay.objects.create(user=self.user, trip=mine, date='2026-09-01')
        res = self.client.patch(
            f'/api/trips/days/{day.id}/',
            {'lodging_id': lodging.id},
            format='json',
        )
        self.assertEqual(res.status_code, 400)

    def test_dump_import_fixture_remaps_owner(self):
        VacList.objects.create(name='Death Valley', user=self.user)
        VacList.objects.create(name='Death Valley', user=self.other)
        trip = Trip.objects.create(title='Sierra', user=self.user, start_date='2026-09-08')
        lodging = TripLodging.objects.create(user=self.user, trip=trip, name='The Inn')
        day = TripDay.objects.create(user=self.user, trip=trip, date='2026-09-10', lodging=lodging)
        stop = TripStop.objects.create(user=self.user, day=day, text='Check in', loc='Furnace Creek')
        TripStopAttachment.objects.create(
            user=self.user, stop=stop, kind='url', title='Booking', url='https://example.com/conf'
        )
        TripStopAttachment.objects.create(
            user=self.user, lodging=lodging, kind='picture', title='Room', url='https://example.com/room.jpg'
        )
        with TemporaryDirectory() as tmp:
            src = Path(tmp) / 'trips.json'
            call_command('dump_trip_fixture', email=self.user.email, output=str(src))
            call_command('import_trip_fixture', str(src), email=self.other.email, replace=True)
        copy = Trip.objects.get(user=self.other, title='Sierra')
        self.assertEqual(copy.days.get().lodging.name, 'The Inn')
        self.assertEqual(copy.days.get().stops.get().attachments.get().url, 'https://example.com/conf')
        self.assertEqual(copy.lodgings.get().attachments.get().kind, 'picture')
        self.assertEqual(Trip.objects.filter(user=self.user, title='Sierra').count(), 1)
