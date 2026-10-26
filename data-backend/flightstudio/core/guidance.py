"""Fly a solved path with stick, pedals and throttle, as a pilot would.

The path-following autopilot behind "find the controls for this path". It
never writes a pose: it reads the aircraft each frame and moves the controls,
so what it records is a set of inputs the flight model can actually follow.

Structure, outermost first:

  * Lateral guidance steers at a point a few seconds ahead on the path, which
    gives a desired track; the track error plus the bank the path's curvature
    needs gives a bank command, and a roll loop turns that into aileron.
  * Vertical guidance commands the path's climb rate plus a correction for
    altitude error; the matching flight-path angle plus the angle of attack the
    aircraft is currently carrying gives a pitch command for the elevator loop.
  * Speed is held with throttle, nudged faster or slower to catch up with the
    path's timing when that is asked for.
  * Rudder cancels the difference between heading and ground track, which with
    no wind is sideslip.

Everything is in the editor's sign convention: nose-up pitch, right-wing-down
bank, and pilot-sense controls.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from .flight_path import SolvedFlightPath
from .units import KNOTS_PER_MS, heading_delta, local_offset, normalise_heading

SAMPLE_STEP_S = 0.1
FPM_PER_MS = 196.850394


@dataclass(frozen=True)
class RefPoint:
    t: float
    s: float
    east: float
    north: float
    alt_ft: float
    track_deg: float
    bank_deg: float
    vs_fpm: float
    speed_kt: float


@dataclass(frozen=True)
class PathFix:
    """Where the aircraft is relative to the path."""

    point: RefPoint
    index: int
    cross_track_m: float  # positive when the aircraft is right of the path
    along_m: float


class ReferencePath:
    """The solved path sampled densely, in a local metre frame.

    Bank is always derived from the curvature, never a manual override: the
    autopilot needs the bank that physically produces the turn, whatever the
    shot asked the attitude to look like.
    """

    def __init__(self, solved: SolvedFlightPath, step_s: float = SAMPLE_STEP_S):
        self.origin_lat = solved.origin_lat
        self.origin_lon = solved.origin_lon
        duration = max(solved.duration, step_s)
        count = max(2, int(math.ceil(duration / step_s)) + 1)
        points: list[RefPoint] = []
        travelled = 0.0
        for i in range(count):
            t = min(duration, i * step_s)
            lat, lon, alt_ft = solved.position_at(t)
            north, east = local_offset(self.origin_lat, self.origin_lon, lat, lon)
            if points:
                travelled += math.hypot(east - points[-1].east, north - points[-1].north)
            east_rate, up_rate, north_rate = solved.curve.velocity_at(t)
            ground = math.hypot(east_rate, north_rate)
            points.append(RefPoint(
                t=t, s=travelled, east=east, north=north, alt_ft=alt_ft,
                track_deg=solved.track_heading_at(t), bank_deg=solved.auto_bank_deg(t),
                vs_fpm=up_rate * FPM_PER_MS,
                speed_kt=math.hypot(ground, up_rate) * KNOTS_PER_MS,
            ))
        self.points = points
        self.duration = duration
        self.length_m = travelled

    @property
    def start(self) -> RefPoint:
        return self.points[0]

    def window(self, t0: float, t1: float) -> ReferencePath:
        """The stretch from t0 to t1, its time and distance counted from t0."""
        first = max(0, min(len(self.points) - 2, int(round(t0 / SAMPLE_STEP_S))))
        last = max(first + 1, min(len(self.points) - 1, int(round(t1 / SAMPLE_STEP_S))))
        base = self.points[first]
        cut = object.__new__(ReferencePath)
        cut.origin_lat, cut.origin_lon = self.origin_lat, self.origin_lon
        cut.points = [replace(p, t=p.t - base.t, s=p.s - base.s)
                      for p in self.points[first:last + 1]]
        cut.duration = cut.points[-1].t
        cut.length_m = cut.points[-1].s
        return cut

    def local(self, lat: float, lon: float) -> tuple[float, float]:
        north, east = local_offset(self.origin_lat, self.origin_lon, lat, lon)
        return east, north

    def at_time(self, t: float) -> RefPoint:
        index = max(0, min(len(self.points) - 1, int(t / SAMPLE_STEP_S)))
        return self.points[index]

    def fix(self, east: float, north: float, hint: int = 0,
            behind: int = 30, ahead: int = 300) -> PathFix:
        """Nearest point on the path, searched in a window around the last fix.

        The window keeps the fix moving forward along a path that doubles back
        on itself, where the globally nearest point could be on the wrong leg.
        """
        lo = max(0, hint - behind)
        hi = min(len(self.points) - 1, hint + ahead)
        best = None
        for i in range(lo, max(lo + 1, hi)):
            a, b = self.points[i], self.points[min(i + 1, len(self.points) - 1)]
            de, dn = b.east - a.east, b.north - a.north
            span = de * de + dn * dn
            f = 0.0 if span < 1e-9 else max(0.0, min(1.0, ((east - a.east) * de
                                                            + (north - a.north) * dn) / span))
            pe, pn = a.east + de * f, a.north + dn * f
            distance = math.hypot(east - pe, north - pn)
            if best is None or distance < best[0]:
                best = (distance, i, f, pe, pn)
        _, i, f, pe, pn = best
        a, b = self.points[i], self.points[min(i + 1, len(self.points) - 1)]
        point = RefPoint(
            t=a.t + (b.t - a.t) * f, s=a.s + (b.s - a.s) * f, east=pe, north=pn,
            alt_ft=a.alt_ft + (b.alt_ft - a.alt_ft) * f,
            track_deg=normalise_heading(a.track_deg + heading_delta(a.track_deg, b.track_deg) * f),
            bank_deg=a.bank_deg + (b.bank_deg - a.bank_deg) * f,
            vs_fpm=a.vs_fpm + (b.vs_fpm - a.vs_fpm) * f,
            speed_kt=a.speed_kt + (b.speed_kt - a.speed_kt) * f,
        )
        track = math.radians(point.track_deg)
        # Right of the track direction is (cos, -sin) in east/north.
        cross = (east - pe) * math.cos(track) - (north - pn) * math.sin(track)
        return PathFix(point=point, index=i, cross_track_m=cross, along_m=point.s)


@dataclass
class Gains:
    lookahead_s: float = 7.0
    min_lookahead_m: float = 150.0
    max_intercept_deg: float = 30.0
    bank_per_track_deg: float = 1.2
    max_bank_deg: float = 30.0
    aileron_per_bank_deg: float = 0.035
    aileron_per_roll_rate: float = 0.012
    max_aileron: float = 0.6
    vs_per_alt_ft: float = 6.0  # fpm per foot of altitude error
    max_vs_correction_fpm: float = 800.0
    pitch_per_gamma_deg: float = 0.6
    min_pitch_deg: float = -12.0
    max_pitch_deg: float = 15.0
    # Below this fraction of the path's speed, pitch is traded for airspeed
    # before anything else: a stalled aircraft cannot follow anything.
    slow_fraction: float = 0.8
    pitch_per_slow_kt: float = 0.8
    min_alpha_deg: float = -2.0
    max_alpha_deg: float = 8.0
    elevator_per_pitch_deg: float = 0.04
    elevator_per_pitch_rate: float = 0.015
    elevator_integral: float = 0.02
    max_elevator_trim: float = 0.35
    max_elevator: float = 0.7
    throttle_per_kt: float = 0.03
    throttle_integral: float = 0.008
    timing_horizon_s: float = 10.0
    max_timing_correction: float = 0.15
    rudder_per_slip_deg: float = 0.04
    rudder_integral: float = 0.01
    max_rudder: float = 0.5
    # Thrust lags the lever by seconds on a jet; the speed trend is how a
    # pilot sees it coming before the speed itself has moved.
    throttle_per_kt_per_s: float = 0.0
    max_throttle: float = 1.0
    # Fly-by-wire normal law: the sidestick asks for a roll rate and a load
    # factor, neutral holds bank and flight path, and the computers trim.
    roll_rate_full_deg_s: float = 15.0
    roll_time_s: float = 1.5
    load_factor_full_aft: float = 1.5
    load_factor_full_fwd: float = 2.0
    flight_path_time_s: float = 3.0
    max_flight_path_rate_deg_s: float = 2.0
    stick_integral: float = 0.01
    # Roll in this far before the path's bank changes: a slow-rolling
    # aircraft that starts the turn where the path does ends up outside it.
    bank_lead_s: float = 0.0


# A jet's spool-up lag makes the light-aircraft throttle gains surge between
# idle and climb thrust; these move the levers the way a crew does by hand.
AIRLINER_GAINS = Gains(lookahead_s=9.0, min_lookahead_m=300.0, max_bank_deg=30.0,
                       vs_per_alt_ft=5.0, max_vs_correction_fpm=1000.0,
                       throttle_per_kt=0.012, throttle_integral=0.002,
                       throttle_per_kt_per_s=0.04, max_throttle=0.7,
                       timing_horizon_s=20.0, max_timing_correction=0.1,
                       flight_path_time_s=2.5, stick_integral=0.01, bank_lead_s=2.5)


@dataclass(frozen=True)
class Envelope:
    """What the aircraft can actually do, from its DESIGN SPEED simvars."""

    stall_kt: float
    cruise_kt: float

    @property
    def min_kt(self) -> float:
        return self.stall_kt * 1.3


@dataclass
class Aircraft:
    """One frame's reading of the aircraft, in editor signs."""

    t: float
    lat: float
    lon: float
    alt_ft: float
    pitch_deg: float
    bank_deg: float
    heading_deg: float
    tas_kt: float
    vs_fpm: float
    velocity_east_ms: float
    velocity_north_ms: float
    ias_kt: float | None = None


@dataclass
class Command:
    t: float
    aileron: float
    elevator: float
    rudder: float
    throttle: float


@dataclass
class Tracking:
    t: float
    cross_track_m: float
    alt_error_ft: float
    timing_error_m: float


def _clamp(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


@dataclass
class _Filter:
    """First-order low-pass, for rates differentiated from noisy samples."""

    tau: float
    value: float | None = None

    def update(self, sample: float, dt: float) -> float:
        if self.value is None or dt <= 0.0:
            self.value = sample
        else:
            alpha = dt / (self.tau + dt)
            self.value += alpha * (sample - self.value)
        return self.value


class PathFollower:
    def __init__(self, reference: ReferencePath, keep_timing: bool = True,
                 gains: Gains | None = None, throttle_guess: float = 0.6,
                 envelope: Envelope | None = None, fly_by_wire: bool = False,
                 track_ground_speed: bool = False):
        self.reference = reference
        self.keep_timing = keep_timing
        self.gains = gains or Gains()
        self.envelope = envelope
        self.fly_by_wire = fly_by_wire
        # A recorded track's speeds are over the ground; matching them, and
        # its timing, in wind means holding ground speed, not airspeed.
        self.track_ground_speed = track_ground_speed
        # Indicated-airspeed limits for the current configuration, set by the
        # pilot each frame. They override the path's speed: stall and flap
        # limits are not negotiable.
        self.min_ias_kt: float | None = None
        self.max_ias_kt: float | None = None
        self._hint = 0
        self._last: Aircraft | None = None
        self._roll_rate = _Filter(0.15)
        self._pitch_rate = _Filter(0.15)
        self._acceleration = _Filter(1.0)
        self._stick_trim = 0.0
        # Seeded rather than taken from the first reading, which straddles the
        # release and can report a climb or descent the aircraft is not flying.
        self._alpha = _Filter(1.0, value=2.0)
        self._elevator_trim = 0.0
        self._rudder_trim = 0.0
        self._throttle_trim = throttle_guess
        self.last_fix: PathFix | None = None
        self.last_tracking: Tracking | None = None

    @property
    def finished_path(self) -> bool:
        fix = self.last_fix
        return fix is not None and fix.along_m >= self.reference.length_m - 1.0

    def update(self, aircraft: Aircraft, feedforward: dict[str, float] | None = None) -> Command:
        """Controls for this frame.

        With a feedforward schedule the integrators start from zero and only
        learn what the schedule gets wrong; without one they carry the trim.
        """
        g = self.gains
        ff = feedforward or {}
        last, self._last = self._last, aircraft
        dt = aircraft.t - last.t if last is not None else 0.0
        if last is not None and dt > 0.0:
            self._roll_rate.update(heading_delta(last.bank_deg, aircraft.bank_deg) / dt, dt)
            self._pitch_rate.update((aircraft.pitch_deg - last.pitch_deg) / dt, dt)
        roll_rate = self._roll_rate.value or 0.0
        pitch_rate = self._pitch_rate.value or 0.0

        east, north = self.reference.local(aircraft.lat, aircraft.lon)
        fix = self.reference.fix(east, north, self._hint)
        self._hint = fix.index
        self.last_fix = fix
        ref = fix.point

        # -- lateral --
        ground_ms = math.hypot(aircraft.velocity_east_ms, aircraft.velocity_north_ms)
        track = (math.degrees(math.atan2(aircraft.velocity_east_ms, aircraft.velocity_north_ms))
                 if ground_ms > 5.0 else aircraft.heading_deg)
        speed_ms = max(ground_ms, aircraft.tas_kt / KNOTS_PER_MS, 1.0)
        lookahead = max(g.min_lookahead_m, speed_ms * g.lookahead_s)
        intercept = -math.degrees(math.atan2(fix.cross_track_m, lookahead))
        intercept = _clamp(intercept, g.max_intercept_deg)
        track_error = heading_delta(track, normalise_heading(ref.track_deg + intercept))
        # The path's turns and climbs are geometry: off the path's pace, the
        # same curve needs bank in proportion to speed squared, the same slope
        # a climb rate in proportion to speed.
        pace = min(2.0, max(0.3, speed_ms * KNOTS_PER_MS / max(ref.speed_kt, 1.0)))
        path_bank = (self.reference.at_time(ref.t + g.bank_lead_s).bank_deg if g.bank_lead_s
                     else ref.bank_deg)
        curve_bank = math.degrees(math.atan(math.tan(math.radians(path_bank)) * pace ** 2))
        bank_command = _clamp(curve_bank + g.bank_per_track_deg * track_error, g.max_bank_deg)
        # Slow means near the stall, not short of the path's speed: a path the
        # aircraft cannot keep up with should cost time, not altitude.
        if self.min_ias_kt is not None and aircraft.ias_kt is not None:
            slow = self.min_ias_kt - aircraft.ias_kt
        else:
            slow = (self.envelope.min_kt if self.envelope
                    else ref.speed_kt * g.slow_fraction) - aircraft.tas_kt
        if slow > 0.0:
            # Slow: roll towards level first, since bank raises the stall speed.
            bank_command *= 0.5
        if self.fly_by_wire:
            roll_rate_command = (bank_command - aircraft.bank_deg) / g.roll_time_s
            aileron = ff.get("aileron", 0.0) + roll_rate_command / g.roll_rate_full_deg_s
        else:
            aileron = (ff.get("aileron", 0.0)
                       + g.aileron_per_bank_deg * (bank_command - aircraft.bank_deg)
                       - g.aileron_per_roll_rate * roll_rate)

        # -- vertical --
        alt_error = ref.alt_ft - aircraft.alt_ft
        # Banked, the lift is already busy turning; asking it to climb as well
        # is how a steep turn becomes a stall.
        level = max(0.0, math.cos(math.radians(aircraft.bank_deg)))
        vs_command = ref.vs_fpm * pace + _clamp(alt_error * g.vs_per_alt_ft,
                                         g.max_vs_correction_fpm) * level ** 2
        tas_ms = max(aircraft.tas_kt / KNOTS_PER_MS, 10.0)
        gamma_command = math.degrees(math.asin(_clamp(vs_command / FPM_PER_MS / tas_ms, 0.6)))
        gamma = math.degrees(math.asin(_clamp(aircraft.vs_fpm / FPM_PER_MS / tas_ms, 0.6)))
        # Whatever angle of attack the aircraft is carrying now, it will need
        # about the same on the commanded flight path. Clamped, so a stall
        # cannot argue for yet more nose-up.
        alpha = max(g.min_alpha_deg, min(g.max_alpha_deg,
                                         self._alpha.update(aircraft.pitch_deg - gamma, dt)))
        pitch_command = gamma_command + alpha + g.pitch_per_gamma_deg * (gamma_command - gamma)
        if slow > 0.0:
            pitch_command -= g.pitch_per_slow_kt * slow
            gamma_command -= g.pitch_per_slow_kt * slow
        pitch_command = max(g.min_pitch_deg, min(g.max_pitch_deg, pitch_command))
        if self.fly_by_wire:
            elevator = ff.get("elevator", 0.0) + self._load_factor_stick(
                gamma_command, gamma, tas_ms, dt)
        else:
            pitch_error = pitch_command - aircraft.pitch_deg
            if dt > 0.0:
                self._elevator_trim = _clamp(
                    self._elevator_trim + g.elevator_integral * pitch_error * dt,
                    g.max_elevator_trim)
            elevator = (ff.get("elevator", 0.0) + self._elevator_trim
                        + g.elevator_per_pitch_deg * pitch_error
                        - g.elevator_per_pitch_rate * pitch_rate)

        # -- speed --
        timing_error = 0.0
        speed_command = ref.speed_kt
        if self.keep_timing:
            due = self.reference.at_time(min(aircraft.t, self.reference.duration))
            timing_error = due.s - fix.along_m  # positive: behind schedule
            horizon = max(ref.speed_kt / KNOTS_PER_MS * g.timing_horizon_s, 50.0)
            speed_command *= 1.0 + _clamp(timing_error / horizon, g.max_timing_correction)
        over_ground = self.track_ground_speed and ground_ms > 5.0
        measured = ground_ms * KNOTS_PER_MS if over_ground else aircraft.tas_kt
        if self.envelope and not over_ground:
            speed_command = max(self.envelope.min_kt, min(self.envelope.cruise_kt, speed_command))
        speed_error = speed_command - measured
        if aircraft.ias_kt is not None:
            if self.min_ias_kt is not None and aircraft.ias_kt < self.min_ias_kt:
                speed_error = max(speed_error, self.min_ias_kt - aircraft.ias_kt)
            if self.max_ias_kt is not None and aircraft.ias_kt > self.max_ias_kt:
                speed_error = min(speed_error, self.max_ias_kt - aircraft.ias_kt)
        accel = 0.0
        if last is not None and dt > 0.0:
            before = (math.hypot(last.velocity_east_ms, last.velocity_north_ms) * KNOTS_PER_MS
                      if over_ground else last.tas_kt)
            accel = self._acceleration.update((measured - before) / dt, dt)
        base = ff.get("throttle", 0.0)
        if dt > 0.0:
            self._throttle_trim = max(-base, min(g.max_throttle - base, self._throttle_trim
                                                 + g.throttle_integral * speed_error * dt))
        throttle = (base + self._throttle_trim + g.throttle_per_kt * speed_error
                    - g.throttle_per_kt_per_s * accel)

        # -- coordination --
        slip = heading_delta(aircraft.heading_deg, track) if ground_ms > 10.0 else 0.0
        if self.fly_by_wire:
            # The yaw damper coordinates turns; the pedals stay central.
            rudder = ff.get("rudder", 0.0)
        else:
            if dt > 0.0:
                self._rudder_trim = _clamp(self._rudder_trim + g.rudder_integral * slip * dt,
                                           g.max_rudder)
            rudder = ff.get("rudder", 0.0) + self._rudder_trim + g.rudder_per_slip_deg * slip

        self.last_tracking = Tracking(t=aircraft.t, cross_track_m=fix.cross_track_m,
                                      alt_error_ft=-alt_error, timing_error_m=timing_error)
        return Command(
            t=aircraft.t,
            aileron=_clamp(aileron, g.max_aileron),
            elevator=_clamp(elevator, g.max_elevator),
            rudder=_clamp(rudder, g.max_rudder),
            throttle=max(0.0, min(g.max_throttle, throttle)),
        )

    def _load_factor_stick(self, gamma_command: float, gamma: float, tas_ms: float,
                           dt: float) -> float:
        """Sidestick for a normal-law aircraft: the load factor that bends the
        flight path onto the commanded one in about flight_path_time_s.

        Neutral already holds 1 g corrected for pitch, so only the change is asked for.
        """
        g = self.gains
        error = gamma_command - gamma
        rate = _clamp(error / g.flight_path_time_s, g.max_flight_path_rate_deg_s)
        delta_g = tas_ms * math.radians(rate) / 9.80665
        if dt > 0.0:
            self._stick_trim = _clamp(self._stick_trim + g.stick_integral * error * dt, 0.2)
        full = g.load_factor_full_aft if delta_g >= 0.0 else g.load_factor_full_fwd
        return delta_g / full + self._stick_trim

    def peak_speed_kt(self) -> float:
        return max(point.speed_kt for point in self.reference.points)

    def seed_with_feedforward(self) -> None:
        """Start the integrators at zero: the schedule already carries the trim."""
        self._elevator_trim = 0.0
        self._stick_trim = 0.0
        self._rudder_trim = 0.0
        self._throttle_trim = 0.0
