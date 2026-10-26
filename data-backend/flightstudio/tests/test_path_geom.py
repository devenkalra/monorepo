import math
import unittest

from flightstudio.core.bspline import fit_bspline
from flightstudio.core.flight_path import SolvedFlightPath
from flightstudio.core.path_geom import arc_frame, arc_point, hermite_from_chord, hermite_point, path_point
from flightstudio.core.schema import ArcLeg, BSplineLeg, FlightKeyframe, PathDocument, PathMeta, Plane


class PathGeomTests(unittest.TestCase):
    def test_straight_midpoint(self):
        a, b = (0.0, 0.0, 0.0), (100.0, 40.0, 0.0)
        mid = path_point(a, b, None, 0.5)
        self.assertAlmostEqual(mid[0], 50.0)
        self.assertAlmostEqual(mid[1], 20.0)

    def test_hermite_hits_ends(self):
        a, b = (0.0, 10.0, 0.0), (300.0, 10.0, 0.0)
        path = hermite_from_chord(a, b)
        start, end = hermite_point(a, b, path, 0.0), hermite_point(a, b, path, 1.0)
        self.assertAlmostEqual(start[0], a[0])
        self.assertAlmostEqual(end[0], b[0])
        self.assertAlmostEqual(end[1], b[1])

    def test_hermite_along_chord_is_straight(self):
        a, b = (0.0, 0.0, 0.0), (90.0, 0.0, 0.0)
        path = hermite_from_chord(a, b)
        mid = hermite_point(a, b, path, 0.5)
        self.assertAlmostEqual(mid[0], 45.0, places=5)
        self.assertAlmostEqual(mid[1], 0.0, places=5)
        self.assertAlmostEqual(mid[2], 0.0, places=5)

    def test_arc_hits_ends_and_keeps_radius(self):
        a, b = (0.0, 0.0, 0.0), (200.0, 0.0, 0.0)
        path = ArcLeg(side="LEFT", radius_m=200.0, plane=Plane())
        self.assertAlmostEqual(arc_point(a, b, path, 0.0)[0], 0.0, places=5)
        end = arc_point(a, b, path, 1.0)
        self.assertAlmostEqual(end[0], 200.0, places=5)
        self.assertAlmostEqual(end[2], 0.0, places=5)
        frame = arc_frame(a, b, path)
        center, radius = frame[0], frame[1]
        mid = arc_point(a, b, path, 0.5)
        self.assertAlmostEqual(math.dist(mid, center), radius, places=5)
        self.assertGreater(abs(mid[2]), 1.0)

    def test_arc_radius_changes_bulge_without_flipping_sides(self):
        a, b = (0.0, 0.0, 0.0), (900.0, 0.0, 0.0)
        offsets = []
        for radius in (450.0, 460.0, 600.0, 1200.0, 6000.0):
            mid = arc_point(a, b, ArcLeg(side="LEFT", radius_m=radius), 0.5)
            offsets.append(mid[2])
        # Every radius stays on one side of the chord, and a bigger circle
        # always flattens the arc toward it.
        self.assertTrue(all(value < 0.0 for value in offsets), offsets)
        for earlier, later in zip(offsets, offsets[1:]):
            self.assertGreater(later, earlier, offsets)

    def test_arc_radius_below_floor_is_the_half_circle(self):
        a, b = (0.0, 0.0, 0.0), (900.0, 0.0, 0.0)
        floor = arc_point(a, b, ArcLeg(side="LEFT", radius_m=450.0), 0.5)
        under = arc_point(a, b, ArcLeg(side="LEFT", radius_m=10.0), 0.5)
        self.assertAlmostEqual(floor[2], under[2], places=6)
        self.assertAlmostEqual(abs(floor[2]), 450.0, places=4)

    def test_arc_stays_in_tilted_plane(self):
        a, b = (0.0, 0.0, 0.0), (200.0, 80.0, 0.0)
        path = ArcLeg(side="RIGHT", radius_m=160.0, plane=Plane())
        frame = arc_frame(a, b, path)
        self.assertIsNotNone(frame)
        center, radius, _radial, _around, _sweep = frame
        for u in (0.25, 0.5, 0.75):
            point = arc_point(a, b, path, u)
            self.assertAlmostEqual(math.dist(point, center), radius, places=4)
            # Chord and sample stay coplanar with the snapped plane.
            ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
            ap = (point[0] - a[0], point[1] - a[1], point[2] - a[2])
            normal = (
                ab[1] * ap[2] - ab[2] * ap[1],
                ab[2] * ap[0] - ab[0] * ap[2],
                ab[0] * ap[1] - ab[1] * ap[0],
            )
            # First sample defines the plane; later ones must share it.
            if u == 0.25:
                plane = normal
            else:
                mag = math.sqrt(sum(x * x for x in plane)) or 1.0
                self.assertAlmostEqual(
                    (plane[0] * ap[0] + plane[1] * ap[1] + plane[2] * ap[2]) / mag,
                    0.0, places=4,
                )

    def test_bspline_interpolates_ends(self):
        points = [(0.0, 0.0, 0.0), (40.0, 10.0, 20.0), (90.0, 8.0, 10.0), (140.0, 0.0, 0.0)]
        spline = fit_bspline(points, tolerance_m=50.0)
        start, end = spline.point_at(0.0), spline.point_at(1.0)
        self.assertAlmostEqual(start[0], 0.0, places=5)
        self.assertAlmostEqual(end[0], 140.0, places=5)
        self.assertAlmostEqual(end[2], 0.0, places=5)

    def test_bspline_interiors_pull_not_interpolate(self):
        points = [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0), (100.0, 0.0, 100.0), (0.0, 0.0, 100.0)]
        loose = fit_bspline(points, tolerance_m=50.0)
        tight = fit_bspline(points, tolerance_m=1.0)
        params = loose.params
        loose_err = math.dist(loose.point_at(params[1]), points[1])
        tight_err = math.dist(tight.point_at(params[1]), points[1])
        self.assertGreater(loose_err, 8.0)
        self.assertLess(tight_err, loose_err)

    def test_bspline_bows_off_the_end_chord(self):
        points = [(0.0, 0.0, 0.0), (50.0, 0.0, 80.0), (100.0, 0.0, 0.0)]
        spline = fit_bspline(points, tolerance_m=50.0)
        mid = spline.point_at(0.5)
        self.assertGreater(mid[2], 15.0)
        self.assertLess(math.dist(mid, points[1]), 70.0)

    def test_solved_arc_document_passes_through_waypoints(self):
        keys = [
            FlightKeyframe(id="a", time_offset=0, lat=37.8, lon=-122.5, alt_ft_msl=1000,
                           path=ArcLeg(side="LEFT", radius_m=400)),
            FlightKeyframe(id="b", time_offset=20, lat=37.804, lon=-122.5, alt_ft_msl=1000),
        ]
        doc = PathDocument(meta=PathMeta(path_id="arc-1", duration_seconds=20), flight_keyframes=keys)
        flight = SolvedFlightPath.from_document(doc)
        start = flight.position_at(0)
        end = flight.position_at(20)
        self.assertAlmostEqual(start[0], 37.8, places=5)
        self.assertAlmostEqual(end[0], 37.804, places=5)
        mid = flight.position_at(10)
        self.assertNotAlmostEqual(mid[1], -122.5, places=5)

    def test_consecutive_bsplines_coalesce_into_one_span(self):
        keys = [
            FlightKeyframe(id="a", time_offset=0, lat=37.80, lon=-122.50, alt_ft_msl=1000,
                           path=BSplineLeg(end_id="b")),
            FlightKeyframe(id="b", time_offset=10, lat=37.81, lon=-122.49, alt_ft_msl=1100,
                           path=BSplineLeg(end_id="c")),
            FlightKeyframe(id="c", time_offset=20, lat=37.82, lon=-122.50, alt_ft_msl=1000,
                           path=BSplineLeg(end_id="d")),
            FlightKeyframe(id="d", time_offset=30, lat=37.81, lon=-122.51, alt_ft_msl=900),
        ]
        doc = PathDocument(meta=PathMeta(path_id="bs-1", duration_seconds=30),
                           flight_keyframes=keys)
        self.assertEqual(doc.flight_keyframes[0].path.kind, "BSPLINE")
        self.assertEqual(doc.flight_keyframes[0].path.end_id, "d")
        self.assertEqual(doc.flight_keyframes[1].path.kind, "STRAIGHT")
        self.assertEqual(doc.flight_keyframes[2].path.kind, "STRAIGHT")
        flight = SolvedFlightPath.from_document(doc)
        spline = flight.curve.knots[0].spline
        self.assertIsNotNone(spline)
        self.assertGreaterEqual(len(spline.ctrl), 4)
        start = flight.position_at(0)
        end = flight.position_at(30)
        self.assertAlmostEqual(start[0], 37.80, places=5)
        self.assertAlmostEqual(end[0], 37.81, places=5)
        self.assertAlmostEqual(end[1], -122.51, places=5)

    def test_legacy_path_mode_becomes_straight(self):
        key = FlightKeyframe.model_validate({
            "time_offset": 0, "lat": 0, "lon": 0, "alt_ft_msl": 100,
            "path_mode": "SMOOTH",
        })
        self.assertEqual(key.path.kind, "STRAIGHT")


if __name__ == "__main__":
    unittest.main()
