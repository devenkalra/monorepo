"""Path document schema, per design section 6.

Pydantic models rather than plain dataclasses because these are also the API
request and response bodies, and the editor needs the validation errors.
"""

from __future__ import annotations

import re
import secrets
from enum import StrEnum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .clock import parse_time_of_day

SCHEMA_VERSION = 4
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def mint_waypoint_id() -> str:
    return secrets.token_hex(6)


class TimeSource(StrEnum):
    AUTHORED = "AUTHORED"
    IMPORTED = "IMPORTED"
    INTERPOLATED = "INTERPOLATED"


class PlaybackMode(StrEnum):
    POSE_INJECTION = "POSE_INJECTION"
    SIM_FLOWN = "SIM_FLOWN"


class Entity(StrEnum):
    AI_PROXY = "AI_PROXY"
    USER_AIRCRAFT = "USER_AIRCRAFT"


class CameraType(StrEnum):
    CINEMATIC = "CINEMATIC"
    COCKPIT = "COCKPIT"


class CameraTransition(StrEnum):
    """How this camera keyframe joins the shot.

    BLEND is a spline control point on the current interpolate. SHOT cuts to
    this pose and starts a new interpolate; earlier Blend keys do not pull it.
    CUT is a cutaway: the interpolated path ignores it, the camera jumps here
    for ``hold_s``, then snaps back to the pose the current shot would have
    had at that time.
    """

    BLEND = "BLEND"
    SHOT = "SHOT"
    CUT = "CUT"


def camera_sort_key(keyframe) -> tuple[float, int]:
    """Blend, then new shot, then cutaway when several keys share a time.

    A Blend end and a Shot start at the same instant cut on the shot: the
    previous interpolate is used only for t before that time.
    """
    rank = {
        CameraTransition.BLEND: 0,
        CameraTransition.SHOT: 1,
        CameraTransition.CUT: 2,
    }.get(getattr(keyframe, "transition", None), 0)
    return (keyframe.time_offset, rank)


class CockpitView(StrEnum):
    """One of the sim's cockpit presets. Free head direction is not writable
    through SimConnect in MSFS 2024, so a cockpit shot picks a preset."""

    PILOT = "PILOT"
    CLOSE = "CLOSE"
    LANDING = "LANDING"
    COPILOT = "COPILOT"
    INSTRUMENT = "INSTRUMENT"
    QUICKVIEW = "QUICKVIEW"
    # One of the ten cockpit cameras saved in the sim with Ctrl+Alt+0..9.
    # Carries seat, head direction and zoom; loaded by pressing Alt+n.
    CUSTOM = "CUSTOM"


class CockpitCamera(BaseModel):
    view: CockpitView = CockpitView.PILOT
    # Which instrument panel, quickview or custom slot, numbered as the sim
    # numbers them (from 0). Ignored by the four pilot presets.
    index: int = Field(default=0, ge=0)
    # COCKPIT CAMERA ZOOM, percent. None leaves the sim's zoom alone.
    zoom_pct: float | None = Field(default=None, ge=0.0, le=100.0)


class PathKind(StrEnum):
    STRAIGHT = "STRAIGHT"
    ARC = "ARC"
    HERMITE = "HERMITE"
    BSPLINE = "BSPLINE"


class Plane(BaseModel):
    """ENU normal of the plane an arc sits on. Default is local horizontal."""

    normal_east: float = 0.0
    normal_up: float = 1.0
    normal_north: float = 0.0


class StraightLeg(BaseModel):
    kind: Literal["STRAIGHT"] = "STRAIGHT"


class ArcLeg(BaseModel):
    kind: Literal["ARC"] = "ARC"
    side: Literal["LEFT", "RIGHT"] = "LEFT"
    radius_m: float = Field(gt=0.0)
    major: bool = False
    plane: Plane = Field(default_factory=Plane)


class HermiteHandle(BaseModel):
    heading_deg: float = 0.0
    climb_deg: float = 0.0
    length_m: float = Field(gt=0.0)


class HermiteLeg(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    kind: Literal["HERMITE"] = "HERMITE"
    out: HermiteHandle
    into: HermiteHandle


class BSplineLeg(BaseModel):
    """Clamped cubic B-spline from this waypoint through end_id.

    Ends lie on the curve. Interiors pull it; the curve may miss them by
    about tolerance_m. Smaller values hug the points, larger values stay fairer.
    """

    kind: Literal["BSPLINE"] = "BSPLINE"
    end_id: str
    tolerance_m: float = Field(default=50.0, ge=0.0)


FlightPathLeg = Annotated[
    Union[StraightLeg, ArcLeg, HermiteLeg, BSplineLeg],
    Field(discriminator="kind"),
]


def coalesce_bspline_legs(keys: list[FlightKeyframe]) -> None:
    """Turn a run of B-spline 'to next' legs into one span.

    Marking four consecutive waypoints as B-spline used to store four
    two-point fits. A two-point cubic is a chord, so the map showed
    straight edges instead of one curve through those points.
    """
    index_of = {key.id: index for index, key in enumerate(keys)}
    last = len(keys) - 1
    index = 0
    while index < last:
        path = keys[index].path
        if not isinstance(path, BSplineLeg):
            index += 1
            continue
        farthest = index_of.get(path.end_id, index)
        if farthest <= index:
            index += 1
            continue
        scan = index + 1
        while scan < last and isinstance(keys[scan].path, BSplineLeg):
            other = index_of.get(keys[scan].path.end_id, scan + 1)
            farthest = max(farthest, other, scan + 1)
            scan += 1
        farthest = min(farthest, last)
        path.end_id = keys[farthest].id
        for inner in range(index + 1, farthest):
            keys[inner].path = StraightLeg()
        index = farthest


class Easing(BaseModel):
    """Shapes pacing along the curve without moving it (design section 2.2)."""

    # Neutral is 0.0, a constant-rate pass-through. Easing defaults to off so
    # that an imported track does not decelerate at every one of its waypoints.
    ease_in: float = Field(default=0.0, ge=0.0, le=1.0)
    ease_out: float = Field(default=0.0, ge=0.0, le=1.0)
    hold_s: float = Field(default=0.0, ge=0.0)


class AutoAngle(BaseModel):
    mode: Literal["AUTO"] = "AUTO"


class ManualAngle(BaseModel):
    mode: Literal["MANUAL"] = "MANUAL"
    deg: float


Angle = Annotated[Union[AutoAngle, ManualAngle], Field(discriminator="mode")]


class FlightKeyframe(BaseModel):
    # Stable across time-sorts so the editor can select, group and bulk-edit.
    # Empty on old documents; PathDocument mints one before the path is stored.
    id: str = ""
    name: str = ""
    time_offset: float = Field(ge=0.0)
    time_source: TimeSource = TimeSource.AUTHORED
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    alt_ft_msl: float
    # AUTO derives the angle from the curve: heading from the track tangent,
    # pitch from the flight-path angle, bank from turn rate and speed. MANUAL
    # pins it, and the solver splines smoothly between whatever is authored.
    heading: Angle = AutoAngle()
    pitch: Angle = AutoAngle()
    bank: Angle = AutoAngle()
    easing: Easing = Easing()
    # Segment from this keyframe to the next. Ignored on the final keyframe.
    path: FlightPathLeg = Field(default_factory=StraightLeg)
    # The leg from this keyframe rolls on the surface. Playback then puts the
    # wheels on the sim's own terrain instead of trusting alt_ft_msl, which on
    # the ground is only as good as its source and the mesh it was recorded on.
    on_ground: bool = False

    @model_validator(mode="before")
    @classmethod
    def _legacy_path_mode(cls, data):
        if not isinstance(data, dict):
            return data
        if data.get("path") is None:
            data = {**data, "path": {"kind": "STRAIGHT"}}
        data.pop("path_mode", None)
        return data


class WorldPosition(BaseModel):
    frame: Literal["WORLD"] = "WORLD"
    lat: float
    lon: float
    alt_ft_msl: float


class BodyPosition(BaseModel):
    frame: Literal["BODY"] = "BODY"
    ref: str = "CG"
    x_m: float = 0.0
    y_m: float = 0.0
    z_m: float = 0.0


class HorizonPosition(BaseModel):
    """Level-plane offset: a drone that does not roll with the aircraft.

    Azimuth 0 is aft, 90 the right wing, 180 off the nose, 270 the left wing.
    Height is world-up metres from the CG.
    """

    frame: Literal["HORIZON"] = "HORIZON"
    azimuth_deg: float = 0.0
    radius_m: float = Field(gt=0.0)
    height_m: float = 0.0


CameraPosition = Annotated[
    Union[WorldPosition, BodyPosition, HorizonPosition],
    Field(discriminator="frame"),
]


class LookAtWorld(BaseModel):
    mode: Literal["WORLD_POINT"] = "WORLD_POINT"
    lat: float
    lon: float
    alt_ft_msl: float


class LookAtAircraft(BaseModel):
    mode: Literal["AIRCRAFT_POINT"] = "AIRCRAFT_POINT"
    ref: Literal["NOSE", "TAIL", "CG", "COCKPIT"] = "CG"


class LookAtOffset(BaseModel):
    """A ghost point that rides with the aircraft in the level plane.

    Right and forward follow heading, not bank. Height is world-up. Aim here
    to put the airframe off-centre (rule of thirds) while the camera tracks.
    """

    mode: Literal["AIRCRAFT_OFFSET"] = "AIRCRAFT_OFFSET"
    x_m: float = 0.0
    y_m: float = 0.0
    z_m: float = 0.0


class LookAtFree(BaseModel):
    """Explicit orientation; the only form that does not imply a target."""

    mode: Literal["FREE"] = "FREE"
    pitch_deg: float = 0.0
    heading_deg: float = 0.0


LookAt = Annotated[
    Union[LookAtWorld, LookAtAircraft, LookAtOffset, LookAtFree],
    Field(discriminator="mode"),
]


class UpVector(BaseModel):
    mode: Literal["WORLD_UP", "AIRCRAFT_UP", "EXPLICIT"] = "WORLD_UP"
    x: float = 0.0
    y: float = 1.0
    z: float = 0.0


class CameraKeyframe(BaseModel):
    time_offset: float = Field(ge=0.0)
    camera_type: CameraType = CameraType.CINEMATIC
    fov_deg: float | None = Field(default=None, gt=1.0, lt=180.0)
    cockpit: CockpitCamera = CockpitCamera()
    position: CameraPosition | None = None
    look_at: LookAt = LookAtAircraft()
    up: UpVector = UpVector()
    easing: Easing = Easing()
    transition: CameraTransition = CameraTransition.BLEND


class InitialState(BaseModel):
    """Where a sim-flown take starts. The sim does the flying from here."""

    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    alt_ft_msl: float
    heading_deg_true: float = 0.0
    pitch_deg: float = 0.0
    bank_deg: float = 0.0
    airspeed_kt: float = Field(default=150.0, gt=0.0)


class ControlKeyframe(BaseModel):
    """Control positions from this time on. A blank channel holds its last value.

    Signs are the pilot's: positive aileron rolls right, positive elevator is
    back stick (nose up), positive rudder yaws right, positive elevator trim
    is nose up. Throttle is 0..1.
    """

    time_offset: float = Field(ge=0.0)
    aileron: float | None = Field(default=None, ge=-1.0, le=1.0)
    elevator: float | None = Field(default=None, ge=-1.0, le=1.0)
    rudder: float | None = Field(default=None, ge=-1.0, le=1.0)
    throttle: float | None = Field(default=None, ge=0.0, le=1.0)
    elevator_trim: float | None = Field(default=None, ge=-1.0, le=1.0)
    # How the channels this keyframe sets get there from their previous value.
    transition: Literal["RAMP", "STEP"] = "RAMP"


class SimFlight(BaseModel):
    initial: InitialState
    controls: list[ControlKeyframe] = Field(default_factory=list)
    duration_s: float = Field(default=30.0, gt=0.0)
    # Held frozen at the start for this long so scenery can stream in first.
    settle_s: float = Field(default=5.0, ge=0.0)

    @field_validator("controls")
    @classmethod
    def _sorted_by_time(cls, value):
        return sorted(value, key=lambda k: k.time_offset)


class AutoBank(BaseModel):
    """How AUTO bank is faired in time. Positions still go through every key.

    Coordinated bank is atan(omega v / g) from the path. These shape that
    series into a roll a passenger jet would fly, and are stored on the path
    so a take plays the same way twice.
    """

    max_deg: float = Field(default=30.0, gt=0.0, le=90.0)
    roll_rate_deg_s: float = Field(default=5.0, gt=0.0, le=90.0)
    smoothing_s: float = Field(default=6.0, ge=0.1, le=60.0)


class PathMeta(BaseModel):
    path_id: str
    schema_version: int = SCHEMA_VERSION
    duration_seconds: float = 0.0
    target_aircraft: str | None = None
    playback_mode: PlaybackMode = PlaybackMode.POSE_INJECTION
    entity: Entity = Entity.AI_PROXY
    output_fps: int = 30
    auto_bank: AutoBank = Field(default_factory=AutoBank)
    # A flown take saved from a segment of another path: which, and where its
    # time 0 falls on that path's timeline, so takes can be joined back up.
    flown_from: str | None = None
    flown_from_s: float | None = None
    # Local clock when the take starts, HH:MM. None leaves the sim's time alone.
    time_of_day: str | None = None

    @field_validator("time_of_day", mode="before")
    @classmethod
    def _time_of_day(cls, value):
        parsed = parse_time_of_day(None if value == "" else value)
        if parsed is None:
            return None
        return f"{parsed[0]:02d}:{parsed[1]:02d}"


class SystemsKeyframe(BaseModel):
    """What the aircraft's controls and configuration were doing, from a flown take.

    On the flight keyframes' clock. Flaps (the handle position, 0 = up) and
    gear are set during pose-injection playback; the surface and lever
    positions are a record of the flight: a frozen fly-by-wire aircraft winds
    its own elevator, so they cannot be shown faithfully (spike/probe_surfaces.py).
    """

    time_offset: float = Field(ge=0.0)
    flaps: int | None = Field(default=None, ge=0)
    gear_down: bool | None = None
    aileron: float | None = Field(default=None, ge=-1.0, le=1.0)
    elevator: float | None = Field(default=None, ge=-1.0, le=1.0)
    rudder: float | None = Field(default=None, ge=-1.0, le=1.0)
    throttle: float | None = Field(default=None, ge=0.0, le=1.0)


class WaypointGroup(BaseModel):
    """Named membership of flight waypoints. Not a nested path — time still orders the list."""

    id: str
    name: str = ""
    color: str = "#4ea1ff"
    member_ids: list[str] = Field(default_factory=list)

    @field_validator("color")
    @classmethod
    def _hex_color(cls, value: str) -> str:
        text = (value or "").strip().lower()
        if len(text) == 4 and text.startswith("#") and all(c in "0123456789abcdef" for c in text[1:]):
            text = "#" + "".join(c * 2 for c in text[1:])
        if not _HEX_COLOR.match(text):
            raise ValueError("color must be a #rrggbb hex value")
        return text


class PathDocument(BaseModel):
    meta: PathMeta
    flight_keyframes: list[FlightKeyframe] = Field(default_factory=list)
    camera_keyframes: list[CameraKeyframe] = Field(default_factory=list)
    sim_flight: SimFlight | None = None
    systems: list[SystemsKeyframe] = Field(default_factory=list)
    groups: list[WaypointGroup] = Field(default_factory=list)

    @field_validator("flight_keyframes", "camera_keyframes", "systems")
    @classmethod
    def _sorted_by_time(cls, value):
        if value and hasattr(value[0], "transition"):
            return sorted(value, key=camera_sort_key)
        return sorted(value, key=lambda k: k.time_offset)

    @model_validator(mode="after")
    def _mint_waypoint_ids(self):
        seen: set[str] = set()
        for key in self.flight_keyframes:
            if not key.id or key.id in seen:
                key.id = mint_waypoint_id()
            seen.add(key.id)
        ids = [key.id for key in self.flight_keyframes]
        for key in self.flight_keyframes:
            path = key.path
            if isinstance(path, BSplineLeg):
                try:
                    start = ids.index(key.id)
                    end = ids.index(path.end_id)
                except ValueError:
                    key.path = StraightLeg()
                else:
                    if end <= start:
                        key.path = StraightLeg()
        coalesce_bspline_legs(self.flight_keyframes)
        known = {key.id for key in self.flight_keyframes}
        claimed: set[str] = set()
        for group in self.groups:
            kept = []
            for member in group.member_ids:
                if member in known and member not in claimed:
                    kept.append(member)
                    claimed.add(member)
            group.member_ids = kept
        return self

    @property
    def duration(self) -> float:
        times = [k.time_offset for k in self.flight_keyframes]
        times += [k.time_offset for k in self.camera_keyframes]
        times += [k.time_offset for k in self.systems]
        return max(times) if times else 0.0


class Pose(BaseModel):
    """A solved aircraft pose at one instant."""

    lat: float
    lon: float
    alt_ft_msl: float
    pitch_deg: float
    bank_deg: float
    heading_deg_true: float


class CameraPose(BaseModel):
    """A solved camera pose, already reduced to what SimConnect accepts."""

    camera_type: CameraType = CameraType.CINEMATIC
    # Body-frame offset from the user aircraft, in metres.
    x_m: float = 0.0
    y_m: float = 0.0
    z_m: float = 0.0
    pitch_deg: float = 0.0
    bank_deg: float = 0.0
    heading_deg: float = 0.0
    fov_deg: float | None = None
    cockpit: CockpitCamera | None = None
