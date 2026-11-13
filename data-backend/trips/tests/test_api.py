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
        self.assertEqual(res.data['kind'], 'activity')
        detail = self.client.get(f'/api/trips/trips/{trip.id}/')
        self.assertEqual([s['text'] for s in detail.data['days'][0]['stops']], ['First', 'Second'])
        self.assertEqual(first.sort_order, 0)

    def test_travel_stop_fields(self):
        trip = Trip.objects.create(title='Travel', user=self.user)
        day = TripDay.objects.create(user=self.user, trip=trip, date='2026-09-01', title='One')
        res = self.client.post(
            '/api/trips/stops/',
            {
                'day_id': day.id,
                'kind': 'travel',
                'travel_mode': 'drive',
                'text': 'Drive to Sequoia',
                'loc': 'Oakland',
                'arrive_loc': 'Sequoia',
                'start_time': '08:00',
                'duration_minutes': 300,
                'cat': 'Travel',
            },
            format='json',
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['kind'], 'travel')
        self.assertEqual(res.data['travel_mode'], 'drive')
        self.assertEqual(res.data['loc'], 'Oakland')
        self.assertEqual(res.data['arrive_loc'], 'Sequoia')
        bad = self.client.post(
            '/api/trips/stops/',
            {
                'day_id': day.id,
                'kind': 'travel',
                'travel_mode': 'teleport',
                'text': 'Nope',
            },
            format='json',
        )
        self.assertEqual(bad.status_code, 400)

    def test_trip_description_notes_and_open_items_round_trip(self):
        trip = Trip.objects.create(title='Fields', user=self.user)
        res = self.client.patch(f'/api/trips/trips/{trip.id}/', {
            'description': 'Two weeks.', 'notes': '- Visa', 'open_items': '- Beach?',
        }, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual((res.data['description'], res.data['notes'], res.data['open_items']),
                         ('Two weeks.', '- Visa', '- Beach?'))

    def test_report_markdown(self):
        trip = Trip.objects.create(title='Thailand', user=self.user, description='Two weeks in Thailand.',
                                   notes='- Arrival card', open_items='- Phuket or Khao Lak?')
        lodge = TripLodging.objects.create(user=self.user, trip=trip, name='Riverside Hotel')
        d1 = TripDay.objects.create(user=self.user, trip=trip, date='2027-01-08', title='Leave', notes='SFO | BKK\n\nnight')
        TripDay.objects.create(user=self.user, trip=trip, date='2027-01-10', title='**Rest**', lodging=lodge)
        TripStop.objects.create(user=self.user, day=d1, kind='travel', travel_mode='flight', text='Fly to Bangkok',
                                loc='SFO', arrive_loc='BKK', start_time='13:00', duration_minutes=72)
        TripStop.objects.create(user=self.user, day=d1, text='Book hotel', status='tobook', sort_order=1)
        TripStop.objects.create(user=self.user, day=d1, text='Done booking', status='tobook', done=True, sort_order=2)
        TripStop.objects.create(user=self.user, day=d1, text='**Pool**', loc='~Hotel', sort_order=3,
                                description='- Bring [cash](https://x.test)\n- Towels')

        res = self.client.get(f'/api/trips/trips/{trip.id}/report/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['filename'], 'thailand-report.md')
        md = res.data['markdown']
        self.assertTrue(md.startswith('# Thailand\n\n'))
        self.assertIn(' · @tripper\n\nTwo weeks in Thailand.\n', md)
        self.assertIn('| Fri Jan 8 | SFO, BKK, ~Hotel | **Leave** · SFO \\| BKK · night |', md)
        self.assertIn('|  |  | ~Hotel | **Pool** · Bring [cash](https://x.test) · Towels |', md)
        self.assertIn('| Sun Jan 10 | Riverside Hotel | **Rest** |', md)
        self.assertIn('| Fri Jan 8 | 1:00 PM - 2:12 PM | SFO → BKK | Fly to Bangkok |', md)
        self.assertIn('|  |  |  | Book hotel |', md)
        self.assertIn('| Sun Jan 10 |  | Riverside Hotel | **Rest** |', md)
        self.assertIn('## To Dos\n\n- [ ] Book hotel (Fri Jan 8)\n\nNotes:\n\n- Arrival card', md)
        self.assertNotIn('Done booking (', md)
        self.assertIn("## Open Items\n\nAdd a comment on anything you'd change.\n\n- Phuket or Khao Lak?", md)

        other = Trip.objects.create(title='Theirs', user=self.other)
        self.assertEqual(self.client.get(f'/api/trips/trips/{other.id}/report/').status_code, 404)

    def test_bulk_stops_creates_updates_and_deletes(self):
        trip = Trip.objects.create(title='Bulk', user=self.user)
        day = TripDay.objects.create(user=self.user, trip=trip, date='2026-09-01', title='One')
        keep = TripStop.objects.create(user=self.user, day=day, text='Keep me', loc='Valley', sort_order=0)
        TripStop.objects.create(user=self.user, day=day, text='Drop me', sort_order=1)
        res = self.client.post(
            f'/api/trips/days/{day.id}/bulk-stops/',
            {
                'items': [
                    {
                        'kind': 'travel',
                        'travel_mode': 'drive',
                        'text': 'Drive in',
                        'loc': 'Oakland',
                        'arrive_loc': 'Valley',
                        'start_time': '08:00',
                        'duration_minutes': 180,
                    },
                    {
                        'id': keep.id,
                        'kind': 'activity',
                        'text': 'Hike',
                        'loc': 'Valley',
                        'start_time': '11:30',
                        'duration_minutes': 90,
                    },
                ]
            },
            format='json',
        )
        self.assertEqual(res.status_code, 200)
        texts = [row['text'] for row in res.data['stops']]
        self.assertEqual(texts, ['Drive in', 'Hike'])
        self.assertEqual(res.data['stops'][0]['kind'], 'travel')
        self.assertEqual(res.data['stops'][0]['arrive_loc'], 'Valley')
        self.assertEqual(res.data['stops'][1]['id'], keep.id)
        self.assertEqual(res.data['stops'][1]['text'], 'Hike')
        self.assertFalse(TripStop.objects.filter(day=day, text='Drop me').exists())

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

    def test_bulk_days_updates_and_creates_notes(self):
        trip = Trip.objects.create(title='Plan', user=self.user)
        existing = TripDay.objects.create(
            user=self.user, trip=trip, date='2026-09-10', title='Arrive', notes='Land early',
        )
        kept = TripDay.objects.create(
            user=self.user, trip=trip, date='2026-09-12', title='Buffer', notes='Leave alone',
        )
        res = self.client.post(
            f'/api/trips/trips/{trip.id}/bulk-days/',
            {
                'items': [
                    {'id': existing.id, 'date': '2026-09-10', 'title': 'Arrival', 'notes': 'Land mid-afternoon'},
                    {'date': '2026-09-11', 'title': 'Explore', 'notes': 'Hike + sunset'},
                ],
            },
            format='json',
        )
        self.assertEqual(res.status_code, 200)
        existing.refresh_from_db()
        kept.refresh_from_db()
        self.assertEqual(existing.title, 'Arrival')
        self.assertEqual(existing.notes, 'Land mid-afternoon')
        created = trip.days.get(date='2026-09-11')
        self.assertEqual(created.title, 'Explore')
        self.assertEqual(created.notes, 'Hike + sunset')
        self.assertEqual(kept.notes, 'Leave alone')
        by_date = {row['date']: row for row in res.data['days']}
        self.assertEqual(by_date['2026-09-10']['notes'], 'Land mid-afternoon')
        self.assertEqual(by_date['2026-09-11']['notes'], 'Hike + sunset')
        self.assertEqual(by_date['2026-09-12']['notes'], 'Leave alone')

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

    def test_export_import_zip_carries_files(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings

        from trips.models import TripMedia

        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media, MEDIA_URL='/media/'):
            up = self.client.post('/api/gallery/upload/', {
                'file': SimpleUploadedFile('Booking.pdf', b'%PDF-1.4 booking', content_type='application/pdf'),
                'add_to_gallery': 'false',
            }, format='multipart')
            self.assertEqual(up.status_code, 201, up.data)
            trip = Trip.objects.create(title='Thailand Trip', user=self.user, notes='- visa')
            day = TripDay.objects.create(user=self.user, trip=trip, date='2027-01-10', notes='Arrive')
            stop = TripStop.objects.create(user=self.user, day=day, text='Hotel')
            self.client.post('/api/trips/attachments/', {
                'kind': 'document', 'stop_id': stop.id, 'asset_id': up.data['user_media_id'], 'url': up.data['url'],
            }, format='json')
            TripMedia.objects.create(user=self.user, trip=trip, day=day, asset_id=up.data['user_media_id'])

            res = self.client.get(f'/api/trips/trips/{trip.id}/export/')
            self.assertEqual(res.status_code, 200)
            self.assertIn('thailand-trip-export.zip', res['Content-Disposition'])
            bundle = res.content

            for f in Path(media).rglob('*'):
                if f.is_file():
                    f.unlink()

            self.client.force_authenticate(self.other)
            res = self.client.post('/api/trips/trips/import/', {
                'file': SimpleUploadedFile('thailand-trip-export.zip', bundle, content_type='application/zip'),
            }, format='multipart')
            self.assertEqual(res.status_code, 201, res.data)
            self.assertEqual(res.data['counts']['files'], 1)
            self.assertEqual(res.data['counts']['media'], 1)
            copy = Trip.objects.get(pk=res.data['trips'][0]['id'])
            self.assertEqual(copy.user, self.other)
            self.assertEqual(copy.notes, '- visa')
            self.assertEqual(copy.days.get().notes, 'Arrive')
            att = copy.days.get().stops.get().attachments.get()
            self.assertEqual(att.asset.owner, self.other)
            self.assertEqual(att.asset.filename, 'Booking.pdf')
            self.assertEqual((Path(media) / att.asset.url[len('/media/'):]).read_bytes(), b'%PDF-1.4 booking')

            bad = self.client.post('/api/trips/trips/import/', {
                'file': SimpleUploadedFile('x.txt', b'nope'),
            }, format='multipart')
            self.assertEqual(bad.status_code, 400)

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
