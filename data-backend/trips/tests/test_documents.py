from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from trips.models import Trip, TripDay, TripLodging, TripStop, TripStopAttachment

User = get_user_model()


class UploadedDocumentsTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='docs', password='secret', email='docs@example.com')
        self.client.force_authenticate(self.user)
        self.trip = Trip.objects.create(title='Thailand', user=self.user)
        day = TripDay.objects.create(user=self.user, trip=self.trip, date='2027-01-08')
        self.flight = TripStop.objects.create(user=self.user, day=day, text='Fly', kind='travel', travel_mode='flight')
        self.hotel = TripLodging.objects.create(user=self.user, trip=self.trip, name='Hotel')
        other = Trip.objects.create(title='Japan', user=self.user)
        other_day = TripDay.objects.create(user=self.user, trip=other, date='2027-05-01')
        self.other_stop = TripStop.objects.create(user=self.user, day=other_day, text='Train')

    def attach(self, url, title, **where):
        return TripStopAttachment.objects.create(user=self.user, kind='document', url=url, title=title, **where)

    def test_lists_each_document_once_with_its_trip(self):
        self.attach('https://example.com/itinerary.pdf', 'Itinerary', stop=self.flight)
        self.attach('https://example.com/itinerary.pdf', 'Itinerary copy', lodging=self.hotel)
        self.attach('https://example.com/passport.pdf', 'Passport', stop=self.other_stop)
        TripStopAttachment.objects.create(user=self.user, kind='url', url='https://example.com', stop=self.flight)
        stranger = User.objects.create_user(username='x', password='secret', email='x@example.com')
        strangers_trip = Trip.objects.create(title='Theirs', user=stranger)
        strangers_day = TripDay.objects.create(user=stranger, trip=strangers_trip, date='2027-01-01')
        strangers_stop = TripStop.objects.create(user=stranger, day=strangers_day, text='X')
        TripStopAttachment.objects.create(user=stranger, kind='document', url='https://example.com/x.pdf', stop=strangers_stop)

        res = self.client.get('/api/trips/attachments/documents/')
        self.assertEqual(res.status_code, 200)
        got = sorted((d['url'], d['trip_title']) for d in res.data)
        self.assertEqual(got, [
            ('https://example.com/itinerary.pdf', 'Thailand'),
            ('https://example.com/passport.pdf', 'Japan'),
        ])

    def test_attaching_an_existing_document_to_another_stop(self):
        self.attach('https://example.com/passport.pdf', 'Passport', stop=self.other_stop)
        res = self.client.post('/api/trips/attachments/', {
            'kind': 'document', 'stop_id': self.flight.id, 'title': 'Passport',
            'url': 'https://example.com/passport.pdf',
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(TripStopAttachment.objects.filter(url='https://example.com/passport.pdf').count(), 2)
