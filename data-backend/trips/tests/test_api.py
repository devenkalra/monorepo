from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APIClient, APITestCase

from gallery.models import Gallery
from trips.models import Trip, TripDay, TripLodging, TripStop, TripStopAttachment, TripTodo
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

    def test_event_has_no_duration(self):
        trip = Trip.objects.create(title='Events', user=self.user)
        day = TripDay.objects.create(user=self.user, trip=trip, date='2027-01-10')
        res = self.client.post('/api/trips/stops/', {
            'day_id': day.id, 'kind': 'event', 'text': 'Show', 'start_time': '20:00', 'duration_minutes': 90,
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['kind'], 'event')
        self.assertIsNone(res.data['duration_minutes'])

    def test_todos_at_trip_day_and_stop_level(self):
        trip = Trip.objects.create(title='Todos', user=self.user)
        day = TripDay.objects.create(user=self.user, trip=trip, date='2027-01-10')
        stop = TripStop.objects.create(user=self.user, day=day, text='Museum')
        post = lambda body: self.client.post('/api/trips/todos/', {'trip_id': trip.id, **body}, format='json')
        self.assertEqual(post({'text': 'Visa'}).status_code, 201)
        self.assertEqual(post({'text': 'Pack', 'day_id': day.id}).status_code, 201)
        res = post({'text': 'Tickets', 'stop_id': stop.id})
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['day_id'], day.id)
        self.assertEqual(post({'text': '   '}).status_code, 400)
        self.assertEqual(res.data['category'], '')
        self.assertEqual(post({'text': 'Insurance', 'category': '  Money   matters '}).data['category'], 'Money matters')

        done = self.client.patch(f'/api/trips/todos/{res.data["id"]}/', {'done': True, 'category': 'Bookings'},
                                 format='json')
        self.assertTrue(done.data['done'])
        self.assertEqual(done.data['category'], 'Bookings')
        todos = self.client.get(f'/api/trips/trips/{trip.id}/').data['todos']
        self.assertEqual([(t['text'], t['done']) for t in todos],
                         [('Visa', False), ('Pack', False), ('Tickets', True), ('Insurance', False)])

        other_trip = Trip.objects.create(title='Mine 2', user=self.user)
        self.assertEqual(self.client.post('/api/trips/todos/', {
            'trip_id': other_trip.id, 'text': 'Wrong', 'day_id': day.id,
        }, format='json').status_code, 400)
        theirs = Trip.objects.create(title='Theirs', user=self.other)
        self.assertEqual(self.client.post('/api/trips/todos/', {
            'trip_id': theirs.id, 'text': 'Nope',
        }, format='json').status_code, 400)

    def test_trip_description_and_notes_round_trip(self):
        trip = Trip.objects.create(title='Fields', user=self.user)
        res = self.client.patch(f'/api/trips/trips/{trip.id}/', {
            'description': 'Two weeks.', 'notes': '- Visa',
        }, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual((res.data['description'], res.data['notes']), ('Two weeks.', '- Visa'))
        self.assertNotIn('open_items', res.data)

    def test_open_items_to_todos(self):
        from trips.transfer import open_items_to_todos
        self.assertEqual(
            open_items_to_todos('- Phuket or Khao Lak?\n\n* [ ] Book ferry\n1. Rent car\nPlain line\n  -  '),
            ['Phuket or Khao Lak?', 'Book ferry', 'Rent car', 'Plain line'],
        )

    def test_report_markdown(self):
        trip = Trip.objects.create(title='Thailand', user=self.user, description='Two weeks in Thailand.',
                                   notes='- Arrival card')
        lodge = TripLodging.objects.create(user=self.user, trip=trip, name='Riverside Hotel')
        d1 = TripDay.objects.create(user=self.user, trip=trip, date='2027-01-08', title='Leave', notes='SFO | BKK\n\nnight')
        TripDay.objects.create(user=self.user, trip=trip, date='2027-01-10', title='**Rest**', lodging=lodge)
        flight = TripStop.objects.create(user=self.user, day=d1, kind='travel', travel_mode='flight', text='Fly to Bangkok',
                                         loc='SFO', arrive_loc='BKK', start_time='13:00', duration_minutes=72)
        TripStop.objects.create(user=self.user, day=d1, text='Book hotel', status='tobook', sort_order=1)
        TripStop.objects.create(user=self.user, day=d1, kind='event', text='Dinner', start_time='19:30', sort_order=2)
        TripStop.objects.create(user=self.user, day=d1, text='**Pool**', loc='~Hotel', sort_order=3,
                                description='- Bring [cash](https://x.test)\n- Towels')
        TripTodo.objects.create(user=self.user, trip=trip, day=d1, stop=flight, text='Print boarding pass')
        TripTodo.objects.create(user=self.user, trip=trip, day=d1, text='Pack', done=True, sort_order=1)
        TripTodo.objects.create(user=self.user, trip=trip, text='Visa forms', sort_order=2)

        res = self.client.get(f'/api/trips/trips/{trip.id}/report/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['filename'], 'thailand-report.md')
        md = res.data['markdown']
        self.assertTrue(md.startswith('# Thailand\n\n'))
        self.assertIn(' · @tripper\n\nTwo weeks in Thailand.\n', md)
        self.assertNotIn('|', md.replace('SFO | BKK', ''))
        self.assertIn(
            '## Overview\n\n'
            '- **Fri Jan 8** — Leave  \n'
            '  SFO | BKK\n\n'
            '  night\n'
            '- **Sun Jan 10** — Rest\n\n'
            '## Day by day\n\n'
            '### Fri Jan 8 — Leave\n\n'
            '*SFO, BKK, ~Hotel*\n\n'
            '- 1:00 PM - 2:12 PM · **Fly to Bangkok** · SFO → BKK\n'
            '- **Book hotel**\n'
            '- 7:30 PM · **Dinner**\n'
            '- **Pool** · ~Hotel\n'
            '  - Bring [cash](https://x.test)\n'
            '  - Towels\n\n'
            '### Sun Jan 10 — Rest\n\n'
            '*Riverside Hotel*\n\n'
            '## To Dos', md,
        )
        self.assertIn(
            '## To Dos\n\n- [ ] Visa forms\n- [x] Pack (Fri Jan 8)\n'
            '- [ ] Print boarding pass (Fri Jan 8 · Fly to Bangkok)\n\nNotes:\n\n- Arrival card', md,
        )
        self.assertNotIn('Open Items', md)
        from trips.report import _block
        self.assertEqual(_block('Bangkok\nRest\n\n• Afternoon\n- Pool\nlast'), 'Bangkok  \nRest\n\n• Afternoon\n- Pool  \nlast')
        hidden = self.client.get(f'/api/trips/trips/{trip.id}/report/?hide_done=1').data['markdown']
        self.assertNotIn('Pack', hidden)
        self.assertIn('- [ ] Visa forms', hidden)

        TripTodo.objects.filter(text='Visa forms').update(category='Documents')
        TripTodo.objects.filter(text='Pack').update(category='packing')
        TripTodo.objects.create(user=self.user, trip=trip, text='Passport copy', category='Documents', sort_order=3)
        md = self.client.get(f'/api/trips/trips/{trip.id}/report/').data['markdown']
        self.assertIn(
            '## To Dos\n\n### Documents\n\n- [ ] Visa forms\n- [ ] Passport copy\n\n'
            '### packing\n\n- [x] Pack (Fri Jan 8)\n\n'
            '### Other\n\n- [ ] Print boarding pass (Fri Jan 8 · Fly to Bangkok)\n', md,
        )

        other = Trip.objects.create(title='Theirs', user=self.other)
        self.assertEqual(self.client.get(f'/api/trips/trips/{other.id}/report/').status_code, 404)

    def test_stop_price_currency_and_person(self):
        trip = Trip.objects.create(title='Money', user=self.user)
        day = TripDay.objects.create(user=self.user, trip=trip, date='2027-01-08')
        res = self.client.post('/api/trips/stops/', {
            'day_id': day.id, 'text': 'Ferry', 'price': '1500', 'currency': 'thb', 'person': '  Deven  Kalra ',
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual((res.data['price'], res.data['currency'], res.data['person']), ('1500.00', 'THB', 'Deven Kalra'))
        res = self.client.patch(f'/api/trips/stops/{res.data["id"]}/', {'currency': 'usd'}, format='json')
        self.assertEqual(res.data['currency'], '')
        res = self.client.patch(f'/api/trips/stops/{res.data["id"]}/', {'currency': 'baht'}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_report_types_and_sections(self):
        trip = Trip.objects.create(title='Thailand', user=self.user, notes='Bring sunscreen')
        d1 = TripDay.objects.create(user=self.user, trip=trip, date='2027-01-08', title='Leave')
        d2 = TripDay.objects.create(user=self.user, trip=trip, date='2027-01-09', title='Bangkok')
        TripStop.objects.create(user=self.user, day=d1, kind='travel', travel_mode='flight', text='Fly to Bangkok',
                                cat='Travel', price='1200.50', person='Deven')
        TripStop.objects.create(user=self.user, day=d2, text='Temple', cat='Sight', price='500', currency='THB',
                                sort_order=0)
        TripStop.objects.create(user=self.user, day=d2, kind='event', text='Dinner', cat='food', price='1800',
                                currency='THB', person='Asha', status='tobook', sort_order=1)
        TripStop.objects.create(user=self.user, day=d2, text='Walk', sort_order=2)
        TripTodo.objects.create(user=self.user, trip=trip, text='Visa')
        url = f'/api/trips/trips/{trip.id}/report/'

        full = self.client.get(url).data['markdown']
        self.assertIn('## Day by day', full)
        self.assertIn('## To Dos', full)
        self.assertNotIn('## Expenses', full)
        self.assertIn('- **Fly to Bangkok** · $1,200.50 · Deven\n', full)

        summary = self.client.get(url, {'type': 'summary'})
        self.assertEqual(summary.data['filename'], 'thailand-summary.md')
        self.assertIn('## Overview', summary.data['markdown'])
        self.assertNotIn('## Day by day', summary.data['markdown'])
        self.assertNotIn('## To Dos', summary.data['markdown'])

        expenses = self.client.get(url, {'type': 'expenses'})
        self.assertEqual(expenses.data['filename'], 'thailand-expenses.md')
        md = expenses.data['markdown']
        self.assertNotIn('## Overview', md)
        self.assertIn(
            '## Expenses\n\n**Total:** $1,200.50 · THB 2,300\n\n'
            '### By category\n\n- **food** — THB 1,800\n- **Sight** — THB 500\n- **Travel** — $1,200.50\n\n'
            '### By person\n\n- **Asha** — THB 1,800\n- **Deven** — $1,200.50\n- **Unassigned** — THB 500\n\n'
            '### Items\n\n'
            '- **Fri Jan 8** · Fly to Bangkok · Travel · Deven — $1,200.50\n'
            '- **Sat Jan 9** · Temple · Sight — THB 500\n'
            '- **Sat Jan 9** · Dinner · food · Asha — THB 1,800 (to book)\n', md,
        )
        self.assertNotIn('Walk', md)

        picked = self.client.get(url, {'type': 'full', 'sections': 'days,expenses'}).data['markdown']
        self.assertNotIn('## Overview', picked)
        self.assertIn('## Day by day', picked)
        self.assertNotIn('## To Dos', picked)
        self.assertIn('## Expenses', picked)

        self.assertEqual(self.client.get(url, {'type': 'full', 'sections': ''}).status_code, 400)
        self.assertEqual(self.client.get(url, {'type': 'full', 'sections': 'bogus'}).status_code, 400)
        self.assertEqual(self.client.get(url, {'type': 'weekly'}).status_code, 400)

        empty = Trip.objects.create(title='Empty', user=self.user)
        self.assertIn('No prices entered yet.', self.client.get(
            f'/api/trips/trips/{empty.id}/report/', {'type': 'expenses'}).data['markdown'])

    def test_bulk_stops_price_and_person(self):
        trip = Trip.objects.create(title='Bulk money', user=self.user)
        day = TripDay.objects.create(user=self.user, trip=trip, date='2026-09-01')
        kept = TripStop.objects.create(user=self.user, day=day, text='Old client row', price='40', person='Asha')
        url = f'/api/trips/days/{day.id}/bulk-stops/'
        res = self.client.post(url, {'items': [
            {'id': kept.id, 'text': 'Old client row'},
            {'text': 'Ferry', 'price': '1500.00', 'currency': 'thb', 'person': 'Deven'},
        ]}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        kept.refresh_from_db()
        self.assertEqual((str(kept.price), kept.person), ('40.00', 'Asha'))
        ferry = TripStop.objects.get(day=day, text='Ferry')
        self.assertEqual((str(ferry.price), ferry.currency, ferry.person), ('1500.00', 'THB', 'Deven'))

        res = self.client.post(url, {'items': [
            {'id': kept.id, 'text': 'Old client row', 'price': None, 'currency': '', 'person': ''},
        ]}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        kept.refresh_from_db()
        self.assertEqual((kept.price, kept.person), (None, ''))

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
            TripTodo.objects.create(user=self.user, trip=trip, day=day, stop=stop, text='Confirm', done=True,
                                    category='Bookings')

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
            todo = copy.todos.get()
            self.assertEqual((todo.text, todo.category, todo.done, todo.stop.text, todo.day.notes),
                             ('Confirm', 'Bookings', True, 'Hotel', 'Arrive'))
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

    def test_trip_create_generates_days_from_date_range(self):
        res = self.client.post('/api/trips/trips/', {
            'title': 'Kyoto Week',
            'start_date': '2027-04-01',
            'end_date': '2027-04-04',
            'timezone': 'Asia/Tokyo',
            'generate_days': True,
        }, format='json')
        self.assertEqual(res.status_code, 201)
        dates = [d['date'] for d in res.data['days']]
        self.assertEqual(dates, ['2027-04-01', '2027-04-02', '2027-04-03', '2027-04-04'])

        bad = self.client.post('/api/trips/trips/', {
            'title': 'Backwards',
            'start_date': '2027-04-05',
            'end_date': '2027-04-01',
            'generate_days': True,
        }, format='json')
        self.assertEqual(bad.status_code, 400)

    def test_stop_default_no_booking_and_option_status(self):
        trip = Trip.objects.create(title='Options', user=self.user)
        day = TripDay.objects.create(user=self.user, trip=trip, date='2027-05-01')
        res = self.client.post('/api/trips/stops/', {'day_id': day.id, 'text': 'Park walk'}, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['status'], 'no_booking')

        opt = self.client.post('/api/trips/stops/', {
            'day_id': day.id, 'text': 'Boat tour', 'status': 'option', 'price': '45',
        }, format='json')
        self.assertEqual(opt.status_code, 201)
        self.assertEqual(opt.data['status'], 'option')

        rep = self.client.get(f'/api/trips/trips/{trip.id}/report/?kind=full')
        self.assertEqual(rep.status_code, 200)
        self.assertIn('(option)', rep.data['markdown'])

    def test_legs_and_structural_route_operations(self):
        trip = Trip.objects.create(title='Thailand Route', user=self.user)
        d1 = TripDay.objects.create(user=self.user, trip=trip, date='2027-01-10', title='Bangkok 1')
        d2 = TripDay.objects.create(user=self.user, trip=trip, date='2027-01-11', title='Bangkok 2')
        d3 = TripDay.objects.create(user=self.user, trip=trip, date='2027-01-12', title='Chiang Mai 1')
        d4 = TripDay.objects.create(user=self.user, trip=trip, date='2027-01-13', title='Chiang Mai 2')
        TripStop.objects.create(user=self.user, day=d1, text='Grand Palace')
        TripStop.objects.create(user=self.user, day=d3, text='Doi Suthep')

        # Create two legs assigning days
        r1 = self.client.post('/api/trips/legs/', {
            'trip_id': trip.id, 'name': 'Bangkok', 'location': 'Bangkok', 'day_ids': [d1.id, d2.id],
        }, format='json')
        r2 = self.client.post('/api/trips/legs/', {
            'trip_id': trip.id, 'name': 'Chiang Mai', 'location': 'Chiang Mai', 'day_ids': [d3.id, d4.id],
        }, format='json')
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        bkk_id, cnx_id = r1.data['id'], r2.data['id']

        # Shift whole trip by +3 days
        res = self.client.post(f'/api/trips/trips/{trip.id}/shift-dates/', {'days': 3}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual([d['date'] for d in res.data['days']], ['2027-01-13', '2027-01-14', '2027-01-15', '2027-01-16'])

        # Insert day with ripple on 2027-01-14 (pushes 14..16 -> 15..17)
        res = self.client.post(f'/api/trips/trips/{trip.id}/insert-day/', {
            'date': '2027-01-14', 'title': 'Extra Bangkok', 'ripple': True,
        }, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data['days']), 5)
        inserted = next(d for d in res.data['days'] if d['date'] == '2027-01-14')
        self.assertEqual(inserted['title'], 'Extra Bangkok')
        self.assertEqual(inserted['leg'], bkk_id)

        # Remove that inserted day with ripple (pulls back to 13..16)
        res = self.client.post(f'/api/trips/trips/{trip.id}/remove-day/', {
            'day_id': inserted['id'], 'ripple': True,
        }, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual([d['date'] for d in res.data['days']], ['2027-01-13', '2027-01-14', '2027-01-15', '2027-01-16'])

        # Swap d1 and d3 (moves stops with their day)
        res = self.client.post(f'/api/trips/trips/{trip.id}/swap-days/', {
            'day_a_id': d1.id, 'day_b_id': d3.id,
        }, format='json')
        self.assertEqual(res.status_code, 200)
        by_date = {d['date']: d for d in res.data['days']}
        self.assertEqual(by_date['2027-01-13']['title'], 'Chiang Mai 1')
        self.assertEqual(by_date['2027-01-15']['title'], 'Bangkok 1')
        # Swap back
        self.client.post(f'/api/trips/trips/{trip.id}/swap-days/', {'day_a_id': d1.id, 'day_b_id': d3.id}, format='json')

        # Adjust leg: add_day to Bangkok twice (ripple) -> 6 days, Bangkok now has 4 days (asymmetric 4d + 2d)
        res = self.client.post(f'/api/trips/trips/{trip.id}/adjust-leg/', {
            'leg_id': bkk_id, 'action': 'add_day', 'ripple': True,
        }, format='json')
        self.assertEqual(res.status_code, 200)
        res = self.client.post(f'/api/trips/trips/{trip.id}/adjust-leg/', {
            'leg_id': bkk_id, 'action': 'add_day', 'ripple': True,
        }, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len([d for d in res.data['days'] if d['leg'] == bkk_id]), 4)
        self.assertEqual(len(res.data['days']), 6)

        # Reorder legs: move Bangkok down (asymmetric 4d vs 2d — tests temp-date collision safety)
        res = self.client.post(f'/api/trips/trips/{trip.id}/adjust-leg/', {
            'leg_id': bkk_id, 'action': 'move_down',
        }, format='json')
        self.assertEqual(res.status_code, 200)
        leg_seq = [d['leg'] for d in res.data['days']]
        self.assertEqual(leg_seq, [cnx_id, cnx_id, bkk_id, bkk_id, bkk_id, bkk_id])

        # Move a day (shift mode)
        first_day_id = res.data['days'][0]['id']
        res = self.client.post(f'/api/trips/trips/{trip.id}/move-day/', {
            'day_id': first_day_id, 'target_date': '2027-01-15', 'mode': 'shift',
        }, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(next(d for d in res.data['days'] if d['id'] == first_day_id)['date'], '2027-01-15')

    def test_unscheduled_ideas_pool_and_ai_routing(self):
        from datetime import date
        from trips import transfer
        from trips.models import TripLeg, TripSuggestion, TripSuggestionBatch

        trip = Trip.objects.create(user=self.user, title='Japan Ideas')
        leg = TripLeg.objects.create(user=self.user, trip=trip, name='Kyoto', location='Kyoto, Japan')
        day = TripDay.objects.create(user=self.user, trip=trip, date=date(2027, 4, 1), title='Arrival', leg=leg)

        # Create unscheduled idea linked to trip + leg (no day)
        res = self.client.post('/api/trips/stops/', {
            'trip_id': trip.id,
            'day_id': None,
            'leg_id': leg.id,
            'text': 'Fushimi Inari early hike',
            'loc': 'Kyoto',
            'cat': 'Sight',
            'status': TripStop.STATUS_OPTION,
        }, format='json')
        self.assertEqual(res.status_code, 201)
        idea_id = res.data['id']
        self.assertIsNone(res.data['day'])
        self.assertEqual(res.data['trip'], trip.id)
        self.assertEqual(res.data['leg'], leg.id)

        # Appears in trip.ideas (not in day.stops)
        detail = self.client.get(f'/api/trips/trips/{trip.id}/').data
        self.assertEqual([i['id'] for i in detail['ideas']], [idea_id])
        self.assertEqual(detail['days'][0]['stops'], [])

        # Attach URL & to-do to unscheduled idea
        att = self.client.post('/api/trips/attachments/', {
            'stop_id': idea_id, 'kind': 'url', 'title': 'Guide', 'url': 'https://example.com/inari',
        }, format='json')
        self.assertEqual(att.status_code, 201)
        todo = self.client.post('/api/trips/todos/', {
            'trip_id': trip.id, 'stop_id': idea_id, 'text': 'Check sunrise time',
        }, format='json')
        self.assertEqual(todo.status_code, 201)

        # Promote idea to a scheduled day
        res = self.client.patch(f'/api/trips/stops/{idea_id}/', {
            'day_id': day.id, 'start_time': '07:00', 'status': TripStop.STATUS_NO_BOOKING,
        }, format='json')
        self.assertEqual(res.status_code, 200)
        detail = self.client.get(f'/api/trips/trips/{trip.id}/').data
        self.assertEqual(detail['ideas'], [])
        self.assertEqual([s['id'] for s in detail['days'][0]['stops']], [idea_id])
        self.assertEqual(len(detail['days'][0]['stops'][0]['attachments']), 1)

        # Move scheduled stop back to Ideas pool
        res = self.client.patch(f'/api/trips/stops/{idea_id}/', {
            'day_id': None, 'start_time': None, 'status': TripStop.STATUS_OPTION,
        }, format='json')
        self.assertEqual(res.status_code, 200)
        detail = self.client.get(f'/api/trips/trips/{trip.id}/').data
        self.assertEqual([i['id'] for i in detail['ideas']], [idea_id])

        # Route AI suggestion directly to Ideas pool (inherits leg from suggested day!)
        batch = TripSuggestionBatch.objects.create(
            user=self.user, trip=trip, day=day, prompt='Ramen spots', status=TripSuggestionBatch.STATUS_DONE,
        )
        sug = TripSuggestion.objects.create(
            user=self.user,
            batch=batch,
            kind=TripSuggestion.KIND_STOP,
            data={
                'name': 'Nishiki Market',
                'address': 'Kyoto, Japan',
                'url': 'https://example.com/nishiki',
                'description': 'Historic food arcade',
                'category': 'Food',
                'day_id': day.id,
            },
        )
        res = self.client.post(f'/api/trips/suggestions/{sug.id}/apply/', {
            'fields': {'to_ideas': True},
        }, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['status'], TripSuggestion.STATUS_ADDED)
        detail = self.client.get(f'/api/trips/trips/{trip.id}/').data
        self.assertEqual(len(detail['ideas']), 2)
        ai_idea = next(i for i in detail['ideas'] if i['text'] == 'Nishiki Market')
        self.assertEqual(ai_idea['leg'], leg.id)
        self.assertEqual(ai_idea['status'], TripStop.STATUS_OPTION)
        self.assertEqual(len(ai_idea['attachments']), 2)

        # Export & import round-trip preserves unscheduled ideas and their leg
        payload = {'version': transfer.FORMAT_VERSION, 'trips': [transfer.export_trip(trip)]}
        self.assertEqual(len(payload['trips'][0]['ideas']), 2)
        imported, _ = transfer.import_payload(self.other, payload)
        restored = imported[0]
        restored_ideas = list(restored.stops.filter(day__isnull=True).select_related('leg'))
        self.assertEqual(len(restored_ideas), 2)
        self.assertTrue(all(i.leg and i.leg.name == 'Kyoto' for i in restored_ideas))

    def test_leg_contiguity_enforced(self):
        trip = Trip.objects.create(user=self.user, title='Contiguous Route')
        d1 = TripDay.objects.create(user=self.user, trip=trip, date=date(2027, 5, 1), title='D1')
        d2 = TripDay.objects.create(user=self.user, trip=trip, date=date(2027, 5, 2), title='D2')
        d3 = TripDay.objects.create(user=self.user, trip=trip, date=date(2027, 5, 3), title='D3')
        d4 = TripDay.objects.create(user=self.user, trip=trip, date=date(2027, 5, 4), title='D4')

        # Non-contiguous day_ids on leg creation -> rejected
        res = self.client.post('/api/trips/legs/', {
            'trip_id': trip.id, 'name': 'Split', 'day_ids': [d1.id, d3.id],
        }, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('day_ids', res.data)

        # Contiguous creation succeeds
        res = self.client.post('/api/trips/legs/', {
            'trip_id': trip.id, 'name': 'North', 'day_ids': [d1.id, d2.id, d3.id],
        }, format='json')
        self.assertEqual(res.status_code, 201)
        north_id = res.data['id']

        # Creating a second leg on just d2 would split North into [d1, d3] -> rejected
        res = self.client.post('/api/trips/legs/', {
            'trip_id': trip.id, 'name': 'Middle', 'day_ids': [d2.id],
        }, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('day_ids', res.data)

        # Creating a second leg on [d3, d4] trims the edge of North cleanly -> succeeds
        res = self.client.post('/api/trips/legs/', {
            'trip_id': trip.id, 'name': 'South', 'day_ids': [d3.id, d4.id],
        }, format='json')
        self.assertEqual(res.status_code, 201)
        south_id = res.data['id']

        # Direct per-day PATCH that would make North non-contiguous (assigning d4 to North) -> rejected
        res = self.client.patch(f'/api/trips/days/{d4.id}/', {'leg_id': north_id}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('leg_id', res.data)

        # Inserting a day with a non-contiguous leg_id (at d4 assigned to North) -> rejected
        res = self.client.post(f'/api/trips/trips/{trip.id}/insert-day/', {
            'date': '2027-05-05', 'leg_id': north_id, 'ripple': False,
        }, format='json')
        self.assertEqual(res.status_code, 400)

        # Inserting a day between two days of South with no explicit leg_id inherits South
        res = self.client.post(f'/api/trips/trips/{trip.id}/insert-day/', {
            'date': '2027-05-04', 'title': 'Extra South', 'ripple': True,
        }, format='json')
        self.assertEqual(res.status_code, 200)
        inserted = next(d for d in res.data['days'] if d['title'] == 'Extra South')
        self.assertEqual(inserted['leg'], south_id)

    def test_prep_bookings_confirmation_and_lodging_budget(self):
        from trips import report as trip_report
        from trips import transfer

        trip = Trip.objects.create(user=self.user, title='Prep & Bookings Test')
        day = TripDay.objects.create(user=self.user, trip=trip, date=date(2027, 8, 1), title='Arrival')

        # Create lodging with status, price, currency, person, confirmation
        res = self.client.post('/api/trips/lodgings/', {
            'trip_id': trip.id,
            'name': 'Park Hyatt Tokyo',
            'status': TripLodging.STATUS_BOOKED,
            'confirmation': 'HYATT-991',
            'price': '850.00',
            'currency': '',
            'person': 'Deven',
            'day_ids': [day.id],
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['status'], TripLodging.STATUS_BOOKED)
        self.assertEqual(res.data['confirmation'], 'HYATT-991')
        self.assertEqual(res.data['price'], '850.00')
        self.assertEqual(res.data['person'], 'Deven')
        lodging_id = res.data['id']

        # Progress lodging to confirmed
        res = self.client.patch(f'/api/trips/lodgings/{lodging_id}/', {
            'status': TripLodging.STATUS_CONFIRMED,
        }, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['status'], TripLodging.STATUS_CONFIRMED)

        # Create stop with confirmation code
        res = self.client.post('/api/trips/stops/', {
            'day_id': day.id,
            'kind': TripStop.KIND_TRAVEL,
            'travel_mode': TripStop.TRAVEL_FLIGHT,
            'text': 'JL61 LAX → NRT',
            'status': TripStop.STATUS_CONFIRMED,
            'confirmation': 'PNR-77X',
            'price': '1200.00',
            'cat': 'Flight',
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['confirmation'], 'PNR-77X')

        # Generated report includes both stop confirmation and lodging price in Expenses
        md = trip_report.build(trip, sections=('overview', 'days', 'expenses'))
        self.assertIn('Conf: PNR-77X', md)
        self.assertIn('Park Hyatt Tokyo', md)
        self.assertIn('Lodging', md)
        self.assertIn('$2,050', md)

        # Export / import round-trip preserves confirmation + lodging booking fields
        payload = {'version': transfer.FORMAT_VERSION, 'trips': [transfer.export_trip(trip)]}
        imported, _ = transfer.import_payload(self.other, payload)
        restored = imported[0]
        restored_lodging = restored.lodgings.get()
        self.assertEqual(restored_lodging.status, TripLodging.STATUS_CONFIRMED)
        self.assertEqual(str(restored_lodging.price), '850.00')
        self.assertEqual(restored_lodging.person, 'Deven')
        restored_stop = restored.stops.get()
        self.assertEqual(restored_stop.confirmation, 'PNR-77X')

    def test_sharing_roles_owner_editor_viewer(self):
        from trips.models import TripShare

        editor = User.objects.create_user(username='editor_u', email='editor@example.com', password='pw')
        viewer = User.objects.create_user(username='viewer_u', email='viewer@example.com', password='pw')
        stranger = User.objects.create_user(username='stranger_u', email='stranger@example.com', password='pw')

        trip = Trip.objects.create(user=self.user, title='Shared Kyoto')
        day = TripDay.objects.create(user=self.user, trip=trip, date='2027-05-01', title='Arrival')
        stop = TripStop.objects.create(user=self.user, trip=trip, day=day, text='Ramen')

        # Owner invites editor & viewer (also verifies email normalization & self-share guard)
        res = self.client.post('/api/trips/shares/', {
            'trip_id': trip.id, 'email': 'EDITOR@example.com', 'role': TripShare.ROLE_EDITOR,
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['email'], 'editor@example.com')
        self.assertTrue(res.data['accepted'])

        res = self.client.post('/api/trips/shares/', {
            'trip_id': trip.id, 'email': 'viewer@example.com', 'role': TripShare.ROLE_VIEWER,
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)

        res = self.client.post('/api/trips/shares/', {
            'trip_id': trip.id, 'email': self.user.email, 'role': TripShare.ROLE_EDITOR,
        }, format='json')
        self.assertEqual(res.status_code, 400)

        # Stranger cannot see trip
        stranger_client = APIClient()
        stranger_client.force_authenticate(user=stranger)
        self.assertEqual(stranger_client.get(f'/api/trips/trips/{trip.id}/').status_code, 404)

        # Viewer can read trip & report, but cannot mutate anything
        viewer_client = APIClient()
        viewer_client.force_authenticate(user=viewer)
        res = viewer_client.get('/api/trips/trips/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]['my_role'], 'viewer')

        detail = viewer_client.get(f'/api/trips/trips/{trip.id}/')
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data['my_role'], 'viewer')
        self.assertEqual(detail.data['shares'], [])

        self.assertEqual(viewer_client.patch(f'/api/trips/trips/{trip.id}/', {'title': 'Hacked'}, format='json').status_code, 403)
        self.assertEqual(viewer_client.patch(f'/api/trips/stops/{stop.id}/', {'text': 'Nope'}, format='json').status_code, 403)
        self.assertEqual(viewer_client.delete(f'/api/trips/stops/{stop.id}/').status_code, 403)
        self.assertEqual(viewer_client.post(f'/api/trips/trips/{trip.id}/shift-dates/', {'days': 1}, format='json').status_code, 403)
        self.assertIn(
            viewer_client.post('/api/trips/stops/', {'day_id': day.id, 'text': 'Blocked'}, format='json').status_code,
            (400, 403),
        )

        # Editor can edit trip, add stops, shift dates, and ownership stays with self.user!
        editor_client = APIClient()
        editor_client.force_authenticate(user=editor)
        res = editor_client.patch(f'/api/trips/trips/{trip.id}/', {'title': 'Shared Kyoto Updated'}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        trip.refresh_from_db()
        self.assertEqual(trip.user_id, self.user.id)
        self.assertEqual(trip.title, 'Shared Kyoto Updated')

        res = editor_client.post('/api/trips/stops/', {'day_id': day.id, 'text': 'Tea ceremony'}, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        new_stop = TripStop.objects.get(pk=res.data['id'])
        self.assertEqual(new_stop.user_id, self.user.id)

        res = editor_client.post(f'/api/trips/trips/{trip.id}/shift-dates/', {'days': 2}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        day.refresh_from_db()
        self.assertEqual(str(day.date), '2027-05-03')

        # Editor cannot delete trip or toggle public link
        self.assertEqual(editor_client.delete(f'/api/trips/trips/{trip.id}/').status_code, 403)
        self.assertEqual(editor_client.post(f'/api/trips/trips/{trip.id}/public-link/', {'enabled': True}, format='json').status_code, 403)

        # Viewer can leave shared trip
        res = viewer_client.post(f'/api/trips/trips/{trip.id}/leave/')
        self.assertEqual(res.status_code, 204)
        self.assertEqual(viewer_client.get(f'/api/trips/trips/{trip.id}/').status_code, 404)

    def test_public_read_only_link(self):
        trip = Trip.objects.create(user=self.user, title='Public Alps', description='Mountain loop')
        day = TripDay.objects.create(user=self.user, trip=trip, date='2027-06-10', title='Zermatt')
        lodging = TripLodging.objects.create(
            user=self.user, trip=trip, name='Alpine Lodge',
            confirmation='SECRET-CONF-1', price='500.00',
        )
        day.lodging = lodging
        day.save()
        stop = TripStop.objects.create(
            user=self.user, trip=trip, day=day, text='Gornergrat train',
            confirmation='TRAIN-SECRET', price='120.00',
        )
        TripStopAttachment.objects.create(
            user=self.user, stop=stop, kind=TripStopAttachment.KIND_DOCUMENT,
            title='Private Ticket PDF', url='https://example.com/private.pdf',
        )
        TripStopAttachment.objects.create(
            user=self.user, stop=stop, kind=TripStopAttachment.KIND_URL,
            title='Official timetable', url='https://gornergrat.ch',
        )
        TripTodo.objects.create(user=self.user, trip=trip, text='Private todo')

        anon = APIClient()

        # Enable public link
        res = self.client.post(f'/api/trips/trips/{trip.id}/public-link/', {'enabled': True}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(res.data['public_enabled'])
        token1 = res.data['share_token']
        self.assertGreaterEqual(len(token1), 24)
        self.assertEqual(res.data['public_path'], f'/app/trips/share/{token1}')

        # Unauthenticated GET succeeds and strips private fields/docs/todos
        pub = anon.get(f'/api/trips/public/{token1}/')
        self.assertEqual(pub.status_code, 200, pub.data)
        self.assertEqual(pub.data['title'], 'Public Alps')
        self.assertNotIn('todos', pub.data)
        self.assertNotIn('comments', pub.data)
        self.assertNotIn('shares', pub.data)
        pub_lodge = pub.data['lodgings'][0]
        self.assertEqual(pub_lodge['name'], 'Alpine Lodge')
        self.assertNotIn('confirmation', pub_lodge)
        self.assertNotIn('price', pub_lodge)
        pub_stop = pub.data['days'][0]['stops'][0]
        self.assertNotIn('confirmation', pub_stop)
        self.assertNotIn('price', pub_stop)
        self.assertEqual([a['title'] for a in pub_stop['attachments']], ['Official timetable'])

        # Regenerating invalidates old token immediately
        res = self.client.post(f'/api/trips/trips/{trip.id}/public-link/', {'regenerate': True}, format='json')
        self.assertEqual(res.status_code, 200)
        token2 = res.data['share_token']
        self.assertNotEqual(token1, token2)
        self.assertEqual(anon.get(f'/api/trips/public/{token1}/').status_code, 404)
        self.assertEqual(anon.get(f'/api/trips/public/{token2}/').status_code, 200)

        # Disabling returns 404
        res = self.client.post(f'/api/trips/trips/{trip.id}/public-link/', {'enabled': False}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data['public_enabled'])
        self.assertEqual(anon.get(f'/api/trips/public/{token2}/').status_code, 404)

    def test_threaded_comments_all_levels_and_resolve(self):
        from trips.models import TripLeg, TripShare

        viewer = User.objects.create_user(username='c_viewer', email='cviewer@example.com', password='pw')
        editor = User.objects.create_user(username='c_editor', email='ceditor@example.com', password='pw')

        trip = Trip.objects.create(user=self.user, title='Italy Comments')
        leg = TripLeg.objects.create(user=self.user, trip=trip, name='Rome')
        day = TripDay.objects.create(user=self.user, trip=trip, date='2027-07-01', title='Day 1', leg=leg)
        lodging = TripLodging.objects.create(user=self.user, trip=trip, name='Hotel Roma')
        stop = TripStop.objects.create(user=self.user, trip=trip, day=day, text='Colosseum')
        idea = TripStop.objects.create(user=self.user, trip=trip, day=None, text='Gelato place')

        TripShare.objects.create(trip=trip, user=viewer, email=viewer.email, role=TripShare.ROLE_VIEWER)
        TripShare.objects.create(trip=trip, user=editor, email=editor.email, role=TripShare.ROLE_EDITOR)

        viewer_client = APIClient()
        viewer_client.force_authenticate(user=viewer)
        editor_client = APIClient()
        editor_client.force_authenticate(user=editor)

        # Reject multi-target comment
        bad = viewer_client.post('/api/trips/comments/', {
            'trip_id': trip.id, 'day_id': day.id, 'stop_id': stop.id, 'body': 'Too many targets',
        }, format='json')
        self.assertEqual(bad.status_code, 400)

        # Viewer creates comments on Trip, Leg, Day, Stop, Idea, and Lodging
        c_trip = viewer_client.post('/api/trips/comments/', {'trip_id': trip.id, 'body': 'Excited!'}, format='json')
        c_leg = viewer_client.post('/api/trips/comments/', {'trip_id': trip.id, 'leg_id': leg.id, 'body': 'Extend Rome?'}, format='json')
        c_day = viewer_client.post('/api/trips/comments/', {'trip_id': trip.id, 'day_id': day.id, 'body': 'Early start?'}, format='json')
        c_stop = viewer_client.post('/api/trips/comments/', {'trip_id': trip.id, 'stop_id': stop.id, 'body': 'Need timed tickets'}, format='json')
        c_idea = viewer_client.post('/api/trips/comments/', {'trip_id': trip.id, 'stop_id': idea.id, 'body': 'Must try pistachio'}, format='json')
        c_lodge = viewer_client.post('/api/trips/comments/', {'trip_id': trip.id, 'lodging_id': lodging.id, 'body': 'Has AC?'}, format='json')
        for r in (c_trip, c_leg, c_day, c_stop, c_idea, c_lodge):
            self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(c_trip.data['target_type'], 'trip')
        self.assertEqual(c_leg.data['target_type'], 'leg')
        self.assertEqual(c_day.data['target_type'], 'day')
        self.assertEqual(c_stop.data['target_type'], 'stop')
        self.assertEqual(c_lodge.data['target_type'], 'lodging')

        # Owner replies to stop comment; reply inherits stop target
        reply = self.client.post('/api/trips/comments/', {
            'trip_id': trip.id, 'parent_id': c_stop.data['id'], 'body': 'Booked for 9 AM!',
        }, format='json')
        self.assertEqual(reply.status_code, 201, reply.data)
        self.assertEqual(reply.data['parent'], c_stop.data['id'])
        self.assertEqual(reply.data['stop'], stop.id)

        # Viewer cannot edit or delete Owner's reply
        self.assertEqual(viewer_client.patch(f'/api/trips/comments/{reply.data["id"]}/', {'body': 'Hijack'}, format='json').status_code, 403)
        self.assertEqual(viewer_client.delete(f'/api/trips/comments/{reply.data["id"]}/').status_code, 403)

        # Editor resolves the stop thread; check resolved_by and open_comment_count
        res = editor_client.post(f'/api/trips/comments/{c_stop.data["id"]}/resolve/')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(res.data['resolved'])
        self.assertEqual(res.data['resolved_by'], editor.id)

        # Filter open vs resolved & target_type
        open_stop = self.client.get(f'/api/trips/comments/?trip={trip.id}&resolved=false&target_type=stop')
        self.assertEqual(len(open_stop.data), 1)  # only c_idea remains open (reply has resolved=False too? wait - let's check!)

        # Reopen works
        res = self.client.post(f'/api/trips/comments/{c_stop.data["id"]}/reopen/')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data['resolved'])
        self.assertIsNone(res.data['resolved_by'])

        # Trip detail includes open_comment_count = 6 top-level threads
        detail = self.client.get(f'/api/trips/trips/{trip.id}/')
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data['open_comment_count'], 6)
        self.assertEqual(len(detail.data['comments']), 7)  # 6 roots + 1 reply

    def test_export_import_v2_full_roundtrip_legs_ideas_sharing_comments_files(self):
        import io
        import json
        import zipfile
        from decimal import Decimal
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings

        from trips.models import TripComment, TripLeg, TripMedia, TripShare

        collaborator = User.objects.create_user(
            username='collab-export', email='collab-export@example.com', password='pw',
        )

        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media, MEDIA_URL='/media/'):
            idea_up = self.client.post('/api/gallery/upload/', {
                'file': SimpleUploadedFile('IdeaBrochure.pdf', b'%PDF-1.4 idea-brochure', content_type='application/pdf'),
                'add_to_gallery': 'false',
            }, format='multipart')
            self.assertEqual(idea_up.status_code, 201, idea_up.data)

            trip = Trip.objects.create(
                title='Japan 2027',
                user=self.user,
                start_date='2027-04-01',
                end_date='2027-04-03',
                timezone='Asia/Tokyo',
                notes='JR Pass needed',
                public_enabled=True,
                share_token='japan-2027-public-tok',
            )
            leg = TripLeg.objects.create(
                user=self.user, trip=trip, name='Tokyo', location='Tokyo, Japan',
                timezone='Asia/Tokyo', notes='Shibuya base',
            )
            lodging = TripLodging.objects.create(
                user=self.user, trip=trip, name='Park Hyatt',
                status='confirmed', price=Decimal('1200.50'), currency='USD',
                confirmation='HYATT-889', person='Alex', notes='High floor',
            )
            day = TripDay.objects.create(
                user=self.user, trip=trip, leg=leg, date='2027-04-01',
                title='Arrival', lodging=lodging, journal='Landed at HND',
            )
            stop = TripStop.objects.create(
                user=self.user, trip=trip, day=day, text='TeamLab Borderless',
                status='booked', confirmation='TLB-42', price=Decimal('45.00'),
                timezone='Asia/Tokyo', start_time='14:00',
            )
            idea = TripStop.objects.create(
                user=self.user, trip=trip, day=None, leg=leg, text='Ghibli Museum',
                status='option', description='Book 1 month ahead',
            )
            self.client.post('/api/trips/attachments/', {
                'kind': 'document', 'stop_id': idea.id,
                'asset_id': idea_up.data['user_media_id'], 'url': idea_up.data['url'],
                'title': 'Ghibli map',
            }, format='json')
            TripMedia.objects.create(
                user=self.user, trip=trip, stop=idea, asset_id=idea_up.data['user_media_id'],
            )
            TripTodo.objects.create(
                user=self.user, trip=trip, day=day, stop=stop,
                text='Pick up Suica', category='Transport', done=False,
            )
            TripShare.objects.create(
                trip=trip, email=collaborator.email, user=collaborator, role='editor', invited_by=self.user,
            )
            TripShare.objects.create(
                trip=trip, email=self.other.email, user=self.other, role='viewer', invited_by=self.user,
            )
            TripShare.objects.create(
                trip=trip, email='pending-friend@example.com', role='viewer', invited_by=self.user,
            )

            c_trip = TripComment.objects.create(trip=trip, author=self.user, body='Can not wait!')
            c_leg = TripComment.objects.create(trip=trip, leg=leg, author=collaborator, body='Stay in Shinjuku?')
            c_day = TripComment.objects.create(trip=trip, day=day, author=self.user, body='Jet lag day')
            c_stop = TripComment.objects.create(
                trip=trip, stop=stop, author=collaborator, body='Timed entry booked?',
                resolved=True, resolved_by=self.user,
            )
            TripComment.objects.create(
                trip=trip, stop=stop, parent=c_stop, author=self.user, body='Yes, 2pm slot!',
            )
            TripComment.objects.create(trip=trip, stop=idea, author=collaborator, body='Must go!')
            TripComment.objects.create(trip=trip, lodging=lodging, author=self.user, body='Pool view')

            res = self.client.get(f'/api/trips/trips/{trip.id}/export/')
            self.assertEqual(res.status_code, 200)
            bundle = res.content

            # Verify archive structure includes format_version=2 and the unscheduled idea's file
            with zipfile.ZipFile(io.BytesIO(bundle), 'r') as zf:
                names = set(zf.namelist())
                self.assertIn('trip.json', names)
                file_entries = [n for n in names if n.startswith('files/')]
                self.assertEqual(len(file_entries), 1)
                self.assertEqual(zf.read(file_entries[0]), b'%PDF-1.4 idea-brochure')
                exported = json.loads(zf.read('trip.json'))
                self.assertEqual(exported['version'], 2)
                self.assertEqual(exported['trips'][0]['share_token'], 'japan-2027-public-tok')
                self.assertTrue(exported['trips'][0]['public_enabled'])

            # Wipe local media files to simulate importing on a fresh production server
            for f in Path(media).rglob('*'):
                if f.is_file():
                    f.unlink()

            # 1) Import while original trip still exists -> share_token rotates to avoid collision
            self.client.force_authenticate(self.other)
            imp1 = self.client.post('/api/trips/trips/import/', {
                'file': SimpleUploadedFile('japan-2027-export.zip', bundle, content_type='application/zip'),
            }, format='multipart')
            self.assertEqual(imp1.status_code, 201, imp1.data)
            counts = imp1.data['counts']
            self.assertEqual(counts['trips'], 1)
            self.assertEqual(counts['legs'], 1)
            self.assertEqual(counts['lodgings'], 1)
            self.assertEqual(counts['days'], 1)
            self.assertEqual(counts['stops'], 2)  # 1 scheduled + 1 idea
            self.assertEqual(counts['todos'], 1)
            self.assertEqual(counts['shares'], 2)  # skipped self.other's own email
            self.assertEqual(counts['comments'], 7)
            self.assertEqual(counts['attachments'], 1)
            self.assertEqual(counts['media'], 1)
            self.assertEqual(counts['files'], 1)

            copy = Trip.objects.get(pk=imp1.data['trips'][0]['id'])
            self.assertEqual(copy.user, self.other)
            self.assertTrue(copy.public_enabled)
            self.assertTrue(copy.share_token)
            self.assertNotEqual(copy.share_token, 'japan-2027-public-tok')

            copy_leg = copy.legs.get()
            self.assertEqual((copy_leg.name, copy_leg.location, copy_leg.timezone, copy_leg.notes),
                             ('Tokyo', 'Tokyo, Japan', 'Asia/Tokyo', 'Shibuya base'))
            copy_lodging = copy.lodgings.get()
            self.assertEqual((copy_lodging.name, copy_lodging.status, copy_lodging.price, copy_lodging.confirmation),
                             ('Park Hyatt', 'confirmed', Decimal('1200.50'), 'HYATT-889'))
            copy_day = copy.days.get()
            self.assertEqual((copy_day.leg_id, copy_day.lodging_id, copy_day.journal),
                             (copy_leg.id, copy_lodging.id, 'Landed at HND'))
            copy_stop = copy_day.stops.get()
            self.assertEqual((copy_stop.text, copy_stop.status, copy_stop.confirmation, copy_stop.price),
                             ('TeamLab Borderless', 'booked', 'TLB-42', Decimal('45.00')))

            copy_idea = copy.stops.filter(day__isnull=True).get()
            self.assertEqual((copy_idea.text, copy_idea.leg_id, copy_idea.status),
                             ('Ghibli Museum', copy_leg.id, 'option'))
            idea_att = copy_idea.attachments.get()
            self.assertEqual(idea_att.asset.owner, self.other)
            self.assertEqual(idea_att.asset.filename, 'IdeaBrochure.pdf')
            self.assertEqual((Path(media) / idea_att.asset.url[len('/media/'):]).read_bytes(), b'%PDF-1.4 idea-brochure')
            self.assertEqual(copy_idea.media.count(), 1)

            # Verify shares
            shares_by_email = {s.email: s for s in copy.shares.all()}
            self.assertEqual(set(shares_by_email.keys()), {collaborator.email, 'pending-friend@example.com'})
            self.assertEqual(shares_by_email[collaborator.email].user, collaborator)
            self.assertEqual(shares_by_email[collaborator.email].role, 'editor')
            self.assertIsNone(shares_by_email['pending-friend@example.com'].user)

            # Verify threaded comments & target remapping
            self.assertEqual(copy.comments.count(), 7)
            copy_stop_root = copy.comments.get(stop=copy_stop, parent__isnull=True)
            self.assertTrue(copy_stop_root.resolved)
            self.assertEqual(copy_stop_root.author, collaborator)
            self.assertEqual(copy_stop_root.resolved_by, self.user)
            copy_stop_reply = copy.comments.get(parent=copy_stop_root)
            self.assertEqual(copy_stop_reply.body, 'Yes, 2pm slot!')
            self.assertEqual(copy_stop_reply.stop_id, copy_stop.id)
            self.assertEqual(copy.comments.filter(leg=copy_leg).count(), 1)
            self.assertEqual(copy.comments.filter(day=copy_day).count(), 1)
            self.assertEqual(copy.comments.filter(stop=copy_idea).count(), 1)
            self.assertEqual(copy.comments.filter(lodging=copy_lodging).count(), 1)

            # 2) Delete original trip and import again -> exact share_token is preserved (fresh prod server)
            trip.delete()
            imp2 = self.client.post('/api/trips/trips/import/', {
                'file': SimpleUploadedFile('japan-2027-export.zip', bundle, content_type='application/zip'),
            }, format='multipart')
            self.assertEqual(imp2.status_code, 201, imp2.data)
            copy2 = Trip.objects.get(pk=imp2.data['trips'][0]['id'])
            self.assertEqual(copy2.share_token, 'japan-2027-public-tok')
            self.assertTrue(copy2.public_enabled)

    def test_non_owner_export_omits_sharing_and_export_all_endpoint(self):
        import io
        import json
        import zipfile
        from django.core.files.uploadedfile import SimpleUploadedFile

        from trips.models import TripShare

        t1 = Trip.objects.create(
            title='Owned One', user=self.user, public_enabled=True, share_token='secret-tok-1',
        )
        Trip.objects.create(title='Owned Two', user=self.user)
        TripShare.objects.create(
            trip=t1, email=self.other.email, user=self.other, role='viewer', invited_by=self.user,
        )

        # Viewer exporting shared trip does NOT receive share_token or shares
        self.client.force_authenticate(self.other)
        v_res = self.client.get(f'/api/trips/trips/{t1.id}/export/')
        self.assertEqual(v_res.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(v_res.content), 'r') as zf:
            payload = json.loads(zf.read('trip.json'))
        exported_t1 = payload['trips'][0]
        self.assertEqual(exported_t1['shares'], [])
        self.assertEqual(exported_t1['share_token'], '')
        self.assertFalse(exported_t1['public_enabled'])

        # User with no owned trips gets 400 from export-all
        empty_res = self.client.get('/api/trips/trips/export-all/')
        self.assertEqual(empty_res.status_code, 400)

        # Owner exports all owned trips into one archive, and other imports both
        self.client.force_authenticate(self.user)
        all_res = self.client.get('/api/trips/trips/export-all/')
        self.assertEqual(all_res.status_code, 200)
        self.assertIn('trips-export.zip', all_res['Content-Disposition'])
        with zipfile.ZipFile(io.BytesIO(all_res.content), 'r') as zf:
            all_payload = json.loads(zf.read('trip.json'))
        self.assertEqual({t['title'] for t in all_payload['trips']}, {'Owned One', 'Owned Two'})

        self.client.force_authenticate(self.other)
        imp = self.client.post('/api/trips/trips/import/', {
            'file': SimpleUploadedFile('trips-export.zip', all_res.content, content_type='application/zip'),
        }, format='multipart')
        self.assertEqual(imp.status_code, 201, imp.data)
        self.assertEqual(imp.data['counts']['trips'], 2)
        self.assertEqual(Trip.objects.filter(user=self.other).count(), 2)

    def test_trip_share_sends_and_resends_invitation_email(self):
        from unittest.mock import patch
        from django.core import mail
        from django.test import override_settings

        from trips.models import TripShare

        trip = Trip.objects.create(
            title='Patagonia Trek',
            user=self.user,
            start_date='2027-02-10',
            end_date='2027-02-18',
        )

        with override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'):
            mail.outbox.clear()
            res = self.client.post('/api/trips/shares/', {
                'trip_id': trip.id,
                'email': 'newfriend@example.com',
                'role': TripShare.ROLE_EDITOR,
            }, format='json')
            self.assertEqual(res.status_code, 201, res.data)
            self.assertTrue(res.data['email_status']['sent'])
            self.assertFalse(res.data['email_status']['console_only'])
            self.assertEqual(res.data['email_status']['error'], '')

            self.assertEqual(len(mail.outbox), 1)
            msg = mail.outbox[0]
            self.assertEqual(msg.to, ['newfriend@example.com'])
            self.assertEqual(msg.reply_to, [self.user.email])
            self.assertIn('Patagonia Trek', msg.subject)
            self.assertIn('Editor', msg.body)
            self.assertIn(f'/app/trips/?trip={trip.id}', msg.body)
            self.assertIn('newfriend@example.com', msg.body)  # pending signup hint
            self.assertEqual(len(msg.alternatives), 1)
            self.assertEqual(msg.alternatives[0][1], 'text/html')

            # Owner can resend invite
            share_id = res.data['id']
            resend = self.client.post(f'/api/trips/shares/{share_id}/resend/', {}, format='json')
            self.assertEqual(resend.status_code, 200, resend.data)
            self.assertTrue(resend.data['email_status']['sent'])
            self.assertEqual(len(mail.outbox), 2)

            # Non-owner cannot resend
            self.client.force_authenticate(self.other)
            denied = self.client.post(f'/api/trips/shares/{share_id}/resend/', {}, format='json')
            self.assertEqual(denied.status_code, 404)

            # SMTP failure does not block creating the share and surfaces the error cleanly
            self.client.force_authenticate(self.user)
            with patch('django.core.mail.EmailMultiAlternatives.send', side_effect=OSError('SMTP refused')):
                res2 = self.client.post('/api/trips/shares/', {
                    'trip_id': trip.id,
                    'email': self.other.email,
                    'role': TripShare.ROLE_VIEWER,
                }, format='json')
            self.assertEqual(res2.status_code, 201, res2.data)
            self.assertFalse(res2.data['email_status']['sent'])
            self.assertIn('SMTP refused', res2.data['email_status']['error'])
            self.assertTrue(TripShare.objects.filter(trip=trip, email=self.other.email).exists())








