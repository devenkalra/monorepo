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
from flightstudio.core.program_geom import (
    ProgramError,
    direction_angles,
    evaluate,
    sample_by_distance,
)

ORIGIN = GeoPoint(lat=37.8, lon=-122.4, alt_ft_msl=2000.0)


def program(*segments) -> PathProgram:
    return PathProgram(origin=ORIGIN, segments=list(segments))


def north_line(distance_m: float = 1000.0) -> LineToSegment:
    return LineToSegment(heading_deg=0.0, distance_m=distance_m)


class LineTests(unittest.TestCase):
    def test_line_runs_the_stated_distance_on_the_stated_heading(self):
        solved = evaluate(program(north_line(1000.0)))
        geometry = solved.segments[0]
        self.assertAlmostEqual(geometry.length_m, 1000.0)
        # Heading 0 is due north, so east is untouched and north is the run.
        self.assertAlmostEqual(geometry.end[0], 0.0, places=6)
        self.assertAlmostEqual(geometry.end[2], 1000.0, places=6)

    def test_climb_raises_the_end(self):
        solved = evaluate(program(
            LineToSegment(heading_deg=90.0, climb_deg=30.0, distance_m=200.0)))
        end = solved.segments[0].end
        start_up = solved.segments[0].start[1]
        self.assertAlmostEqual(end[1] - start_up, 100.0, places=6)
        self.assertAlmostEqual(end[0], 200.0 * math.cos(math.radians(30.0)), places=6)

    def test_legs_chain_from_the_pen(self):
        solved = evaluate(program(
            north_line(500.0),
            LineToSegment(heading_deg=90.0, distance_m=300.0),
        ))
        first, second = solved.segments
        self.assertEqual(first.end, second.start)
        self.assertAlmostEqual(second.end[0], 300.0, places=6)
        self.assertAlmostEqual(second.end[2], 500.0, places=6)

    def test_inherit_direction_carries_straight_on(self):
        solved = evaluate(program(
            LineToSegment(heading_deg=45.0, distance_m=100.0),
            LineToSegment(distance_m=100.0, inherit_direction=True),
        ))
        first, second = solved.segments
        heading, _ = direction_angles(second.tangent_at(0.0))
        self.assertAlmostEqual(heading, 45.0, places=6)
        # Two equal runs on one heading land twice as far along it.
        self.assertAlmostEqual(second.end[0], 2.0 * first.end[0], places=6)

    def test_inherit_direction_without_a_pen_direction_is_an_error(self):
        with self.assertRaises(ProgramError) as caught:
            evaluate(program(LineToSegment(distance_m=100.0, inherit_direction=True)))
        self.assertEqual(caught.exception.index, 0)


class ArcTests(unittest.TestCase):
    def test_quarter_turn_left_from_north_ends_heading_west(self):
        solved = evaluate(program(
            north_line(100.0),
            ArcSegment(side="LEFT", radius_m=500.0, sweep_deg=90.0),
        ))
        arc = solved.segments[1]
        heading, _ = direction_angles(arc.tangent_at(1.0))
        self.assertAlmostEqual(heading, 270.0, places=4)
        # Centre on the left of a northbound leg is due west of its start.
        self.assertAlmostEqual(arc.center[0], arc.start[0] - 500.0, places=6)

    def test_quarter_turn_right_from_north_ends_heading_east(self):
        solved = evaluate(program(
            north_line(100.0),
            ArcSegment(side="RIGHT", radius_m=500.0, sweep_deg=90.0),
        ))
        arc = solved.segments[1]
        heading, _ = direction_angles(arc.tangent_at(1.0))
        self.assertAlmostEqual(heading, 90.0, places=4)
        self.assertAlmostEqual(arc.center[0], arc.start[0] + 500.0, places=6)

    def test_arc_leaves_along_the_pen_tangent(self):
        solved = evaluate(program(
            LineToSegment(heading_deg=123.0, distance_m=100.0),
            ArcSegment(side="LEFT", radius_m=800.0, sweep_deg=45.0),
        ))
        line, arc = solved.segments
        before = direction_angles(line.tangent_at(1.0))
        after = direction_angles(arc.tangent_at(0.0))
        self.assertAlmostEqual(before[0], after[0], places=6)
        self.assertAlmostEqual(before[1], after[1], places=6)

    def test_every_point_sits_on_the_circle(self):
        solved = evaluate(program(
            north_line(10.0),
            ArcSegment(side="LEFT", radius_m=300.0, sweep_deg=200.0),
        ))
        arc = solved.segments[1]
        for step in range(11):
            point = arc.point_at(step / 10.0)
            flat = (point[0] - arc.center[0], 0.0, point[2] - arc.center[2])
            self.assertAlmostEqual(math.hypot(flat[0], flat[2]), 300.0, places=6)

    def test_full_circle_returns_to_the_start(self):
        solved = evaluate(program(
            north_line(10.0),
            ArcSegment(side="LEFT", radius_m=400.0, sweep_deg=360.0),
        ))
        arc = solved.segments[1]
        self.assertAlmostEqual(math.dist(arc.start, arc.end), 0.0, places=6)
        self.assertAlmostEqual(arc.length_m, 2.0 * math.pi * 400.0, places=6)

    def test_sweep_past_360_keeps_turning(self):
        """The thing the waypoint model could not express at any setting."""
        solved = evaluate(program(
            north_line(10.0),
            ArcSegment(side="LEFT", radius_m=400.0, sweep_deg=1080.0),
        ))
        arc = solved.segments[1]
        self.assertAlmostEqual(arc.length_m, 3.0 * 2.0 * math.pi * 400.0, places=6)
        self.assertAlmostEqual(math.dist(arc.start, arc.end), 0.0, places=6)

    def test_rise_defaults_to_matching_the_pen_climb(self):
        """A climbing entry hands over to the helix without a kink."""
        solved = evaluate(program(
            LineToSegment(heading_deg=0.0, climb_deg=6.0, distance_m=500.0),
            ArcSegment(side="LEFT", radius_m=600.0, sweep_deg=180.0),
        ))
        line, arc = solved.segments
        self.assertAlmostEqual(
            direction_angles(line.tangent_at(1.0))[1],
            direction_angles(arc.tangent_at(0.0))[1],
            places=6,
        )
        # Still climbing at the same angle when it comes out the far side.
        self.assertAlmostEqual(direction_angles(arc.tangent_at(1.0))[1], 6.0, places=6)

    def test_explicit_rise_climbs_by_that_much_per_turn(self):
        solved = evaluate(program(
            north_line(10.0),
            ArcSegment(side="LEFT", radius_m=500.0, sweep_deg=720.0,
                       rise_per_turn_m=100.0),
        ))
        arc = solved.segments[1]
        self.assertAlmostEqual(arc.end[1] - arc.start[1], 200.0, places=6)

    def test_level_pen_gives_a_flat_circle(self):
        solved = evaluate(program(
            north_line(10.0),
            ArcSegment(side="LEFT", radius_m=250.0, sweep_deg=270.0),
        ))
        arc = solved.segments[1]
        self.assertAlmostEqual(arc.end[1] - arc.start[1], 0.0, places=9)

    def test_arc_without_a_pen_direction_is_an_error(self):
        with self.assertRaises(ProgramError) as caught:
            evaluate(program(ArcSegment(radius_m=100.0, sweep_deg=90.0)))
        self.assertEqual(caught.exception.index, 0)

    def test_arc_from_a_vertical_tangent_is_an_error(self):
        with self.assertRaises(ProgramError) as caught:
            evaluate(program(
                LineToSegment(climb_deg=90.0, distance_m=100.0),
                ArcSegment(radius_m=100.0, sweep_deg=90.0),
            ))
        self.assertEqual(caught.exception.index, 1)

    def test_positive_tilt_rolls_the_plane_toward_the_right(self):
        solved = evaluate(program(
            north_line(10.0),
            ArcSegment(side="LEFT", radius_m=500.0, sweep_deg=90.0, tilt_deg=30.0),
        ))
        arc = solved.segments[1]
        # Heading north, right is east, so the normal leans east of up.
        self.assertGreater(arc.normal[0], 0.0)
        self.assertAlmostEqual(arc.normal[0], math.sin(math.radians(30.0)), places=6)


class SeamTests(unittest.TestCase):
    def test_move_to_jumps_without_drawing_a_leg(self):
        solved = evaluate(program(
            north_line(1000.0),
            MoveToSegment(to=GeoPoint(lat=37.9, lon=-122.5, alt_ft_msl=3000.0),
                          tangent=Direction(heading_deg=180.0)),
            north_line(500.0),
        ))
        jump = solved.segments[1]
        self.assertEqual(jump.length_m, 0.0)
        # The MoveTo draws nothing, so the break belongs to the leg after it.
        self.assertFalse(jump.seam)
        self.assertTrue(solved.segments[2].seam)
        # The pen really moved: the leg after it starts somewhere else.
        self.assertGreater(math.dist(solved.segments[0].end, solved.segments[2].start), 1000.0)

    def test_leading_move_to_is_not_a_seam(self):
        """Starting somewhere is not a cut, because nothing has been drawn yet."""
        solved = evaluate(program(
            MoveToSegment(to=ORIGIN, tangent=Direction(heading_deg=0.0)),
            north_line(100.0),
        ))
        self.assertFalse(solved.segments[0].seam)
        self.assertFalse(solved.segments[1].seam)

    def test_move_to_reseeds_the_tangent(self):
        solved = evaluate(program(
            north_line(100.0),
            MoveToSegment(to=GeoPoint(lat=37.9, lon=-122.5),
                          tangent=Direction(heading_deg=270.0)),
            LineToSegment(distance_m=100.0, inherit_direction=True),
        ))
        heading, _ = direction_angles(solved.segments[2].tangent_at(0.0))
        self.assertAlmostEqual(heading, 270.0, places=6)

    def test_move_to_without_a_tangent_leaves_the_pen_blank(self):
        with self.assertRaises(ProgramError) as caught:
            evaluate(program(
                north_line(100.0),
                MoveToSegment(to=GeoPoint(lat=37.9, lon=-122.5)),
                ArcSegment(radius_m=100.0, sweep_deg=90.0),
            ))
        self.assertEqual(caught.exception.index, 2)

    def test_sampling_marks_the_break_once(self):
        solved = evaluate(program(
            north_line(100.0),
            MoveToSegment(to=GeoPoint(lat=37.9, lon=-122.5),
                          tangent=Direction(heading_deg=0.0)),
            north_line(100.0),
        ))
        rows = sample_by_distance(solved, step_m=50.0)
        breaks = [index for index, row in enumerate(rows) if row["break_before"]]
        self.assertEqual(len(breaks), 1)
        # It lands on the first row after the jump, not on the last row before.
        self.assertEqual(rows[breaks[0]]["segment_id"], solved.segments[2].segment_id)
        self.assertAlmostEqual(rows[breaks[0]]["u"], 0.0)

    def test_distance_lookup_is_right_continuous_at_a_seam(self):
        """At the jump the post-jump pose wins, so a cut reads as a cut."""
        solved = evaluate(program(
            north_line(100.0),
            MoveToSegment(to=GeoPoint(lat=37.9, lon=-122.5),
                          tangent=Direction(heading_deg=0.0)),
            north_line(100.0),
        ))
        point, _ = solved.at_distance(100.0)
        self.assertAlmostEqual(math.dist(point, solved.segments[2].start), 0.0, places=6)
        self.assertGreater(math.dist(point, solved.segments[0].end), 1000.0)


class ProgramTests(unittest.TestCase):
    def test_segment_ids_are_minted_and_unique(self):
        built = program(north_line(10.0), north_line(20.0), north_line(30.0))
        ids = [segment.id for segment in built.segments]
        self.assertTrue(all(ids))
        self.assertEqual(len(set(ids)), 3)

    def test_duplicate_ids_are_replaced(self):
        built = PathProgram(origin=ORIGIN, segments=[
            LineToSegment(id="same", distance_m=10.0),
            LineToSegment(id="same", distance_m=20.0),
        ])
        self.assertNotEqual(built.segments[0].id, built.segments[1].id)

    def test_total_length_is_the_sum_of_the_segments(self):
        solved = evaluate(program(
            north_line(100.0),
            ArcSegment(side="LEFT", radius_m=200.0, sweep_deg=180.0),
            LineToSegment(distance_m=400.0, inherit_direction=True),
        ))
        self.assertAlmostEqual(solved.length_m, 100.0 + math.pi * 200.0 + 400.0, places=6)

    def test_velocity_profile_is_a_cubic_in_normalised_arc_length(self):
        profile = VelocityProfile(c0=100.0, c1=-40.0, c2=0.0, c3=0.0)
        self.assertAlmostEqual(profile.speed_at(0.0), 100.0)
        self.assertAlmostEqual(profile.speed_at(0.5), 80.0)
        self.assertAlmostEqual(profile.speed_at(1.0), 60.0)


if __name__ == "__main__":
    unittest.main()
