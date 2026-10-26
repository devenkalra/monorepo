"""Tune the hand-flying pilot's gains for an aircraft, by flying it.

Three pieces, none of which knows about any particular path:

  * A manoeuvre suite built from the aircraft's own speeds, so the same suite
    exercises a C172 and an A320: S-turns, a climbing turn, and a slowing
    descent that needs the flaps.
  * A score for one flown run against its path: cross-track, altitude and
    timing error, how busy the thrust levers were, and whether it got there.
  * A coordinate search: one gain at a time, up then down, halving the step
    when neither helps. Runs are noisy, so a change has to beat the incumbent
    by a margin, and the incumbent is re-flown now and then and averaged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields
from typing import Callable

from .guidance import Gains, ReferencePath
from .schema import FlightKeyframe
from .units import KNOTS_PER_MS, offset_latlon

G = 9.80665
KEYFRAME_STEP_S = 5.0
# A segment's first seconds are the release settling, not the pilot.
SCORE_SKIP_S = 15.0
LEAD_IN_S = 15.0
SUITE_BANK_DEG = 20.0
ROLL_IN_S = 4.0

# What one unit of cost is worth: 20 m off track, 50 ft off altitude and 1 s
# off the clock count the same.
CROSS_TRACK_SCALE_M = 20.0
ALT_SCALE_FT = 50.0
TIMING_SCALE_S = 1.0
# Lever travel per second, averaged: a pilot pumping the levers is not one to copy.
THROTTLE_ACTIVITY_SCALE = 0.05
UNFINISHED_PENALTY = 20.0
FAILED_COST = 100.0


# -- the manoeuvre suite ---------------------------------------------------

@dataclass(frozen=True)
class SuiteSpeeds:
    """Indicated airspeeds for the suite, from the aircraft's own limits."""

    low_kt: float
    mid_kt: float
    high_kt: float
    climb_fpm: float
    descent_fpm: float

    @classmethod
    def for_aircraft(cls, clean_min_kt: float, full_flap_min_kt: float | None,
                     cruise_kt: float, jet: bool) -> SuiteSpeeds:
        """`clean_min_kt` and `full_flap_min_kt`: the lowest selectable speeds, VLS."""
        ceiling = cruise_kt * 0.9
        mid = min(clean_min_kt * 1.25, ceiling)
        high = min(clean_min_kt * 1.5, ceiling)
        low = (full_flap_min_kt + 15.0) if full_flap_min_kt else clean_min_kt + 5.0
        # Slowing while descending must be possible at idle with flaps: an
        # A320 asked to lose 130 kt in 70 s at 1000 fpm ran 5 s late however
        # it was flown, and a tuner would chase that for nothing.
        return cls(low_kt=min(low, mid), mid_kt=mid, high_kt=max(high, mid),
                   climb_fpm=1500.0 if jet else 500.0,
                   descent_fpm=500.0 if jet else 300.0)


@dataclass
class Manoeuvre:
    name: str
    keyframes: list[FlightKeyframe]

    @property
    def duration(self) -> float:
        return self.keyframes[-1].time_offset


def tas_kt(ias_kt: float, alt_ft: float) -> float:
    sigma = max(0.2, 1.0 - 6.8756e-6 * alt_ft) ** 4.2559
    return ias_kt / math.sqrt(sigma)


def _fly(lat: float, lon: float, alt_ft: float, heading_deg: float, duration_s: float,
         speed_ias: Callable[[float], float], vs_fpm: Callable[[float], float],
         bank_deg: Callable[[float], float]) -> list[FlightKeyframe]:
    """Integrate a coordinated flight at 0.1 s and keep a keyframe every few seconds."""
    dt = 0.1
    north = east = 0.0
    heading, alt, t = heading_deg, alt_ft, 0.0
    keyframes = []
    steps = int(round(duration_s / dt))
    for i in range(steps + 1):
        t = i * dt
        if i % int(round(KEYFRAME_STEP_S / dt)) == 0 or i == steps:
            k_lat, k_lon = offset_latlon(lat, lon, north, east)
            keyframes.append(FlightKeyframe(time_offset=round(t, 3), lat=k_lat, lon=k_lon,
                                            alt_ft_msl=round(alt, 1)))
        speed = tas_kt(speed_ias(t), alt) / KNOTS_PER_MS
        heading += math.degrees(G * math.tan(math.radians(bank_deg(t))) / speed) * dt
        north += speed * math.cos(math.radians(heading)) * dt
        east += speed * math.sin(math.radians(heading)) * dt
        alt += vs_fpm(t) / 60.0 * dt
    return keyframes


def _banked(segments: list[tuple[float, float, float]]) -> Callable[[float], float]:
    """Bank over time from (start, end, bank) pieces, rolled in and out over ROLL_IN_S."""
    def bank(t: float) -> float:
        for start, end, value in segments:
            if start <= t <= end:
                ramp = min(1.0, (t - start) / ROLL_IN_S, (end - t) / ROLL_IN_S)
                return value * max(0.0, ramp)
        return 0.0
    return bank


def manoeuvre_suite(lat: float, lon: float, alt_ft: float, speeds: SuiteSpeeds,
                    heading_deg: float = 0.0) -> list[Manoeuvre]:
    b = SUITE_BANK_DEG
    lead = LEAD_IN_S
    s_turns = _fly(lat, lon, alt_ft, heading_deg, lead + 75.0,
                   lambda t: speeds.high_kt, lambda t: 0.0,
                   _banked([(lead, lead + 25.0, b), (lead + 30.0, lead + 55.0, -b)]))
    climb = _fly(lat, lon, alt_ft, heading_deg, lead + 75.0,
                 lambda t: speeds.mid_kt,
                 lambda t: speeds.climb_fpm * min(1.0, max(0.0, (t - lead) / 10.0)),
                 _banked([(lead + 10.0, lead + 50.0, -b)]))

    def slowing(t: float) -> float:
        fraction = min(1.0, max(0.0, (t - lead) / 90.0))
        return speeds.mid_kt + (speeds.low_kt - speeds.mid_kt) * fraction

    descent = _fly(lat, lon, alt_ft, heading_deg, lead + 95.0, slowing,
                   lambda t: -speeds.descent_fpm * min(1.0, max(0.0, (t - lead) / 10.0)),
                   _banked([(lead + 20.0, lead + 45.0, b * 0.75)]))
    return [Manoeuvre("s-turns", s_turns), Manoeuvre("climbing-turn", climb),
            Manoeuvre("slowing-descent", descent)]


# -- scoring ----------------------------------------------------------------

@dataclass
class RunScore:
    cost: float
    rms_cross_track_m: float = 0.0
    rms_alt_ft: float = 0.0
    rms_timing_s: float = 0.0
    max_cross_track_m: float = 0.0
    max_alt_ft: float = 0.0
    throttle_activity: float = 0.0
    progress: float = 0.0
    failed: str | None = None

    def as_dict(self) -> dict:
        return {f.name: (round(v, 3) if isinstance(v, float) else v)
                for f in fields(self) for v in [getattr(self, f.name)]}


def _rms(values: list[float]) -> float:
    return math.sqrt(sum(v * v for v in values) / len(values)) if values else 0.0


def score_run(samples: list[dict], commands: list[dict], reference: ReferencePath,
              skip_s: float = SCORE_SKIP_S) -> RunScore:
    """How well one run followed its path. Samples and commands as the API returns them."""
    if len(samples) < 2:
        return RunScore(cost=FAILED_COST, failed="no samples")
    hint = 0
    cross, alt, late = [], [], []
    for s in samples:
        east, north = reference.local(s["lat"], s["lon"])
        fix = reference.fix(east, north, hint)
        hint = fix.index
        if s["t"] < skip_s:
            continue
        cross.append(fix.cross_track_m)
        alt.append(s["alt_ft_msl"] - fix.point.alt_ft)
        late.append(s["t"] - fix.point.t)
    progress = min(1.0, reference.points[hint].s / max(reference.length_m, 1.0))
    travel = sum(abs(b["throttle"] - a["throttle"]) for a, b in zip(commands, commands[1:]))
    span = commands[-1]["t"] - commands[0]["t"] if len(commands) > 1 else 0.0
    activity = travel / span if span > 0 else 0.0
    score = RunScore(cost=0.0, rms_cross_track_m=_rms(cross), rms_alt_ft=_rms(alt),
                     rms_timing_s=_rms(late),
                     max_cross_track_m=max((abs(v) for v in cross), default=0.0),
                     max_alt_ft=max((abs(v) for v in alt), default=0.0),
                     throttle_activity=activity, progress=progress)
    score.cost = (score.rms_cross_track_m / CROSS_TRACK_SCALE_M
                  + score.rms_alt_ft / ALT_SCALE_FT
                  + score.rms_timing_s / TIMING_SCALE_S
                  + activity / THROTTLE_ACTIVITY_SCALE
                  + UNFINISHED_PENALTY * max(0.0, 0.98 - progress) / 0.98)
    return score


# -- the search --------------------------------------------------------------

@dataclass(frozen=True)
class Param:
    name: str
    lo: float
    hi: float
    step: float

    def clip(self, value: float) -> float:
        return round(max(self.lo, min(self.hi, value)), 6)


FLY_BY_WIRE_PARAMS = [
    Param("lookahead_s", 5.0, 15.0, 2.0),
    Param("bank_per_track_deg", 0.5, 2.5, 0.4),
    Param("bank_lead_s", 0.0, 5.0, 1.0),
    Param("roll_time_s", 0.8, 3.0, 0.4),
    Param("vs_per_alt_ft", 2.0, 10.0, 1.5),
    Param("flight_path_time_s", 1.5, 6.0, 0.75),
    Param("stick_integral", 0.0, 0.03, 0.005),
    Param("throttle_per_kt", 0.004, 0.03, 0.004),
    Param("throttle_integral", 0.0, 0.006, 0.001),
    Param("throttle_per_kt_per_s", 0.0, 0.1, 0.02),
]

CONVENTIONAL_PARAMS = [
    Param("lookahead_s", 4.0, 12.0, 1.5),
    Param("bank_per_track_deg", 0.5, 2.5, 0.4),
    Param("bank_lead_s", 0.0, 3.0, 1.0),
    Param("aileron_per_bank_deg", 0.015, 0.07, 0.01),
    Param("aileron_per_roll_rate", 0.0, 0.03, 0.005),
    Param("vs_per_alt_ft", 2.0, 10.0, 1.5),
    Param("pitch_per_gamma_deg", 0.2, 1.5, 0.2),
    Param("elevator_per_pitch_deg", 0.02, 0.08, 0.01),
    Param("elevator_per_pitch_rate", 0.0, 0.04, 0.006),
    Param("elevator_integral", 0.005, 0.05, 0.008),
    Param("throttle_per_kt", 0.01, 0.06, 0.01),
    Param("throttle_integral", 0.002, 0.02, 0.003),
    Param("rudder_per_slip_deg", 0.0, 0.1, 0.02),
]

GAIN_NAMES = {f.name for f in fields(Gains)}


def gains_with(base: Gains, overrides: dict[str, float]) -> Gains:
    unknown = set(overrides) - GAIN_NAMES
    if unknown:
        raise ValueError(f"Unknown gains: {', '.join(sorted(unknown))}")
    values = {f.name: getattr(base, f.name) for f in fields(Gains)}
    values.update({k: float(v) for k, v in overrides.items()})
    return Gains(**values)


@dataclass
class SearchResult:
    gains: dict[str, float]
    cost: float
    evaluations: int
    history: list[tuple[dict[str, float], float]] = field(default_factory=list)


def coordinate_search(evaluate: Callable[[dict[str, float]], float], params: list[Param],
                      start: dict[str, float], max_evals: int = 40, margin: float = 0.03,
                      min_step_fraction: float = 0.125, recheck_every: int = 8) -> SearchResult:
    """Minimise a noisy cost one parameter at a time.

    A candidate replaces the incumbent only if it beats the incumbent's mean
    cost by `margin`, and every `recheck_every` evaluations the incumbent is
    flown again, so one lucky run cannot hold the lead for long.
    """
    best = {p.name: p.clip(start.get(p.name, (p.lo + p.hi) / 2)) for p in params}
    history: list[tuple[dict[str, float], float]] = []

    def run(gains: dict[str, float]) -> float:
        cost = evaluate(dict(gains))
        history.append((dict(gains), cost))
        return cost

    best_costs = [run(best)]
    steps = {p.name: p.step for p in params}
    since_check = 0
    while len(history) < max_evals:
        live = [p for p in params if steps[p.name] >= p.step * min_step_fraction]
        if not live:
            break
        for p in live:
            if len(history) >= max_evals:
                break
            improved = False
            for direction in (1.0, -1.0):
                candidate = dict(best)
                candidate[p.name] = p.clip(best[p.name] + direction * steps[p.name])
                if candidate[p.name] == best[p.name] or len(history) >= max_evals:
                    continue
                cost = run(candidate)
                since_check += 1
                incumbent = sum(best_costs) / len(best_costs)
                if cost < incumbent * (1.0 - margin):
                    best, best_costs, improved = candidate, [cost], True
                    break
            if not improved:
                steps[p.name] *= 0.5
            if since_check >= recheck_every and len(history) < max_evals:
                best_costs.append(run(best))
                since_check = 0
    return SearchResult(gains=best, cost=sum(best_costs) / len(best_costs),
                        evaluations=len(history), history=history)
