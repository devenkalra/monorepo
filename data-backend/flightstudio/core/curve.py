"""Spatial curve and time law, per design section 2.2.

Authored legs (straight, planar arc, Hermite, B-spline) decide where the path
goes. `hermite_ease` decides when it gets there. Editing pacing never moves
the line. Catmull-Rom remains only for MANUAL attitude series.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field

from .bspline import FittedBSpline
from .path_geom import path_point

Vec3 = tuple[float, float, float]


def hermite_ease(u: float, ease_out: float, ease_in: float) -> float:
    """Reshape 0..1 progress. Endpoint speed falls as the ease weight rises.

    A weight of 0.0 is a constant-rate pass-through and 1.0 is a full stop, as
    the design specifies. Monotonic for any weights in that range, so the path
    never reverses.
    """
    v0 = 1.0 - min(1.0, max(0.0, ease_out))
    v1 = 1.0 - min(1.0, max(0.0, ease_in))
    u = min(1.0, max(0.0, u))
    u2, u3 = u * u, u * u * u
    return v0 * (u3 - 2.0 * u2 + u) + (-2.0 * u3 + 3.0 * u2) + v1 * (u3 - u2)


def catmull_rom(p0: Vec3, p1: Vec3, p2: Vec3, p3: Vec3, u: float, alpha: float = 0.5) -> Vec3:
    """Centripetal Catmull-Rom. Will not cusp or self-intersect on tight turns."""

    def knot(t: float, a: Vec3, b: Vec3) -> float:
        distance = math.dist(a, b)
        return t + (distance**alpha if distance > 1e-9 else 1e-9)

    t0 = 0.0
    t1 = knot(t0, p0, p1)
    t2 = knot(t1, p1, p2)
    t3 = knot(t2, p2, p3)
    t = t1 + u * (t2 - t1)

    def between(a: Vec3, b: Vec3, ta: float, tb: float) -> Vec3:
        if abs(tb - ta) < 1e-12:
            return a
        w = (t - ta) / (tb - ta)
        return (a[0] + (b[0] - a[0]) * w, a[1] + (b[1] - a[1]) * w, a[2] + (b[2] - a[2]) * w)

    a1 = between(p0, p1, t0, t1)
    a2 = between(p1, p2, t1, t2)
    a3 = between(p2, p3, t2, t3)
    b1 = between(a1, a2, t0, t2)
    b2 = between(a2, a3, t1, t3)
    return between(b1, b2, t1, t2)


def mirror(inner: Vec3, edge: Vec3) -> Vec3:
    """Phantom control point reflected through the end knot.

    Forces the end knot collinear with its neighbour, so the curve leaves the
    end along the chord rather than the tangent. Only correct when there is no
    third point to infer curvature from; prefer `extrapolate`.
    """
    return (2.0 * edge[0] - inner[0], 2.0 * edge[1] - inner[1], 2.0 * edge[2] - inner[2])


def extrapolate(edge: Vec3, second: Vec3, third: Vec3) -> Vec3:
    """Phantom control point continuing the parabola through the first three knots.

    `mirror` zeroes the curvature at the ends, which tips the end tangent by
    half the turn per segment and makes a steady turn read as a brief reversal.
    Extending the quadratic instead keeps the curvature, cutting that tangent
    error by well over an order of magnitude on a circular arc.
    """
    return (
        3.0 * edge[0] - 3.0 * second[0] + third[0],
        3.0 * edge[1] - 3.0 * second[1] + third[1],
        3.0 * edge[2] - 3.0 * second[2] + third[2],
    )


def catmull_rom_scalar(v0: float, v1: float, v2: float, v3: float, u: float) -> float:
    """Catmull-Rom through a scalar series, from v1 at u=0 to v2 at u=1.

    Clamped to the bracketing pair, so an authored value is never overshot:
    asking for 30 degrees of bank must not produce 34 on the way there.
    """
    u2 = u * u
    u3 = u2 * u
    value = 0.5 * (
        2.0 * v1
        + (v2 - v0) * u
        + (2.0 * v0 - 5.0 * v1 + 4.0 * v2 - v3) * u2
        + (3.0 * v1 - v0 - 3.0 * v2 + v3) * u3
    )
    return min(max(value, min(v1, v2)), max(v1, v2))


def spline_series(values: list[float], index: int, u: float) -> float:
    """Smooth value at progress `u` through segment `index` of a scalar series.

    Linear interpolation would put a corner in the series at every knot, which
    on an attitude channel reads as the aircraft snapping between angles.
    """
    count = len(values)
    if count == 1:
        return values[0]
    if count == 2:
        return values[0] + (values[1] - values[0]) * u
    index = min(max(index, 0), count - 2)
    v1, v2 = values[index], values[index + 1]
    # Same reasoning as the vector curve: reflecting the neighbour would zero
    # the curvature at the ends and tip the series away from its trend.
    v0 = values[index - 1] if index > 0 else 3.0 * v1 - 3.0 * v2 + values[2]
    v3 = (values[index + 2] if index + 2 < count
          else 3.0 * v2 - 3.0 * v1 + values[-3])
    return catmull_rom_scalar(v0, v1, v2, v3, u)


@dataclass
class Knot:
    time: float
    point: Vec3
    ease_in: float = 0.0
    ease_out: float = 0.0
    hold_s: float = 0.0
    path: object | None = None
    payload: dict = field(default_factory=dict)
    span_end: int | None = None
    spline: FittedBSpline | None = None
    spline_params: list[float] | None = None


def lerp3(a: Vec3, b: Vec3, u: float) -> Vec3:
    u = min(1.0, max(0.0, u))
    return (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u)


ARC_TABLE_SAMPLES = 64


class Curve:
    """A timed, eased path through authored legs.

    By default a segment is crossed at an even rate of the spline parameter,
    and the speed along it is whatever the parameterisation gives: slow where
    the neighbouring knots are close, fast where they are far, with a step at
    every knot. `by_distance` instead moves at a speed through each knot shared
    by both segments, so speed is continuous and only varies within a segment
    as far as getting there on time needs.
    """

    def __init__(self, knots: list[Knot], by_distance: bool = False):
        if not knots:
            raise ValueError("a curve needs at least one knot")
        self.knots = sorted(knots, key=lambda k: k.time)
        self._times = [k.time for k in self.knots]
        self._span_start = self._index_spans()
        self.by_distance = by_distance and len(self.knots) > 1
        if self.by_distance:
            self._build_distance_law()

    def _index_spans(self) -> list[int | None]:
        """For each pair-interval, the knot index that starts a covering B-spline, if any."""
        count = max(0, len(self.knots) - 1)
        starts: list[int | None] = [None] * count
        for index, knot in enumerate(self.knots):
            if knot.span_end is None or knot.spline is None:
                continue
            for pair in range(index, min(knot.span_end, count)):
                if starts[pair] is None:
                    starts[pair] = index
        return starts

    @property
    def duration(self) -> float:
        last = self.knots[-1]
        return last.time + last.hold_s

    def _segment_index(self, t: float) -> int:
        """The segment whose knot interval contains t (the last one past the end)."""
        return min(max(bisect.bisect_right(self._times, t) - 1, 0), len(self.knots) - 2)

    def segment_at(self, t: float) -> tuple[int, float]:
        """Segment index and eased progress within it."""
        if len(self.knots) == 1:
            return 0, 0.0
        index = self._segment_index(t)
        start, end = self.knots[index], self.knots[index + 1]
        if t < start.time + start.hold_s:
            return index, 0.0
        if t >= end.time:
            return index, 1.0
        span = end.time - (start.time + start.hold_s)
        raw = (t - start.time - start.hold_s) / span if span > 1e-9 else 1.0
        return index, hermite_ease(raw, start.ease_out, end.ease_in)

    def _controls(self, index: int) -> tuple[Vec3, Vec3, Vec3, Vec3]:
        points = [k.point for k in self.knots]
        p1, p2 = points[index], points[index + 1]
        if index > 0:
            p0 = points[index - 1]
        elif len(points) > 2:
            p0 = extrapolate(p1, p2, points[2])
        else:
            p0 = mirror(p2, p1)
        if index + 2 < len(points):
            p3 = points[index + 2]
        elif len(points) > 2:
            p3 = extrapolate(p2, p1, points[-3])
        else:
            p3 = mirror(p1, p2)
        return p0, p1, p2, p3

    def _segment_point(self, index: int, u: float) -> Vec3:
        """Position at parameter u in 0..1 along segment index."""
        span = self._span_start[index] if index < len(self._span_start) else None
        if span is not None:
            knot = self.knots[span]
            params = knot.spline_params or []
            local = index - span
            if knot.spline and 0 <= local < len(params) - 1:
                start_u, end_u = params[local], params[local + 1]
                return knot.spline.point_at(start_u + (end_u - start_u) * min(1.0, max(0.0, u)))
        start, end = self.knots[index], self.knots[min(index + 1, len(self.knots) - 1)]
        return path_point(start.point, end.point, start.path, u)

    def _build_distance_law(self) -> None:
        count = len(self.knots) - 1
        self._tables: list[list[float]] = []
        lengths, spans = [], []
        for index in range(count):
            previous = self._segment_point(index, 0.0)
            table = [0.0]
            for step in range(1, ARC_TABLE_SAMPLES + 1):
                point = self._segment_point(index, step / ARC_TABLE_SAMPLES)
                table.append(table[-1] + math.dist(previous, point))
                previous = point
            self._tables.append(table)
            lengths.append(table[-1])
            start, end = self.knots[index], self.knots[index + 1]
            spans.append(end.time - (start.time + start.hold_s))
        speeds = [length / span if span > 1e-9 else 0.0 for length, span in zip(lengths, spans)]

        # Fritsch-Butland weighted harmonic mean: never overshoots either
        # neighbour, so distance against time stays monotonic.
        through = [speeds[0]]
        for k in range(1, count):
            before, after = speeds[k - 1], speeds[k]
            if self.knots[k].hold_s > 0.0 or before <= 0.0 or after <= 0.0:
                through.append(0.0)
                continue
            w1 = 2.0 * spans[k] + spans[k - 1]
            w2 = spans[k] + 2.0 * spans[k - 1]
            through.append((w1 + w2) / (w1 / before + w2 / after))
        through.append(speeds[-1])

        self._segment_law = []
        for index in range(count):
            mean = speeds[index]
            leaving = through[index] * (1.0 - min(1.0, max(0.0, self.knots[index].ease_out)))
            arriving = through[index + 1] * (1.0 - min(1.0, max(0.0, self.knots[index + 1].ease_in)))
            if mean > 0.0:
                alpha, beta = leaving / mean, arriving / mean
                size = math.hypot(alpha, beta)
                if size > 3.0:
                    leaving, arriving = leaving * 3.0 / size, arriving * 3.0 / size
            self._segment_law.append((lengths[index], spans[index], leaving, arriving))

    def _locate(self, t: float) -> tuple[int, float]:
        """Segment index and raw, uneased fraction of its moving time."""
        index = self._segment_index(t)
        start, end = self.knots[index], self.knots[index + 1]
        if t < start.time + start.hold_s:
            return index, 0.0
        if t >= end.time:
            return index, 1.0
        span = end.time - (start.time + start.hold_s)
        return index, (t - start.time - start.hold_s) / span if span > 1e-9 else 1.0

    def _point_by_distance(self, t: float) -> Vec3:
        index, fraction = self._locate(t)
        length, span, leaving, arriving = self._segment_law[index]
        if length <= 1e-9:
            return self.knots[index].point
        f = min(1.0, max(0.0, fraction))
        f2, f3 = f * f, f * f * f
        travelled = (length * (-2.0 * f3 + 3.0 * f2)
                     + span * (leaving * (f3 - 2.0 * f2 + f) + arriving * (f3 - f2)))
        travelled = min(length, max(0.0, travelled))
        table = self._tables[index]
        slot = min(max(bisect.bisect_left(table, travelled), 1), len(table) - 1)
        low, high = table[slot - 1], table[slot]
        within = (travelled - low) / (high - low) if high - low > 1e-12 else 0.0
        return self._segment_point(index, (slot - 1 + within) / ARC_TABLE_SAMPLES)

    def point_at(self, t: float) -> Vec3:
        if len(self.knots) == 1:
            return self.knots[0].point
        if self.by_distance:
            return self._point_by_distance(t)
        index, progress = self.segment_at(t)
        return self._segment_point(index, progress)

    def knot_at(self, t: float) -> Knot:
        index, _ = self.segment_at(t)
        return self.knots[index]

    def velocity_at(self, t: float, dt: float = 0.02) -> Vec3:
        """Finite-difference derivative, used to derive heading and attitude."""
        before = self.point_at(max(0.0, t - dt))
        after = self.point_at(min(self.duration, t + dt))
        span = min(self.duration, t + dt) - max(0.0, t - dt)
        if span < 1e-9:
            return (0.0, 0.0, 0.0)
        return (
            (after[0] - before[0]) / span,
            (after[1] - before[1]) / span,
            (after[2] - before[2]) / span,
        )
