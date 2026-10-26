"""Program-mode preview — stage 5 of SEGMENT_MODEL.md.

The sample rows must match what ``preview(PathDocument)`` already produces,
so the map, 3D view and exporters can consume a PathProgram without knowing
it is one. The one addition is ``break_before`` at a mid-path MoveTo.
"""

import unittest

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from flightstudio.core.program import (
    ArcSegment,
    CameraAnchor,
    Direction,
    GeoPoint,
    HermiteHandle,
    HermiteSegment,
    LineToSegment,
    MoveToSegment,
    PathProgram,
    ProgramCameraKeyframe,
    VelocityProfile,
)
from flightstudio.core.schema import CameraType, HorizonPosition, LookAtAircraft
from flightstudio.preview import preview_program

ORIGIN = GeoPoint(lat=37.8716, lon=-122.2727, alt_ft_msl=2000.0)
SAMPLE_KEYS = {
    "t", "lat", "lon", "alt_ft", "heading", "bank", "pitch", "speed_kt",
    "path_kind", "path_mode", "break_before", "segment_index",
}


def program(*segments) -> PathProgram:
    return PathProgram(origin=ORIGIN, segments=list(segments))


def velocity(speed=100.0):
    return VelocityProfile(c0=speed, inherit_entry=False)


class PreviewProgramShapeTests(unittest.TestCase):
    def test_empty_program_matches_the_empty_document_shape(self):
        payload = preview_program(program())
        self.assertEqual(payload["duration"], 0.0)
        self.assertEqual(payload["samples"], [])
        self.assertEqual(payload["camera_track"], [])

    def test_sample_rows_carry_every_field_the_player_reads(self):
        payload = preview_program(program(
            LineToSegment(heading_deg=0.0, distance_m=2000.0, velocity=velocity()),
        ))
        self.assertGreater(len(payload["samples"]), 2)
        self.assertEqual(set(payload["samples"][0]), SAMPLE_KEYS)
        self.assertEqual(payload["camera_track"], [])
        self.assertEqual(payload["camera_keys"], [])
        self.assertEqual(payload["source"], "program")
        self.assertEqual(len(payload["segments"]), 1)
        self.assertIn("solvability", payload["segments"][0])
        self.assertIn("start", payload["segments"][0])
        self.assertIn("end", payload["segments"][0])

    def test_duration_matches_the_timed_program(self):
        payload = preview_program(program(
            LineToSegment(heading_deg=0.0, distance_m=1000.0, velocity=velocity(50.0)),
        ))
        self.assertAlmostEqual(payload["duration"], 20.0, places=3)
        self.assertAlmostEqual(payload["samples"][0]["t"], 0.0)
        self.assertAlmostEqual(payload["samples"][-1]["t"], 20.0, places=3)

    def test_anchored_camera_produces_a_camera_track(self):
        line = LineToSegment(
            heading_deg=90.0, distance_m=2000.0, velocity=velocity(100.0),
        )
        # Mint segment ids first, then bind the camera to the resolved id.
        seeded = PathProgram(origin=ORIGIN, segments=[line])
        prog = seeded.model_copy(update={
            "camera_keyframes": [
                ProgramCameraKeyframe(
                    anchor=CameraAnchor(
                        segment_id=seeded.segments[0].id, at=0.5,
                    ),
                    camera_type=CameraType.CINEMATIC,
                    position=HorizonPosition(
                        azimuth_deg=0.0, radius_m=80.0, height_m=15.0,
                    ),
                    look_at=LookAtAircraft(ref="CG"),
                ),
            ],
        })
        payload = preview_program(prog)
        self.assertGreater(len(payload["camera_track"]), 0)
        self.assertEqual(len(payload["camera_keys"]), 1)
        self.assertFalse(payload["camera_keys"][0]["orphan"])
        self.assertAlmostEqual(
            payload["camera_keys"][0]["time_offset"],
            payload["duration"] * 0.5,
            places=2,
        )
        sample = payload["camera_track"][len(payload["camera_track"]) // 2]
        self.assertIn("look_lat", sample)
        self.assertIn("fov_deg", sample)
        # One key covers the whole flight — not only the instant it is anchored.
        self.assertAlmostEqual(payload["camera_track"][0]["t"], 0.0, places=3)
        self.assertAlmostEqual(
            payload["camera_track"][-1]["t"], payload["duration"], places=3,
        )
        first, last = payload["camera_track"][0], payload["camera_track"][-1]
        self.assertNotAlmostEqual(first["lon"], last["lon"], places=4)

    def test_duplicate_segment_id_keeps_camera_on_first_keeper(self):
        """Later duplicates are reminted; cameras named the shared id stay on
        the first keeper so the camera track is not emptied on re-preview."""
        raw = {
            "origin": ORIGIN.model_dump(mode="json"),
            "segments": [
                {
                    "kind": "LINE_TO", "id": "dup",
                    "heading_deg": 90.0, "distance_m": 2000.0,
                    "velocity": velocity(100.0).model_dump(mode="json"),
                },
                {
                    "kind": "LINE_TO", "id": "dup",
                    "heading_deg": 0.0, "distance_m": 1000.0,
                    "velocity": VelocityProfile(
                        c0=100.0, inherit_entry=True,
                    ).model_dump(mode="json"),
                },
            ],
            "camera_keyframes": [
                {
                    "anchor": {"segment_id": "dup", "at": 0.0},
                    "camera_type": "CINEMATIC",
                    "position": {
                        "frame": "HORIZON",
                        "azimuth_deg": 0.0, "radius_m": 80.0, "height_m": 15.0,
                    },
                    "look_at": {"mode": "AIRCRAFT_POINT", "ref": "CG"},
                },
            ],
        }
        prog = PathProgram.model_validate(raw)
        self.assertEqual(prog.segments[0].id, "dup")
        self.assertNotEqual(prog.segments[1].id, "dup")
        self.assertEqual(prog.camera_keyframes[0].anchor.segment_id, "dup")
        payload = preview_program(prog)
        self.assertFalse(payload["camera_keys"][0]["orphan"])
        self.assertGreater(len(payload["camera_track"]), 0)

    def test_free_look_angles_blend_between_keys(self):
        """Fixed-angle keys pan toward the next key instead of holding and
        snapping at it, then hold the last key's aim to the end."""
        def free_key(at, heading):
            return {
                "anchor": {"segment_id": "s", "at": at},
                "camera_type": "CINEMATIC",
                "position": {"frame": "HORIZON", "azimuth_deg": 0.0,
                             "radius_m": 1.0, "height_m": 1.0},
                "look_at": {"mode": "FREE", "pitch_deg": 0.0, "heading_deg": heading},
            }
        prog = PathProgram.model_validate({
            "origin": ORIGIN.model_dump(mode="json"),
            "segments": [{
                "kind": "LINE_TO", "id": "s", "heading_deg": 0.0,
                "distance_m": 2000.0,
                "velocity": velocity(100.0).model_dump(mode="json"),
            }],
            "camera_keyframes": [free_key(0.0, 90.0), free_key(0.5, -90.0)],
        })
        payload = preview_program(prog)
        duration = payload["duration"]
        by_time = {row["t"]: row for row in payload["camera_track"]}

        def relative_heading(t):
            row = by_time[min(by_time, key=lambda x: abs(x - t))]
            return ((row["heading"] + 180.0) % 360.0) - 180.0

        self.assertAlmostEqual(relative_heading(0.0), 90.0, delta=1.0)
        self.assertAlmostEqual(relative_heading(duration * 0.25), 0.0, delta=5.0)
        self.assertAlmostEqual(relative_heading(duration * 0.5), -90.0, delta=1.0)
        self.assertAlmostEqual(relative_heading(duration), -90.0, delta=1.0)

    def test_empty_segment_id_binds_blank_camera_anchor(self):
        raw = {
            "origin": ORIGIN.model_dump(mode="json"),
            "segments": [
                {
                    "kind": "LINE_TO", "id": "",
                    "heading_deg": 90.0, "distance_m": 2000.0,
                    "velocity": velocity(100.0).model_dump(mode="json"),
                },
            ],
            "camera_keyframes": [
                {
                    "anchor": {"segment_id": "", "at": 0.0},
                    "camera_type": "CINEMATIC",
                    "position": {
                        "frame": "HORIZON",
                        "azimuth_deg": 0.0, "radius_m": 80.0, "height_m": 15.0,
                    },
                    "look_at": {"mode": "AIRCRAFT_POINT", "ref": "CG"},
                },
            ],
        }
        prog = PathProgram.model_validate(raw)
        self.assertTrue(prog.segments[0].id)
        self.assertEqual(
            prog.camera_keyframes[0].anchor.segment_id, prog.segments[0].id,
        )
        payload = preview_program(prog)
        self.assertFalse(payload["camera_keys"][0]["orphan"])
        self.assertGreater(len(payload["camera_track"]), 0)

    def test_path_kinds_map_onto_the_colours_the_map_already_knows(self):
        payload = preview_program(program(
            LineToSegment(heading_deg=0.0, distance_m=500.0, velocity=velocity()),
            ArcSegment(side="LEFT", radius_m=400.0, sweep_deg=90.0,
                       velocity=VelocityProfile(c0=100.0, inherit_entry=True)),
            HermiteSegment(
                to=GeoPoint(lat=37.8900, lon=-122.2500, alt_ft_msl=2000.0),
                into=HermiteHandle(heading_deg=90.0, length_m=400.0),
                velocity=VelocityProfile(c0=100.0, inherit_entry=True),
            ),
        ))
        kinds = {row["path_kind"] for row in payload["samples"]}
        self.assertEqual(kinds, {"STRAIGHT", "ARC", "HERMITE"})
        for row in payload["samples"]:
            self.assertEqual(row["path_kind"], row["path_mode"])

    def test_a_seam_sets_break_before_and_nothing_else(self):
        payload = preview_program(program(
            LineToSegment(heading_deg=0.0, distance_m=2000.0, velocity=velocity(100.0)),
            MoveToSegment(
                to=GeoPoint(lat=37.95, lon=-122.5, alt_ft_msl=4500.0),
                tangent=Direction(heading_deg=90.0), speed_ms=100.0,
            ),
            LineToSegment(distance_m=2000.0, inherit_direction=True,
                          velocity=VelocityProfile(c0=100.0, inherit_entry=True)),
        ))
        breaks = [row for row in payload["samples"] if row["break_before"]]
        self.assertEqual(len(breaks), 1)
        # The break sample is the post-jump pose — right-continuous at the seam.
        self.assertAlmostEqual(breaks[0]["lat"], 37.95, places=4)
        self.assertAlmostEqual(breaks[0]["alt_ft"], 4500.0, places=0)
        # Every other sample is continuous.
        self.assertTrue(all(not row["break_before"] for row in payload["samples"]
                            if row is not breaks[0]))

    def test_bank_and_speed_are_populated(self):
        payload = preview_program(program(
            # Long enough that the start is outside the 6 s bank smoothing.
            LineToSegment(heading_deg=0.0, distance_m=3000.0, velocity=velocity(80.0)),
            ArcSegment(side="RIGHT", radius_m=600.0, sweep_deg=180.0,
                       velocity=VelocityProfile(c0=80.0, inherit_entry=True)),
        ))
        banks = [abs(row["bank"]) for row in payload["samples"]]
        self.assertGreater(max(banks), 5.0)
        # Straight portion is wings-level and at the authored speed.
        early = payload["samples"][2]
        self.assertAlmostEqual(early["bank"], 0.0, places=1)
        self.assertAlmostEqual(early["speed_kt"], 80.0 * 1.94384, delta=1.0)

    def test_boundaries_are_sampled_so_a_short_arc_is_not_a_chord(self):
        """A 5° arc would vanish between coarse grid points without this."""
        payload = preview_program(program(
            LineToSegment(heading_deg=0.0, distance_m=3000.0, velocity=velocity(50.0)),
            ArcSegment(side="LEFT", radius_m=200.0, sweep_deg=5.0,
                       velocity=VelocityProfile(c0=50.0, inherit_entry=True)),
            LineToSegment(distance_m=3000.0, inherit_direction=True,
                          velocity=VelocityProfile(c0=50.0, inherit_entry=True)),
        ), samples=20)
        # The arc's own path_kind must appear, which only happens if a sample
        # lands inside it.
        self.assertIn("ARC", {row["path_kind"] for row in payload["samples"]})


class PreviewProgramApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user("preview-prog", password="x")

    def post(self, body):
        return self.client.post("/api/flightstudio/program/preview/", body, format="json")

    def test_requires_auth(self):
        response = self.post({"program": {
            "origin": {"lat": 37.87, "lon": -122.27, "alt_ft_msl": 2000},
            "segments": [{"kind": "LINE_TO", "heading_deg": 0, "distance_m": 1000}],
        }})
        self.assertIn(response.status_code, (401, 403))

    def test_returns_the_player_shape(self):
        self.client.force_authenticate(self.user)
        response = self.post({"program": {
            "origin": {"lat": 37.8716, "lon": -122.2727, "alt_ft_msl": 2000},
            "segments": [
                {"kind": "LINE_TO", "heading_deg": 0, "distance_m": 1000,
                 "velocity": {"c0": 50, "inherit_entry": False}},
            ],
        }})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn("duration", response.data)
        self.assertIn("samples", response.data)
        self.assertIn("camera_track", response.data)
        self.assertEqual(set(response.data["samples"][0]), SAMPLE_KEYS)
        self.assertAlmostEqual(response.data["duration"], 20.0, places=2)

    def test_a_seam_survives_the_round_trip(self):
        self.client.force_authenticate(self.user)
        response = self.post({"program": {
            "origin": {"lat": 37.8716, "lon": -122.2727, "alt_ft_msl": 2000},
            "segments": [
                {"kind": "LINE_TO", "heading_deg": 0, "distance_m": 1000,
                 "velocity": {"c0": 50, "inherit_entry": False}},
                {"kind": "MOVE_TO",
                 "to": {"lat": 37.95, "lon": -122.5, "alt_ft_msl": 4500},
                 "tangent": {"heading_deg": 90}, "speed_ms": 50},
                {"kind": "LINE_TO", "distance_m": 1000, "inherit_direction": True},
            ],
        }})
        self.assertEqual(response.status_code, 200, response.data)
        breaks = [row for row in response.data["samples"] if row["break_before"]]
        self.assertEqual(len(breaks), 1)

    def test_an_invalid_program_names_the_segment(self):
        self.client.force_authenticate(self.user)
        response = self.post({"program": {
            "origin": {"lat": 37.87, "lon": -122.27, "alt_ft_msl": 2000},
            "segments": [{"kind": "LINE_TO", "heading_deg": 0, "distance_m": -10}],
        }})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["index"], 0)

    def test_constrained_line_carries_solvability_for_the_editor(self):
        """Stage 7 popup / gizmos read segments[] from the same preview call."""
        self.client.force_authenticate(self.user)
        response = self.post({"program": {
            "origin": {"lat": 37.8716, "lon": -122.2727, "alt_ft_msl": 2000},
            "segments": [{
                "kind": "LINE_TO", "heading_deg": 0.0, "distance_m": 100.0,
                "velocity": {"c0": 50, "inherit_entry": False},
                "constraints": [{
                    "lat": 37.8797, "lon": -122.2625, "alt_ft_msl": 2000.0,
                }],
            }],
        }})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["constrained"])
        self.assertEqual(len(response.data["segments"]), 1)
        fit = response.data["segments"][0]["solvability"]
        self.assertEqual(fit["state"], "DETERMINED")
        self.assertNotIn("arc", response.data["segments"][0])
        self.assertGreater(
            response.data["solved_program"]["segments"][0]["distance_m"], 1000.0
        )


if __name__ == "__main__":
    unittest.main()
