"""Hermite and Spline — stage 4 of SEGMENT_MODEL.md."""

import math
import unittest

from pydantic import ValidationError

from flightstudio.core.bspline import NurbsCurve, clamped_knots
from flightstudio.core.program import (
    Construction,
    ControlPoint,
    GeoPoint,
    HermiteHandle,
    HermiteSegment,
    LineToSegment,
    PathProgram,
    SplineSegment,
    VelocityProfile,
)
from flightstudio.core.program_construct import (
    construction_still_matches,
    fit_spline_from_points,
    hull_divergence,
)
from flightstudio.core.program_geom import (
    HermiteGeometry,
    SplineGeometry,
    direction_angles,
    enu_point,
    evaluate,
)
from flightstudio.core.program_solve import DETERMINED, UNDER_DETERMINED, solve

ORIGIN = GeoPoint(lat=37.8716, lon=-122.2727, alt_ft_msl=2000.0)


def program(*segments) -> PathProgram:
    return PathProgram(origin=ORIGIN, segments=list(segments))


def velocity():
    return VelocityProfile(c0=100.0, inherit_entry=False)


class HermiteGeometryTests(unittest.TestCase):
    def test_endpoints_are_the_authored_ones(self):
        end = GeoPoint(lat=37.8900, lon=-122.2500, alt_ft_msl=3000.0)
        solved = evaluate(program(HermiteSegment(
            to=end, into=HermiteHandle(heading_deg=90.0, length_m=400.0),
            velocity=velocity(),
        )))
        geometry = solved.segments[0]
        self.assertIsInstance(geometry, HermiteGeometry)
        lat, lon, alt = solved.to_latlon(geometry.end)
        self.assertAlmostEqual(lat, end.lat, places=5)
        self.assertAlmostEqual(lon, end.lon, places=5)
        self.assertAlmostEqual(alt, end.alt_ft_msl, places=1)

    def test_out_handle_defaults_from_the_pen(self):
        """G1 with the previous segment is free rather than maintained."""
        built = program(
            LineToSegment(heading_deg=30.0, climb_deg=5.0, distance_m=1000.0,
                          velocity=velocity()),
            HermiteSegment(
                to=GeoPoint(lat=37.9000, lon=-122.2400, alt_ft_msl=2500.0),
                into=HermiteHandle(heading_deg=60.0, length_m=500.0),
                velocity=velocity(),
            ),
        )
        solved = evaluate(built)
        entry = direction_angles(solved.segments[1].tangent_at(0.0))
        self.assertAlmostEqual(entry[0], 30.0, places=1)
        self.assertAlmostEqual(entry[1], 5.0, places=1)

    def test_an_authored_out_handle_overrides_the_pen(self):
        built = program(
            LineToSegment(heading_deg=0.0, distance_m=500.0, velocity=velocity()),
            HermiteSegment(
                to=GeoPoint(lat=37.8900, lon=-122.2500, alt_ft_msl=2000.0),
                out=HermiteHandle(heading_deg=90.0, length_m=400.0),
                into=HermiteHandle(heading_deg=90.0, length_m=400.0),
                velocity=velocity(),
            ),
        )
        heading, _ = direction_angles(evaluate(built).segments[1].tangent_at(0.0))
        self.assertAlmostEqual(heading, 90.0, places=1)

    def test_length_is_positive_and_at_least_the_chord(self):
        end = GeoPoint(lat=37.8900, lon=-122.2500, alt_ft_msl=2000.0)
        solved = evaluate(program(HermiteSegment(
            to=end,
            out=HermiteHandle(heading_deg=45.0, length_m=800.0),
            into=HermiteHandle(heading_deg=135.0, length_m=800.0),
            velocity=velocity(),
        )))
        chord = math.dist(solved.segments[0].start, solved.segments[0].end)
        self.assertGreater(solved.segments[0].length_m, chord)


class NurbsTests(unittest.TestCase):
    def test_unit_weights_match_an_unweighted_b_spline(self):
        ctrl = [(0.0, 0.0, 0.0), (100.0, 0.0, 300.0),
                (200.0, 50.0, 300.0), (300.0, 0.0, 0.0)]
        knots = clamped_knots(4, 3)
        weighted = NurbsCurve(ctrl, [1.0, 1.0, 1.0, 1.0], knots, 3)
        from flightstudio.core.bspline import FittedBSpline
        plain = FittedBSpline(ctrl, knots, 3, [])
        for u in (0.0, 0.25, 0.5, 0.75, 1.0):
            a, b = weighted.point_at(u), plain.point_at(u)
            self.assertAlmostEqual(a[0], b[0], places=9)
            self.assertAlmostEqual(a[1], b[1], places=9)
            self.assertAlmostEqual(a[2], b[2], places=9)

    def test_clamped_ends_lie_on_the_first_and_last_control_points(self):
        ctrl = [(0.0, 0.0, 0.0), (50.0, 10.0, 100.0),
                (150.0, -10.0, 200.0), (200.0, 0.0, 300.0)]
        curve = NurbsCurve(ctrl, [1.0] * 4, clamped_knots(4, 3), 3)
        self.assertEqual(curve.point_at(0.0), ctrl[0])
        self.assertEqual(curve.point_at(1.0), ctrl[-1])

    def test_raising_a_weight_pulls_the_curve_toward_that_control(self):
        ctrl = [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0),
                (100.0, 0.0, 100.0), (0.0, 0.0, 100.0)]
        knots = clamped_knots(4, 3)
        plain = NurbsCurve(ctrl, [1.0, 1.0, 1.0, 1.0], knots, 3).point_at(0.5)
        pulled = NurbsCurve(ctrl, [1.0, 8.0, 1.0, 1.0], knots, 3).point_at(0.5)
        # Closer to the second control point after its weight rises.
        before = math.dist(plain, ctrl[1])
        after = math.dist(pulled, ctrl[1])
        self.assertLess(after, before)

    def test_tangent_is_a_unit_vector(self):
        ctrl = [(0.0, 0.0, 0.0), (100.0, 0.0, 50.0),
                (200.0, 20.0, 100.0), (300.0, 0.0, 150.0)]
        curve = NurbsCurve(ctrl, [1.0] * 4, clamped_knots(4, 3), 3)
        for u in (0.0, 0.3, 0.7, 1.0):
            tangent = curve.tangent_at(u)
            self.assertAlmostEqual(math.dist((0, 0, 0), tangent), 1.0, places=6)


class SplineGeometryTests(unittest.TestCase):
    def four_point_spline(self, **extra):
        return SplineSegment(
            control_points=[
                ControlPoint(lat=37.8716, lon=-122.2727, alt_ft_msl=2000.0),
                ControlPoint(lat=37.8800, lon=-122.2600, alt_ft_msl=2200.0),
                ControlPoint(lat=37.8900, lon=-122.2500, alt_ft_msl=2100.0),
                ControlPoint(lat=37.9000, lon=-122.2400, alt_ft_msl=2000.0),
            ],
            velocity=velocity(),
            **extra,
        )

    def test_the_curve_starts_and_ends_on_the_hull(self):
        solved = evaluate(program(self.four_point_spline()))
        geometry = solved.segments[0]
        self.assertIsInstance(geometry, SplineGeometry)
        self.assertAlmostEqual(geometry.start[0], geometry.controls[0][0], places=6)
        self.assertAlmostEqual(geometry.end[0], geometry.controls[-1][0], places=6)

    def test_a_hull_away_from_the_pen_is_a_seam(self):
        """Authoring a polygon somewhere else is a jump, not a continuous join."""
        segment = self.four_point_spline()
        # Shift every control point a kilometre north so the start is not the origin.
        for point in segment.control_points:
            point.lat += 0.01
        solved = evaluate(program(
            LineToSegment(heading_deg=0.0, distance_m=100.0, velocity=velocity()),
            segment,
        ))
        self.assertTrue(solved.segments[1].seam)

    def test_too_few_control_points_for_the_degree_is_refused(self):
        with self.assertRaises(ValidationError):
            SplineSegment(control_points=[
                ControlPoint(lat=0.0, lon=0.0),
                ControlPoint(lat=1.0, lon=1.0),
            ], degree=3)

    def test_a_wrong_knot_count_is_refused(self):
        with self.assertRaises(ValidationError):
            self.four_point_spline(knots=[0.0, 1.0])


class ConstructionTests(unittest.TestCase):
    def picks(self):
        return [
            GeoPoint(lat=37.8716, lon=-122.2727, alt_ft_msl=2000.0),
            GeoPoint(lat=37.8800, lon=-122.2650, alt_ft_msl=2100.0),
            GeoPoint(lat=37.8900, lon=-122.2550, alt_ft_msl=2200.0),
            GeoPoint(lat=37.9000, lon=-122.2450, alt_ft_msl=2000.0),
            GeoPoint(lat=37.9100, lon=-122.2400, alt_ft_msl=2000.0),
        ]

    def test_fitting_produces_an_evaluable_spline(self):
        built = PathProgram(origin=ORIGIN, segments=[])
        segment, warning = fit_spline_from_points(built, self.picks(), tolerance_m=30.0)
        self.assertEqual(warning.control_edits, 0)
        self.assertEqual(segment.construction.kind, "FIT_POINTS")
        self.assertEqual(len(segment.construction.points), 5)
        solved = evaluate(program(segment))
        self.assertGreater(solved.segments[0].length_m, 1000.0)

    def test_the_fit_passes_near_the_picks(self):
        built = PathProgram(origin=ORIGIN, segments=[])
        segment, _ = fit_spline_from_points(built, self.picks(), tolerance_m=40.0)
        solved = evaluate(program(segment))
        geometry = solved.segments[0]
        # Sample densely and check each pick has some nearby point on the curve.
        samples = [geometry.point_at(i / 40.0) for i in range(41)]
        for pick in self.picks():
            target = enu_point(built, pick)
            nearest = min(math.dist(sample, target) for sample in samples)
            self.assertLess(nearest, 80.0, msg=f"missed pick {pick}")

    def test_a_direct_edit_is_detected_against_produced(self):
        built = PathProgram(origin=ORIGIN, segments=[])
        segment, _ = fit_spline_from_points(built, self.picks())
        self.assertTrue(construction_still_matches(segment, built))
        segment.control_points[1].lat += 0.01
        warning = hull_divergence(segment, program=built)
        self.assertEqual(warning.control_edits, 1)
        self.assertIn("1 control-point edit", warning.detail)

    def test_a_weight_edit_is_named_in_the_warning(self):
        built = PathProgram(origin=ORIGIN, segments=[])
        segment, _ = fit_spline_from_points(built, self.picks())
        segment.control_points[2].weight = 3.0
        warning = hull_divergence(segment, program=built)
        self.assertEqual(warning.weight_edits, 1)
        self.assertIn("1 weight", warning.detail)

    def test_refitting_preserves_identity_and_warns(self):
        built = PathProgram(origin=ORIGIN, segments=[])
        first, _ = fit_spline_from_points(built, self.picks(), name="Coast")
        first.control_points[1].lat += 0.005
        again, warning = fit_spline_from_points(
            built, self.picks(), existing=first, tolerance_m=30.0,
        )
        self.assertEqual(again.id, first.id)
        self.assertEqual(again.name, "Coast")
        self.assertGreater(warning.control_edits, 0)


class HermiteSolveTests(unittest.TestCase):
    def test_pinning_the_endpoint_alone_is_closed_form(self):
        target = GeoPoint(lat=37.8900, lon=-122.2500, alt_ft_msl=2500.0)
        built = program(HermiteSegment(
            to=GeoPoint(lat=37.8800, lon=-122.2600, alt_ft_msl=2000.0),
            into=HermiteHandle(heading_deg=45.0, length_m=400.0),
            pinned={"into.heading_deg", "into.climb_deg", "into.length_m"},
            constraints=[{"lat": target.lat, "lon": target.lon,
                          "alt_ft_msl": target.alt_ft_msl}],
            velocity=velocity(),
        ))
        outcome = solve(built)
        self.assertEqual(outcome.reports[0].state, DETERMINED)
        self.assertEqual(outcome.reports[0].method, "closed form")
        self.assertAlmostEqual(outcome.program.segments[0].to.lat, target.lat, places=6)

    def test_free_handles_leave_an_endpoint_under_determined(self):
        target = GeoPoint(lat=37.8900, lon=-122.2500, alt_ft_msl=2000.0)
        built = program(HermiteSegment(
            to=GeoPoint(lat=37.8800, lon=-122.2600, alt_ft_msl=2000.0),
            into=HermiteHandle(heading_deg=45.0, length_m=400.0),
            constraints=[{"lat": target.lat, "lon": target.lon,
                          "alt_ft_msl": target.alt_ft_msl}],
            velocity=velocity(),
        ))
        report = solve(built).reports[0]
        self.assertEqual(report.state, UNDER_DETERMINED)
        self.assertGreater(report.short_by, 0)


class SplineSolveTests(unittest.TestCase):
    def test_a_through_point_moves_an_interior_control(self):
        """Exact 'pass through here' is a POINT constraint, not a re-fit."""
        controls = [
            ControlPoint(lat=37.8716, lon=-122.2727, alt_ft_msl=2000.0),
            ControlPoint(lat=37.8800, lon=-122.2600, alt_ft_msl=2000.0),
            ControlPoint(lat=37.8900, lon=-122.2500, alt_ft_msl=2000.0),
            ControlPoint(lat=37.9000, lon=-122.2400, alt_ft_msl=2000.0),
        ]
        # Pin the ends and the weights so only the two interiors can move.
        pinned = {
            "control_points.0.lat", "control_points.0.lon", "control_points.0.alt_ft_msl",
            "control_points.0.weight",
            "control_points.3.lat", "control_points.3.lon", "control_points.3.alt_ft_msl",
            "control_points.3.weight",
            "control_points.1.weight", "control_points.2.weight",
        }
        target = GeoPoint(lat=37.8850, lon=-122.2550, alt_ft_msl=2000.0)
        built = program(SplineSegment(
            control_points=controls, pinned=pinned,
            constraints=[{"at": 0.5, "lat": target.lat, "lon": target.lon,
                          "alt_ft_msl": target.alt_ft_msl}],
            velocity=velocity(),
        ))
        outcome = solve(built)
        self.assertLessEqual(outcome.reports[0].residual_m, 0.5)
        # Midpoint of the solved curve lands on the target.
        mid = outcome.solved.segments[0].point_at(0.5)
        expected = enu_point(outcome.program, target)
        self.assertLess(math.dist(mid, expected), 1.0)

    def test_pinning_the_last_control_to_an_endpoint_is_closed_form(self):
        controls = [
            ControlPoint(lat=37.8716, lon=-122.2727, alt_ft_msl=2000.0),
            ControlPoint(lat=37.8800, lon=-122.2600, alt_ft_msl=2000.0),
            ControlPoint(lat=37.8900, lon=-122.2500, alt_ft_msl=2000.0),
            ControlPoint(lat=37.9000, lon=-122.2400, alt_ft_msl=2000.0),
        ]
        pinned = {name for i in range(3) for name in (
            f"control_points.{i}.lat", f"control_points.{i}.lon",
            f"control_points.{i}.alt_ft_msl", f"control_points.{i}.weight",
        )}
        pinned |= {"control_points.3.weight"}
        target = GeoPoint(lat=37.9050, lon=-122.2350, alt_ft_msl=2200.0)
        built = program(SplineSegment(
            control_points=controls, pinned=pinned,
            constraints=[{"at": 1.0, "lat": target.lat, "lon": target.lon,
                          "alt_ft_msl": target.alt_ft_msl}],
            velocity=velocity(),
        ))
        outcome = solve(built)
        self.assertEqual(outcome.reports[0].method, "closed form")
        self.assertEqual(outcome.reports[0].state, DETERMINED)
        self.assertAlmostEqual(outcome.program.segments[0].control_points[-1].lat,
                               target.lat, places=6)


if __name__ == "__main__":
    unittest.main()
