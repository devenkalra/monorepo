import json
from unittest import mock

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from trips import ai
from trips.models import Trip, TripDay, TripLodging, TripStop, TripSuggestion, TripSuggestionBatch
from trips.tasks import generate_suggestions

User = get_user_model()


def _reply(*items):
    return json.dumps({'suggestions': list(items)})


class TripAssistantTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tripper', password='secret', email='trip@example.com')
        self.other = User.objects.create_user(username='other', password='secret', email='other@example.com')
        self.client.force_authenticate(self.user)
        self.trip = Trip.objects.create(title='Italy', user=self.user, description='Family trip by rail.')
        self.d1 = TripDay.objects.create(user=self.user, trip=self.trip, date='2027-05-14', title='Milan')
        self.d2 = TripDay.objects.create(user=self.user, trip=self.trip, date='2027-05-15', title='Varenna')
        TripStop.objects.create(user=self.user, day=self.d1, text='Duomo di Milano', start_time='12:30',
                                duration_minutes=120, loc='Piazza del Duomo')

    def _batch(self, day=None, prompt='Things to do'):
        return TripSuggestionBatch.objects.create(user=self.user, trip=self.trip, day=day, prompt=prompt)

    def test_context_lists_days_items_and_focus(self):
        text = ai.build_context(self.trip, self.d2)
        self.assertIn(f'day_id={self.d1.id} Fri 2027-05-14 "Milan"', text)
        self.assertIn('12:30 for 120 min [activity] Duomo di Milano @ Piazza del Duomo', text)
        self.assertIn(f'Focus on day_id={self.d2.id}', text)

    def test_parse_cleans_and_drops_bad_rows(self):
        raw = '<think>hmm</think>Sure! ' + _reply(
            {'kind': 'Hotel', 'name': 'Albergo Milano', 'day_ids': [self.d2.id, 9999], 'check_in_time': '3:00 PM',
             'url': 'javascript:alert(1)'},
            {'kind': 'activity', 'title': 'Villa Monastero', 'day_id': self.d2.id, 'start_time': '11:30',
             'duration_minutes': '90', 'url': 'https://villamonastero.eu'},
            {'kind': 'event', 'name': 'Pasta class', 'day_id': 9999, 'start_time': '25:00', 'needs_booking': True},
            {'kind': 'stop', 'name': 'duomo di milano'},
            {'kind': 'spaceship', 'name': 'Nope'},
            {'kind': 'stop', 'name': ''},
            {'kind': 'stop', 'name': 'Villa Monastero'},
        )
        rows = ai.parse_suggestions(raw, self.trip)
        self.assertEqual([(k, d['name']) for k, d in rows], [
            ('lodging', 'Albergo Milano'), ('stop', 'Villa Monastero'), ('event', 'Pasta class'), ('stop', 'duomo di milano'),
        ])
        lodging, stop, event, dup = (d for _, d in rows)
        self.assertEqual((lodging['day_ids'], lodging['check_in_time'], lodging['url']), ([self.d2.id], '03:00', ''))
        self.assertEqual((stop['day_id'], stop['start_time'], stop['duration_minutes']), (self.d2.id, '11:30', 90))
        self.assertEqual((event['day_id'], event['start_time'], event['needs_booking']), (None, None, True))
        self.assertTrue(dup['already_planned'])
        self.assertFalse(stop['already_planned'])

    def test_parse_handles_garbage(self):
        self.assertEqual(ai.parse_suggestions('not json at all', self.trip), [])
        self.assertEqual(ai.parse_suggestions('{"suggestions": "nope"}', self.trip), [])

    def test_task_stores_suggestions(self):
        batch = self._batch(day=self.d2)
        reply = _reply({'kind': 'stop', 'name': 'Bellagio', 'day_id': self.d2.id})
        with mock.patch.object(ai, 'chat_completion', return_value=reply) as chat:
            generate_suggestions(batch.id)
        self.assertIn('Request: Things to do', chat.call_args.kwargs['prompt'])
        batch.refresh_from_db()
        self.assertEqual(batch.status, 'done')
        self.assertEqual([s.data['name'] for s in batch.suggestions.all()], ['Bellagio'])

    def test_task_records_failure(self):
        batch = self._batch()
        with mock.patch.object(ai, 'chat_completion', side_effect=RuntimeError('model down')):
            generate_suggestions(batch.id)
        batch.refresh_from_db()
        self.assertEqual((batch.status, batch.error), ('failed', 'model down'))

        batch = self._batch()
        with mock.patch.object(ai, 'chat_completion', return_value='{}'):
            generate_suggestions(batch.id)
        batch.refresh_from_db()
        self.assertEqual(batch.status, 'failed')
        self.assertIn('usable suggestions', batch.error)

    @mock.patch('trips.views.llm_available', return_value=True)
    @mock.patch('trips.views.generate_suggestions')
    def test_create_batch_queues_task(self, task, _available):
        with self.captureOnCommitCallbacks(execute=True):
            res = self.client.post('/api/trips/assistant/', {
                'trip_id': self.trip.id, 'day_id': self.d2.id, 'prompt': 'Hotels in Varenna',
            }, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['status'], 'running')
        task.delay.assert_called_once_with(res.data['id'])

        theirs = Trip.objects.create(title='Theirs', user=self.other)
        res = self.client.post('/api/trips/assistant/', {'trip_id': theirs.id, 'prompt': 'x'}, format='json')
        self.assertEqual(res.status_code, 400)
        other_day = TripDay.objects.create(user=self.user, trip=Trip.objects.create(title='B', user=self.user),
                                           date='2027-01-01')
        res = self.client.post('/api/trips/assistant/', {
            'trip_id': self.trip.id, 'day_id': other_day.id, 'prompt': 'x',
        }, format='json')
        self.assertEqual(res.status_code, 400)

    @mock.patch('trips.views.llm_available', return_value=False)
    def test_create_batch_without_model(self, _available):
        res = self.client.post('/api/trips/assistant/', {'trip_id': self.trip.id, 'prompt': 'x'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(TripSuggestionBatch.objects.exists())

    def test_apply_event_creates_stop_with_link(self):
        batch = self._batch()
        sug = TripSuggestion.objects.create(user=self.user, batch=batch, kind='event', data={
            'name': 'Pasta class', 'address': 'Via XX Settembre 18', 'url': 'https://lucia.test', 'description': 'Make pasta.',
            'why': 'Fun with kids', 'price_hint': '$$', 'category': 'Food', 'day_id': self.d2.id,
            'start_time': '18:00', 'needs_booking': True,
        })
        res = self.client.post(f'/api/trips/suggestions/{sug.id}/apply/', {}, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        stop = TripStop.objects.get(pk=res.data['stop_id'])
        self.assertEqual((stop.day_id, stop.kind, stop.text, stop.loc, stop.cat, stop.status, str(stop.start_time)),
                         (self.d2.id, 'event', 'Pasta class', 'Via XX Settembre 18', 'Food', 'tobook', '18:00:00'))
        self.assertEqual(stop.description, 'Make pasta.\n\n*Why:* Fun with kids\n\nPrice: $$')
        self.assertEqual(stop.extra, {'ai_suggestion_id': sug.id})
        self.assertEqual(list(stop.attachments.values_list('kind', 'url')), [
            ('url', 'https://lucia.test'),
            ('location', 'https://www.google.com/maps/search/?api=1&query=Pasta+class%2C+Via+XX+Settembre+18'),
        ])
        self.assertEqual(res.data['status'], 'added')

        res = self.client.post(f'/api/trips/suggestions/{sug.id}/apply/', {}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_apply_stop_with_user_edits_and_day_checks(self):
        batch = self._batch()
        sug = TripSuggestion.objects.create(user=self.user, batch=batch, kind='stop', data={
            'name': 'Bellagio', 'day_id': None, 'duration_minutes': 120,
        })
        res = self.client.post(f'/api/trips/suggestions/{sug.id}/apply/', {}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('day_id', res.data)

        foreign = TripDay.objects.create(user=self.other, trip=Trip.objects.create(title='T', user=self.other),
                                         date='2027-01-01')
        res = self.client.post(f'/api/trips/suggestions/{sug.id}/apply/', {'fields': {'day_id': foreign.id}}, format='json')
        self.assertEqual(res.status_code, 400)

        res = self.client.post(f'/api/trips/suggestions/{sug.id}/apply/', {
            'fields': {'day_id': self.d2.id, 'text': 'Bellagio walk', 'start_time': '14:00', 'user': self.other.id},
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        stop = TripStop.objects.get(pk=res.data['stop_id'])
        self.assertEqual((stop.user_id, stop.day_id, stop.text, stop.duration_minutes, stop.sort_order),
                         (self.user.id, self.d2.id, 'Bellagio walk', 120, 0))

    def test_apply_lodging_assigns_nights(self):
        batch = self._batch()
        sug = TripSuggestion.objects.create(user=self.user, batch=batch, kind='lodging', data={
            'name': 'Albergo Milano', 'address': 'Varenna', 'url': 'https://albergo.test', 'description': 'Lake views',
            'day_ids': [self.d2.id], 'check_in_time': '15:00', 'check_out_time': None,
        })
        res = self.client.post(f'/api/trips/suggestions/{sug.id}/apply/', {}, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        lodging = TripLodging.objects.get(pk=res.data['lodging_id'])
        self.assertEqual((lodging.trip_id, lodging.url, lodging.notes), (self.trip.id, 'https://albergo.test', 'Lake views'))
        self.d2.refresh_from_db()
        self.assertEqual(self.d2.lodging_id, lodging.id)

    def test_dismiss_and_isolation(self):
        sug = TripSuggestion.objects.create(user=self.user, batch=self._batch(), kind='stop', data={'name': 'X'})
        res = self.client.post(f'/api/trips/suggestions/{sug.id}/dismiss/')
        self.assertEqual(res.data['status'], 'dismissed')

        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.post(f'/api/trips/suggestions/{sug.id}/apply/', {}, format='json').status_code, 404)
        self.assertEqual(self.client.get(f'/api/trips/assistant/?trip={self.trip.id}').data, [])

    def test_list_batches_for_trip(self):
        batch = self._batch(prompt='Hotels')
        TripSuggestion.objects.create(user=self.user, batch=batch, kind='lodging', data={'name': 'Albergo'})
        res = self.client.get(f'/api/trips/assistant/?trip={self.trip.id}')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data[0]['prompt'], 'Hotels')
        self.assertEqual(res.data[0]['suggestions'][0]['data']['name'], 'Albergo')
        self.assertEqual(res.data[0]['suggestions'][0]['draft']['name'], 'Albergo')
        self.assertEqual(res.data[0]['suggestions'][0]['draft']['day_ids'], [])
        self.assertEqual(res.data[0]['suggestions'][0]['maps_url'],
                         'https://www.google.com/maps/search/?api=1&query=Albergo')
