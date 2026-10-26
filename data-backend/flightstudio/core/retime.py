"""Retime flight keyframes so the speed between them changes smoothly.

A segment's speed is its length over its time, so keyframes whose times were
rounded, or logged at uneven intervals, make the aircraft surge and brake at
every knot even when the track itself is smooth. Bank follows speed squared,
so it surges too. This keeps every position and the first and last times, and
moves only the times in between.
"""

from __future__ import annotations

import math

from .flight_path import SolvedFlightPath
from .schema import FlightKeyframe

# Below this a segment is a deliberate stop, and keeps its own timing.
STATIONARY_M = 1.0
MIN_SEGMENT_S = 0.05
ARC_SAMPLES = 40
PASSES = 3


def segment_lengths(path: SolvedFlightPath) -> list[float]:
    """Distance flown along the curve between each pair of keyframes."""
    lengths = []
    for a, b in zip(path.keyframes, path.keyframes[1:]):
        start = a.time_offset + a.easing.hold_s
        span = b.time_offset - start
        previous = path.curve.point_at(start)
        length = 0.0
        for i in range(1, ARC_SAMPLES + 1):
            point = path.curve.point_at(start + span * i / ARC_SAMPLES)
            length += math.dist(previous, point)
            previous = point
        lengths.append(length)
    return lengths


def smooth_timing(keyframes: list[FlightKeyframe], window_s: float = 10.0) -> list[FlightKeyframe]:
    """Keyframes with their times moved so speed varies over about `window_s`.

    Speed is averaged as distance over time across neighbouring segments,
    weighted by how close in time they are, so a long fast segment counts for
    more than a short slow one, and real speed-ups wider than the window stay.
    """
    if len(keyframes) < 3:
        return list(keyframes)
    path = SolvedFlightPath(keyframes)
    frames = path.keyframes
    lengths = segment_lengths(path)
    holds = [frame.easing.hold_s for frame in frames]
    spans = [b.time_offset - (a.time_offset + a.easing.hold_s) for a, b in zip(frames, frames[1:])]
    moving = [length >= STATIONARY_M and span > 0 for length, span in zip(lengths, spans)]
    budget = sum(span for span, moves in zip(spans, moving) if moves)
    if budget <= 0:
        return list(frames)
    sigma = max(window_s, 0.1) / 2.0
    original = list(spans)

    # Each pass averages the original speeds, but centred where the previous
    # pass moved each segment to.
    for _ in range(PASSES):
        middles, clock = [], frames[0].time_offset
        for hold, span in zip(holds, spans):
            clock += hold
            middles.append(clock + span / 2.0)
            clock += span
        new_spans = list(spans)
        for i, moves in enumerate(moving):
            if not moves:
                continue
            distance = time = 0.0
            for j, other in enumerate(moving):
                if not other:
                    continue
                weight = math.exp(-0.5 * ((middles[j] - middles[i]) / sigma) ** 2)
                distance += weight * lengths[j]
                time += weight * original[j]
            new_spans[i] = lengths[i] / (distance / time)
        scale = budget / sum(span for span, moves in zip(new_spans, moving) if moves)
        spans = [max(MIN_SEGMENT_S, span * scale) if moves else span
                 for span, moves in zip(new_spans, moving)]

    retimed, clock = [frames[0]], frames[0].time_offset
    for frame, hold, span in zip(frames[1:], holds, spans):
        clock += hold + span
        retimed.append(frame.model_copy(update={"time_offset": round(clock, 3)}))
    # Rounding and the minimum span can drift the end; the shot keeps its length.
    retimed[-1] = retimed[-1].model_copy(update={"time_offset": frames[-1].time_offset})
    return retimed


def worst_speed_jump(keyframes: list[FlightKeyframe]) -> float:
    """Largest ratio between neighbouring moving segments' speeds."""
    if len(keyframes) < 3:
        return 1.0
    path = SolvedFlightPath(keyframes)
    frames = path.keyframes
    speeds = []
    for length, a, b in zip(segment_lengths(path), frames, frames[1:]):
        span = b.time_offset - (a.time_offset + a.easing.hold_s)
        speeds.append(length / span if length >= STATIONARY_M and span > 0 else None)
    worst = 1.0
    for a, b in zip(speeds, speeds[1:]):
        if a and b:
            worst = max(worst, max(a, b) / min(a, b))
    return worst
