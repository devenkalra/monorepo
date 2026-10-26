"""Segment path program — the authored model from SEGMENT_MODEL.md.

A path is an origin plus an ordered list of segments that advance a pen.
Parameters are primary and endpoints are derived, which is the inversion of
the waypoint model in ``schema.py``. The two coexist: nothing here migrates or
replaces an existing ``PathDocument``.

Stages 1 to 4 of the build order: schema, geometry, clock, solver, and the
Hermite / Spline primitives with their construction provenance.
"""

from __future__ import annotations

import math
import re
import secrets
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_serializer, model_validator

from .schema import (
    Angle,
    AutoAngle,
    AutoBank,
    CameraPosition,
    CameraTransition,
    CameraType,
    CockpitCamera,
    Easing,
    LookAt,
    LookAtAircraft,
    UpVector,
)

PROGRAM_SCHEMA_VERSION = 1

# A pin on a spline names a control point by index. The count is not fixed, so
# the validator matches the shape rather than looking the name up in a table.
_SPLINE_PIN = re.compile(
    r"^control_points\.\d+\.(lat|lon|alt_ft_msl|weight)$"
)


def mint_segment_id() -> str:
    return secrets.token_hex(6)


class GeoPoint(BaseModel):
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    alt_ft_msl: float = 0.0


class Direction(BaseModel):
    """A direction in the local horizon frame."""

    heading_deg: float = 0.0
    climb_deg: float = Field(default=0.0, ge=-90.0, le=90.0)


class VelocityProfile(BaseModel):
    """Speed in m/s as a cubic in normalised arc length.

    ``v(s) = c0 + c1*s + c2*s**2 + c3*s**3`` where s runs 0..1 across the
    segment. Normalised rather than absolute arc length so the entry and exit
    speeds survive a geometry edit: with endpoints solved, a segment's length
    changes constantly, and in absolute arc length ``v(L)`` would drift every
    time a radius moved, silently breaking continuity with the next segment.

    Stored and carried from stage 1; consumed by the time law in stage 2.
    """

    c0: float = Field(default=100.0, gt=0.0)
    c1: float = 0.0
    c2: float = 0.0
    c3: float = 0.0
    # Take c0 from the previous segment's exit speed, so a boundary is smooth
    # by default rather than by hand.
    inherit_entry: bool = True

    def speed_at(self, s: float) -> float:
        s = min(1.0, max(0.0, s))
        return self.c0 + self.c1 * s + self.c2 * s * s + self.c3 * s * s * s

    @property
    def entry_speed(self) -> float:
        return self.c0

    @property
    def exit_speed(self) -> float:
        return self.c0 + self.c1 + self.c2 + self.c3

    def scaled(self, k: float) -> "VelocityProfile":
        """Multiply every speed by k, which divides the segment's duration by k."""
        return self.model_copy(update={
            "c0": self.c0 * k, "c1": self.c1 * k,
            "c2": self.c2 * k, "c3": self.c3 * k,
        })

    def with_entry(self, speed: float) -> "VelocityProfile":
        """Re-seat the entry speed, keeping the shape — the c1..c3 deltas — intact."""
        return self.model_copy(update={"c0": speed})

    def minimum_speed(self) -> tuple[float, float]:
        """The lowest speed on [0, 1] and where it occurs.

        Exact rather than sampled: a cubic on a closed interval takes its
        minimum either at an endpoint or at a root of its quadratic
        derivative, and there are at most two of those.
        """
        candidates = [0.0, 1.0]
        # v'(s) = c1 + 2*c2*s + 3*c3*s**2
        a, b, c = 3.0 * self.c3, 2.0 * self.c2, self.c1
        if abs(a) < 1e-12:
            if abs(b) > 1e-12:
                candidates.append(-c / b)
        else:
            discriminant = b * b - 4.0 * a * c
            if discriminant >= 0.0:
                root = math.sqrt(discriminant)
                candidates.append((-b + root) / (2.0 * a))
                candidates.append((-b - root) / (2.0 * a))
        inside = [s for s in candidates if 0.0 <= s <= 1.0]
        return min((self.speed_at(s), s) for s in inside)


class Boundary(BaseModel):
    """The join at the end of a segment.

    A dwell cannot be expressed as a speed: ``v -> 0`` makes the time integral
    diverge, so a hold stays explicit here.
    """

    dwell_s: float = Field(default=0.0, ge=0.0)
    heading: Angle = AutoAngle()
    pitch: Angle = AutoAngle()
    bank: Angle = AutoAngle()


class Constraint(BaseModel):
    """Somewhere the curve must pass through.

    Pinning a point is a constraint rather than a stored coordinate, so one
    form covers both a pinned endpoint (``at = 1.0``) and a through-point
    partway along. That is why there is one spline primitive and not two.

    The two locks exist so altitude alone can be constrained — "be at 5000
    feet by the end of this leg" says nothing about where.
    """

    kind: Literal["POINT"] = "POINT"
    at: float = Field(default=1.0, ge=0.0, le=1.0)
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    alt_ft_msl: float = 0.0
    lock_horizontal: bool = True
    lock_vertical: bool = True

    @property
    def equations(self) -> int:
        return 2 * int(self.lock_horizontal) + int(self.lock_vertical)


# The parameters the solver may move, per segment kind. Names are dotted
# paths into the model. Used to reject a typo in ``pinned`` at parse time,
# when the kind is known, rather than letting it silently pin nothing.
# Spline pins are matched by pattern — the control count is not fixed.
SOLVER_PARAMETERS: dict[str, tuple[str, ...]] = {
    "MOVE_TO": ("to.lat", "to.lon", "to.alt_ft_msl",
                "tangent.heading_deg", "tangent.climb_deg", "speed_ms"),
    "LINE_TO": ("heading_deg", "climb_deg", "distance_m"),
    "ARC": ("radius_m", "sweep_deg", "tilt_deg", "rise_per_turn_m", "side"),
    "HERMITE": ("to.lat", "to.lon", "to.alt_ft_msl",
                "out.heading_deg", "out.climb_deg", "out.length_m",
                "into.heading_deg", "into.climb_deg", "into.length_m"),
}


class Construction(BaseModel):
    """How this segment was originally built. Never read during evaluation.

    The fitter and the three-point arc tool leave their inputs here so the
    operator can re-open them. ``produced`` records the hull the construction
    returned, so the editor can tell whether a re-fit would discard direct
    edits made since.
    """

    kind: Literal["FIT_POINTS", "ARC_THREE_POINT"] = "FIT_POINTS"
    points: list[GeoPoint] = Field(default_factory=list)
    tolerance_m: float | None = None
    # East/up/north metres of the hull at construction time. Empty when the
    # construction did not produce a polygon (an arc three-point leaves none).
    produced: list[tuple[float, float, float]] = Field(default_factory=list)


class SegmentBase(BaseModel):
    id: str = ""
    name: str = ""
    velocity: VelocityProfile = Field(default_factory=VelocityProfile)
    on_ground: bool = False
    end: Boundary = Field(default_factory=Boundary)
    # Every parameter always holds a value; this names the ones the solver
    # may not move. Values rather than holes, so the document draws without
    # a solve having to succeed, and so the stored numbers can seed the
    # numeric solver — on a system with several solutions, starting from
    # where the operator left it is what stops the shape jumping branches
    # mid-drag.
    pinned: set[str] = Field(default_factory=set)
    constraints: list[Constraint] = Field(default_factory=list)
    construction: Construction | None = None

    @field_serializer("pinned")
    def _sorted_pins(self, pinned: set[str]) -> list[str]:
        # A set has no order, and an unordered list makes every save a diff.
        return sorted(pinned)

    @model_validator(mode="after")
    def _check_pins(self):
        kind = getattr(self, "kind", "")
        if kind == "SPLINE":
            unknown = sorted(name for name in self.pinned if not _SPLINE_PIN.match(name))
            hint = "control_points.<i>.{lat,lon,alt_ft_msl,weight}"
        else:
            known = SOLVER_PARAMETERS.get(kind, ())
            unknown = sorted(self.pinned - set(known))
            hint = ", ".join(known) if known else "(none)"
        if unknown:
            raise ValueError(
                f"{', '.join(unknown)} cannot be pinned on a {kind} segment. "
                f"It has {hint}."
            )
        return self


class MoveToSegment(SegmentBase):
    """Jump the pen without flying the gap.

    Legal mid-path: a hand-drawn tour that cuts between locations, or a flown
    track with an uninteresting middle removed. Time stays continuous and only
    position jumps, so cutting ten minutes out makes the take ten minutes
    shorter rather than leaving a hole in the clock.

    Tangent and speed mean nothing across a jump, so this may re-seed them.
    Leave them unset and the following segment must supply its own start
    direction.
    """

    kind: Literal["MOVE_TO"] = "MOVE_TO"
    to: GeoPoint
    tangent: Direction | None = None
    speed_ms: float | None = Field(default=None, gt=0.0)


class LineToSegment(SegmentBase):
    """Straight, stated polar: where to point and how far to go."""

    kind: Literal["LINE_TO"] = "LINE_TO"
    heading_deg: float = 0.0
    climb_deg: float = Field(default=0.0, ge=-90.0, le=90.0)
    distance_m: float = Field(gt=0.0)
    # Carry straight on from the pen instead of using the stored angles.
    inherit_direction: bool = False


class ArcSegment(SegmentBase):
    """Helical arc leaving along the pen tangent.

    ``side`` is not redundant with the sign of the sweep. Given the pen
    position, the entry tangent and the plane, the centre can sit on either
    side at ``radius_m`` and no other parameter resolves that, so the sweep
    stays non-negative and the one sign lives here where it reads.

    There is no radius floor. The chord/2 clamp and the old ``major`` flag
    both existed only because two endpoints were fixed by construction, and
    neither is now.
    """

    kind: Literal["ARC"] = "ARC"
    side: Literal["LEFT", "RIGHT"] = "LEFT"
    radius_m: float = Field(gt=0.0)
    # Unbounded above: past 360 is simply more than one turn.
    sweep_deg: float = Field(default=90.0, ge=0.0)
    # Roll of the circle's plane about the entry tangent, positive toward the
    # right of travel. Zero is a horizontal circle.
    tilt_deg: float = Field(default=0.0, gt=-90.0, lt=90.0)
    # None matches the pen's climb, which is what keeps the join smooth: a
    # helix's tangent carries a component along the plane normal equal to the
    # rise rate. Setting it explicitly is allowed and kinks the vertical only.
    rise_per_turn_m: float | None = None


class HermiteHandle(BaseModel):
    """A cubic Hermite tangent, stated polar so a map gizmo can drag it.

    ``length_m`` is the visual handle length. The tangent magnitude used in
    the cubic is three times that — the same convention the waypoint model's
    HermiteLeg uses — so a handle that looks a third of the chord long is the
    fair default for a near-straight span.
    """

    heading_deg: float = 0.0
    climb_deg: float = Field(default=0.0, ge=-90.0, le=90.0)
    length_m: float = Field(default=500.0, gt=0.0)


class HermiteSegment(SegmentBase):
    """Cubic Hermite: end point with in and out handles.

    The out handle defaults from the pen tangent (``out is None``), so G1
    continuity with the previous segment is free rather than something to
    maintain. Setting it explicitly is allowed and introduces a kink.
    """

    kind: Literal["HERMITE"] = "HERMITE"
    to: GeoPoint
    out: HermiteHandle | None = None
    into: HermiteHandle = Field(default_factory=HermiteHandle)


class ControlPoint(BaseModel):
    """One vertex of a NURBS control polygon, with its weight."""

    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    alt_ft_msl: float = 0.0
    weight: float = Field(default=1.0, gt=0.0)


class SplineSegment(SegmentBase):
    """A NURBS curve whose control polygon is authoritative.

    Evaluation reads only the hull and the weights. There is no solve on
    edit, the response to a drag is continuous, and support is local: moving
    one control point cannot disturb the far end. The fitter survives only
    as a constructor that writes into ``construction`` (§7.2).
    """

    kind: Literal["SPLINE"] = "SPLINE"
    control_points: list[ControlPoint] = Field(min_length=2)
    degree: int = Field(default=3, ge=1, le=7)
    # None means a clamped uniform knot vector for the current control count.
    # Authored knots are kept when the operator has edited them; a re-fit
    # replaces them.
    knots: list[float] | None = None

    @model_validator(mode="after")
    def _check_degree(self):
        if len(self.control_points) <= self.degree:
            raise ValueError(
                f"a degree-{self.degree} spline needs more than {self.degree} "
                f"control points; this one has {len(self.control_points)}"
            )
        if self.knots is not None:
            expected = len(self.control_points) + self.degree + 1
            if len(self.knots) != expected:
                raise ValueError(
                    f"a degree-{self.degree} spline with "
                    f"{len(self.control_points)} control points needs "
                    f"{expected} knots; this one has {len(self.knots)}"
                )
        return self


Segment = Annotated[
    Union[MoveToSegment, LineToSegment, ArcSegment, HermiteSegment, SplineSegment],
    Field(discriminator="kind"),
]


class CameraAnchor(BaseModel):
    """Where a camera key sits on the program — a fraction along one segment.

    Absolute time is derived at preview from the timed program, so reshaping
    or retiming a segment keeps the shot framed as authored (§8).
    """

    segment_id: str
    at: float = Field(default=0.5, ge=0.0, le=1.0)


class ProgramCameraKeyframe(BaseModel):
    """Same cinematic payload as a waypoint camera key, bound by anchor."""

    anchor: CameraAnchor
    camera_type: CameraType = CameraType.CINEMATIC
    fov_deg: float | None = Field(default=None, gt=1.0, lt=180.0)
    cockpit: CockpitCamera = Field(default_factory=CockpitCamera)
    position: CameraPosition | None = None
    look_at: LookAt = Field(default_factory=LookAtAircraft)
    up: UpVector = Field(default_factory=UpVector)
    easing: Easing = Field(default_factory=Easing)
    transition: CameraTransition = CameraTransition.BLEND


class PathProgram(BaseModel):
    schema_version: int = PROGRAM_SCHEMA_VERSION
    # Where the pen starts. A leading MoveTo is allowed but not required.
    origin: GeoPoint
    segments: list[Segment] = Field(default_factory=list)
    # The same bank law the waypoint model uses, so a program banks the way
    # the rest of the app already does.
    auto_bank: AutoBank = Field(default_factory=AutoBank)
    camera_keyframes: list[ProgramCameraKeyframe] = Field(default_factory=list)

    @model_validator(mode="after")
    def _mint_segment_ids(self):
        """Mint empty/duplicate segment ids without orphaning camera anchors.

        A duplicate id is reminted on the later segment only; cameras that
        named the shared string still refer to the first keeper, so they must
        not be rewritten. Empty ids are replaced, and any camera still anchored
        to "" is bound to the first segment that was minted from empty.
        """
        seen: set[str] = set()
        first_empty_mint: str | None = None
        for segment in self.segments:
            old = segment.id
            if not segment.id or segment.id in seen:
                segment.id = mint_segment_id()
                if not old and first_empty_mint is None:
                    first_empty_mint = segment.id
            seen.add(segment.id)
        if first_empty_mint:
            for key in self.camera_keyframes:
                if not key.anchor.segment_id:
                    key.anchor.segment_id = first_empty_mint
        return self
