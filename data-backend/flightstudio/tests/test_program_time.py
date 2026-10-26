import math
import unittest

from flightstudio.core.program import (
    ArcSegment,
    Direction,
    GeoPoint,
    LineToSegment,
    MoveToSegment,
    PathProgram,
    VelocityProfile,
)
from flightstudio.core.program_geom import ProgramError
from flightstudio.core.program_time import (
    MIN_SPEED_MS,
    RATE_WINDOW_S,
    TimedProgram,
    duration_for,
    fit_duration_holding_entry,
    fit_program_duration,
    fit_scale,
    resolve_profiles,
    sigma_at,
    time_table,
    validate_timing,
)

ORIGIN = GeoPoint(lat=37.8716, lon=-122.2727, alt_ft_msl=2000.0)


def program(*segments) -> PathProgram:
    return PathProgram(origin=ORIGIN, segments=list(segments))


def line(distance_m=1000.0, speed=100.0, **extra):
    velocity = extra.pop("velocity", VelocityProfile(c0=speed, inherit_entry=False))
    return LineToSegment(distance_m=distance_m, velocity=velocity, **extra)


class VelocityProfileTests(unittest.TestCase):
    def test_constant_profile_is_distance_over_speed(self):
        profile = VelocityProfile(c0=50.0)
        self.assertAlmostEqual(duration_for(1000.0, profile), 20.0, places=6)

    def test_duration_is_linear_in_length(self):
        profile = VelocityProfile(c0=80.0, c1=20.0, c2=-10.0)
        single = duration_for(1000.0, profile)
        self.assertAlmostEqual(duration_for(3000.0, profile), 3.0 * single, places=6)

    def test_endpoint_speeds_are_the_coefficients(self):
        profile = VelocityProfile(c0=60.0, c1=10.0, c2=5.0, c3=-5.0)
        self.assertAlmostEqual(profile.entry_speed, 60.0)
        self.assertAlmostEqual(profile.exit_speed, 70.0)
        self.assertAlmostEqual(profile.speed_at(1.0), profile.exit_speed)

    def test_linear_ramp_matches_the_closed_form(self):
        """v = a + b*sigma integrates to L/b * ln((a+b)/a), which pins the quadrature."""
        a, b, length = 50.0, 50.0, 2000.0
        profile = VelocityProfile(c0=a, c1=b)
        expected = length / b * math.log((a + b) / a)
        self.assertAlmostEqual(duration_for(length, profile), expected, places=7)

    def test_scaling_all_coefficients_divides_the_duration(self):
        """The identity in section 6.2 that makes a duration fit a division."""
        profile = VelocityProfile(c0=90.0, c1=30.0, c2=-20.0, c3=10.0)
        base = duration_for(5000.0, profile)
        for k in (0.5, 1.25, 3.0):
            self.assertAlmostEqual(duration_for(5000.0, profile.scaled(k)), base / k, places=7)

    def test_minimum_of_a_cubic_is_found_exactly(self):
        # v = 100 - 120*sigma + 120*sigma**2 dips to 70 at sigma = 0.5.
        profile = VelocityProfile(c0=100.0, c1=-120.0, c2=120.0)
        slowest, where = profile.minimum_speed()
        self.assertAlmostEqual(slowest, 70.0, places=9)
        self.assertAlmostEqual(where, 0.5, places=9)

    def test_monotone_profile_takes_its_minimum_at_an_end(self):
        slowest, where = VelocityProfile(c0=100.0, c1=-40.0).minimum_speed()
        self.assertAlmostEqual(slowest, 60.0, places=9)
        self.assertAlmostEqual(where, 1.0, places=9)


class TimeInversionTests(unittest.TestCase):
    def test_sigma_at_spans_the_segment(self):
        table = time_table(1000.0, VelocityProfile(c0=50.0))
        self.assertAlmostEqual(sigma_at(table, 0.0), 0.0, places=9)
        self.assertAlmostEqual(sigma_at(table, table[-1]), 1.0, places=9)

    def test_constant_speed_moves_uniformly(self):
        table = time_table(1000.0, VelocityProfile(c0=50.0))
        self.assertAlmostEqual(sigma_at(table, 10.0), 0.5, places=6)

    def test_inversion_round_trips_a_curved_profile(self):
        profile = VelocityProfile(c0=40.0, c1=120.0, c2=-60.0)
        table = time_table(3000.0, profile)
        for fraction in (0.1, 0.25, 0.5, 0.75, 0.9):
            seconds = table[-1] * fraction
            sigma = sigma_at(table, seconds)
            # Re-integrating to that sigma must land back on the same instant.
            self.assertAlmostEqual(
                duration_for(3000.0 * sigma, _restricted(profile, sigma)), seconds, places=2
            )

    def test_a_slow_start_covers_less_ground_early(self):
        profile = VelocityProfile(c0=20.0, c1=160.0)
        table = time_table(2000.0, profile)
        self.assertLess(sigma_at(table, table[-1] * 0.5), 0.5)


def _restricted(profile: VelocityProfile, sigma: float) -> VelocityProfile:
    """The same speed law re-normalised onto [0, sigma], for round-trip checks."""
    return VelocityProfile(
        c0=profile.c0,
        c1=profile.c1 * sigma,
        c2=profile.c2 * sigma * sigma,
        c3=profile.c3 * sigma * sigma * sigma,
    )


class InheritanceTests(unittest.TestCase):
    def test_entry_speed_comes_from_the_previous_exit(self):
        built = program(
            line(speed=100.0, velocity=VelocityProfile(c0=100.0, c1=40.0, inherit_entry=False)),
            line(velocity=VelocityProfile(c0=10.0, c1=-20.0, inherit_entry=True)),
        )
        first, second = resolve_profiles(built)
        self.assertAlmostEqual(first.exit_speed, 140.0)
        self.assertAlmostEqual(second.entry_speed, 140.0)
        # The shape is kept, so the exit moves with the entry.
        self.assertAlmostEqual(second.exit_speed, 120.0)

    def test_inherit_off_keeps_the_stored_entry(self):
        built = program(
            line(velocity=VelocityProfile(c0=100.0, c1=40.0, inherit_entry=False)),
            line(velocity=VelocityProfile(c0=60.0, inherit_entry=True ^ True)),
        )
        _, second = resolve_profiles(built)
        self.assertAlmostEqual(second.entry_speed, 60.0)

    def test_speed_is_not_carried_across_a_cut(self):
        """A speed carried over a teleport describes nothing, so it is dropped."""
        built = program(
            line(velocity=VelocityProfile(c0=200.0, inherit_entry=False)),
            MoveToSegment(to=GeoPoint(lat=37.82, lon=-122.34),
                          tangent=Direction(heading_deg=90.0)),
            LineToSegment(distance_m=1000.0, inherit_direction=True,
                          velocity=VelocityProfile(c0=70.0, inherit_entry=True)),
        )
        profiles = resolve_profiles(built)
        self.assertIsNone(profiles[1])
        self.assertAlmostEqual(profiles[2].entry_speed, 70.0)

    def test_a_move_to_may_re_seed_the_speed(self):
        built = program(
            line(velocity=VelocityProfile(c0=200.0, inherit_entry=False)),
            MoveToSegment(to=GeoPoint(lat=37.82, lon=-122.34),
                          tangent=Direction(heading_deg=90.0), speed_ms=55.0),
            LineToSegment(distance_m=1000.0, inherit_direction=True,
                          velocity=VelocityProfile(c0=70.0, inherit_entry=True)),
        )
        self.assertAlmostEqual(resolve_profiles(built)[2].entry_speed, 55.0)


class TimelineTests(unittest.TestCase):
    def test_duration_is_the_sum_of_the_segments(self):
        timed = TimedProgram(program(line(1000.0, speed=50.0), line(600.0, speed=30.0)))
        self.assertAlmostEqual(timed.duration_s, 20.0 + 20.0, places=6)

    def test_a_dwell_adds_wall_clock_without_moving_anything(self):
        built = program(line(1000.0, speed=50.0), line(1000.0, speed=50.0))
        built.segments[0].end.dwell_s = 5.0
        timed = TimedProgram(built)
        self.assertAlmostEqual(timed.duration_s, 45.0, places=6)
        self.assertAlmostEqual(timed.dwell_total_s, 5.0)
        self.assertAlmostEqual(timed.flying_s, 40.0, places=6)
        held = timed.pose_at(22.5)
        self.assertAlmostEqual(held.ground_speed_ms, 0.0, places=9)
        # Frozen where the first segment ended.
        end = timed.position_at(20.0 - 1e-9)
        self.assertAlmostEqual(held.lat, end[0], places=6)

    def test_a_cut_costs_no_time(self):
        """Cutting the middle out shortens the take rather than leaving a hole."""
        without = TimedProgram(program(line(1000.0, speed=50.0), line(1000.0, speed=50.0)))
        with_cut = TimedProgram(program(
            line(1000.0, speed=50.0),
            MoveToSegment(to=GeoPoint(lat=37.95, lon=-122.5),
                          tangent=Direction(heading_deg=0.0), speed_ms=50.0),
            LineToSegment(distance_m=1000.0, inherit_direction=True,
                          velocity=VelocityProfile(c0=50.0, inherit_entry=True)),
        ))
        self.assertAlmostEqual(with_cut.duration_s, without.duration_s, places=6)
        self.assertEqual(len(with_cut.seam_times), 1)
        self.assertAlmostEqual(with_cut.seam_times[0], 20.0, places=6)

    def test_pose_at_a_seam_is_right_continuous_with_a_left_limit(self):
        timed = TimedProgram(program(
            line(1000.0, speed=50.0),
            MoveToSegment(to=GeoPoint(lat=37.95, lon=-122.5),
                          tangent=Direction(heading_deg=0.0), speed_ms=50.0),
            LineToSegment(distance_m=1000.0, inherit_direction=True,
                          velocity=VelocityProfile(c0=50.0, inherit_entry=True)),
        ))
        seam = timed.seam_times[0]
        after = timed.pose_at(seam)
        before = timed.pose_at(seam, left_limit=True)
        self.assertTrue(after.after_seam)
        self.assertGreater(abs(after.lat - before.lat), 0.05)
        self.assertAlmostEqual(after.lat, 37.95, places=4)

    def test_speed_follows_the_profile_through_the_segment(self):
        built = program(line(2000.0, velocity=VelocityProfile(c0=50.0, c1=50.0,
                                                              inherit_entry=False)))
        timed = TimedProgram(built)
        self.assertAlmostEqual(timed.ground_speed_at(0.0), 50.0, places=4)
        self.assertAlmostEqual(timed.ground_speed_at(timed.duration_s), 100.0, places=4)

    def test_a_climb_splits_speed_into_ground_speed_and_pitch(self):
        timed = TimedProgram(program(line(2000.0, speed=100.0, climb_deg=30.0)))
        self.assertAlmostEqual(timed.pitch_deg_at(5.0), 30.0, places=4)
        self.assertAlmostEqual(timed.ground_speed_at(5.0),
                               100.0 * math.cos(math.radians(30.0)), places=4)

    def test_a_profile_that_stops_the_clock_is_refused(self):
        built = program(line(1000.0, velocity=VelocityProfile(c0=10.0, c1=-9.5,
                                                              inherit_entry=False)))
        with self.assertRaises(ProgramError) as caught:
            TimedProgram(built)
        self.assertEqual(caught.exception.index, 0)


class BankTests(unittest.TestCase):
    def straight_then_turn(self):
        return TimedProgram(program(
            line(2000.0, speed=80.0),
            ArcSegment(side="LEFT", radius_m=1500.0, sweep_deg=180.0,
                       velocity=VelocityProfile(c0=80.0, inherit_entry=True)),
        ))

    def test_a_straight_leg_is_wings_level(self):
        # 15 s before the turn; only the far tail of the 6 s smoothing reaches.
        self.assertAlmostEqual(self.straight_then_turn().bank_deg_at(10.0), 0.0, delta=0.1)

    def test_a_corner_between_straights_does_not_flick_the_bank(self):
        """Two lines at different headings meet in a corner. The raw turn rate
        there is near-infinite; the limiter and smoothing keep it to a nudge."""
        timed = TimedProgram(program(
            line(1200.0, speed=100.0, heading_deg=131.26),
            LineToSegment(heading_deg=127.39, distance_m=1000.0,
                          velocity=VelocityProfile(c0=100.0, inherit_entry=True)),
        ))
        corner = timed.segment_start_s(1)
        worst = max(abs(timed.bank_deg_at(corner + k * 0.05)) for k in range(-40, 41))
        self.assertLess(worst, 3.0)
        # Heading eases through the corner instead of stepping in one frame.
        steps = [abs(timed.pose_at(corner + (k + 1) * 0.05).heading_deg_true
                     - timed.pose_at(corner + k * 0.05).heading_deg_true)
                 for k in range(-40, 40)]
        self.assertLess(max(steps), 0.5)

    def test_a_turn_banks_the_coordinated_amount(self):
        timed = self.straight_then_turn()
        # phi = atan(v**2 / (r*g)) for a steady turn at this radius and speed.
        expected = math.degrees(math.atan2(80.0 * 80.0 / 1500.0, 9.80665))
        mid_turn = timed.duration_s - timed.segment_duration(1) / 2.0
        self.assertAlmostEqual(timed.bank_deg_at(mid_turn), -expected, places=1)

    def test_bank_is_held_to_the_path_limit(self):
        timed = TimedProgram(program(
            line(500.0, speed=200.0),
            ArcSegment(side="RIGHT", radius_m=250.0, sweep_deg=180.0,
                       velocity=VelocityProfile(c0=200.0, inherit_entry=True)),
        ))
        limit = timed.program.auto_bank.max_deg
        worst = max(abs(timed.bank_deg_at(t * timed.duration_s / 40.0)) for t in range(41))
        self.assertLessEqual(worst, limit + 1e-9)

    def test_a_seam_produces_no_bank_spike(self):
        """The reason rates are one-sided: a window spanning a jump reads a
        near-infinite turn rate and would throw the bank hard over."""
        timed = TimedProgram(program(
            line(2000.0, speed=80.0),
            # Reverses direction as well as teleporting, so a two-sided window
            # across the seam would see 180 degrees of heading change at once.
            MoveToSegment(to=GeoPoint(lat=38.05, lon=-122.6),
                          tangent=Direction(heading_deg=180.0), speed_ms=80.0),
            LineToSegment(distance_m=2000.0, inherit_direction=True,
                          velocity=VelocityProfile(c0=80.0, inherit_entry=True)),
        ))
        seam = timed.seam_times[0]
        for offset in (-4.0, -1.0, -0.5, -RATE_WINDOW_S, -1e-6,
                       0.0, 1e-6, RATE_WINDOW_S, 0.5, 1.0, 4.0):
            moment = seam + offset
            self.assertAlmostEqual(
                timed.bank_deg_at(moment), 0.0, places=6,
                msg=f"bank spiked {timed.bank_deg_at(moment):.3f} deg at seam{offset:+}s",
            )

    def test_the_turn_rate_window_never_spans_a_seam(self):
        timed = TimedProgram(program(
            line(2000.0, speed=80.0),
            MoveToSegment(to=GeoPoint(lat=38.05, lon=-122.6),
                          tangent=Direction(heading_deg=270.0), speed_ms=80.0),
            LineToSegment(distance_m=2000.0, inherit_direction=True,
                          velocity=VelocityProfile(c0=80.0, inherit_entry=True)),
        ))
        seam = timed.seam_times[0]
        self.assertAlmostEqual(timed.turn_rate_rads(seam), 0.0, places=9)
        self.assertAlmostEqual(timed.turn_rate_rads(seam - RATE_WINDOW_S / 2), 0.0, places=9)


class DurationFitTests(unittest.TestCase):
    def test_fitting_a_segment_is_a_division(self):
        profile = VelocityProfile(c0=70.0, c1=40.0, c2=-15.0)
        current = duration_for(4000.0, profile)
        retimed = profile.scaled(fit_scale(current, 25.0))
        self.assertAlmostEqual(duration_for(4000.0, retimed), 25.0, places=7)

    def test_fitting_a_program_hits_the_target(self):
        built = program(
            line(3000.0, velocity=VelocityProfile(c0=90.0, c1=30.0, inherit_entry=False)),
            ArcSegment(side="LEFT", radius_m=900.0, sweep_deg=270.0,
                       velocity=VelocityProfile(c0=80.0, inherit_entry=True)),
            line(1500.0, velocity=VelocityProfile(c0=60.0, inherit_entry=True)),
        )
        retimed = fit_program_duration(built, 120.0)
        self.assertAlmostEqual(TimedProgram(retimed).duration_s, 120.0, places=5)

    def test_fitting_scales_a_re_seeded_speed_too(self):
        """A re-seed left unscaled makes everything after a cut fly at the old pace."""
        built = program(
            line(2500.0, speed=100.0),
            MoveToSegment(to=GeoPoint(lat=37.95, lon=-122.5),
                          tangent=Direction(heading_deg=90.0), speed_ms=100.0),
            LineToSegment(distance_m=2500.0, inherit_direction=True,
                          velocity=VelocityProfile(c0=100.0, inherit_entry=True)),
        )
        self.assertAlmostEqual(TimedProgram(built).duration_s, 50.0, places=5)
        retimed = fit_program_duration(built, 30.0)
        self.assertAlmostEqual(TimedProgram(retimed).duration_s, 30.0, places=5)
        self.assertAlmostEqual(retimed.segments[1].speed_ms, 100.0 * 50.0 / 30.0, places=6)

    def test_fitting_leaves_dwells_alone(self):
        built = program(line(3000.0, speed=60.0), line(3000.0, speed=60.0))
        built.segments[0].end.dwell_s = 12.0
        retimed = fit_program_duration(built, 100.0)
        timed = TimedProgram(retimed)
        self.assertAlmostEqual(timed.duration_s, 100.0, places=5)
        self.assertAlmostEqual(timed.dwell_total_s, 12.0)
        self.assertAlmostEqual(timed.flying_s, 88.0, places=5)

    def test_a_target_shorter_than_the_dwells_is_refused(self):
        built = program(line(1000.0, speed=50.0))
        built.segments[0].end.dwell_s = 30.0
        with self.assertRaises(ValueError):
            fit_program_duration(built, 10.0)

    def test_holding_the_entry_speed_still_hits_the_target(self):
        profile = VelocityProfile(c0=60.0, c1=60.0)
        retimed = fit_duration_holding_entry(2000.0, profile, 25.0)
        self.assertAlmostEqual(retimed.entry_speed, 60.0, places=9)
        self.assertAlmostEqual(duration_for(2000.0, retimed), 25.0, places=4)

    def test_an_unreachable_target_with_a_held_entry_is_refused(self):
        profile = VelocityProfile(c0=60.0, c1=60.0)
        with self.assertRaises(ValueError):
            fit_duration_holding_entry(2000.0, profile, 500.0)


class ValidationTests(unittest.TestCase):
    def test_a_clean_program_reports_nothing(self):
        self.assertEqual(validate_timing(program(line(1000.0, speed=60.0))), [])

    def test_a_dipping_profile_is_reported_with_its_segment(self):
        built = program(
            line(1000.0, speed=60.0),
            line(1000.0, velocity=VelocityProfile(c0=10.0, c1=-9.9, inherit_entry=False)),
        )
        issues = validate_timing(built)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["index"], 1)
        self.assertEqual(issues[0]["code"], "SPEED_TOO_LOW")

    def test_the_floor_is_what_decides(self):
        built = program(line(1000.0, velocity=VelocityProfile(
            c0=MIN_SPEED_MS * 1.5, inherit_entry=False)))
        self.assertEqual(validate_timing(built), [])

    def test_a_manual_boundary_angle_is_flagged_as_not_yet_applied(self):
        from flightstudio.core.schema import ManualAngle
        built = program(line(1000.0, speed=60.0))
        built.segments[0].end.bank = ManualAngle(deg=15.0)
        codes = [issue["code"] for issue in validate_timing(built)]
        self.assertIn("ANGLE_PIN_IGNORED", codes)


if __name__ == "__main__":
    unittest.main()
