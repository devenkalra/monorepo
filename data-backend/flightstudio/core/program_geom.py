"""Evaluate a PathProgram into geometry, per SEGMENT_MODEL.md sections 3 to 5.

Walks the segments in order carrying pen state — position, tangent and speed —
and turns each into a curve in the program's local east/up/north metre frame.

Stage 1 is geometry only. There is no time here: the velocity profile is
carried but not integrated, so sampling is by distance. The time law, and with
it the one-sided attitude rates at a seam, arrive in stage 2.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from .bspline import NurbsCurve, clamped_knots
from .path_geom import Vec3, _add, _cross, _dot, _norm, _scale, _sub, _unit
from .program import (
    ArcSegment,
    HermiteHandle,
    HermiteSegment,
    LineToSegment,
    MoveToSegment,
    PathProgram,
    SplineSegment,
)
from .units import feet_to_metres, local_offset, metres_to_feet, normalise_heading, offset_latlon

WORLD_UP: Vec3 = (0.0, 1.0, 0.0)
# Below this the tangent has no usable horizontal part, and an arc leaving
# straight up has no "left" to put a centre on.
MIN_HORIZONTAL = 1e-6
TWO_PI = 2.0 * math.pi
# Subdivisions for arc-length of curves without a closed form. Fine enough
# that the length a duration fit sees agrees with what the sampler draws.
LENGTH_SAMPLES = 64


class ProgramError(ValueError):
    """A segment cannot be evaluated. Carries where, so the editor can point at it."""

    def __init__(self, message: str, index: int, segment_id: str = ""):
        super().__init__(message)
        self.index = index
        self.segment_id = segment_id


def direction_vector(heading_deg: float, climb_deg: float) -> Vec3:
    heading = math.radians(heading_deg)
    climb = math.radians(climb_deg)
    return (
        math.sin(heading) * math.cos(climb),
        math.sin(climb),
        math.cos(heading) * math.cos(climb),
    )


def direction_angles(vector: Vec3) -> tuple[float, float]:
    """Heading and climb of a direction, the inverse of direction_vector."""
    east, up, north = vector
    horizontal = math.hypot(east, north)
    heading = normalise_heading(math.degrees(math.atan2(east, north)))
    climb = math.degrees(math.atan2(up, horizontal))
    return heading, climb


@dataclass(frozen=True)
class Pen:
    """What a segment inherits from the one before it.

    Tangent and speed are optional because a MoveTo may leave them unset, in
    which case the next segment has to state its own.
    """

    point: Vec3
    tangent: Vec3 | None = None
    speed_ms: float | None = None


@dataclass(frozen=True)
class SegmentGeometry:
    """One segment's curve in the local metre frame.

    ``seam`` marks a segment the pen jumped to reach, so nothing should be
    drawn from the previous segment's end to this one's start. It sits on the
    segment after the MoveTo rather than on the MoveTo, because the MoveTo
    draws nothing and the break belongs to the first thing that does.
    """

    segment_id: str
    kind: str
    start: Vec3
    end: Vec3
    length_m: float
    seam: bool = False

    def point_at(self, u: float) -> Vec3:
        raise NotImplementedError

    def tangent_at(self, u: float) -> Vec3:
        raise NotImplementedError


@dataclass(frozen=True)
class PointGeometry(SegmentGeometry):
    """A MoveTo: zero length, so every parameter maps to the same point."""

    def point_at(self, u: float) -> Vec3:
        return self.end

    def tangent_at(self, u: float) -> Vec3:
        return (0.0, 0.0, 0.0)


@dataclass(frozen=True)
class LineGeometry(SegmentGeometry):
    direction: Vec3 = (0.0, 0.0, 1.0)

    def point_at(self, u: float) -> Vec3:
        u = min(1.0, max(0.0, u))
        return _add(self.start, _scale(self.direction, u * self.length_m))

    def tangent_at(self, u: float) -> Vec3:
        return self.direction


@dataclass(frozen=True)
class ArcGeometry(SegmentGeometry):
    center: Vec3 = (0.0, 0.0, 0.0)
    # Unit vector from the centre to the start, and the in-plane direction the
    # curve leaves along. Together they span the circle.
    radial: Vec3 = (1.0, 0.0, 0.0)
    circular: Vec3 = (0.0, 0.0, 1.0)
    normal: Vec3 = WORLD_UP
    radius_m: float = 1.0
    sweep_rad: float = 0.0
    rise_per_rad_m: float = 0.0

    def point_at(self, u: float) -> Vec3:
        u = min(1.0, max(0.0, u))
        theta = self.sweep_rad * u
        on_circle = _add(
            _scale(self.radial, self.radius_m * math.cos(theta)),
            _scale(self.circular, self.radius_m * math.sin(theta)),
        )
        climb = _scale(self.normal, self.rise_per_rad_m * theta)
        return _add(self.center, _add(on_circle, climb))

    def tangent_at(self, u: float) -> Vec3:
        u = min(1.0, max(0.0, u))
        theta = self.sweep_rad * u
        around = _add(
            _scale(self.radial, -self.radius_m * math.sin(theta)),
            _scale(self.circular, self.radius_m * math.cos(theta)),
        )
        return _unit(_add(around, _scale(self.normal, self.rise_per_rad_m)))


@dataclass(frozen=True)
class HermiteGeometry(SegmentGeometry):
    """Cubic Hermite between start and end with stored tangent vectors."""

    out_tangent: Vec3 = (0.0, 0.0, 1.0)   # magnitude included, as in the cubic
    into_tangent: Vec3 = (0.0, 0.0, 1.0)

    def point_at(self, u: float) -> Vec3:
        u = min(1.0, max(0.0, u))
        u2, u3 = u * u, u * u * u
        h00 = 2.0 * u3 - 3.0 * u2 + 1.0
        h10 = u3 - 2.0 * u2 + u
        h01 = -2.0 * u3 + 3.0 * u2
        h11 = u3 - u2
        a, b = self.start, self.end
        m0, m1 = self.out_tangent, self.into_tangent
        return (
            h00 * a[0] + h10 * m0[0] + h01 * b[0] + h11 * m1[0],
            h00 * a[1] + h10 * m0[1] + h01 * b[1] + h11 * m1[1],
            h00 * a[2] + h10 * m0[2] + h01 * b[2] + h11 * m1[2],
        )

    def tangent_at(self, u: float) -> Vec3:
        u = min(1.0, max(0.0, u))
        # Derivatives of the Hermite basis.
        u2 = u * u
        dh00 = 6.0 * u2 - 6.0 * u
        dh10 = 3.0 * u2 - 4.0 * u + 1.0
        dh01 = -6.0 * u2 + 6.0 * u
        dh11 = 3.0 * u2 - 2.0 * u
        a, b = self.start, self.end
        m0, m1 = self.out_tangent, self.into_tangent
        return _unit((
            dh00 * a[0] + dh10 * m0[0] + dh01 * b[0] + dh11 * m1[0],
            dh00 * a[1] + dh10 * m0[1] + dh01 * b[1] + dh11 * m1[1],
            dh00 * a[2] + dh10 * m0[2] + dh01 * b[2] + dh11 * m1[2],
        ))


@dataclass(frozen=True)
class SplineGeometry(SegmentGeometry):
    curve: NurbsCurve = None  # type: ignore[assignment]
    # Control polygon in ENU, for gizmos and for change-detection against
    # construction.produced.
    controls: tuple[Vec3, ...] = ()

    def point_at(self, u: float) -> Vec3:
        return self.curve.point_at(u)

    def tangent_at(self, u: float) -> Vec3:
        return self.curve.tangent_at(u)


@dataclass(frozen=True)
class SolvedProgram:
    origin_lat: float
    origin_lon: float
    origin_alt_ft: float
    segments: list[SegmentGeometry]

    @property
    def length_m(self) -> float:
        return sum(segment.length_m for segment in self.segments)

    def to_latlon(self, point: Vec3) -> tuple[float, float, float]:
        east, up, north = point
        lat, lon = offset_latlon(self.origin_lat, self.origin_lon, north, east)
        return lat, lon, metres_to_feet(up)

    def at_distance(self, distance_m: float) -> tuple[Vec3, Vec3]:
        """Point and unit tangent at a distance along the whole program.

        Right-continuous at a seam: where a zero-length MoveTo puts two
        segments at the same distance, the post-jump one wins, which is what
        keeps a cut reading as a cut rather than as its own last frame.
        """
        drawable = [segment for segment in self.segments if segment.length_m > 0.0]
        if not drawable:
            raise ProgramError("the program draws nothing", 0)
        remaining = max(0.0, distance_m)
        for index, segment in enumerate(drawable):
            final = index == len(drawable) - 1
            # Strictly inside, so a distance landing exactly on a boundary
            # falls through to the segment after it. On an ordinary join both
            # answers are the same point; on a seam only the later one is right.
            if remaining < segment.length_m or final:
                u = min(1.0, remaining / segment.length_m)
                return segment.point_at(u), segment.tangent_at(u)
            remaining -= segment.length_m
        raise ProgramError("walked off the end of the program", 0)  # pragma: no cover


def enu_point(program: PathProgram, point) -> Vec3:
    """A lat/lon/altitude in the program's local east/up/north metre frame."""
    north, east = local_offset(
        program.origin.lat, program.origin.lon, point.lat, point.lon
    )
    return (east, feet_to_metres(point.alt_ft_msl), north)


def sampled_length(point_at, samples: int = LENGTH_SAMPLES) -> float:
    """Arc length of a parameterised curve by uniform sampling in u."""
    length = 0.0
    previous = point_at(0.0)
    for index in range(1, samples + 1):
        point = point_at(index / samples)
        length += math.dist(previous, point)
        previous = point
    return length


def handle_vector(handle: HermiteHandle) -> Vec3:
    """Tangent vector for the cubic, matching the waypoint Hermite convention."""
    return _scale(direction_vector(handle.heading_deg, handle.climb_deg),
                  3.0 * handle.length_m)


def default_out_handle(pen: Pen, end: Vec3) -> HermiteHandle:
    """The out handle that keeps G1 with the pen, length chord/3."""
    if pen.tangent is not None:
        heading, climb = direction_angles(pen.tangent)
    else:
        delta = _sub(end, pen.point)
        if _norm(delta) < 1e-9:
            heading, climb = 0.0, 0.0
        else:
            heading, climb = direction_angles(_unit(delta))
    length = max(_norm(_sub(end, pen.point)) / 3.0, 1.0)
    return HermiteHandle(heading_deg=heading, climb_deg=climb, length_m=length)


def _plane_normal(tangent: Vec3, tilt_deg: float, index: int, segment_id: str) -> Vec3:
    """Normal of the arc's plane: world up, rolled about the entry tangent."""
    horizontal = (tangent[0], 0.0, tangent[2])
    if _norm(horizontal) < MIN_HORIZONTAL:
        raise ProgramError(
            "an arc cannot leave along a vertical tangent: there is no "
            "horizontal direction to roll its plane about.",
            index,
            segment_id,
        )
    horizontal = _unit(horizontal)
    # _cross(forward, up) points left of travel, so negate for a positive tilt
    # that rolls the plane toward the right.
    right = _scale(_cross(horizontal, WORLD_UP), -1.0)
    tilt = math.radians(tilt_deg)
    return _unit(
        _add(_scale(WORLD_UP, math.cos(tilt)), _scale(right, math.sin(tilt)))
    )


def _move_geometry(program: PathProgram, pen: Pen,
                   segment: MoveToSegment) -> tuple[SegmentGeometry, Pen]:
    point = enu_point(program, segment.to)
    tangent = (
        direction_vector(segment.tangent.heading_deg, segment.tangent.climb_deg)
        if segment.tangent is not None
        else None
    )
    geometry = PointGeometry(
        segment_id=segment.id,
        kind=segment.kind,
        start=point,
        end=point,
        length_m=0.0,
    )
    return geometry, Pen(point=point, tangent=tangent, speed_ms=segment.speed_ms)


def _line_geometry(pen: Pen, segment: LineToSegment,
                   index: int) -> tuple[SegmentGeometry, Pen]:
    if segment.inherit_direction:
        if pen.tangent is None:
            raise ProgramError(
                "this leg carries on from the previous one, but the pen has "
                "no direction here. Give it a heading, or give the MoveTo "
                "before it an outgoing tangent.",
                index,
                segment.id,
            )
        direction = pen.tangent
    else:
        direction = direction_vector(segment.heading_deg, segment.climb_deg)
    end = _add(pen.point, _scale(direction, segment.distance_m))
    geometry = LineGeometry(
        segment_id=segment.id,
        kind=segment.kind,
        start=pen.point,
        end=end,
        length_m=segment.distance_m,
        direction=direction,
    )
    return geometry, Pen(point=end, tangent=direction, speed_ms=pen.speed_ms)


def _arc_geometry(pen: Pen, segment: ArcSegment,
                  index: int) -> tuple[SegmentGeometry, Pen]:
    if pen.tangent is None:
        raise ProgramError(
            "an arc leaves along the pen's tangent, but the pen has no "
            "direction here. Give the MoveTo before it an outgoing tangent.",
            index,
            segment.id,
        )
    normal = _plane_normal(pen.tangent, segment.tilt_deg, index, segment.id)
    # The circular part of the tangent is what lies in the plane; whatever is
    # along the normal is the helix climbing.
    in_plane = _sub(pen.tangent, _scale(normal, _dot(pen.tangent, normal)))
    in_plane_len = _norm(in_plane)
    if in_plane_len < MIN_HORIZONTAL:
        raise ProgramError(
            "the arc's plane is edge-on to the direction of travel, so the "
            "curve has no circular part. Reduce the tilt.",
            index,
            segment.id,
        )
    circular = _scale(in_plane, 1.0 / in_plane_len)

    lateral = _cross(circular, normal)           # left of travel
    if segment.side == "RIGHT":
        lateral = _scale(lateral, -1.0)
    center = _add(pen.point, _scale(lateral, segment.radius_m))
    radial = _scale(lateral, -1.0)               # centre to start, unit

    if segment.rise_per_turn_m is None:
        # Match the pen's climb so the join is smooth. A helix's tangent is
        # R*circular + rise_per_rad*normal, which is parallel to the pen's
        # tangent exactly when rise_per_rad = R * (T.n) / |T in plane|.
        rise_per_rad = segment.radius_m * _dot(pen.tangent, normal) / in_plane_len
    else:
        rise_per_rad = segment.rise_per_turn_m / TWO_PI

    sweep = math.radians(segment.sweep_deg)
    length = sweep * math.hypot(segment.radius_m, rise_per_rad)
    geometry = ArcGeometry(
        segment_id=segment.id,
        kind=segment.kind,
        start=pen.point,
        end=(0.0, 0.0, 0.0),
        length_m=length,
        center=center,
        radial=radial,
        circular=circular,
        normal=normal,
        radius_m=segment.radius_m,
        sweep_rad=sweep,
        rise_per_rad_m=rise_per_rad,
    )
    # end is read back off the curve rather than computed a second way, so it
    # cannot drift from point_at(1).
    geometry = replace(geometry, end=geometry.point_at(1.0))
    return geometry, Pen(
        point=geometry.end,
        tangent=geometry.tangent_at(1.0),
        speed_ms=pen.speed_ms,
    )


def _hermite_geometry(program: PathProgram, pen: Pen, segment: HermiteSegment,
                      index: int) -> tuple[SegmentGeometry, Pen]:
    end = enu_point(program, segment.to)
    out = segment.out if segment.out is not None else default_out_handle(pen, end)
    # An authored out that fights the pen is allowed; it is the kink the
    # operator asked for. An inherited one is what keeps the join smooth.
    out_tangent = handle_vector(out)
    into_tangent = handle_vector(segment.into)
    geometry = HermiteGeometry(
        segment_id=segment.id, kind=segment.kind,
        start=pen.point, end=end, length_m=0.0,
        out_tangent=out_tangent, into_tangent=into_tangent,
    )
    geometry = replace(geometry, length_m=sampled_length(geometry.point_at))
    return geometry, Pen(
        point=end, tangent=geometry.tangent_at(1.0), speed_ms=pen.speed_ms,
    )


def _spline_geometry(program: PathProgram, pen: Pen, segment: SplineSegment,
                     index: int) -> tuple[SegmentGeometry, Pen]:
    controls = tuple(enu_point(program, point) for point in segment.control_points)
    weights = [point.weight for point in segment.control_points]
    knots = (list(segment.knots) if segment.knots is not None
             else clamped_knots(len(controls), segment.degree))
    # A spline that does not start at the pen is a jump in all but name —
    # the operator authored a hull somewhere else. Honour it, and leave a
    # seam so nothing is drawn across the gap.
    curve = NurbsCurve(list(controls), weights, knots, segment.degree)
    start = curve.point_at(0.0)
    geometry = SplineGeometry(
        segment_id=segment.id, kind=segment.kind,
        start=start, end=curve.point_at(1.0),
        length_m=sampled_length(curve.point_at),
        seam=_norm(_sub(start, pen.point)) > 1.0,
        curve=curve, controls=controls,
    )
    return geometry, Pen(
        point=geometry.end, tangent=curve.tangent_at(1.0), speed_ms=pen.speed_ms,
    )


def segment_geometry(program: PathProgram, pen: Pen, segment,
                     index: int) -> tuple[SegmentGeometry, Pen]:
    """One segment's curve, and the pen state it leaves behind.

    Public because the solver evaluates a single segment over and over
    against trial parameters, and must do it exactly the way a full walk
    would or the solution it finds would not be the one that gets drawn.
    """
    if isinstance(segment, MoveToSegment):
        return _move_geometry(program, pen, segment)
    if isinstance(segment, LineToSegment):
        return _line_geometry(pen, segment, index)
    if isinstance(segment, ArcSegment):
        return _arc_geometry(pen, segment, index)
    if isinstance(segment, HermiteSegment):
        return _hermite_geometry(program, pen, segment, index)
    if isinstance(segment, SplineSegment):
        return _spline_geometry(program, pen, segment, index)
    raise ProgramError(f"unknown segment kind {segment!r}", index)  # pragma: no cover


def start_pen(program: PathProgram) -> Pen:
    return Pen(point=(0.0, feet_to_metres(program.origin.alt_ft_msl), 0.0))


def evaluate(program: PathProgram) -> SolvedProgram:
    """Walk the segments, advancing the pen, and return each one's geometry."""
    pen = start_pen(program)
    geometries: list[SegmentGeometry] = []
    # Set by a mid-path MoveTo and spent on the next segment that draws
    # something, which is where the break in the line actually falls.
    jumped = False
    for index, segment in enumerate(program.segments):
        geometry, pen = segment_geometry(program, pen, segment, index)
        if isinstance(segment, MoveToSegment):
            # A MoveTo before anything has been drawn is where the path
            # begins, not a cut in it.
            jumped = jumped or index > 0
        if jumped and geometry.length_m > 0.0:
            geometry = replace(geometry, seam=True)
            jumped = False
        geometries.append(geometry)
    return SolvedProgram(
        origin_lat=program.origin.lat,
        origin_lon=program.origin.lon,
        origin_alt_ft=program.origin.alt_ft_msl,
        segments=geometries,
    )


def sample_by_distance(solved: SolvedProgram, step_m: float = 25.0) -> list[dict]:
    """Points along the program for drawing, with the seams marked.

    ``break_before`` is true on the first row of a segment the pen jumped to.
    A consumer drawing continuous geometry has to start a new polyline there
    rather than joining it to the row before.
    """
    rows: list[dict] = []
    for geometry in solved.segments:
        if geometry.length_m <= 0.0:
            # A MoveTo contributes no line of its own; it marks the break that
            # the next segment's first row carries.
            continue
        steps = max(1, math.ceil(geometry.length_m / max(step_m, 1e-6)))
        for index in range(steps + 1):
            u = index / steps
            lat, lon, alt_ft = solved.to_latlon(geometry.point_at(u))
            heading, climb = direction_angles(geometry.tangent_at(u))
            rows.append({
                "segment_id": geometry.segment_id,
                "u": round(u, 6),
                "lat": lat,
                "lon": lon,
                "alt_ft": alt_ft,
                "heading": heading,
                "climb": climb,
                "break_before": index == 0 and geometry.seam,
            })
    return rows
