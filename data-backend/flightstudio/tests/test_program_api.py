from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

User = get_user_model()

URL = '/api/flightstudio/program/evaluate/'
ORIGIN = {'lat': 37.8716, 'lon': -122.2727, 'alt_ft_msl': 2000.0}


def program(*segments):
    return {'origin': ORIGIN, 'segments': list(segments)}


LINE = {'kind': 'LINE_TO', 'heading_deg': 0.0, 'distance_m': 1000.0}


class EvaluateProgramTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='flyer', password='secret', email='flyer@example.com'
        )

    def post(self, body):
        return self.client.post(URL, body, format='json')

    def test_unauthenticated_rejected(self):
        self.assertIn(self.post(program(LINE)).status_code, (401, 403))

    def test_evaluates_a_program(self):
        self.client.force_authenticate(self.user)
        response = self.post({'program': program(
            LINE,
            {'kind': 'ARC', 'side': 'LEFT', 'radius_m': 500.0, 'sweep_deg': 90.0},
        )})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data['segments']), 2)
        self.assertTrue(response.data['samples'])
        self.assertAlmostEqual(response.data['length_m'], 1000.0 + 500.0 * 3.14159265 / 2, places=1)

    def test_accepts_a_bare_program_body(self):
        """The harness posts {program, step_m}; a bare program should work too."""
        self.client.force_authenticate(self.user)
        self.assertEqual(self.post(program(LINE)).status_code, 200)

    def test_arc_reports_its_derived_centre_and_rise(self):
        self.client.force_authenticate(self.user)
        response = self.post({'program': program(
            {'kind': 'LINE_TO', 'heading_deg': 0.0, 'climb_deg': 6.0, 'distance_m': 500.0},
            {'kind': 'ARC', 'side': 'LEFT', 'radius_m': 600.0, 'sweep_deg': 720.0},
        )})
        arc = response.data['segments'][1]['arc']
        self.assertAlmostEqual(arc['turns'], 2.0, places=4)
        self.assertTrue(arc['rise_is_default'])
        # The rise was matched to the pen, so it climbed rather than staying level.
        self.assertGreater(arc['rise_per_turn_m'], 0.0)
        self.assertIn('lat', arc['center'])

    def test_a_cut_marks_the_following_segment(self):
        self.client.force_authenticate(self.user)
        response = self.post({'program': program(
            LINE,
            {'kind': 'MOVE_TO', 'to': {'lat': 37.82, 'lon': -122.34, 'alt_ft_msl': 4500.0},
             'tangent': {'heading_deg': 90.0, 'climb_deg': 0.0}},
            {'kind': 'LINE_TO', 'distance_m': 1000.0, 'inherit_direction': True},
        )})
        segments = response.data['segments']
        self.assertFalse(segments[1]['seam'])
        self.assertTrue(segments[2]['seam'])
        breaks = [row for row in response.data['samples'] if row['break_before']]
        self.assertEqual(len(breaks), 1)

    def test_unsolvable_segment_reports_its_index(self):
        self.client.force_authenticate(self.user)
        response = self.post({'program': program(
            {'kind': 'ARC', 'side': 'LEFT', 'radius_m': 500.0, 'sweep_deg': 90.0},
        )})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['index'], 0)

    def test_invalid_parameters_report_their_segment(self):
        self.client.force_authenticate(self.user)
        response = self.post({'program': program(
            LINE,
            {'kind': 'ARC', 'side': 'LEFT', 'radius_m': -5.0, 'sweep_deg': 90.0},
        )})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['index'], 1)
        self.assertTrue(response.data['errors'])

    def test_samples_and_segments_carry_timing(self):
        self.client.force_authenticate(self.user)
        response = self.post({'program': program(
            {'kind': 'LINE_TO', 'heading_deg': 0.0, 'distance_m': 1000.0,
             'velocity': {'c0': 50.0, 'inherit_entry': False}},
        )})
        self.assertAlmostEqual(response.data['duration_s'], 20.0, places=3)
        timing = response.data['segments'][0]['timing']
        self.assertAlmostEqual(timing['duration_s'], 20.0, places=3)
        self.assertAlmostEqual(timing['entry_speed_ms'], 50.0, places=3)
        first, last = response.data['samples'][0], response.data['samples'][-1]
        self.assertAlmostEqual(first['t'], 0.0, places=3)
        self.assertAlmostEqual(last['t'], 20.0, places=3)
        self.assertAlmostEqual(last['speed_ms'], 50.0, places=3)

    def test_a_dwell_gets_samples_of_its_own(self):
        """Sampling is by distance and a hold covers none, so it needs rows."""
        self.client.force_authenticate(self.user)
        response = self.post({'program': program(
            {'kind': 'LINE_TO', 'heading_deg': 0.0, 'distance_m': 1000.0,
             'velocity': {'c0': 50.0, 'inherit_entry': False},
             'end': {'dwell_s': 8.0}},
            {'kind': 'LINE_TO', 'heading_deg': 0.0, 'distance_m': 1000.0,
             'inherit_direction': True},
        )})
        held = [row for row in response.data['samples'] if row['hold']]
        self.assertEqual([row['t'] for row in held], [20.0, 28.0])
        self.assertEqual({row['speed_ms'] for row in held}, {0.0})
        # Frozen in place, not interpolated towards the next segment.
        self.assertEqual(held[0]['lat'], held[1]['lat'])

    def test_a_profile_that_stops_the_clock_reports_its_segment(self):
        self.client.force_authenticate(self.user)
        response = self.post({'program': program(
            LINE,
            {'kind': 'LINE_TO', 'heading_deg': 0.0, 'distance_m': 1000.0,
             'velocity': {'c0': 10.0, 'c1': -9.9, 'inherit_entry': False}},
        )})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['index'], 1)

    def test_fitting_a_duration_returns_the_retimed_program(self):
        self.client.force_authenticate(self.user)
        response = self.post({
            'program': program(
                {'kind': 'LINE_TO', 'heading_deg': 0.0, 'distance_m': 3000.0,
                 'velocity': {'c0': 50.0, 'inherit_entry': False}},
                {'kind': 'ARC', 'side': 'LEFT', 'radius_m': 600.0, 'sweep_deg': 180.0},
            ),
            'fit_duration_s': 45.0,
        })
        self.assertEqual(response.status_code, 200, response.data)
        self.assertAlmostEqual(response.data['duration_s'], 45.0, places=3)
        # The returned program must actually reproduce the fitted duration.
        again = self.post({'program': response.data['solved_program']})
        self.assertAlmostEqual(again.data['duration_s'], 45.0, places=3)

    def test_a_constrained_segment_comes_back_solved(self):
        self.client.force_authenticate(self.user)
        response = self.post({'program': program(
            {'kind': 'LINE_TO', 'heading_deg': 0.0, 'distance_m': 100.0,
             'constraints': [{'lat': 37.8797, 'lon': -122.2625,
                              'alt_ft_msl': 2000.0}]},
        )})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['constrained'])
        solvability = response.data['segments'][0]['solvability']
        self.assertEqual(solvability['state'], 'DETERMINED')
        self.assertEqual(solvability['method'], 'closed form')
        # Stored at 100 m, solved to reach a target about 1.3 km away.
        solved = response.data['solved_program']['segments'][0]
        self.assertGreater(solved['distance_m'], 1000.0)
        self.assertAlmostEqual(response.data['segments'][0]['end']['lat'],
                               37.8797, places=5)

    def test_an_under_determined_segment_says_how_short_it_is(self):
        self.client.force_authenticate(self.user)
        response = self.post({'program': program(
            LINE,
            {'kind': 'ARC', 'side': 'LEFT', 'radius_m': 600.0, 'sweep_deg': 90.0,
             'constraints': [{'lat': 37.8790, 'lon': -122.2790,
                              'lock_vertical': False}]},
        )})
        solvability = response.data['segments'][1]['solvability']
        self.assertEqual(solvability['state'], 'UNDER_DETERMINED')
        self.assertEqual(solvability['short_by'], 1)
        self.assertIn('under-determined by 1', solvability['detail'])

    def test_contradictory_pins_report_how_far_off_they_are(self):
        self.client.force_authenticate(self.user)
        response = self.post({'program': program(
            {'kind': 'LINE_TO', 'heading_deg': 0.0, 'distance_m': 100.0,
             'pinned': ['heading_deg', 'climb_deg', 'distance_m'],
             'constraints': [{'lat': 37.8797, 'lon': -122.2625,
                              'alt_ft_msl': 2000.0}]},
        )})
        solvability = response.data['segments'][0]['solvability']
        self.assertEqual(solvability['state'], 'CONTRADICTORY')
        self.assertGreater(solvability['residual_m'], 500.0)

    def test_a_pin_the_segment_does_not_have_is_rejected(self):
        self.client.force_authenticate(self.user)
        response = self.post({'program': program(
            {'kind': 'LINE_TO', 'heading_deg': 0.0, 'distance_m': 100.0,
             'pinned': ['radius_m']},
        )})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['index'], 0)

    def test_an_unconstrained_program_is_left_exactly_as_posted(self):
        self.client.force_authenticate(self.user)
        response = self.post({'program': program(
            {'kind': 'LINE_TO', 'heading_deg': 33.0, 'climb_deg': 4.0,
             'distance_m': 1234.0},
        )})
        self.assertFalse(response.data['constrained'])
        solved = response.data['solved_program']['segments'][0]
        self.assertEqual(solved['heading_deg'], 33.0)
        self.assertEqual(solved['distance_m'], 1234.0)
        self.assertEqual(response.data['segments'][0]['solvability']['state'],
                         'UNCONSTRAINED')

    def test_an_impossible_duration_fit_is_refused(self):
        self.client.force_authenticate(self.user)
        response = self.post({
            'program': program({'kind': 'LINE_TO', 'heading_deg': 0.0,
                                'distance_m': 1000.0, 'end': {'dwell_s': 30.0}}),
            'fit_duration_s': 10.0,
        })
        self.assertEqual(response.status_code, 400)

    def test_a_manual_boundary_angle_surfaces_as_an_issue(self):
        self.client.force_authenticate(self.user)
        response = self.post({'program': program(
            {'kind': 'LINE_TO', 'heading_deg': 0.0, 'distance_m': 1000.0,
             'end': {'bank': {'mode': 'MANUAL', 'deg': 12.0}}},
        )})
        codes = [issue['code'] for issue in response.data['issues']]
        self.assertIn('ANGLE_PIN_IGNORED', codes)

    def test_step_is_held_to_a_sane_sample_count(self):
        """A fine step on a long path must not be allowed to wedge the browser."""
        self.client.force_authenticate(self.user)
        response = self.post({'program': program(
            {'kind': 'LINE_TO', 'heading_deg': 0.0, 'distance_m': 20000.0},
            {'kind': 'ARC', 'side': 'LEFT', 'radius_m': 10000.0, 'sweep_deg': 1440.0},
        ), 'step_m': 0.01})
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.data['samples']), 20010)
        self.assertGreater(response.data['step_m'], 0.01)
