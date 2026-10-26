"""Put a clock on an evaluated PathProgram — SEGMENT_MODEL.md sections 5.1 and 6.

Stage 1 produced geometry parameterised by distance. This turns that into a
timeline: each segment's velocity profile gives a duration, dwells sit between
them, and inverting the time law gives a pose at any instant.

Two things here exist because a mid-path MoveTo is allowed. Time stays
continuous across one while position jumps, so the clock never has a hole in
it; and attitude rates are differenced one-sided and never across the jump,
because a window spanning it reads a near-infinite turn rate and would throw
the bank hard over for one frame.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass

from .program import MoveToSegment, PathProgram, VelocityProfile
from .program_geom import (
    MIN_HORIZONTAL,
    ProgramError,
    SegmentGeometry,
    SolvedProgram,
    Vec3,
    direction_angles,
    direction_vector,
    evaluate,
)
from .units import GRAVITY_MS2, heading_delta, normalise_heading

# A speed law that reaches zero makes the time integral diverge, so the
# profile needs a floor. Two knots: slow enough for anything real, fast
# enough that the integral stays well conditioned.
MIN_SPEED_MS = 1.0
# Attitude rates are differenced over this window, matching the waypoint
# model's flight_path.RATE_WINDOW_S so both models bank alike.
RATE_WINDOW_S = 0.05
# Subintervals in each segment's time table. The integrand is smooth, so this
# is already far finer than the pose needs.
TIME_TABLE_STEPS = 64
# Attitude series spacing, matching flight_path.BANK_SAMPLE_S. Capped in count
# so a very long dwell does not allocate millions of samples.
ATTITUDE_SAMPLE_S = 0.1
MAX_ATTITUDE_SAMPLES = 20000
# Heading and pitch are lightly smoothed so a corner between two straight
# segments yaws through it instead of snapping in one frame. Symmetric, so a
# steady turn is unchanged and nothing lags.
ATTITUDE_SMOOTHING_S = 0.5


def _gauss_legendre_5() -> tuple[tuple[float, float], ...]:
    """Nodes and weights on [-1, 1], exact for polynomials up to degree 9.

    Written out in closed form rather than as decimal literals so the values
    carry their own proof.
    """
    inner = math.sqrt(10.0 / 7.0)
    near = math.sqrt(5.0 - 2.0 * inner) / 3.0
    far = math.sqrt(5.0 + 2.0 * inner) / 3.0
    near_weight = (322.0 + 13.0 * math.sqrt(70.0)) / 900.0
    far_weight = (322.0 - 13.0 * math.sqrt(70.0)) / 900.0
    return (
        (0.0, 128.0 / 225.0),
        (-near, near_weight), (near, near_weight),
        (-far, far_weight), (far, far_weight),
    )


GAUSS_LEGENDRE_5 = _gauss_legendre_5()


def time_table(length_m: float, profile: VelocityProfile) -> list[float]:
    """Cumulative time at each tabulated sigma, from dt = L*dsigma / v(sigma).

    The total is the last entry rather than a separately integrated number, so
    the duration and the inversion can never disagree about the same segment.
    """
    table = [0.0]
    step = 1.0 / TIME_TABLE_STEPS
    half = step / 2.0
    for index in range(TIME_TABLE_STEPS):
        middle = index * step + half
        total = 0.0
        for node, weight in GAUSS_LEGENDRE_5:
            total += weight / profile.speed_at(middle + half * node)
        table.append(table[-1] + length_m * total * half)
    return table


def duration_for(length_m: float, profile: VelocityProfile) -> float:
    return time_table(length_m, profile)[-1]


def sigma_at(table: list[float], seconds: float) -> float:
    """Invert the time law: how far along the segment we are at this instant."""
    total = table[-1]
    if total <= 0.0:
        return 0.0
    seconds = min(total, max(0.0, seconds))
    slot = min(max(bisect.bisect_left(table, seconds), 1), len(table) - 1)
    low, high = table[slot - 1], table[slot]
    within = (seconds - low) / (high - low) if high - low > 1e-12 else 0.0
    return (slot - 1 + within) / TIME_TABLE_STEPS


def time_at_sigma(table: list[float], sigma: float) -> float:
    """How long into the segment a given fraction along it is — the forward law."""
    sigma = min(1.0, max(0.0, sigma))
    position = sigma * TIME_TABLE_STEPS
    slot = min(int(position), TIME_TABLE_STEPS - 1)
    return table[slot] + (table[slot + 1] - table[slot]) * (position - slot)


def resolve_profiles(program: PathProgram) -> list[VelocityProfile | None]:
    """The profile each segment is actually flown with, after inheritance.

    `inherit_entry` reseats c0 on the previous segment's exit speed. A MoveTo
    has no profile of its own; it either states the speed to carry on with or
    clears it, since a speed carried across a jump describes nothing.
    """
    resolved: list[VelocityProfile | None] = []
    carried: float | None = None
    for segment in program.segments:
        if isinstance(segment, MoveToSegment):
            resolved.append(None)
            carried = segment.speed_ms
            continue
        profile = segment.velocity
        if profile.inherit_entry and carried is not None:
            profile = profile.with_entry(carried)
        resolved.append(profile)
        carried = profile.exit_speed
    return resolved


def _gaussian(values: list[float], step: float, sigma: float) -> list[float]:
    """Gaussian smoothing of an evenly spaced series, renormalised at the ends."""
    if sigma <= 0.0 or step <= 0.0 or len(values) < 3:
        return list(values)
    reach = max(1, round(3.0 * sigma / step))
    weights = [math.exp(-0.5 * (k * step / sigma) ** 2) for k in range(-reach, reach + 1)]
    count = len(values)
    smoothed = []
    for i in range(count):
        total = weight_sum = 0.0
        for k, weight in enumerate(weights, start=-reach):
            j = i + k
            if 0 <= j < count:
                total += values[j] * weight
                weight_sum += weight
        smoothed.append(total / weight_sum)
    return smoothed


@dataclass(frozen=True)
class Phase:
    """A stretch of the timeline covered by one segment.

    FLY advances along the curve; HOLD sits at a dwell, where the aircraft is
    stationary and nothing but the clock moves.
    """

    kind: str
    index: int
    start_s: float
    end_s: float


@dataclass(frozen=True)
class ProgramPose:
    lat: float
    lon: float
    alt_ft_msl: float
    heading_deg_true: float
    pitch_deg: float
    bank_deg: float
    ground_speed_ms: float
    # True when the pen jumped to reach this instant, so a consumer drawing a
    # playhead should cut rather than slide.
    after_seam: bool


class TimedProgram:
    """An evaluated program with a clock on it."""

    def __init__(self, program: PathProgram, solved: SolvedProgram | None = None):
        self.program = program
        self.solved = solved if solved is not None else evaluate(program)
        self.profiles = resolve_profiles(program)
        self._check_speeds()

        self._tables: list[list[float] | None] = []
        self._phases: list[Phase] = []
        self._hold: dict[int, tuple[Vec3, Vec3]] = {}
        self._fly_start: dict[int, float] = {}
        self.seam_times: list[float] = []
        self._build()
        self._attitude = ([self._attitude_run(start, end) for start, end in self._runs()]
                          if self._phases else [])

    # ---------------------------------------------------------------- build

    def _check_speeds(self) -> None:
        for index, profile in enumerate(self.profiles):
            if profile is None:
                continue
            slowest, where = profile.minimum_speed()
            if slowest < MIN_SPEED_MS:
                raise ProgramError(
                    f"the speed profile drops to {slowest:.2f} m/s at {where:.0%} "
                    f"along this segment, which stops the clock. Keep it above "
                    f"{MIN_SPEED_MS:.0f} m/s, or use a dwell to hold still.",
                    index,
                    self.program.segments[index].id,
                )

    def _frozen_state(self, index: int) -> tuple[Vec3, Vec3]:
        """Where a dwell sits and which way the nose points through it."""
        geometry = self.solved.segments[index]
        if geometry.length_m > 0.0:
            return geometry.end, geometry.tangent_at(1.0)
        # A MoveTo has no tangent of its own unless it stated one. Falling
        # forward to whatever is flown next keeps the nose pointing where the
        # aircraft is about to go instead of where it used to.
        segment = self.program.segments[index]
        if isinstance(segment, MoveToSegment) and segment.tangent is not None:
            return geometry.end, direction_vector(
                segment.tangent.heading_deg, segment.tangent.climb_deg
            )
        for later in self.solved.segments[index + 1:]:
            if later.length_m > 0.0:
                return geometry.end, later.tangent_at(0.0)
        return geometry.end, (0.0, 0.0, 1.0)

    def _build(self) -> None:
        clock = 0.0
        for index, segment in enumerate(self.program.segments):
            geometry = self.solved.segments[index]
            profile = self.profiles[index]
            if isinstance(segment, MoveToSegment) and index > 0:
                self.seam_times.append(clock)
            if geometry.length_m > 0.0 and profile is not None:
                table = time_table(geometry.length_m, profile)
                self._tables.append(table)
                self._fly_start[index] = clock
                self._phases.append(Phase("FLY", index, clock, clock + table[-1]))
                clock += table[-1]
            else:
                self._tables.append(None)
            dwell = segment.end.dwell_s
            if dwell > 0.0:
                self._hold[index] = self._frozen_state(index)
                self._phases.append(Phase("HOLD", index, clock, clock + dwell))
                clock += dwell
        self.duration_s = clock

    # ------------------------------------------------------------- timeline

    def segment_duration(self, index: int) -> float:
        table = self._tables[index]
        return table[-1] if table else 0.0

    def segment_start_s(self, index: int) -> float:
        """When a segment begins. A MoveTo has no span, so it begins where it ends."""
        if index in self._fly_start:
            return self._fly_start[index]
        later = [start for key, start in self._fly_start.items() if key > index]
        return min(later) if later else self.duration_s

    def time_at(self, index: int, sigma: float) -> float:
        """Absolute time at a fraction along a segment."""
        table = self._tables[index]
        if table is None:
            return self.segment_start_s(index)
        return self._fly_start[index] + time_at_sigma(table, sigma)

    @property
    def dwell_total_s(self) -> float:
        return sum(segment.end.dwell_s for segment in self.program.segments)

    @property
    def flying_s(self) -> float:
        return self.duration_s - self.dwell_total_s

    def _phase_at(self, seconds: float, left_limit: bool = False) -> Phase:
        if not self._phases:
            raise ProgramError("the program has no duration", 0)
        seconds = min(max(seconds, 0.0), self.duration_s)
        if left_limit:
            for phase in reversed(self._phases):
                if phase.start_s < seconds <= phase.end_s:
                    return phase
            return self._phases[0]
        for index, phase in enumerate(self._phases):
            # Strictly inside, so an instant landing on a boundary belongs to
            # what comes after. On an ordinary join both give the same pose;
            # at a seam only the later one is right.
            if seconds < phase.end_s or index == len(self._phases) - 1:
                return phase
        return self._phases[-1]

    def _run_containing(self, seconds: float) -> tuple[float, float]:
        """The longest stretch around this instant that the pen never jumps in."""
        bounds = [0.0, *self.seam_times, self.duration_s]
        slot = min(max(bisect.bisect_right(bounds, seconds) - 1, 0), len(bounds) - 2)
        return bounds[slot], bounds[slot + 1]

    # ----------------------------------------------------------------- pose

    def state_at(self, seconds: float, left_limit: bool = False) -> tuple[Vec3, Vec3, float]:
        """Position, unit tangent and speed along the path at this instant."""
        phase = self._phase_at(seconds, left_limit)
        geometry: SegmentGeometry = self.solved.segments[phase.index]
        if phase.kind == "HOLD":
            point, tangent = self._hold[phase.index]
            return point, tangent, 0.0
        table = self._tables[phase.index]
        profile = self.profiles[phase.index]
        sigma = sigma_at(table, seconds - phase.start_s)
        return geometry.point_at(sigma), geometry.tangent_at(sigma), profile.speed_at(sigma)

    def position_at(self, seconds: float, left_limit: bool = False) -> tuple[float, float, float]:
        point, _, _ = self.state_at(seconds, left_limit)
        return self.solved.to_latlon(point)

    def track_heading_at(self, seconds: float, left_limit: bool = False) -> float:
        _, tangent, _ = self.state_at(seconds, left_limit)
        if math.hypot(tangent[0], tangent[2]) < MIN_HORIZONTAL:
            return 0.0
        return normalise_heading(math.degrees(math.atan2(tangent[0], tangent[2])))

    def ground_speed_at(self, seconds: float, left_limit: bool = False) -> float:
        _, tangent, speed = self.state_at(seconds, left_limit)
        return speed * math.hypot(tangent[0], tangent[2])

    def pitch_deg_at(self, seconds: float, left_limit: bool = False) -> float:
        _, tangent, _ = self.state_at(seconds, left_limit)
        return direction_angles(tangent)[1]

    def turn_rate_rads(self, seconds: float) -> float:
        """How fast the track is turning, differenced one-sided at a seam.

        The window is clipped to the run containing this instant, so it never
        spans a jump. Across one it would read the whole heading change of a
        teleport as having happened in 0.05 s.
        """
        start, end = self._run_containing(seconds)
        low = max(start, seconds - RATE_WINDOW_S)
        high = min(end, seconds + RATE_WINDOW_S)
        span = high - low
        if span < 1e-9:
            return 0.0
        before = self.track_heading_at(low)
        after = self.track_heading_at(high, left_limit=high >= end)
        return math.radians(heading_delta(before, after)) / span

    def coordinated_bank_deg(self, seconds: float) -> float:
        """Coordinated bank, phi = atan(omega*v / g), held to the path's limit."""
        limit = self.program.auto_bank.max_deg
        bank = math.degrees(math.atan2(
            self.turn_rate_rads(seconds) * self.ground_speed_at(seconds), GRAVITY_MS2
        ))
        return max(-limit, min(limit, bank))

    # ------------------------------------------------------------- attitude

    def _runs(self) -> list[tuple[float, float]]:
        bounds = [0.0, *self.seam_times, self.duration_s]
        return list(zip(bounds[:-1], bounds[1:]))

    def _attitude_run(self, start: float, end: float) -> dict:
        """Smoothed bank, heading and pitch series for one jump-free stretch.

        Bank uses the waypoint model's law: roll-rate limited, then Gaussian
        smoothed. A corner between two straight segments otherwise reads as an
        infinite turn rate and flicks to the bank limit for one frame.
        """
        span = end - start
        count = max(2, min(MAX_ATTITUDE_SAMPLES, math.ceil(span / ATTITUDE_SAMPLE_S) + 1))
        step = span / (count - 1) if span > 1e-9 else 0.0
        times = [start + i * step for i in range(count)]
        # The run's last instant is the left limit when a seam follows it.
        last_left = end < self.duration_s
        bank = [self.coordinated_bank_deg(t) for t in times]
        heading = [self.track_heading_at(t, left_limit=last_left and i == count - 1)
                   for i, t in enumerate(times)]
        pitch = [self.pitch_deg_at(t, left_limit=last_left and i == count - 1)
                 for i, t in enumerate(times)]
        for i in range(1, count):
            heading[i] = heading[i - 1] + heading_delta(heading[i - 1], heading[i])
        if step > 0.0:
            auto = self.program.auto_bank
            limit = auto.roll_rate_deg_s * step
            for i in range(1, count):
                bank[i] = min(max(bank[i], bank[i - 1] - limit), bank[i - 1] + limit)
            for i in range(count - 2, -1, -1):
                bank[i] = min(max(bank[i], bank[i + 1] - limit), bank[i + 1] + limit)
            bank = _gaussian(bank, step, auto.smoothing_s)
            heading = _gaussian(heading, step, ATTITUDE_SMOOTHING_S)
            pitch = _gaussian(pitch, step, ATTITUDE_SMOOTHING_S)
        return {"start": start, "step": step, "bank": bank,
                "heading": heading, "pitch": pitch}

    def _attitude_value(self, key: str, seconds: float, left_limit: bool = False) -> float:
        if not self._attitude:
            raise ProgramError("the program has no duration", 0)
        runs = self._runs()
        slot = len(runs) - 1
        for index, (start, end) in enumerate(runs):
            if seconds < end or (left_limit and seconds <= end):
                slot = index
                break
        series = self._attitude[slot]
        values = series[key]
        if series["step"] <= 0.0 or len(values) == 1:
            return values[0]
        position = min(max((seconds - series["start"]) / series["step"], 0.0),
                       len(values) - 1)
        index = min(int(position), len(values) - 2)
        fraction = position - index
        return values[index] + (values[index + 1] - values[index]) * fraction

    def bank_deg_at(self, seconds: float) -> float:
        """Coordinated bank, roll-rate limited and smoothed like waypoint paths."""
        return self._attitude_value("bank", seconds)

    def heading_deg_at(self, seconds: float, left_limit: bool = False) -> float:
        """Nose heading: the track, rounded through corners."""
        return normalise_heading(self._attitude_value("heading", seconds, left_limit))

    def attitude_pitch_deg_at(self, seconds: float, left_limit: bool = False) -> float:
        return self._attitude_value("pitch", seconds, left_limit)

    def pose_at(self, seconds: float, left_limit: bool = False) -> ProgramPose:
        lat, lon, alt_ft = self.position_at(seconds, left_limit)
        return ProgramPose(
            lat=lat, lon=lon, alt_ft_msl=alt_ft,
            heading_deg_true=self.heading_deg_at(seconds, left_limit),
            pitch_deg=self.attitude_pitch_deg_at(seconds, left_limit),
            bank_deg=self.bank_deg_at(seconds),
            ground_speed_ms=self.ground_speed_at(seconds, left_limit),
            after_seam=any(abs(seconds - seam) < 1e-9 for seam in self.seam_times),
        )

    def segment_index_at(self, seconds: float, left_limit: bool = False) -> int:
        """Which segment the clock is in — including a dwell after it."""
        return self._phase_at(seconds, left_limit).index

    def boundary_times(self) -> list[float]:
        """Every instant the geometry or the clock changes character.

        Segment starts, dwell starts, and seams. The preview samples these so
        a tight turn authored as a short arc is not drawn as a chord across
        the grid points that missed it.
        """
        times = {0.0, self.duration_s, *self.seam_times}
        for phase in self._phases:
            times.add(phase.start_s)
            times.add(phase.end_s)
        return sorted(times)


# ------------------------------------------------------------- duration fit


def fit_scale(current_s: float, target_s: float) -> float:
    """The factor to multiply every coefficient by to hit a target duration.

    Scaling all four coefficients by k scales the duration by exactly 1/k,
    because k factors straight out of the integral. So this is a division,
    not a search.
    """
    if target_s <= 0.0:
        raise ValueError("a target duration must be positive")
    return current_s / target_s


def fit_program_duration(program: PathProgram, target_s: float) -> PathProgram:
    """A copy of the program retimed to a total duration, dwells excluded.

    Dwells are wall-clock holds and do not stretch, so the flying time absorbs
    the whole change.
    """
    timed = TimedProgram(program)
    target_flying = target_s - timed.dwell_total_s
    if target_flying <= 0.0:
        raise ValueError(
            f"the dwells alone come to {timed.dwell_total_s:.1f} s, so {target_s:.1f} s "
            "is not reachable without shortening them"
        )
    scale = fit_scale(timed.flying_s, target_flying)
    retimed = program.model_copy(deep=True)
    for segment in retimed.segments:
        if not isinstance(segment, MoveToSegment):
            segment.velocity = segment.velocity.scaled(scale)
        elif segment.speed_ms is not None:
            # A re-seed is a speed like any other. Leaving it alone makes
            # everything downstream of a cut fly at the old pace, and the
            # program misses the target by whatever that stretch is worth.
            segment.speed_ms *= scale
    return retimed


def fit_duration_holding_entry(
    length_m: float, profile: VelocityProfile, target_s: float,
    bracket: tuple[float, float] = (0.0, 20.0), tolerance_s: float = 1e-6,
) -> VelocityProfile:
    """Retime a segment without moving its entry speed.

    Holding c0 for continuity leaves only the shape terms free, so there is no
    factoring trick and this bisects on a scale applied to c1..c3.
    """
    if target_s <= 0.0:
        raise ValueError("a target duration must be positive")

    def shaped(scale: float) -> VelocityProfile:
        return profile.model_copy(update={
            "c1": profile.c1 * scale, "c2": profile.c2 * scale, "c3": profile.c3 * scale,
        })

    def duration(scale: float) -> float:
        candidate = shaped(scale)
        if candidate.minimum_speed()[0] < MIN_SPEED_MS:
            return math.inf
        return duration_for(length_m, candidate)

    low, high = bracket
    low_s, high_s = duration(low), duration(high)
    if not (min(low_s, high_s) <= target_s <= max(low_s, high_s)):
        raise ValueError(
            f"{target_s:.1f} s is outside what this segment can do with its entry "
            f"speed held ({min(low_s, high_s):.1f}-{max(low_s, high_s):.1f} s)"
        )
    descending = high_s < low_s
    for _ in range(80):
        middle = (low + high) / 2.0
        current = duration(middle)
        if abs(current - target_s) < tolerance_s:
            break
        if (current > target_s) == descending:
            low = middle
        else:
            high = middle
    return shaped((low + high) / 2.0)


# ----------------------------------------------------------------- validate


def validate_timing(program: PathProgram) -> list[dict]:
    """Report what would make the clock misbehave, without raising.

    The evaluator refuses a profile that stops the clock; this says the same
    thing in a form an editor can put next to the offending segment.
    """
    issues: list[dict] = []
    for index, (segment, profile) in enumerate(zip(program.segments, resolve_profiles(program))):
        if profile is not None:
            slowest, where = profile.minimum_speed()
            if slowest < MIN_SPEED_MS:
                issues.append({
                    "index": index, "segment_id": segment.id, "code": "SPEED_TOO_LOW",
                    "detail": f"drops to {slowest:.2f} m/s at {where:.0%} along the segment",
                })
        for name in ("heading", "pitch", "bank"):
            if getattr(segment.end, name).mode == "MANUAL":
                issues.append({
                    "index": index, "segment_id": segment.id, "code": "ANGLE_PIN_IGNORED",
                    "detail": f"a MANUAL {name} at this boundary is stored but not yet "
                              "applied; attitude is still derived from the path",
                })
    return issues
