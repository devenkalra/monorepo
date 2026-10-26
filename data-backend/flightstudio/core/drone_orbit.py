"""Fill cinematic keyframes with a level drone orbit around the aircraft.

The sim's own drone camera ignores SimConnect, so this writes ordinary
HORIZON cinematic keys the existing solver already flies.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .schema import (
    CameraKeyframe,
    CameraType,
    HorizonPosition,
    LookAtAircraft,
    UpVector,
)

MAX_STEP_DEG = 15.0
MAX_STEP_S = 0.5
LookAtRef = Literal["CG", "NOSE", "TAIL", "COCKPIT"]
OrbitDirection = Literal["CW", "CCW"]


class OrbitSpec(BaseModel):
    from_s: float = Field(ge=0.0)
    to_s: float = Field(gt=0.0)
    radius_m: float = Field(gt=0.0, le=1000.0)
    height_m: float = 0.0
    look_at: LookAtRef = "CG"
    speed_deg_s: float = Field(gt=0.0, le=180.0)
    direction: OrbitDirection = "CW"
    start_azimuth_deg: float = 0.0
    fov_deg: float | None = Field(default=None, gt=1.0, lt=180.0)


def sample_step_s(speed_deg_s: float) -> float:
    """One key at least every 15° or 0.5 s, whichever is tighter."""
    if speed_deg_s <= 0.0:
        raise ValueError("orbit speed must be greater than 0")
    return min(MAX_STEP_S, MAX_STEP_DEG / speed_deg_s)


def build_orbit(spec: OrbitSpec) -> list[CameraKeyframe]:
    if spec.to_s <= spec.from_s:
        raise ValueError("orbit To must be after From")
    span = spec.to_s - spec.from_s
    count = max(2, round(span / sample_step_s(spec.speed_deg_s)) + 1)
    sign = 1.0 if spec.direction == "CW" else -1.0
    frames: list[CameraKeyframe] = []
    for index in range(count):
        time = spec.from_s + span * index / (count - 1)
        azimuth = spec.start_azimuth_deg + sign * spec.speed_deg_s * (time - spec.from_s)
        frames.append(CameraKeyframe(
            time_offset=time,
            camera_type=CameraType.CINEMATIC,
            fov_deg=spec.fov_deg,
            position=HorizonPosition(
                azimuth_deg=azimuth,
                radius_m=spec.radius_m,
                height_m=spec.height_m,
            ),
            look_at=LookAtAircraft(ref=spec.look_at),
            up=UpVector(mode="WORLD_UP"),
        ))
    return frames


def apply_orbit(existing: list[CameraKeyframe], spec: OrbitSpec) -> list[CameraKeyframe]:
    """Replace cinematic keys in range. Cockpit keys in the span refuse."""
    for keyframe in existing:
        if spec.from_s <= keyframe.time_offset <= spec.to_s:
            if keyframe.camera_type is CameraType.COCKPIT:
                raise ValueError(
                    f"A cockpit camera at {keyframe.time_offset:.1f}s sits in the "
                    "orbit range. Move the range or remove that keyframe first."
                )
    orbit = build_orbit(spec)
    kept = [
        keyframe for keyframe in existing
        if not (spec.from_s <= keyframe.time_offset <= spec.to_s)
    ]
    return sorted(kept + orbit, key=lambda keyframe: keyframe.time_offset)
