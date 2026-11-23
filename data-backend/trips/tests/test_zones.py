from datetime import date, time

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from trips import zones
from trips.models import Trip, TripDay, TripStop

User = get_user_model()


class TripZoneTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tz', password='secret', email='tz@example.com')
        self.client.force_authenticate(self.user)
        self.trip = Trip.objects.create(title='Thailand', user=self.user, timezone='America/Los_Angeles')
        self.d1 = TripDay.objects.create(user=self.user, trip=self.trip, date='2027-01-08', title='Leave')
        self.d2 = TripDay.objects.create(user=self.user, trip=self.trip, date='2027-01-09', title='Bangkok')

    def stop(self, day, text, order, **kw):
        return TripStop.objects.create(user=self.user, day=day, text=text, sort_order=order, **kw)

    def resolved(self):
        days = list(self.trip.days.order_by('date'))
        return zones.resolve(self.trip, days, {d.id: list(d.stops.order_by('sort_order')) for d in days})

    def test_zone_runs_through_the_trip_and_switches_at_arrival(self):
        lunch = self.stop(self.d1, 'Lunch', 0, start_time='11:00')
        flight = self.stop(self.d1, 'Fly', 1, kind='travel', travel_mode='flight', start_time='13:00',
                           duration_minutes=17 * 60 + 10, arrive_timezone='Asia/Bangkok')
        late = self.stop(self.d1, 'Late snack', 2)
        temple = self.stop(self.d2, 'Temple', 0, start_time='09:00')
        call = self.stop(self.d2, 'Call home', 1, start_time='20:00', timezone='America/Los_Angeles')
        out = self.resolved()

        self.assertEqual(out[self.d1.id].zones, ['America/Los_Angeles', 'Asia/Bangkok'])
        self.assertEqual(out[self.d1.id].stops[lunch.id].zone, 'America/Los_Angeles')
        f = out[self.d1.id].stops[flight.id]
        self.assertEqual((f.zone, f.arrive_zone, f.arrive_time, f.arrive_day_offset),
                         ('America/Los_Angeles', 'Asia/Bangkok', time(21, 10), 1))
        self.assertTrue(out[self.d1.id].stops[late.id].after_overnight)
        self.assertEqual(out[self.d1.id].stops[late.id].zone, 'Asia/Bangkok')
        self.assertEqual(out[self.d2.id].stops[temple.id].zone, 'Asia/Bangkok')
        self.assertEqual(out[self.d2.id].stops[call.id].zone, 'America/Los_Angeles')
        self.assertEqual(out[self.d2.id].zones[0], 'Asia/Bangkok')

    def test_day_zone_overrides_and_flight_back_across_date_line(self):
        self.d2.timezone = 'Asia/Tokyo'
        self.d2.save()
        flight = self.stop(self.d2, 'Tokyo to Honolulu', 0, kind='travel', travel_mode='flight', start_time='21:00',
                           duration_minutes=7 * 60, arrive_timezone='Pacific/Honolulu')
        f = self.resolved()[self.d2.id].stops[flight.id]
        self.assertEqual((f.zone, f.arrive_time, f.arrive_day_offset), ('Asia/Tokyo', time(9, 0), 0))
        flight.start_time = '08:00'
        flight.save()
        f = self.resolved()[self.d2.id].stops[flight.id]
        self.assertEqual((f.arrive_time, f.arrive_day_offset), (time(20, 0), -1))

    def test_abbreviation(self):
        self.assertEqual(zones.abbreviation('America/Los_Angeles', date(2027, 1, 8)), 'PST')
        self.assertEqual(zones.abbreviation('America/Los_Angeles', date(2027, 7, 8)), 'PDT')
        self.assertEqual(zones.abbreviation('Asia/Bangkok', date(2027, 1, 8)), 'GMT+7')
        self.assertEqual(zones.abbreviation('Asia/Kolkata', date(2027, 1, 8)), 'IST')

    def test_api_validates_and_stores_zones(self):
        res = self.client.patch(f'/api/trips/trips/{self.trip.id}/', {'timezone': 'Mars/Olympus'}, format='json')
        self.assertEqual(res.status_code, 400)
        res = self.client.patch(f'/api/trips/days/{self.d2.id}/', {'timezone': 'Asia/Bangkok'}, format='json')
        self.assertEqual((res.status_code, res.data['timezone']), (200, 'Asia/Bangkok'))
        res = self.client.post('/api/trips/stops/', {
            'day_id': self.d1.id, 'text': 'Fly', 'kind': 'travel', 'travel_mode': 'flight',
            'timezone': 'America/Los_Angeles', 'arrive_timezone': 'Asia/Bangkok',
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['arrive_timezone'], 'Asia/Bangkok')
        res = self.client.post('/api/trips/stops/', {
            'day_id': self.d1.id, 'text': 'Dinner', 'arrive_timezone': 'Asia/Bangkok',
        }, format='json')
        self.assertEqual(res.data['arrive_timezone'], '')

    def test_report_labels_zones(self):
        self.stop(self.d1, 'Lunch', 0, start_time='11:00')
        self.stop(self.d1, 'Fly to Bangkok', 1, kind='travel', travel_mode='flight', start_time='13:00',
                  duration_minutes=17 * 60 + 10, arrive_timezone='Asia/Bangkok')
        self.stop(self.d2, 'Temple', 0, start_time='09:00', duration_minutes=90)
        md = self.client.get(f'/api/trips/trips/{self.trip.id}/report/').data['markdown']
        self.assertIn('### Fri Jan 8 — Leave · PST → GMT+7\n', md)
        self.assertIn('- 11:00 AM PST · **Lunch**\n', md)
        self.assertIn('- 1:00 PM PST → 9:10 PM GMT+7 (+1) · **Fly to Bangkok**\n', md)
        self.assertIn('### Sat Jan 9 — Bangkok · GMT+7\n', md)
        self.assertIn('- 9:00 AM - 10:30 AM · **Temple**\n', md)
