"""What a sim-flown take actually did, and how to turn it into an editable path.

The recording, not the control inputs, is what makes a take reusable: the same
inputs never fly quite the same path twice, because frame timing and weather
differ between runs. Converting the recording to ordinary flight keyframes lets
it be replayed exactly by pose injection, with cameras, as often as wanted.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from .controls import CHANNELS
from .schema import ControlKeyframe, FlightKeyframe, ManualAngle, SystemsKeyframe, TimeSource


@dataclass(frozen=True)
class Sample:
    t: float
    lat: float
    lon: float
    alt_ft_msl: float
    pitch_deg: float
    bank_deg: float
    heading_deg_true: float
    airspeed_kt: float
    vertical_speed_fpm: float
    aileron: float
    elevator: float
    rudder: float
    throttle: float
    elevator_trim: float = 0.0
    ias_kt: float = 0.0
    flaps: float = 0.0
    gear_pct: float = 0.0
    on_ground: bool = False

    def as_dict(self) -> dict:
        return {key: (value if isinstance(value, bool) else round(value, 6))
                for key, value in asdict(self).items()}


def _chosen(samples: list[Sample], interval_s: float) -> list[Sample]:
    """One sample per interval, plus the final one."""
    interval_s = max(0.05, interval_s)
    chosen: list[Sample] = []
    next_due = samples[0].t
    for sample in samples:
        if sample.t + 1e-9 >= next_due:
            chosen.append(sample)
            next_due = sample.t + interval_s
    if chosen[-1] is not samples[-1]:
        if samples[-1].t - chosen[-1].t < interval_s * 0.25 and len(chosen) > 1:
            chosen[-1] = samples[-1]
        else:
            chosen.append(samples[-1])
    return chosen


def to_keyframes(samples: list[Sample], interval_s: float = 1.0) -> list[FlightKeyframe]:
    """One keyframe per interval, plus the final sample.

    Attitude is pinned from the recording rather than derived, because a flown
    aircraft sideslips, crabs and carries angle of attack that the curve alone
    cannot reproduce. A keyframe is flagged on_ground when the aircraft was on
    its wheels for the whole leg it starts, so a touchdown leg stays airborne
    until the keyframe that actually lands.
    """
    if not samples:
        return []
    chosen = _chosen(samples, interval_s)
    start = chosen[0].t
    keyframes = []
    cursor = 0
    for index, sample in enumerate(chosen):
        leg_end = chosen[index + 1].t if index + 1 < len(chosen) else sample.t
        while cursor < len(samples) and samples[cursor].t < sample.t:
            cursor += 1
        scan = cursor
        on_ground = True
        while scan < len(samples) and samples[scan].t <= leg_end:
            on_ground = on_ground and samples[scan].on_ground
            scan += 1
        keyframes.append(FlightKeyframe(
            time_offset=round(sample.t - start, 3),
            time_source=TimeSource.IMPORTED,
            lat=sample.lat, lon=sample.lon, alt_ft_msl=sample.alt_ft_msl,
            heading=ManualAngle(deg=round(sample.heading_deg_true, 2)),
            pitch=ManualAngle(deg=round(sample.pitch_deg, 2)),
            bank=ManualAngle(deg=round(sample.bank_deg, 2)),
            on_ground=on_ground,
        ))
    return keyframes


def to_systems(samples: list[Sample], interval_s: float = 1.0) -> list[SystemsKeyframe]:
    """Flaps, gear, surfaces and thrust at the same instants as to_keyframes.

    Gear counts as down from the moment it starts extending, and up from the
    moment it starts retracting, because that is when the lever was moved and
    when playback must move it to look the same. The gear position is
    recorded in percent.
    """
    if not samples:
        return []
    down: dict[int, bool] = {}
    state, previous = samples[0].gear_pct >= 50.0, samples[0].gear_pct
    for i, sample in enumerate(samples):
        pct = sample.gear_pct
        if pct >= 99.0:
            state = True
        elif pct <= 1.0:
            state = False
        elif pct > previous + 1e-6:
            state = True
        elif pct < previous - 1e-6:
            state = False
        previous = pct
        down[id(sample)] = state
    chosen = _chosen(samples, interval_s)
    start = chosen[0].t
    clip = lambda v, low=-1.0: round(max(low, min(1.0, v)), 4)
    return [
        SystemsKeyframe(
            time_offset=round(sample.t - start, 3),
            flaps=max(0, int(round(sample.flaps))), gear_down=down[id(sample)],
            aileron=clip(sample.aileron), elevator=clip(sample.elevator),
            rudder=clip(sample.rudder), throttle=clip(sample.throttle, 0.0),
        )
        for sample in chosen
    ]


# -- recorded controls to a schedule ---------------------------------------

MIN_STEP_S = 0.2
# Throttle acts through engine spool-up and speed, so it tolerates more.
CHANNEL_TOLERANCE_SCALE = {"aileron": 1.0, "elevator": 1.0, "rudder": 1.5, "throttle": 3.0,
                           "elevator_trim": 1.0}


def _running_total(times: list[float], values: list[float]) -> list[float]:
    """Integral of a control held from each frame to the next, as it was sent."""
    total = [0.0]
    for i in range(1, len(times)):
        total.append(total[-1] + values[i - 1] * (times[i] - times[i - 1]))
    return total


def _total_at(times: list[float], total: list[float], t: float) -> float:
    if t <= times[0]:
        return 0.0
    if t >= times[-1]:
        return total[-1]
    lo, hi = 0, len(times) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if times[mid] <= t:
            lo = mid
        else:
            hi = mid
    span = times[hi] - times[lo]
    f = 0.0 if span < 1e-12 else (t - times[lo]) / span
    return total[lo] + (total[hi] - total[lo]) * f


def _simplify(times: list[float], values: list[float], tolerance: float) -> set[int]:
    """Ramer-Douglas-Peucker: indices whose straight joins stay within tolerance."""
    keep = {0, len(times) - 1}
    stack = [(0, len(times) - 1)]
    while stack:
        first, last = stack.pop()
        if last - first < 2:
            continue
        t0, v0, t1, v1 = times[first], values[first], times[last], values[last]
        worst, worst_error = None, tolerance
        for i in range(first + 1, last):
            line = v0 if t1 - t0 < 1e-9 else v0 + (v1 - v0) * (times[i] - t0) / (t1 - t0)
            error = abs(values[i] - line)
            if error > worst_error:
                worst, worst_error = i, error
        if worst is not None:
            keep.add(worst)
            stack.extend([(first, worst), (worst, last)])
    return keep


def commands_to_keyframes(commands: list[dict], tolerance: float = 0.01) -> list[ControlKeyframe]:
    """A step schedule whose controls add up over time to what was recorded.

    Matching the recorded values point by point is the wrong target. Bank is
    roughly the time-integral of aileron, so an aileron that is off by 0.005
    for a minute turns the aircraft somewhere else, while a brief spike that
    averages out does nothing. So each channel's running total is simplified
    instead, to within `tolerance` control-seconds, and each step holds the
    exact average between its breakpoints. Every channel is written at every
    breakpoint, so blank-cell rules cannot change what it means.
    """
    if len(commands) < 2:
        return []
    times = [c["t"] - commands[0]["t"] for c in commands]
    channels = [ch for ch in CHANNELS if ch in commands[0]]
    totals = {ch: _running_total(times, [c[ch] for c in commands]) for ch in channels}
    kept: set[int] = set()
    for channel in channels:
        kept |= _simplify(times, totals[channel], tolerance * CHANNEL_TOLERANCE_SCALE[channel])

    end = times[-1]
    breaks: list[float] = []
    for i in sorted(kept):
        t = round(times[i], 2)
        if t < end - MIN_STEP_S / 2 and (not breaks or t - breaks[-1] >= MIN_STEP_S):
            breaks.append(t)
    keyframes = []
    for t0, t1 in zip(breaks, breaks[1:] + [end]):
        values = {}
        for channel in channels:
            mean = (_total_at(times, totals[channel], t1)
                    - _total_at(times, totals[channel], t0)) / max(t1 - t0, 1e-9)
            low = 0.0 if channel == "throttle" else -1.0
            values[channel] = round(max(low, min(1.0, mean)), 4)
        keyframes.append(ControlKeyframe(time_offset=t0, transition="STEP", **values))
    return keyframes


def deviation(samples: list[Sample], reference) -> dict | None:
    """How far a recording strayed from a reference path (a guidance.ReferencePath)."""
    if not samples:
        return None
    hint = 0
    cross, alt = [], []
    for sample in samples:
        east, north = reference.local(sample.lat, sample.lon)
        fix = reference.fix(east, north, hint)
        hint = fix.index
        cross.append(fix.cross_track_m)
        alt.append(sample.alt_ft_msl - fix.point.alt_ft)
    end = reference.points[-1]
    east, north = reference.local(samples[-1].lat, samples[-1].lon)
    return {
        "rms_cross_track_m": round(math.sqrt(sum(c * c for c in cross) / len(cross)), 1),
        "max_cross_track_m": round(max(abs(c) for c in cross), 1),
        "rms_alt_error_ft": round(math.sqrt(sum(a * a for a in alt) / len(alt)), 1),
        "max_alt_error_ft": round(max(abs(a) for a in alt), 1),
        "end_miss_m": round(math.hypot(east - end.east, north - end.north), 1),
        "progress": round(min(1.0, reference.points[hint].s / max(reference.length_m, 1.0)), 3),
    }
