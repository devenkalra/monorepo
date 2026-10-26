"""Solve a path into something the editor can draw.

The browser never splines anything itself. If it did, the line on the map and
the line the aircraft flies would be two different curves that drift apart as
the solver changes, and the operator would have no way to tell which was
lying.

Two document types share this output contract (§2 of SEGMENT_MODEL.md): a
``PathDocument`` of waypoints, and a ``PathProgram`` of segments. The sample
rows look the same either way — with one addition on programs, ``break_before``,
so a mid-path MoveTo does not get drawn as a line across the gap.
"""

from __future__ import annotations

import bisect
import math

from .core.camera_path import SolvedCameraPath
from .core.flight_path import SolvedFlightPath
from .core.program import PathProgram
from .core.program_camera import pose_from_program, resolve_program_cameras
from .core.program_solve import solve
from .core.program_time import TimedProgram
from .core.schema import BSplineLeg, PathDocument
from .program_preview import segment_summaries

DEFAULT_SAMPLES = 240
# A long document at DEFAULT_SAMPLES puts seconds between map points, and a
# tight turn authored as a few half-second legs is drawn as a corner cut
# straight across them. The grid never gets coarser than this, and every
# keyframe instant is sampled too, so the line always passes through each
# waypoint whatever the spacing.
MAX_SAMPLE_STEP_S = 0.5
MS_TO_KT = 1.94384

# Map program segment kinds onto the colours the existing map already knows.
# SPLINE is drawn as BSPLINE so a purple track means "control polygon" either
# way; LINE_TO is STRAIGHT for the same reason.
PROGRAM_PATH_KIND = {
    "LINE_TO": "STRAIGHT",
    "ARC": "ARC",
    "HERMITE": "HERMITE",
    "SPLINE": "BSPLINE",
    "MOVE_TO": "STRAIGHT",
}


def _path_kind_at(document: PathDocument, t: float) -> str:
    """Kind of the authored leg that contains time t (from the leaving keyframe)."""
    frames = document.flight_keyframes
    if len(frames) < 2:
        return "STRAIGHT"
    times = [frame.time_offset for frame in frames]
    index = min(max(bisect.bisect_right(times, t) - 1, 0), len(frames) - 2)
    for start in range(index + 1):
        path = frames[start].path
        if isinstance(path, BSplineLeg):
            end = next((j for j, frame in enumerate(frames) if frame.id == path.end_id), None)
            if end is not None and start <= index < end:
                return "BSPLINE"
    return getattr(frames[index].path, "kind", "STRAIGHT")


def sample_times(document: PathDocument, duration: float,
                 samples: int = DEFAULT_SAMPLES) -> list[float]:
    """When to sample: an even grid plus every keyframe instant, ascending."""
    count = max(samples, math.ceil(duration / MAX_SAMPLE_STEP_S))
    times = {round(duration * index / count, 6) for index in range(count + 1)}
    times.update(round(frame.time_offset, 6) for frame in document.flight_keyframes
                 if 0.0 <= frame.time_offset <= duration)
    times.update(round(frame.time_offset, 6) for frame in document.camera_keyframes
                 if 0.0 <= frame.time_offset <= duration)
    return sorted(times)


def preview(document: PathDocument, samples: int = DEFAULT_SAMPLES) -> dict:
    if not document.flight_keyframes:
        return {"duration": 0.0, "samples": [], "camera_track": []}

    flight = SolvedFlightPath.from_document(document)
    camera = SolvedCameraPath(
        document.camera_keyframes, flight.origin_lat, flight.origin_lon
    )
    duration = max(document.duration, 1e-6)

    rows = []
    camera_track = []
    for t in sample_times(document, duration, samples):
        pose = flight.pose_at(t)
        kind = _path_kind_at(document, t)
        rows.append({
            "t": round(t, 3),
            "lat": pose.lat,
            "lon": pose.lon,
            "alt_ft": round(pose.alt_ft_msl, 1),
            "heading": round(pose.heading_deg_true, 2),
            "bank": round(pose.bank_deg, 2),
            "pitch": round(pose.pitch_deg, 2),
            "speed_kt": round(flight.ground_speed_ms(t) * MS_TO_KT, 1),
            # Solved with the geometry: the map colours from this so a stale
            # client keyframe mode cannot paint a curved leg mint-green.
            "path_kind": kind,
            "path_mode": kind,
            # Waypoint documents have no mid-path jump; the flag is here so
            # both document types share one sample shape.
            "break_before": False,
        })

        view = camera.world_view_at(t, pose)
        if view is not None:
            lat, lon, alt_ft, heading, pitch = view
            look = camera.look_target_at(t, pose)
            if look is None:
                look_lat, look_lon, look_alt_ft = pose.lat, pose.lon, pose.alt_ft_msl
            else:
                look_lat, look_lon, look_alt_ft = look
            camera_track.append({
                "t": round(t, 3),
                "lat": lat,
                "lon": lon,
                "alt_ft": round(alt_ft, 1),
                "heading": round(heading, 2),
                "pitch": round(pitch, 2),
                "look_lat": look_lat,
                "look_lon": look_lon,
                "look_alt_ft": round(look_alt_ft, 1),
                "fov_deg": round(camera.fov_at(t), 2),
            })

    return {"duration": duration, "samples": rows, "camera_track": camera_track}


def sample_times_for_program(timed: TimedProgram,
                             samples: int = DEFAULT_SAMPLES,
                             extra_times: list[float] | None = None) -> list[float]:
    """Even grid plus every boundary, so short arcs are not drawn as chords.

    Boundaries keep full float precision. Rounding them (even to 1e-6) can
    push a seam or an arc start onto the previous phase, and the sample then
    carries the wrong pose and the wrong path_kind. Camera anchor times are
    folded in so cinematic keys land on a sample.
    """
    duration = max(timed.duration_s, 1e-6)
    count = max(samples, math.ceil(duration / MAX_SAMPLE_STEP_S))
    times = {duration * index / count for index in range(count + 1)}
    times.update(boundary for boundary in timed.boundary_times()
                 if 0.0 <= boundary <= duration + 1e-12)
    if extra_times:
        times.update(t for t in extra_times if 0.0 <= t <= duration + 1e-12)
    return sorted(times)


def _program_camera_track(timed: TimedProgram, program: PathProgram,
                          times: list[float]) -> tuple[list[dict], list[dict]]:
    """Solve anchored cameras into the same camera_track shape as waypoint preview."""
    timed_keys, report = resolve_program_cameras(program, timed)
    if not timed_keys:
        return [], report
    camera = SolvedCameraPath(
        timed_keys, program.origin.lat, program.origin.lon,
    )
    track = []
    for t in times:
        pose = pose_from_program(timed.pose_at(t))
        view = camera.world_view_at(t, pose)
        if view is None:
            continue
        lat, lon, alt_ft, heading, pitch = view
        look = camera.look_target_at(t, pose)
        if look is None:
            look_lat, look_lon, look_alt_ft = pose.lat, pose.lon, pose.alt_ft_msl
        else:
            look_lat, look_lon, look_alt_ft = look
        track.append({
            "t": round(t, 3),
            "lat": lat,
            "lon": lon,
            "alt_ft": round(alt_ft, 1),
            "heading": round(heading, 2),
            "pitch": round(pitch, 2),
            "look_lat": look_lat,
            "look_lon": look_lon,
            "look_alt_ft": round(look_alt_ft, 1),
            "fov_deg": round(camera.fov_at(t), 2),
        })
    return track, report


def preview_program(program: PathProgram, samples: int = DEFAULT_SAMPLES) -> dict:
    """Solve a PathProgram into the same sample format ``preview`` produces.

    Camera keys anchor to ``segment_id`` + ``at`` (§8); absolute times are
    derived here and fed through ``SolvedCameraPath`` so the map and 3D view
    see the same ``camera_track`` shape as waypoint paths.

    ``segments`` carries the same per-segment tips and solvability the harness
    uses, so stage 7 can drive the popup and map gizmos from one round-trip.
    """
    if not program.segments:
        return {
            "duration": 0.0, "samples": [], "camera_track": [],
            "camera_keys": [],
            "segments": [], "solved_program": program.model_dump(mode="json"),
            "constrained": False, "source": "program",
        }

    outcome = solve(program)
    # Cameras are authored on the pre-solve program (segment ids are stable);
    # geometry/timing use the solved copy.
    timed = TimedProgram(outcome.program, outcome.solved)
    summaries = segment_summaries(timed, outcome)
    camera_times = []
    camera_report: list[dict] = []
    if program.camera_keyframes:
        _, camera_report = resolve_program_cameras(program, timed)
        camera_times = [
            entry["time_offset"] for entry in camera_report
            if entry["time_offset"] is not None
        ]
    if timed.duration_s <= 0.0:
        return {
            "duration": 0.0, "samples": [], "camera_track": [],
            "camera_keys": camera_report,
            "segments": summaries,
            "solved_program": outcome.program.model_dump(mode="json"),
            "constrained": any(seg.constraints for seg in outcome.program.segments),
            "source": "program",
        }

    seams = list(timed.seam_times)
    times = sample_times_for_program(timed, samples, camera_times)
    rows = []
    for t in times:
        pose = timed.pose_at(t)
        index = timed.segment_index_at(t)
        kind = PROGRAM_PATH_KIND.get(
            outcome.program.segments[index].kind, "STRAIGHT"
        )
        rows.append({
            "t": round(t, 3),
            "lat": pose.lat,
            "lon": pose.lon,
            "alt_ft": round(pose.alt_ft_msl, 1),
            "heading": round(pose.heading_deg_true, 2),
            "bank": round(pose.bank_deg, 2),
            "pitch": round(pose.pitch_deg, 2),
            "speed_kt": round(pose.ground_speed_ms * MS_TO_KT, 1),
            "path_kind": kind,
            "path_mode": kind,
            # Index into program.segments — the editor highlights the selection.
            "segment_index": index,
            # True on the first sample of a segment the pen jumped to. A
            # consumer drawing a continuous line has to start a new polyline
            # here rather than join it to the row before.
            "break_before": any(abs(t - seam) < 1e-9 for seam in seams),
        })

    camera_track, camera_report = _program_camera_track(timed, program, times)

    return {
        "duration": round(timed.duration_s, 6),
        "samples": rows,
        "camera_track": camera_track,
        "camera_keys": camera_report,
        "segments": summaries,
        "constrained": any(seg.constraints for seg in outcome.program.segments),
        # Handy for the harness and for stage 6 side-by-side comparison; the
        # existing player ignores keys it does not know.
        "source": "program",
        "solved_program": outcome.program.model_dump(mode="json"),
    }
