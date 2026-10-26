"""Approximating flight keys from a cleaned GPS track.

Catmull-Rom interpolates every keyframe. A dense ADS-B or flown recording
then forces the aircraft through measurement jitter. This fits a Whittaker
smoother that is allowed to miss the samples, places fewer knots on that
curve, and times them from ADS-B ground speed so the tape matches the report.
"""

from __future__ import annotations

import math
import numpy as np

from .schema import FlightKeyframe, StraightLeg, SystemsKeyframe, TimeSource
from .track_clean import GAP_S, CleanedTrack, TrackPoint
from .units import (
    KNOTS_PER_MS, feet_to_metres, interpolate_heading, local_offset,
    metres_to_feet, offset_latlon,
)

# Horizontal residual the plan is allowed. 15 m still follows ADS-B lateral
# snakes; AUTO bank is atan(omega v / g), so those show as wing rock. 40 m
# is typical ADS-B noise and leaves only the real turns.
HORIZONTAL_RMS_M = 40.0
VERTICAL_RMS_M = 10.0
# How far along the fit before we drop another knot. Time fills long ADS-B gaps
# so Catmull does not stretch a 20–30 s chord.
SAMPLE_M = 250.0
SAMPLE_S = 5.0
GAP_FILL_S = 2.0
PIN = 1.0e8
FILL_WEIGHT = 0.05
# Last-roll ADS-B can read near zero; a floor keeps dt finite.
MIN_SPEED_KT = 20.0
# ADS-B has no gear lever. Extend this high above the field so playback
# sends GEAR_UP at cruise (otherwise the sim keeps the last landing's gear).
GEAR_EXTEND_AGL_FT = 2000.0


def _second_diff(n: int) -> np.ndarray:
    matrix = np.zeros((n - 2, n))
    for i in range(n - 2):
        matrix[i, i] = 1.0
        matrix[i, i + 1] = -2.0
        matrix[i, i + 2] = 1.0
    return matrix


def _whittaker(values: np.ndarray, lam: float, weights: np.ndarray) -> np.ndarray:
    n = len(values)
    if n < 3:
        return values.copy()
    pinned = weights.copy()
    pinned[0] = pinned[-1] = PIN
    penalty = _second_diff(n)
    system = np.diag(pinned) + lam * (penalty.T @ penalty)
    return np.linalg.solve(system, pinned * values)


def _measured_rms(fit: np.ndarray, values: np.ndarray, measured: np.ndarray) -> float:
    error = (fit - values)[measured]
    if error.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(error ** 2)))


def _lambda_for_rms(values: np.ndarray, target_rms: float, weights: np.ndarray,
                    measured: np.ndarray) -> float:
    """Largest smoothing that stays near `target_rms` on the measured samples."""
    if int(np.count_nonzero(measured)) < 3 or float(np.std(values[measured])) < 1e-9:
        return 1.0
    lo, hi, chosen = 1e-3, 1e8, 1.0
    for _ in range(28):
        mid = math.sqrt(lo * hi)
        residual = _measured_rms(_whittaker(values, mid, weights), values, measured)
        chosen = mid
        if residual < target_rms:
            lo = mid
        else:
            hi = mid
    return chosen


def _lambda_horizontal(north: np.ndarray, east: np.ndarray, weights: np.ndarray,
                       measured: np.ndarray, target_rms: float) -> float:
    if int(np.count_nonzero(measured)) < 3:
        return 1.0
    lo, hi, chosen = 1e-3, 1e8, 1.0
    for _ in range(28):
        mid = math.sqrt(lo * hi)
        dn = _whittaker(north, mid, weights) - north
        de = _whittaker(east, mid, weights) - east
        residual = _measured_rms(np.hypot(dn, de), np.zeros_like(dn), measured)
        chosen = mid
        if residual < target_rms:
            lo = mid
        else:
            hi = mid
    return chosen


def fill_gaps(points: list[TrackPoint]) -> list[TrackPoint]:
    """Even samples across ADS-B holes so the smoother sees time, not index."""
    if len(points) < 2:
        return list(points)
    origin = points[0]
    filled = [points[0]]
    for previous, point in zip(points, points[1:]):
        dt = point.t - previous.t
        if dt > GAP_S:
            steps = max(2, int(round(dt / GAP_FILL_S)))
            n0, e0 = local_offset(origin.lat, origin.lon, previous.lat, previous.lon)
            n1, e1 = local_offset(origin.lat, origin.lon, point.lat, point.lon)
            for step in range(1, steps):
                fraction = step / steps
                lat, lon = offset_latlon(
                    origin.lat, origin.lon,
                    n0 + (n1 - n0) * fraction,
                    e0 + (e1 - e0) * fraction,
                )
                filled.append(TrackPoint(
                    t=previous.t + dt * fraction,
                    lat=lat,
                    lon=lon,
                    alt_ft=previous.alt_ft + (point.alt_ft - previous.alt_ft) * fraction,
                    speed_kt=previous.speed_kt + (point.speed_kt - previous.speed_kt) * fraction,
                    track_deg=interpolate_heading(previous.track_deg, point.track_deg, fraction),
                    on_ground=previous.on_ground and point.on_ground,
                    notes=["gap-fill"],
                ))
        filled.append(point)
    return filled


def _enu(points: list[TrackPoint]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    origin = points[0]
    north, east, up = [], [], []
    for point in points:
        n, e = local_offset(origin.lat, origin.lon, point.lat, point.lon)
        north.append(n)
        east.append(e)
        up.append(feet_to_metres(point.alt_ft))
    return np.asarray(north), np.asarray(east), np.asarray(up)


def smooth_enu(points: list[TrackPoint]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pinned-end Whittaker fit of the cleaned samples, in local metres."""
    north, east, up = _enu(points)
    measured = np.array(["gap-fill" not in p.notes for p in points])
    weights = np.where(measured, 1.0, FILL_WEIGHT)
    lam_xy = _lambda_horizontal(north, east, weights, measured, HORIZONTAL_RMS_M)
    return (
        _whittaker(north, lam_xy, weights),
        _whittaker(east, lam_xy, weights),
        _whittaker(up, _lambda_for_rms(up, VERTICAL_RMS_M, weights, measured), weights),
    )


def _sample_indices(times: np.ndarray, north: np.ndarray, east: np.ndarray,
                    up: np.ndarray) -> list[int]:
    keep = [0]
    travelled = 0.0
    elapsed = 0.0
    for i in range(1, len(times)):
        step = math.dist(
            (north[i], east[i], up[i]),
            (north[i - 1], east[i - 1], up[i - 1]),
        )
        travelled += step
        elapsed += times[i] - times[i - 1]
        if travelled >= SAMPLE_M or elapsed >= SAMPLE_S or i == len(times) - 1:
            if keep[-1] != i:
                keep.append(i)
            travelled = 0.0
            elapsed = 0.0
    if keep[-1] != len(times) - 1:
        keep.append(len(times) - 1)
    return keep


def _speed_ms(knots: float) -> float:
    return max(knots, MIN_SPEED_KT) / KNOTS_PER_MS


def times_from_adsb_speed(indices: list[int], north: np.ndarray, east: np.ndarray,
                          up: np.ndarray, points: list[TrackPoint]) -> list[float]:
    """Clock so each span's mean speed is the reported ADS-B speed along it.

    Positions stay on the fit. Time is rebuilt: dt = ds / v_reported, using
    the cleaned (and gap-filled) speed at each dense sample.
    """
    clock = [0.0]
    for start, end in zip(indices, indices[1:]):
        dt = 0.0
        for i in range(start, end):
            step = math.dist(
                (north[i], east[i], up[i]),
                (north[i + 1], east[i + 1], up[i + 1]),
            )
            speed = 0.5 * (_speed_ms(points[i].speed_kt) + _speed_ms(points[i + 1].speed_kt))
            dt += step / speed
        clock.append(clock[-1] + dt)
    return clock


def approximating_keyframes(track: CleanedTrack) -> list[FlightKeyframe]:
    """Keyframes on a smooth fit of `track`, not on the raw GPS hits."""
    if len(track.points) < 2:
        raise ValueError("an approximating path needs at least two cleaned points")
    points = fill_gaps(track.points)
    north, east, up = smooth_enu(points)
    sample_times = np.asarray([p.t for p in points])
    origin = points[0]
    last = len(points) - 1
    indices = _sample_indices(sample_times, north, east, up)
    clocks = times_from_adsb_speed(indices, north, east, up, points)
    keys = []
    for slot, i in enumerate(indices):
        lat, lon = offset_latlon(origin.lat, origin.lon, float(north[i]), float(east[i]))
        point = points[i]
        imported = i in (0, last) and "gap-fill" not in point.notes
        keys.append(FlightKeyframe(
            time_offset=round(clocks[slot], 3),
            time_source=TimeSource.IMPORTED if imported else TimeSource.INTERPOLATED,
            lat=round(lat, 7),
            lon=round(lon, 7),
            alt_ft_msl=round(metres_to_feet(float(up[i])), 1),
            path=StraightLeg(),
            on_ground=point.on_ground,
        ))
    return keys


def approximating_systems(keys: list[FlightKeyframe]) -> list[SystemsKeyframe]:
    """Gear and flaps the GPS never recorded, so playback can raise the gear.

    Without a systems track the sim keeps whatever the last take left — usually
    down, after a landing. Up from the start until the path is about 2000 ft
    above the field (or the first on-ground key), then down.
    """
    if not keys:
        return []
    if keys[0].on_ground:
        return [SystemsKeyframe(time_offset=keys[0].time_offset, flaps=0, gear_down=True)]
    field = next((k.alt_ft_msl for k in keys if k.on_ground), None)
    t_down = None
    for key in keys:
        if key.on_ground:
            t_down = key.time_offset
            break
        if field is not None and key.alt_ft_msl <= field + GEAR_EXTEND_AGL_FT:
            t_down = key.time_offset
            break
    start = keys[0].time_offset
    systems = [SystemsKeyframe(time_offset=start, flaps=0, gear_down=False)]
    if t_down is not None and t_down > start:
        systems.append(SystemsKeyframe(time_offset=t_down, flaps=2, gear_down=True))
    return systems
