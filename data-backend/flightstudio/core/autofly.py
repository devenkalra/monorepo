"""Plan and judge an unattended fly-tune-fly run over a whole path.

The path is cut into overlapping segments. Each is flown, and if the take is
not good enough the pilot is tuned on that segment, every tuning flight being
a fresh take; the best take is kept. A segment that cannot be brought within
limits is split in two, since a shorter stretch drifts less, and when that
fails too its best take is kept and flagged. The takes are then joined.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Callable

from .joining import MIN_BLEND_S, SETTLE_S, Take, blend_window
from .units import ground_distance_m, heading_delta

SEGMENT_S = 120.0
# Long enough to fade between takes after the later one has settled.
OVERLAP_S = SETTLE_S + 3 * MIN_BLEND_S
MIN_SEGMENT_S = 60.0


@dataclass(frozen=True)
class Limits:
    """What counts as flown well enough, judged after the release settling."""

    rms_cross_track_m: float = 30.0
    max_cross_track_m: float = 90.0
    rms_alt_ft: float = 75.0
    max_alt_ft: float = 200.0
    rms_timing_s: float = 2.0
    progress: float = 0.98

    def misses(self, score: dict) -> list[str]:
        """The limits a run's score breaks, worded for a log; empty when accepted."""
        if score.get("failed"):
            return [f"failed: {score['failed']}"]
        out = []
        for name, limit in asdict(self).items():
            value = score.get(name)
            if value is None:
                continue
            if name == "progress" and value < limit:
                out.append(f"progress {value:.0%} < {limit:.0%}")
            elif name != "progress" and value > limit:
                out.append(f"{name} {value:.1f} > {limit:g}")
        return out

    def accepts(self, score: dict) -> bool:
        return not self.misses(score)


def plan_segments(start_s: float, end_s: float, length_s: float = SEGMENT_S,
                  overlap_s: float = OVERLAP_S) -> list[tuple[float, float]]:
    """Equal segments covering start..end, each overlapping the next by overlap_s."""
    if end_s - start_s <= length_s:
        return [(start_s, end_s)]
    if overlap_s >= length_s:
        raise ValueError("The overlap must be shorter than a segment")
    count = math.ceil((end_s - start_s - overlap_s) / (length_s - overlap_s))
    advance = (end_s - start_s - overlap_s) / count
    return [(round(start_s + i * advance, 1),
             round(end_s if i == count - 1 else start_s + i * advance + advance + overlap_s, 1))
            for i in range(count)]


def split_segment(segment: tuple[float, float], overlap_s: float = OVERLAP_S,
                  min_length_s: float = MIN_SEGMENT_S) -> list[tuple[float, float]] | None:
    """Two overlapping halves, or None when the halves would be too short."""
    t0, t1 = segment
    middle = (t0 + t1) / 2.0
    first = (t0, round(middle + overlap_s / 2.0, 1))
    second = (round(middle - overlap_s / 2.0, 1), t1)
    if first[1] - first[0] < min_length_s or first[1] >= t1:
        return None
    return [first, second]


@dataclass(frozen=True)
class SeamLimits:
    """How far two takes may disagree where the join fades from one to the other.

    The fade spreads the difference over its length, so a gap within these
    reads as a gentle drift rather than a bump.
    """

    alt_ft: float = 100.0
    # Mostly along the path: takes run up to a second or two apart. Faded over
    # 15 s, 100 m reads as about 13 kt of speed change.
    track_m: float = 100.0
    attitude_deg: float = 6.0

    def misses(self, gap: dict) -> list[str]:
        if gap.get("failed"):
            return [gap["failed"]]
        return [f"seam {name} {gap[name]:.1f} > {limit:g}"
                for name, limit in asdict(self).items() if gap[name] > limit]

    def cost(self, gap: dict) -> float:
        if gap.get("failed"):
            return UNJOINABLE
        return sum(gap[name] / limit for name, limit in asdict(self).items())


UNJOINABLE = 1e6


def seam_gap(earlier: Take, later: Take, step_s: float = 0.5) -> dict:
    """The largest disagreement between two takes across the fade that joins them."""
    try:
        start, end, _ = blend_window(earlier, later)
    except ValueError as error:
        return {"failed": str(error)}
    alt = track = attitude = 0.0
    count = max(1, int(round((end - start) / step_s)))
    for i in range(count + 1):
        t = start + (end - start) * i / count
        a, b = earlier.pose_at(t), later.pose_at(t)
        alt = max(alt, abs(a[2] - b[2]))
        track = max(track, ground_distance_m(a[0], a[1], b[0], b[1]))
        attitude = max(attitude, abs(a[3] - b[3]), abs(a[4] - b[4]), abs(heading_delta(a[5], b[5])))
    return {"from": round(start, 1), "to": round(end, 1), "alt_ft": round(alt, 1),
            "track_m": round(track, 1), "attitude_deg": round(attitude, 1)}


def choose_takes(costs: list[list[float]], seam_cost: Callable[[int, int, int], float]) -> list[int]:
    """Pick one candidate take per segment, minimising take costs plus seam costs.

    costs[i][k] is candidate k of segment i; seam_cost(i, j, k) joins candidate
    j of segment i to candidate k of segment i + 1. Dynamic programming over the
    chain, so every combination is considered without trying them all.
    """
    if not costs or any(not c for c in costs):
        raise ValueError("Every segment needs at least one take")
    totals = [list(costs[0])]
    back: list[list[int]] = [[]]
    for i in range(1, len(costs)):
        row, links = [], []
        for k, cost in enumerate(costs[i]):
            j = min(range(len(costs[i - 1])), key=lambda j: totals[-1][j] + seam_cost(i - 1, j, k))
            row.append(totals[-1][j] + seam_cost(i - 1, j, k) + cost)
            links.append(j)
        totals.append(row)
        back.append(links)
    k = min(range(len(totals[-1])), key=lambda k: totals[-1][k])
    chosen = [k]
    for i in range(len(costs) - 1, 0, -1):
        k = back[i][k]
        chosen.append(k)
    return chosen[::-1]


def flight_minutes(segments: list[tuple[float, float]], flights_each: int,
                   setup_s: float = 30.0) -> float:
    """The worst case: every segment uses its whole flight budget."""
    return sum(t1 - t0 + setup_s for t0, t1 in segments) * flights_each / 60.0
