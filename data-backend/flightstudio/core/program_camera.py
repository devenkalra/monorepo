"""Resolve program camera anchors into timed CameraKeyframes (§8).

Preview and exporters keep using ``SolvedCameraPath``; this module only turns
``segment_id`` + ``at`` into ``time_offset``.
"""

from __future__ import annotations

from .program import PathProgram, ProgramCameraKeyframe
from .program_time import TimedProgram
from .schema import CameraKeyframe, Pose


def segment_index_by_id(program: PathProgram) -> dict[str, int]:
    return {segment.id: index for index, segment in enumerate(program.segments)}


def resolve_camera_keyframe(
    key: ProgramCameraKeyframe,
    timed: TimedProgram,
    index_by_id: dict[str, int] | None = None,
) -> tuple[CameraKeyframe | None, float | None, bool]:
    """Return (timed key, time_offset, orphan).

    Orphan keys (unknown segment_id) are dropped from the solve but reported
    so the editor can warn rather than silently lose the shot.
    """
    lookup = index_by_id if index_by_id is not None else segment_index_by_id(timed.program)
    index = lookup.get(key.anchor.segment_id)
    if index is None:
        return None, None, True
    time_offset = timed.time_at(index, key.anchor.at)
    resolved = CameraKeyframe(
        time_offset=max(0.0, time_offset),
        camera_type=key.camera_type,
        fov_deg=key.fov_deg,
        cockpit=key.cockpit,
        position=key.position,
        look_at=key.look_at,
        up=key.up,
        easing=key.easing,
        transition=key.transition,
    )
    return resolved, time_offset, False


def resolve_program_cameras(
    program: PathProgram, timed: TimedProgram,
) -> tuple[list[CameraKeyframe], list[dict]]:
    """Timed keys for SolvedCameraPath, plus per-authored-key diagnostics."""
    lookup = segment_index_by_id(program)
    resolved: list[CameraKeyframe] = []
    report: list[dict] = []
    for slot, key in enumerate(program.camera_keyframes):
        timed_key, time_offset, orphan = resolve_camera_keyframe(key, timed, lookup)
        entry = {
            "index": slot,
            "segment_id": key.anchor.segment_id,
            "at": key.anchor.at,
            "orphan": orphan,
            "time_offset": None if time_offset is None else round(time_offset, 4),
        }
        report.append(entry)
        if timed_key is not None:
            resolved.append(timed_key)
    return resolved, report


def pose_from_program(pose) -> Pose:
    """ProgramPose → schema Pose for SolvedCameraPath."""
    return Pose(
        lat=pose.lat,
        lon=pose.lon,
        alt_ft_msl=pose.alt_ft_msl,
        pitch_deg=pose.pitch_deg,
        bank_deg=pose.bank_deg,
        heading_deg_true=pose.heading_deg_true,
    )
