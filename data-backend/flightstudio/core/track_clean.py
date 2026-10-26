"""Clean a recorded flight track before it becomes a path.

Flightradar24 and similar ADS-B exports carry position, barometric altitude,
ground speed and ground track, with times rounded to whole seconds. Each
field has its own faults: spikes from a bad sample, 25 ft altitude steps,
altitude relative to 1013 hPa rather than sea level, and timestamps whose
rounding alone makes a 2 s leg look 25% fast or slow. Positions and speeds
are redundant (distance over speed is time), so each can check the others.
"""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass, field, replace
from datetime import datetime

import numpy as np

from .schema import FlightKeyframe, TimeSource
from .units import KNOTS_PER_MS, bearing_deg, ground_distance_m, heading_delta, normalise_heading

ALT_SPIKE_FT = 200.0
SPEED_SPIKE_KT = 15.0
TRACK_SPIKE_DEG = 25.0
# A leg whose direction disagrees with the tracks at both its ends by more
# than this, in opposite senses either side of a point, puts the point off the line.
POSITION_BEARING_DEG = 20.0
# Below this the track and the speed are taxi noise, too poor to check against.
MIN_CHECK_KT = 50.0
# Whole-second rounding moves a time by up to 0.5 s; past this the timestamp
# or the position is wrong, not rounded.
TIME_RESIDUAL_S = 1.5
TIME_ROUNDING_S = 0.35
POSITION_NOISE_M = 15.0
SPEED_NOISE = 0.01
GAP_S = 6.0
# ADS-B stops reporting airborne a little above the runway.
FLARE_FT = 20.0
MIN_ALT_OFFSET_FT = 50.0

COLUMN_ALIASES = {
    "time": ("time", "t", "seconds", "timestamp", "utc"),
    "lat": ("lat", "latitude"),
    "lon": ("lon", "long", "lng", "longitude"),
    "alt": ("altitude_ft", "altitude", "alt", "alt_ft"),
    "speed": ("speed_kt", "speed", "gs", "ground_speed", "groundspeed"),
    "track": ("heading_deg", "heading", "track", "track_deg", "direction"),
}


@dataclass
class TrackPoint:
    t: float
    lat: float
    lon: float
    alt_ft: float
    speed_kt: float
    track_deg: float
    on_ground: bool = False
    row: int = 0
    original_t: float = 0.0
    original_alt_ft: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass
class Issue:
    t: float
    kind: str
    detail: str
    action: str


@dataclass
class CleanedTrack:
    points: list[TrackPoint]
    issues: list[Issue]
    alt_offset_ft: float = 0.0
    worst_speed_mismatch_before_kt: float = 0.0
    worst_speed_mismatch_after_kt: float = 0.0

    def report(self) -> str:
        lines = [f"{len(self.points)} points kept, {self.points[0].t:.1f} to {self.points[-1].t:.1f} s."]
        if self.alt_offset_ft:
            lines.append(f"Altitudes raised {self.alt_offset_ft:+.0f} ft from pressure altitude to MSL.")
        lines.append(f"Worst gap between leg speed from positions and reported speed: "
                     f"{self.worst_speed_mismatch_before_kt:.0f} kt with the recorded times, "
                     f"{self.worst_speed_mismatch_after_kt:.0f} kt after retiming.")
        for issue in self.issues:
            lines.append(f"  t={issue.t:6.1f}  {issue.kind:10s} {issue.action:9s} {issue.detail}")
        return "\n".join(lines)


def _column(header: list[str], name: str) -> int:
    # A byte-order mark, read as UTF-8 or as cp1252.
    lowered = [h.strip().removeprefix("\ufeff").removeprefix("ï»¿").lower() for h in header]
    for alias in COLUMN_ALIASES[name]:
        if alias in lowered:
            return lowered.index(alias)
    raise ValueError(f"No {name} column; expected one of {', '.join(COLUMN_ALIASES[name])}.")


def _seconds(text: str) -> float:
    text = text.strip()
    try:
        return float(text)
    except ValueError:
        pass
    if text.count(":") == 2 and "T" not in text and "-" not in text:
        h, m, s = text.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


def _header_names(header: list[str]) -> list[str]:
    return [h.strip().removeprefix("\ufeff").removeprefix("ï»¿").lower() for h in header]


def _position_index(header: list[str]) -> int | None:
    lowered = _header_names(header)
    if "position" in lowered:
        return lowered.index("position")
    return None


def read_track_csv(text: str) -> list[TrackPoint]:
    rows = [row for row in csv.reader(io.StringIO(text)) if row and any(c.strip() for c in row)]
    if len(rows) < 3:
        raise ValueError("A track needs a header and at least two points.")
    header, body = rows[0], rows[1:]
    try:
        columns = {name: _column(header, name) for name in COLUMN_ALIASES}
        position = None
    except ValueError:
        position = _position_index(header)
        if position is None:
            raise
        columns = {name: _column(header, name) for name in COLUMN_ALIASES
                   if name not in ("lat", "lon")}
    points = []
    for number, row in enumerate(body, start=2):
        try:
            values = {name: row[index] for name, index in columns.items()}
            if position is not None:
                lat_s, lon_s = row[position].split(",")
                values["lat"], values["lon"] = lat_s.strip(), lon_s.strip()
            alt = values["alt"].strip().lower()
            points.append(TrackPoint(
                t=_seconds(values["time"]), lat=float(values["lat"]), lon=float(values["lon"]),
                alt_ft=0.0 if alt in ("", "ground", "gnd") else float(alt),
                speed_kt=float(values["speed"]), track_deg=float(values["track"]) % 360.0,
                row=number,
            ))
        except (ValueError, IndexError) as exc:
            raise ValueError(f"Row {number}: {exc}") from exc
    start = points[0].t
    for point in points:
        point.t -= start
        point.original_t = point.t
        point.original_alt_ft = point.alt_ft
    return points


def _between(a: float, b: float, fraction: float) -> float:
    return a + (b - a) * fraction


def _fix_field(points: list[TrackPoint], name: str, attr: str, unit: str, limit: float,
               checkable, angle: bool = False) -> list[Issue]:
    """Replace values that disagree with their neighbours' trend.

    A spike also pulls its neighbours' trends towards it, so they can look
    half as wrong; only the worst of a run of suspects is a spike.
    """
    def expected(i: int, values: list[float]) -> float:
        prev, point, nxt = points[i - 1], points[i], points[i + 1]
        fraction = (point.t - prev.t) / (nxt.t - prev.t)
        if angle:
            return normalise_heading(values[i - 1] + heading_delta(values[i - 1], values[i + 1]) * fraction)
        return _between(values[i - 1], values[i + 1], fraction)

    def error(i: int, values: list[float]) -> float:
        if not checkable(points[i - 1], points[i], points[i + 1]):
            return 0.0
        e = expected(i, values)
        return abs(heading_delta(e, values[i])) if angle else abs(values[i] - e)

    values = [getattr(p, attr) for p in points]
    errors = [0.0] + [error(i, values) for i in range(1, len(points) - 1)] + [0.0]
    issues = []
    for i in range(1, len(points) - 1):
        if errors[i] <= limit or errors[i] < errors[i - 1] or errors[i] < errors[i + 1]:
            continue
        replacement = expected(i, values)
        point = points[i]
        issues.append(Issue(point.t, name, f"{values[i]:.0f} {unit} against {replacement:.0f} "
                            f"{unit} from its neighbours", "replaced"))
        setattr(point, attr, replacement)
        point.notes.append(f"{name} spike")
    return issues


def _fix_spikes(points: list[TrackPoint], issues: list[Issue]) -> None:
    def airborne(*ps: TrackPoint) -> bool:
        return not any(p.on_ground for p in ps)

    def fast(*ps: TrackPoint) -> bool:
        return min(ps[0].speed_kt, ps[2].speed_kt) > MIN_CHECK_KT

    issues += _fix_field(points, "altitude", "alt_ft", "ft", ALT_SPIKE_FT, airborne)
    issues += _fix_field(points, "speed", "speed_kt", "kt", SPEED_SPIKE_KT, fast)
    issues += _fix_field(points, "track", "track_deg", "deg", TRACK_SPIKE_DEG,
                         lambda *ps: airborne(*ps) and fast(*ps), angle=True)


def _leg_bearing_error(a: TrackPoint, b: TrackPoint) -> float:
    mean_track = normalise_heading(a.track_deg + heading_delta(a.track_deg, b.track_deg) / 2.0)
    return heading_delta(mean_track, bearing_deg(a.lat, a.lon, b.lat, b.lon))


def _drop_off_line(points: list[TrackPoint], issues: list[Issue]) -> list[TrackPoint]:
    """Drop points that sit to one side of the line their tracks describe."""
    kept = [points[0]]
    for i in range(1, len(points) - 1):
        prev, point, nxt = kept[-1], points[i], points[i + 1]
        if min(prev.speed_kt, point.speed_kt, nxt.speed_kt) > MIN_CHECK_KT:
            inbound, outbound = _leg_bearing_error(prev, point), _leg_bearing_error(point, nxt)
            if (abs(inbound) > POSITION_BEARING_DEG and abs(outbound) > POSITION_BEARING_DEG
                    and inbound * outbound < 0):
                offset = ground_distance_m(prev.lat, prev.lon, point.lat, point.lon) * math.sin(
                    math.radians(abs(inbound)))
                issues.append(Issue(point.t, "position", f"about {offset:.0f} m off the line its "
                                    f"tracks describe ({inbound:+.0f} then {outbound:+.0f} deg)",
                                    "dropped"))
                continue
        kept.append(point)
    kept.append(points[-1])
    return kept


def _leg(a: TrackPoint, b: TrackPoint) -> tuple[float, float]:
    """Distance along a constant-rate turn between two points, and mean speed in m/s."""
    chord = ground_distance_m(a.lat, a.lon, b.lat, b.lon)
    speed = (a.speed_kt + b.speed_kt) / 2.0 / KNOTS_PER_MS
    turn = math.radians(abs(heading_delta(a.track_deg, b.track_deg)))
    if speed * KNOTS_PER_MS > MIN_CHECK_KT and turn > 1e-6:
        chord *= (turn / 2.0) / math.sin(turn / 2.0)
    return chord, speed


def _worst_mismatch(points: list[TrackPoint]) -> float:
    worst = 0.0
    for a, b in zip(points, points[1:]):
        distance, speed = _leg(a, b)
        if speed * KNOTS_PER_MS > MIN_CHECK_KT and b.t > a.t:
            worst = max(worst, abs(distance / (b.t - a.t) - speed) * KNOTS_PER_MS)
    return worst


def _retime(points: list[TrackPoint], issues: list[Issue]) -> None:
    """Times that best agree with both the timestamps and distance over speed.

    Least squares: each time stays within its rounding of the timestamp, and
    each leg takes about its distance over its mean speed. Slow legs say
    little about time, so they weigh little.
    """
    n = len(points)
    stamps = np.array([p.t for p in points])
    matrix = np.eye(n) / TIME_ROUNDING_S ** 2
    rhs = stamps / TIME_ROUNDING_S ** 2
    for i, (a, b) in enumerate(zip(points, points[1:])):
        distance, speed = _leg(a, b)
        speed = max(speed, 0.5)
        expected = distance / speed
        sigma = SPEED_NOISE * expected + POSITION_NOISE_M / speed
        if b.t - a.t > GAP_S:
            sigma += SPEED_NOISE * expected
        weight = 1.0 / sigma ** 2
        matrix[i, i] += weight
        matrix[i + 1, i + 1] += weight
        matrix[i, i + 1] -= weight
        matrix[i + 1, i] -= weight
        rhs[i] -= weight * expected
        rhs[i + 1] += weight * expected
    fitted = np.linalg.solve(matrix, rhs)
    fitted = np.maximum.accumulate(fitted)
    fitted -= fitted[0]
    for point, t in zip(points, fitted):
        residual = t - point.original_t
        if abs(residual) > TIME_RESIDUAL_S and point.speed_kt > MIN_CHECK_KT:
            issues.append(Issue(point.original_t, "time", f"timestamp disagrees with distance "
                                f"over speed by {residual:+.1f} s; position or time is off",
                                "retimed"))
            point.notes.append("time mismatch")
        point.t = float(t)
    for a, b in zip(points, points[1:]):
        if b.t <= a.t:
            b.t = a.t + 0.05


def _smooth_altitude(points: list[TrackPoint], window_s: float) -> None:
    """Local linear fit, which keeps a steady descent where a plain average would bend it at the ends."""
    airborne = [p for p in points if not p.on_ground]
    if window_s <= 0 or len(airborne) < 3:
        return
    times = np.array([p.t for p in airborne])
    alts = np.array([p.alt_ft for p in airborne])
    sigma = window_s / 2.0
    smoothed = []
    for t in times:
        w = np.exp(-0.5 * ((times - t) / sigma) ** 2)
        x = times - t
        sw, swx, swxx = w.sum(), (w * x).sum(), (w * x * x).sum()
        swy, swxy = (w * alts).sum(), (w * x * alts).sum()
        det = sw * swxx - swx * swx
        smoothed.append(swy / sw if abs(det) < 1e-9 else (swxx * swy - swx * swxy) / det)
    for point, alt in zip(airborne, smoothed):
        point.alt_ft = float(alt)


def clean_track(points: list[TrackPoint], field_elevation_ft: float | None = None,
                taxi_below_kt: float = 30.0, smooth_alt_s: float = 6.0) -> CleanedTrack:
    """Repair what can be repaired, drop what cannot, and say what was done."""
    issues: list[Issue] = []
    ordered = []
    for point in sorted(points, key=lambda p: p.t):
        if ordered and point.t <= ordered[-1].t:
            issues.append(Issue(point.t, "time", f"row {point.row} repeats or reverses time",
                                "dropped"))
            continue
        ordered.append(replace(point, notes=list(point.notes)))
    for point in ordered:
        point.on_ground = point.alt_ft <= 0.0

    touchdown = next((i for i, p in enumerate(ordered) if p.on_ground and i > 0
                      and not ordered[i - 1].on_ground), None)
    if touchdown is not None:
        stop = next((i for i in range(touchdown, len(ordered))
                     if ordered[i].speed_kt < taxi_below_kt), None)
        if stop is not None and stop + 1 < len(ordered):
            dropped = ordered[stop + 1:]
            issues.append(Issue(dropped[0].t, "taxi", f"{len(dropped)} points below "
                                f"{taxi_below_kt:.0f} kt after the landing roll, to "
                                f"{dropped[-1].t:.0f} s", "dropped"))
            ordered = ordered[:stop + 1]

    _fix_spikes(ordered, issues)
    ordered = _drop_off_line(ordered, issues)
    before = _worst_mismatch(ordered)

    for a, b in zip(ordered, ordered[1:]):
        if b.t - a.t > GAP_S:
            issues.append(Issue(a.t, "gap", f"no data for {b.t - a.t:.0f} s, track "
                                f"{a.track_deg:.0f} to {b.track_deg:.0f} deg", "bridged"))
    _retime(ordered, issues)

    offset = 0.0
    if touchdown is not None:
        last_airborne = max(i for i, p in enumerate(ordered) if not p.on_ground and
                            p.original_t < next(q.original_t for q in ordered if q.on_ground))
        if field_elevation_ft is None:
            issues.append(Issue(ordered[last_airborne].t, "altitude", "ground points have no "
                                "altitude; pass the field elevation to place them and to correct "
                                "pressure altitude", "kept"))
        else:
            measured = ordered[last_airborne].alt_ft
            estimate = field_elevation_ft + FLARE_FT - measured
            if abs(estimate) >= MIN_ALT_OFFSET_FT:
                offset = estimate
                issues.append(Issue(ordered[last_airborne].t, "altitude", f"last airborne report "
                                    f"{measured:.0f} ft against a {field_elevation_ft:.0f} ft field: "
                                    f"pressure altitude, all raised {offset:+.0f} ft", "corrected"))
            for point in ordered:
                if point.on_ground:
                    point.alt_ft = field_elevation_ft
                else:
                    point.alt_ft += offset
    _smooth_altitude(ordered, smooth_alt_s)

    return CleanedTrack(points=ordered, issues=sorted(issues, key=lambda i: i.t),
                        alt_offset_ft=offset, worst_speed_mismatch_before_kt=before,
                        worst_speed_mismatch_after_kt=_worst_mismatch(ordered))


def write_track_csv(track: CleanedTrack) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["time", "lat", "long", "altitude_ft", "speed_kt", "heading_deg", "on_ground",
                     "original_time", "original_altitude_ft", "notes"])
    for p in track.points:
        writer.writerow([f"{p.t:.2f}", f"{p.lat:.6f}", f"{p.lon:.6f}", f"{p.alt_ft:.0f}",
                         f"{p.speed_kt:.1f}", f"{p.track_deg:.0f}", int(p.on_ground),
                         f"{p.original_t:.0f}", f"{p.original_alt_ft:.0f}", "; ".join(p.notes)])
    return out.getvalue()


def to_keyframes(track: CleanedTrack) -> list[FlightKeyframe]:
    return [FlightKeyframe(time_offset=round(p.t, 2), time_source=TimeSource.IMPORTED,
                           lat=p.lat, lon=p.lon, alt_ft_msl=round(p.alt_ft, 1))
            for p in track.points]
