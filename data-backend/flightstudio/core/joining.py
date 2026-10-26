"""Join flown segment takes back into one continuous flight.

Each take was released at its segment's start on the source path's timeline
and recorded from 0, so a take's time t is the source's start + t. Where two
takes overlap, the joined flight fades from the earlier to the later one. The
fade waits until the later take has settled after its release, if the overlap
is long enough; otherwise it uses the end of the overlap and says so.
"""

from __future__ import annotations

import math
import re
from bisect import bisect_right
from dataclasses import dataclass, field

from .schema import FlightKeyframe, ManualAngle, PathDocument, SystemsKeyframe, TimeSource
from .units import heading_delta, normalise_heading

SETTLE_S = 15.0
MIN_BLEND_S = 5.0
STEP_S = 0.5
_RANGE_IN_NAME = re.compile(r"-(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)$")


SURFACES = ("aileron", "elevator", "rudder", "throttle")


@dataclass
class Take:
    name: str
    start_s: float
    times: list[float]
    poses: list[tuple[float, float, float, float, float, float]]  # lat, lon, alt, pitch, bank, heading
    systems: list[SystemsKeyframe] = field(default_factory=list)

    @property
    def end_s(self) -> float:
        return self.start_s + self.times[-1]

    def systems_at(self, t: float) -> dict | None:
        """Flaps and gear as last set by t; surfaces and thrust interpolated."""
        if not self.systems:
            return None
        local = t - self.start_s
        times = [k.time_offset for k in self.systems]
        i = max(1, min(len(times) - 1, bisect_right(times, local)))
        a, b = self.systems[i - 1], self.systems[i]
        f = 0.0 if b.time_offset <= a.time_offset else min(1.0, max(0.0, (local - a.time_offset)
                                                                    / (b.time_offset - a.time_offset)))
        held = b if local >= b.time_offset else a
        out = {"flaps": held.flaps, "gear_down": held.gear_down}
        for name in SURFACES:
            x, y = getattr(a, name), getattr(b, name)
            out[name] = None if x is None or y is None else x + (y - x) * f
        return out

    def pose_at(self, t: float) -> tuple[float, ...]:
        """Pose at source time t, interpolated between recorded keyframes."""
        local = min(max(t - self.start_s, self.times[0]), self.times[-1])
        i = max(1, min(len(self.times) - 1, bisect_right(self.times, local)))
        t0, t1 = self.times[i - 1], self.times[i]
        f = 0.0 if t1 <= t0 else (local - t0) / (t1 - t0)
        return _mix(self.poses[i - 1], self.poses[i], f)


def _mix(a: tuple[float, ...], b: tuple[float, ...], f: float) -> tuple[float, ...]:
    lat, lon, alt, pitch, bank = (x + (y - x) * f for x, y in zip(a[:5], b[:5]))
    heading = normalise_heading(a[5] + heading_delta(a[5], b[5]) * f)
    return lat, lon, alt, pitch, bank, heading


def _angle(angle, fallback: float = 0.0) -> float:
    return angle.deg if isinstance(angle, ManualAngle) else fallback


def take_from(document: PathDocument, start_s: float | None = None) -> Take:
    """A saved take, placed on its source's timeline.

    Its start comes from the path's flown_from_s, else from a "-FROM-TO" name.
    """
    name = document.meta.path_id
    if start_s is None:
        start_s = document.meta.flown_from_s
    if start_s is None:
        match = _RANGE_IN_NAME.search(name)
        if not match:
            raise ValueError(f"{name}: no segment start recorded; give it as {name}@SECONDS")
        start_s = float(match.group(1))
    frames = document.flight_keyframes
    if len(frames) < 2:
        raise ValueError(f"{name}: a take needs at least two waypoints")
    return Take(name=name, start_s=start_s, times=[k.time_offset for k in frames],
                poses=[(k.lat, k.lon, k.alt_ft_msl, _angle(k.pitch), _angle(k.bank),
                        _angle(k.heading)) for k in frames],
                systems=list(document.systems))


@dataclass
class Joined:
    keyframes: list[FlightKeyframe]
    start_s: float
    blends: list[tuple[str, str, float, float]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    systems: list[SystemsKeyframe] = field(default_factory=list)


def joined_document(joined: Joined, path_id: str, source: PathDocument) -> PathDocument:
    """The joined flight as a path, with the source's setup and its cameras over the same stretch."""
    duration = joined.keyframes[-1].time_offset
    cameras = [k.model_copy(update={"time_offset": round(k.time_offset - joined.start_s, 3)})
               for k in source.camera_keyframes
               if joined.start_s <= k.time_offset <= joined.start_s + duration]
    if not cameras and source.camera_keyframes:
        cameras = [source.camera_keyframes[0].model_copy(update={"time_offset": 0.0})]
    meta = source.meta.model_copy(update={
        "path_id": path_id, "duration_seconds": duration,
        "flown_from": source.meta.path_id, "flown_from_s": joined.start_s,
    })
    return PathDocument(meta=meta, flight_keyframes=joined.keyframes,
                        camera_keyframes=cameras, sim_flight=None, systems=joined.systems)


def blend_window(earlier: Take, later: Take, settle_s: float = SETTLE_S,
                 min_blend_s: float = MIN_BLEND_S) -> tuple[float, float, str | None]:
    overlap_start, overlap_end = later.start_s, earlier.end_s
    if overlap_end <= overlap_start:
        raise ValueError(f"{earlier.name} ends at {earlier.end_s:.1f} s but {later.name} starts "
                         f"at {later.start_s:.1f} s: takes must overlap to be joined")
    start = max(overlap_start, later.start_s + settle_s)
    if overlap_end - start >= min_blend_s:
        return start, overlap_end, None
    start = max(overlap_start, overlap_end - min_blend_s)
    return start, overlap_end, (
        f"{earlier.name} and {later.name} overlap {overlap_end - overlap_start:.0f} s, not enough "
        f"to wait out {later.name}'s {settle_s:.0f} s of release settling: the fade from "
        f"{start:.1f} to {overlap_end:.1f} s uses some of it. Overlap by {settle_s + min_blend_s:.0f} s "
        "or more for a clean join.")


def join_takes(takes: list[Take], step_s: float = STEP_S, settle_s: float = SETTLE_S,
               min_blend_s: float = MIN_BLEND_S) -> Joined:
    takes = sorted(takes, key=lambda take: take.start_s)
    if not takes:
        raise ValueError("Nothing to join")
    windows = []
    warnings = []
    for earlier, later in zip(takes, takes[1:]):
        if later.end_s <= earlier.end_s:
            raise ValueError(f"{later.name} lies inside {earlier.name}; nothing to add")
        start, end, warning = blend_window(earlier, later, settle_s, min_blend_s)
        windows.append((start, end))
        if warning:
            warnings.append(warning)

    def fades(t: float):
        for (start, end), later in zip(windows, takes[1:]):
            if t <= start:
                break
            f = 1.0 if t >= end else (t - start) / (end - start)
            # Smoothstep: no kink in speed where the fade begins and ends.
            yield later, f * f * (3.0 - 2.0 * f)

    def pose(t: float) -> tuple[float, ...]:
        current = takes[0].pose_at(t)
        for later, f in fades(t):
            current = _mix(current, later.pose_at(t), f)
        return current

    def systems(t: float) -> dict:
        """Surfaces fade like the pose; flaps and gear switch halfway through a fade."""
        current = takes[0].systems_at(t)
        for later, f in fades(t):
            other = later.systems_at(t)
            mixed = {k: (other if f >= 0.5 else current)[k] for k in ("flaps", "gear_down")}
            for name in SURFACES:
                x, y = current[name], other[name]
                mixed[name] = y if x is None else x if y is None else x + (y - x) * f
            current = mixed
        return current

    first, last = takes[0].start_s, takes[-1].end_s
    count = int(math.floor((last - first) / step_s))
    times = [first + i * step_s for i in range(count + 1)]
    if last - times[-1] > 1e-6:
        times.append(last)
    keyframes = []
    for t in times:
        lat, lon, alt, pitch, bank, heading = pose(t)
        keyframes.append(FlightKeyframe(
            time_offset=round(t - first, 3), time_source=TimeSource.IMPORTED,
            lat=lat, lon=lon, alt_ft_msl=round(alt, 1),
            pitch=ManualAngle(deg=round(pitch, 2)), bank=ManualAngle(deg=round(bank, 2)),
            heading=ManualAngle(deg=round(heading, 2)),
        ))
    blends = [(a.name, b.name, s, e) for (s, e), a, b in zip(windows, takes, takes[1:])]
    joined_systems = []
    if all(take.systems for take in takes):
        for t in times:
            values = systems(t)
            joined_systems.append(SystemsKeyframe(
                time_offset=round(t - first, 3), flaps=values["flaps"],
                gear_down=values["gear_down"],
                **{name: None if values[name] is None else round(values[name], 4)
                   for name in SURFACES}))
    elif any(take.systems for take in takes):
        warnings.append("Some takes have no flaps and gear recorded, so the joined path has none.")
    return Joined(keyframes=keyframes, start_s=first, blends=blends, warnings=warnings,
                  systems=joined_systems)
