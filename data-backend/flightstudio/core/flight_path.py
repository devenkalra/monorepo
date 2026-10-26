"""Solve a flight keyframe list into a pose at any instant.

Positions are splined in a local north/east/up metre frame rather than in
degrees, so a degree of longitude near the poles does not stretch the curve.

Attitude follows design section 2.2: bank from the splined turn rate and ground
speed, pitch from the flight-path angle, either of which a keyframe may override
with an explicit value.
"""

from __future__ import annotations

import math

from dataclasses import dataclass

from .curve import Curve, Knot, spline_series
from .bspline import chord_params, fit_bspline
from .schema import AutoBank, BSplineLeg, FlightKeyframe, PathDocument, Pose, StraightLeg
from .units import (
    GRAVITY_MS2,
    body_rates,
    feet_to_metres,
    heading_delta,
    local_offset,
    metres_to_feet,
    normalise_heading,
    offset_latlon,
    unwrap_degrees,
    world_to_body,
)


@dataclass(frozen=True)
class BodyMotion:
    """How the aircraft is moving, in its own axes. Metres per second and degrees per second."""
    right_ms: float
    up_ms: float
    forward_ms: float
    pitch_rate_dps: float   # about the right axis, nose-up positive
    yaw_rate_dps: float     # about the up axis, right-turn positive
    roll_rate_dps: float    # about the forward axis, right-wing-down positive


# Attitude rates are differenced over this window: short enough to follow a
# roll, long enough that the spline's floating-point noise does not show.
RATE_WINDOW_S = 0.05
# The authored altitude at a touchdown or lift-off keyframe can be tens of
# feet from the sim's surface, so the ground clamp fades in and out over this
# long either side of a flagged leg rather than stepping at the keyframe.
GROUND_BLEND_S = 1.0

# Defaults when a path has no AutoBank block (older JSON). Same numbers as
# schema.AutoBank. MANUAL keys may still pin a steeper bank.
MAX_BANK_DEG = 30.0
MAX_PITCH_DEG = 30.0
BANK_SAMPLE_S = 0.1
BANK_SMOOTHING_S = 6.0
MAX_ROLL_RATE_DEG_S = 5.0


class SolvedFlightPath:
    def __init__(self, keyframes: list[FlightKeyframe], auto_bank: AutoBank | None = None):
        if len(keyframes) < 1:
            raise ValueError("a flight path needs at least one keyframe")
        law = auto_bank or AutoBank()
        self.auto_bank = law
        self.max_bank_deg = law.max_deg
        self.roll_rate_deg_s = law.roll_rate_deg_s
        self.bank_smoothing_s = law.smoothing_s
        self.keyframes = sorted(keyframes, key=lambda k: k.time_offset)
        self.origin_lat = self.keyframes[0].lat
        self.origin_lon = self.keyframes[0].lon

        knots: list[Knot] = []
        for keyframe in self.keyframes:
            north, east = local_offset(
                self.origin_lat, self.origin_lon, keyframe.lat, keyframe.lon
            )
            knots.append(Knot(
                time=keyframe.time_offset,
                point=(east, feet_to_metres(keyframe.alt_ft_msl), north),
                ease_in=keyframe.easing.ease_in,
                ease_out=keyframe.easing.ease_out,
                hold_s=keyframe.easing.hold_s,
                path=keyframe.path,
                payload={"keyframe": keyframe, "id": keyframe.id},
            ))
        self._attach_bsplines(knots)
        self.curve = Curve(knots, by_distance=True)
        self._ground_spans = self._flagged_spans()
        # Built here, not lazily: pose_at reads bank on every sample, and a
        # missed cache rebuilds a Gaussian over the whole take (~25 s on a
        # 36 s AUTO path). The table only depends on the curve.
        self._bank_cache = self._compute_bank_samples()

    def _attach_bsplines(self, knots: list[Knot]) -> None:
        by_id = {knot.payload.get("id"): index for index, knot in enumerate(knots)}
        covered = [False] * len(knots)
        for index, knot in enumerate(knots):
            path = knot.path
            if not isinstance(path, BSplineLeg) or covered[index]:
                continue
            end = by_id.get(path.end_id)
            if end is None or end <= index:
                knot.path = StraightLeg()
                continue
            knot.span_end = end
            knot.spline_params = None
            targets = [knots[j].point for j in range(index, end + 1)]
            knot.spline = fit_bspline(targets, path.tolerance_m)
            knot.spline_params = chord_params(targets)
            for j in range(index + 1, end):
                covered[j] = True

    @classmethod
    def from_document(cls, document: PathDocument) -> SolvedFlightPath:
        return cls(document.flight_keyframes, auto_bank=document.meta.auto_bank)

    def _flagged_spans(self) -> list[tuple[float, float]]:
        """Time intervals of consecutive on-ground legs, merged."""
        spans: list[tuple[float, float]] = []
        frames = self.keyframes
        for index, frame in enumerate(frames):
            if not frame.on_ground:
                continue
            start = frame.time_offset
            # A flagged final keyframe keeps the aircraft down through its hold.
            end = frames[index + 1].time_offset if index + 1 < len(frames) else self.duration
            if spans and spans[-1][1] >= start:
                spans[-1] = (spans[-1][0], max(spans[-1][1], end))
            else:
                spans.append((start, end))
        return spans

    @property
    def duration(self) -> float:
        return self.curve.duration

    def ground_weight(self, t: float) -> float:
        """How much of the altitude the surface decides: 1 on a flagged leg.

        Fades linearly over GROUND_BLEND_S outside each flagged span, so the
        clamp blends in before a flagged touchdown and out after lift-off.
        Nothing is clamped on a path with no flags.
        """
        best = 0.0
        for start, end in self._ground_spans:
            if start <= t <= end:
                return 1.0
            distance = start - t if t < start else t - end
            best = max(best, 1.0 - distance / GROUND_BLEND_S)
        return max(0.0, best)

    def position_at(self, t: float) -> tuple[float, float, float]:
        east, up_m, north = self.curve.point_at(t)
        lat, lon = offset_latlon(self.origin_lat, self.origin_lon, north, east)
        return lat, lon, metres_to_feet(up_m)

    def ground_speed_ms(self, t: float) -> float:
        east_rate, _up_rate, north_rate = self.curve.velocity_at(t)
        return math.hypot(east_rate, north_rate)

    def track_heading_at(self, t: float) -> float:
        """Where the aircraft is going, from the curve tangent.

        Distinct from where it is pointing: a keyframe may pin the heading, in
        which case the aircraft crabs and the two differ.
        """
        east_rate, _up, north_rate = self.curve.velocity_at(t)
        if math.hypot(east_rate, north_rate) >= 1e-6:
            return normalise_heading(math.degrees(math.atan2(east_rate, north_rate)))
        # Stationary at this instant, so the tangent says nothing. Use the
        # chord across the segment, which is defined unless the knots coincide.
        index, _ = self.curve.segment_at(t)
        start = self.curve.knots[index].point
        end = self.curve.knots[min(index + 1, len(self.curve.knots) - 1)].point
        east, north = end[0] - start[0], end[2] - start[2]
        if math.hypot(east, north) < 1e-9:
            return 0.0
        return normalise_heading(math.degrees(math.atan2(east, north)))

    def heading_at(self, t: float) -> float:
        """Where the nose points: the track angle unless a keyframe overrides it."""
        return normalise_heading(self._angle(t, "heading"))

    def turn_rate_rads(self, t: float, dt: float = 0.1) -> float:
        # Deliberately the track heading, not the nose heading: bank comes from
        # turning the velocity vector, and a manual yaw must not imply a bank.
        before = self.track_heading_at(max(0.0, t - dt))
        after = self.track_heading_at(min(self.duration, t + dt))
        span = min(self.duration, t + dt) - max(0.0, t - dt)
        if span < 1e-9:
            return 0.0
        return math.radians(heading_delta(before, after)) / span

    def coordinated_bank_deg(self, t: float) -> float:
        """phi = atan(omega * v / g). Keeps turns from looking like a UFO."""
        speed = self.ground_speed_ms(t)
        omega = self.turn_rate_rads(t)
        bank = math.degrees(math.atan2(omega * speed, GRAVITY_MS2))
        return max(-self.max_bank_deg, min(self.max_bank_deg, bank))

    def auto_bank_deg(self, t: float) -> float:
        """The coordinated bank, smoothed and roll-rate limited."""
        samples = self._bank_samples()
        if len(samples) == 1:
            return samples[0]
        horizon = max(self.keyframes[-1].time_offset, 1e-9)
        step = horizon / (len(samples) - 1)
        position = min(max(t, 0.0), horizon) / step
        index = min(int(position), len(samples) - 2)
        fraction = position - index
        return samples[index] + (samples[index + 1] - samples[index]) * fraction

    def _bank_samples(self) -> list[float]:
        return self._bank_cache

    def _compute_bank_samples(self) -> list[float]:
        # Sample the moving path only. hold_s on the last waypoint extends
        # curve.duration (the take clock) but the aircraft is stopped, so a
        # 12-hour hold must not allocate a bank sample every 0.1 s.
        horizon = max(self.keyframes[-1].time_offset, 1e-9)
        if horizon <= 1e-9:
            return [self.coordinated_bank_deg(0.0)]

        count = max(2, math.ceil(horizon / BANK_SAMPLE_S) + 1)
        step = horizon / (count - 1)
        limited = [self.coordinated_bank_deg(i * step) for i in range(count)]

        # Forward then backward, so a peak is clipped symmetrically rather
        # than the roll lagging the turn it belongs to.
        limit = self.roll_rate_deg_s * step
        for i in range(1, count):
            limited[i] = min(max(limited[i], limited[i - 1] - limit), limited[i - 1] + limit)
        for i in range(count - 2, -1, -1):
            limited[i] = min(max(limited[i], limited[i + 1] - limit), limited[i + 1] + limit)

        # Smoothing second rounds off the corners the limiter leaves, and
        # averaging cannot raise a rate the limiter already capped.
        sigma = self.bank_smoothing_s
        reach = max(1, round(3.0 * sigma / step))
        weights = [math.exp(-0.5 * (k * step / sigma) ** 2)
                   for k in range(-reach, reach + 1)]
        smoothed = []
        for i in range(count):
            total = weight_sum = 0.0
            for k, weight in enumerate(weights, start=-reach):
                j = i + k
                if 0 <= j < count:
                    total += limited[j] * weight
                    weight_sum += weight
            smoothed.append(total / weight_sum)
        return smoothed

    def auto_pitch_deg(self, t: float) -> float:
        """Flight-path angle from the climb rate against ground speed."""
        _east, up_rate, _north = self.curve.velocity_at(t)
        speed = self.ground_speed_ms(t)
        if speed < 0.5:
            return 0.0
        pitch = math.degrees(math.atan2(up_rate, speed))
        return max(-MAX_PITCH_DEG, min(MAX_PITCH_DEG, pitch))

    def _auto(self, which: str, t: float) -> float:
        if which == "bank":
            return self.auto_bank_deg(t)
        if which == "pitch":
            return self.auto_pitch_deg(t)
        return self.track_heading_at(t)

    def _angle(self, t: float, which: str) -> float:
        """The authored angle channel, splined between keyframes.

        A path with no override on this channel tracks the derived value
        continuously, which is finer than sampling it at the keyframes. As
        soon as one keyframe pins a value, the channel becomes a series
        through every keyframe and is splined, so AUTO and MANUAL join
        smoothly instead of stepping.
        """
        values = self._series(which)
        if values is None:
            return self._auto(which, t)
        index, progress = self.curve.segment_at(t)
        return spline_series(values, index, progress)

    def _series(self, which: str) -> list[float] | None:
        """The per-keyframe values for a channel, or None if it is all AUTO.

        Built once: it only depends on the keyframes, and a preview asks for
        it thousands of times.
        """
        cache = self.__dict__.setdefault("_series_cache", {})
        if which in cache:
            return cache[which]
        angles = [getattr(keyframe, which) for keyframe in self.keyframes]
        if all(angle.mode == "AUTO" for angle in angles):
            cache[which] = None
            return None
        values = [
            angle.deg if angle.mode == "MANUAL" else self._auto(which, keyframe.time_offset)
            for angle, keyframe in zip(angles, self.keyframes)
        ]
        if which == "heading":
            values = unwrap_degrees(values)
        cache[which] = values
        return values

    def pose_at(self, t: float) -> Pose:
        lat, lon, alt_ft = self.position_at(t)
        return Pose(
            lat=lat,
            lon=lon,
            alt_ft_msl=alt_ft,
            pitch_deg=self._angle(t, "pitch"),
            bank_deg=self._angle(t, "bank"),
            heading_deg_true=self.heading_at(t),
        )

    def body_motion_at(self, t: float, pose: Pose | None = None) -> BodyMotion:
        """Velocity and rotation rates in the aircraft's axes at time t.

        The velocity is the path's, resolved along the nose rather than the
        track, so a pinned (crabbed) heading shows as a sideways component.
        """
        pose = pose or self.pose_at(t)
        east, up, north = self.curve.velocity_at(t)
        # On the surface the altitude follows the terrain, not the authored
        # curve, so whatever climb the curve has there is not real.
        up *= 1.0 - self.ground_weight(t)
        right_ms, up_ms, forward_ms = world_to_body(
            north, east, up, pose.heading_deg_true, pose.pitch_deg, pose.bank_deg)

        before = max(0.0, t - RATE_WINDOW_S)
        after = min(self.duration, t + RATE_WINDOW_S)
        span = after - before
        if span < 1e-9:
            heading_rate = pitch_rate = bank_rate = 0.0
        else:
            heading_rate = heading_delta(self.heading_at(before), self.heading_at(after)) / span
            pitch_rate = (self._angle(after, "pitch") - self._angle(before, "pitch")) / span
            bank_rate = (self._angle(after, "bank") - self._angle(before, "bank")) / span
        pitch_dps, yaw_dps, roll_dps = body_rates(
            heading_rate, pitch_rate, bank_rate, pose.pitch_deg, pose.bank_deg)
        return BodyMotion(right_ms, up_ms, forward_ms, pitch_dps, yaw_dps, roll_dps)
