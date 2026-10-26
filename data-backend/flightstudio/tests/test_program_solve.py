import math
import unittest

from pydantic import ValidationError

from flightstudio.core.program import (
    ArcSegment,
    Constraint,
    Direction,
    GeoPoint,
    LineToSegment,
    MoveToSegment,
    PathProgram,
    VelocityProfile,
)
from flightstudio.core.program_geom import enu_point, evaluate
from flightstudio.core.program_solve import (
    CONTRADICTORY,
    DETERMINED,
    RESIDUAL_TOLERANCE_M,
    UNCONSTRAINED,
    UNDER_DETERMINED,
    free_parameters,
    matrix_rank,
    solve,
)

ORIGIN = GeoPoint(lat=37.8716, lon=-122.2727, alt_ft_msl=2000.0)
# Roughly 900 m north and 900 m east of the origin, well inside the flat-earth
# approximation the local frame uses.
NORTH_EAST = GeoPoint(lat=37.8797, lon=-122.2625, alt_ft_msl=2000.0)


def program(*segments) -> PathProgram:
    return PathProgram(origin=ORIGIN, segments=list(segments))


def line(**extra):
    extra.setdefault("distance_m", 1500.0)
    extra.setdefault("velocity", VelocityProfile(c0=100.0, inherit_entry=False))
    return LineToSegment(**extra)


def point(target: GeoPoint, **extra) -> Constraint:
    return Constraint(lat=target.lat, lon=target.lon,
                      alt_ft_msl=target.alt_ft_msl, **extra)


def reached(built: PathProgram, index: int, at: float = 1.0) -> GeoPoint:
    """Where a program actually goes, as a target for another program.

    Guessing a latitude and hoping a curve can reach it tests the guess. This
    takes a point off a reference path, so the answer the solver has to find
    is known exactly and the test asserts recovery rather than proximity.
    """
    solved = evaluate(built)
    lat, lon, alt_ft = solved.to_latlon(solved.segments[index].point_at(at))
    return GeoPoint(lat=lat, lon=lon, alt_ft_msl=alt_ft)


class Reached:
    """Mixin: assert a solved program actually passes through its constraints."""

    def assertReaches(self, outcome, index=0, tolerance=RESIDUAL_TOLERANCE_M):
        segment = outcome.program.segments[index]
        geometry = outcome.solved.segments[index]
        for constraint in segment.constraints:
            target = enu_point(outcome.program, constraint)
            east, up, north = geometry.point_at(constraint.at)
            if constraint.lock_horizontal:
                self.assertLess(math.hypot(east - target[0], north - target[2]), tolerance)
            if constraint.lock_vertical:
                self.assertLess(abs(up - target[1]), tolerance)


class FreeParameterTests(unittest.TestCase):
    def test_a_polar_line_has_three(self):
        self.assertEqual(free_parameters(line()),
                         ["heading_deg", "climb_deg", "distance_m"])

    def test_carrying_on_costs_the_two_angles(self):
        """They come from the pen, so they are not the solver's to move."""
        self.assertEqual(free_parameters(line(inherit_direction=True)), ["distance_m"])

    def test_pinning_removes_a_parameter(self):
        self.assertEqual(free_parameters(line(pinned={"distance_m"})),
                         ["heading_deg", "climb_deg"])

    def test_an_arc_has_four_only_once_rise_is_authored(self):
        """None means 'whatever keeps the join smooth', not a value to nudge."""
        self.assertEqual(free_parameters(ArcSegment(radius_m=800.0)),
                         ["radius_m", "sweep_deg", "tilt_deg"])
        self.assertEqual(free_parameters(ArcSegment(radius_m=800.0, rise_per_turn_m=50.0)),
                         ["radius_m", "sweep_deg", "tilt_deg", "rise_per_turn_m"])

    def test_a_move_to_frees_its_tangent_only_when_it_has_one(self):
        jump = MoveToSegment(to=NORTH_EAST)
        self.assertEqual(free_parameters(jump), ["to.lat", "to.lon", "to.alt_ft_msl"])
        jump.tangent = Direction(heading_deg=90.0)
        self.assertIn("tangent.heading_deg", free_parameters(jump))

    def test_a_pin_the_segment_does_not_have_is_refused(self):
        with self.assertRaises(ValidationError) as caught:
            LineToSegment(distance_m=100.0, pinned={"radius_m"})
        self.assertIn("radius_m", str(caught.exception))

    def test_pins_serialise_in_a_stable_order(self):
        dumped = line(pinned={"distance_m", "climb_deg", "heading_deg"}).model_dump()
        self.assertEqual(dumped["pinned"], ["climb_deg", "distance_m", "heading_deg"])


class LineSolveTests(unittest.TestCase, Reached):
    def test_an_unconstrained_segment_is_left_alone(self):
        built = program(line(heading_deg=45.0, distance_m=1500.0))
        outcome = solve(built)
        self.assertEqual(outcome.reports[0].state, UNCONSTRAINED)
        self.assertEqual(outcome.program.segments[0].heading_deg, 45.0)
        self.assertEqual(outcome.program.segments[0].distance_m, 1500.0)

    def test_a_pinned_endpoint_determines_a_line_exactly(self):
        """Three unknowns, three equations: the leg just points at the target."""
        built = program(line(constraints=[point(NORTH_EAST)]))
        outcome = solve(built)
        report = outcome.reports[0]
        self.assertEqual(report.state, DETERMINED)
        self.assertEqual(report.equations, 3)
        self.assertEqual(report.rank, 3)
        self.assertEqual(report.method, "closed form")
        self.assertReaches(outcome)

    def test_a_climbing_endpoint_is_reached_in_three_dimensions(self):
        high = GeoPoint(lat=NORTH_EAST.lat, lon=NORTH_EAST.lon, alt_ft_msl=6000.0)
        outcome = solve(program(line(constraints=[point(high)])))
        self.assertEqual(outcome.reports[0].state, DETERMINED)
        self.assertGreater(outcome.program.segments[0].climb_deg, 10.0)
        self.assertReaches(outcome)

    def test_holding_the_direction_leaves_the_distance_to_solve(self):
        target = reached(program(line(heading_deg=45.0, distance_m=2200.0)), 0)
        built = program(line(
            heading_deg=45.0, distance_m=1500.0, pinned={"heading_deg", "climb_deg"},
            constraints=[point(target)],
        ))
        outcome = solve(built)
        self.assertEqual(outcome.reports[0].free, ["distance_m"])
        self.assertEqual(outcome.reports[0].state, DETERMINED)
        self.assertEqual(outcome.program.segments[0].heading_deg, 45.0)
        self.assertAlmostEqual(outcome.program.segments[0].distance_m, 2200.0, places=3)

    def test_an_altitude_alone_is_solved_by_the_climb(self):
        """Be at 5000 ft by the end, without saying anything about where."""
        built = program(line(
            heading_deg=0.0, distance_m=4000.0, pinned={"heading_deg", "distance_m"},
            constraints=[Constraint(lat=0.0, lon=0.0, alt_ft_msl=5000.0,
                                    lock_horizontal=False)],
        ))
        outcome = solve(built)
        self.assertEqual(outcome.reports[0].free, ["climb_deg"])
        self.assertEqual(outcome.reports[0].equations, 1)
        self.assertEqual(outcome.reports[0].state, DETERMINED)
        self.assertEqual(outcome.program.segments[0].distance_m, 4000.0)
        self.assertReaches(outcome)

    def test_a_through_point_partway_along_is_the_same_object(self):
        built = program(line(constraints=[point(NORTH_EAST, at=0.5)]))
        outcome = solve(built)
        self.assertEqual(outcome.reports[0].state, DETERMINED)
        self.assertReaches(outcome)
        # Reached at the halfway mark, so the leg runs on to twice as far.
        self.assertAlmostEqual(outcome.program.segments[0].distance_m,
                               2.0 * _distance_to(outcome, NORTH_EAST), delta=1.0)

    def test_the_pen_is_where_an_endpoint_is_measured_from(self):
        """The second leg solves against where the first one left the pen."""
        built = program(
            line(heading_deg=0.0, distance_m=900.0),
            line(constraints=[point(NORTH_EAST)]),
        )
        outcome = solve(built)
        self.assertEqual(outcome.reports[1].state, DETERMINED)
        self.assertReaches(outcome, index=1)
        # Due east of the pen, which is already north of the target's latitude.
        self.assertAlmostEqual(outcome.program.segments[1].heading_deg, 90.0, delta=4.0)


def _distance_to(outcome, target: GeoPoint) -> float:
    start = outcome.solved.segments[0].start
    return math.dist(start, enu_point(outcome.program, target))


class ArcSolveTests(unittest.TestCase, Reached):
    def entry(self, **extra):
        return line(heading_deg=0.0, distance_m=500.0, **extra)

    def arc(self, **extra):
        extra.setdefault("side", "RIGHT")
        extra.setdefault("radius_m", 600.0)
        return program(self.entry(**extra.pop("entry", {})), ArcSegment(**extra))

    def test_sweep_is_solved_in_closed_form(self):
        """Radius and plane held, so where the curve stops is one unknown."""
        target = reached(self.arc(sweep_deg=137.0), 1)
        built = self.arc(sweep_deg=45.0, pinned={"radius_m", "tilt_deg"},
                         constraints=[point(target)])
        outcome = solve(built)
        report = outcome.reports[1]
        self.assertEqual(report.free, ["sweep_deg"])
        self.assertEqual(report.method, "closed form")
        self.assertEqual(report.state, DETERMINED)
        self.assertAlmostEqual(outcome.program.segments[1].sweep_deg, 137.0, places=3)
        self.assertEqual(outcome.program.segments[1].radius_m, 600.0)

    def test_a_multi_turn_helix_keeps_its_turns(self):
        """Every sweep a full turn apart lands in the same place. Taking the
        one nearest the stored value is what stops a three-turn climb
        collapsing to the first crossing."""
        reference = self.arc(side="LEFT", radius_m=500.0, sweep_deg=1100.0,
                             rise_per_turn_m=200.0, entry={"climb_deg": 5.0})
        built = self.arc(side="LEFT", radius_m=500.0, sweep_deg=1080.0,
                         rise_per_turn_m=200.0, entry={"climb_deg": 5.0},
                         pinned={"radius_m", "tilt_deg", "rise_per_turn_m"},
                         constraints=[point(reached(reference, 1))])
        outcome = solve(built)
        self.assertEqual(outcome.reports[1].state, DETERMINED)
        self.assertAlmostEqual(outcome.program.segments[1].sweep_deg, 1100.0, places=2)
        self.assertReaches(outcome, index=1)

    def test_which_crossing_is_chosen_follows_the_stored_value(self):
        """One target, four answers a full turn apart, all equally valid in
        plan. Which comes back is decided by the seed — section 4.1's reason
        for storing values rather than holes."""
        reference = self.arc(side="LEFT", radius_m=500.0, sweep_deg=1100.0,
                             rise_per_turn_m=200.0, entry={"climb_deg": 5.0})
        target = reached(reference, 1)
        for stored, expected in ((30.0, 20.0), (350.0, 380.0),
                                 (730.0, 740.0), (1080.0, 1100.0)):
            with self.subTest(stored=stored):
                built = self.arc(side="LEFT", radius_m=500.0, sweep_deg=stored,
                                 rise_per_turn_m=200.0, entry={"climb_deg": 5.0},
                                 pinned={"radius_m", "tilt_deg", "rise_per_turn_m"},
                                 constraints=[point(target, lock_vertical=False)])
                self.assertAlmostEqual(solve(built).program.segments[1].sweep_deg,
                                       expected, places=2)

    def test_an_unpinned_side_is_enumerated_not_descended(self):
        """LEFT cannot be reached from RIGHT by descending, so both get tried."""
        target = reached(self.arc(side="RIGHT", radius_m=400.0, sweep_deg=100.0), 1)
        built = self.arc(side="LEFT", radius_m=400.0, sweep_deg=90.0,
                         pinned={"radius_m", "tilt_deg"},
                         constraints=[point(target)])
        outcome = solve(built)
        self.assertEqual(outcome.program.segments[1].side, "RIGHT")
        self.assertEqual(outcome.reports[1].state, DETERMINED)
        self.assertReaches(outcome, index=1)

    def test_the_stored_side_survives_a_tie(self):
        """Barely turning, so both sides reach it. The shape must not flip."""
        for side in ("LEFT", "RIGHT"):
            with self.subTest(side=side):
                target = reached(self.arc(side=side, sweep_deg=0.5), 1)
                built = self.arc(side=side, sweep_deg=10.0,
                                 pinned={"radius_m", "tilt_deg"},
                                 constraints=[point(target)])
                self.assertEqual(solve(built).program.segments[1].side, side)

    def test_pinning_the_side_stops_the_enumeration(self):
        target = reached(self.arc(side="RIGHT", radius_m=400.0, sweep_deg=100.0), 1)
        built = self.arc(side="LEFT", radius_m=400.0, sweep_deg=90.0,
                         pinned={"side", "radius_m", "tilt_deg"},
                         constraints=[point(target)])
        outcome = solve(built)
        self.assertEqual(outcome.program.segments[1].side, "LEFT")
        self.assertEqual(outcome.reports[1].state, CONTRADICTORY)

    def test_radius_and_sweep_together_fall_back_to_the_numeric_solver(self):
        target = reached(self.arc(radius_m=750.0, sweep_deg=110.0), 1)
        built = self.arc(radius_m=500.0, sweep_deg=80.0, pinned={"tilt_deg"},
                         constraints=[point(target)])
        outcome = solve(built)
        self.assertEqual(outcome.reports[1].method, "numeric")
        self.assertLessEqual(outcome.reports[1].residual_m, RESIDUAL_TOLERANCE_M)
        self.assertReaches(outcome, index=1)


class DegreesOfFreedomTests(unittest.TestCase, Reached):
    def test_an_arc_with_a_pinned_endpoint_is_short_by_one(self):
        """Section 4.3: a fully pinned endpoint leaves an arc one short. That
        is a state the editor reports, not an error."""
        built = program(
            line(heading_deg=0.0, distance_m=500.0),
            ArcSegment(side="LEFT", radius_m=600.0, sweep_deg=90.0,
                       constraints=[point(GeoPoint(lat=37.8790, lon=-122.2790),
                                          lock_vertical=False)]),
        )
        report = solve(built).reports[1]
        self.assertEqual(report.state, UNDER_DETERMINED)
        self.assertEqual(len(report.free), 3)
        self.assertEqual(report.equations, 2)
        self.assertEqual(report.short_by, 1)
        self.assertIn("under-determined by 1", report.detail)

    def test_contradictory_pins_are_named_as_such(self):
        """Distance pinned short of a target it cannot possibly reach."""
        built = program(line(
            distance_m=100.0, pinned={"distance_m"},
            constraints=[point(NORTH_EAST)],
        ))
        report = solve(built).reports[0]
        self.assertEqual(report.state, CONTRADICTORY)
        self.assertGreater(report.residual_m, 500.0)
        self.assertIn("cannot all be met", report.detail)

    def test_everything_pinned_still_reports_whether_it_fits(self):
        built = program(line(
            heading_deg=0.0, distance_m=1000.0,
            pinned={"heading_deg", "climb_deg", "distance_m"},
            constraints=[point(NORTH_EAST)],
        ))
        report = solve(built).reports[0]
        self.assertEqual(report.free, [])
        self.assertEqual(report.state, CONTRADICTORY)

    def test_an_over_determined_but_reachable_target_still_solves(self):
        """More equations than unknowns is fine when the target happens to lie
        on what the segment can reach."""
        straight_ahead = GeoPoint(lat=37.8806, lon=-122.2727, alt_ft_msl=2000.0)
        built = program(line(
            heading_deg=0.0, climb_deg=0.0, pinned={"heading_deg", "climb_deg"},
            constraints=[point(straight_ahead)],
        ))
        report = solve(built).reports[0]
        self.assertEqual(len(report.free), 1)
        self.assertEqual(report.equations, 3)
        self.assertEqual(report.state, DETERMINED)

    def test_a_redundant_pair_of_constraints_is_under_determined_not_broken(self):
        """The same point asked for twice adds equations but no information."""
        built = program(line(constraints=[point(NORTH_EAST), point(NORTH_EAST)]))
        report = solve(built).reports[0]
        self.assertEqual(report.equations, 6)
        self.assertEqual(report.rank, 3)
        self.assertEqual(report.state, DETERMINED)


class CascadeTests(unittest.TestCase, Reached):
    def test_an_upstream_edit_moves_a_downstream_solution(self):
        def built(first_distance):
            return program(
                line(heading_deg=0.0, distance_m=first_distance),
                line(constraints=[point(NORTH_EAST)]),
            )
        near = solve(built(300.0))
        far = solve(built(1200.0))
        self.assertReaches(near, index=1)
        self.assertReaches(far, index=1)
        # Same target, different pen, so the second leg must differ.
        self.assertNotAlmostEqual(near.program.segments[1].heading_deg,
                                  far.program.segments[1].heading_deg, places=1)

    def test_a_cut_reseeds_what_the_next_segment_solves_against(self):
        built = program(
            line(heading_deg=0.0, distance_m=2000.0),
            MoveToSegment(to=GeoPoint(lat=37.9000, lon=-122.3000, alt_ft_msl=3000.0),
                          tangent=Direction(heading_deg=90.0), speed_ms=100.0),
            LineToSegment(distance_m=500.0,
                          velocity=VelocityProfile(c0=100.0, inherit_entry=True),
                          constraints=[point(GeoPoint(lat=37.9050, lon=-122.2950,
                                                      alt_ft_msl=3000.0))]),
        )
        outcome = solve(built)
        self.assertEqual(outcome.reports[2].state, DETERMINED)
        self.assertReaches(outcome, index=2)
        self.assertTrue(outcome.solved.segments[2].seam)

    def test_solving_does_not_touch_the_program_it_was_given(self):
        built = program(line(distance_m=1500.0, constraints=[point(NORTH_EAST)]))
        solve(built)
        self.assertEqual(built.segments[0].distance_m, 1500.0)

    def test_the_returned_program_re_evaluates_to_the_same_geometry(self):
        """The solved parameters must be what gets drawn, not a parallel answer."""
        built = program(
            line(constraints=[point(NORTH_EAST)]),
            ArcSegment(side="LEFT", radius_m=500.0, sweep_deg=120.0),
        )
        outcome = solve(built)
        again = evaluate(outcome.program)
        for solved, fresh in zip(outcome.solved.segments, again.segments):
            self.assertAlmostEqual(solved.length_m, fresh.length_m, places=6)
            for axis in range(3):
                self.assertAlmostEqual(solved.end[axis], fresh.end[axis], places=6)


class RankTests(unittest.TestCase):
    def test_an_empty_matrix_has_no_rank(self):
        self.assertEqual(matrix_rank([]), 0)

    def test_independent_rows_count(self):
        self.assertEqual(matrix_rank([[1.0, 0.0], [0.0, 1.0]]), 2)

    def test_a_duplicated_row_adds_nothing(self):
        self.assertEqual(matrix_rank([[1.0, 2.0], [2.0, 4.0]]), 1)

    def test_a_dead_column_is_not_counted(self):
        """A parameter the curve does not respond to cannot pin anything down."""
        self.assertEqual(matrix_rank([[1.0, 0.0], [3.0, 0.0]]), 1)


if __name__ == "__main__":
    unittest.main()
