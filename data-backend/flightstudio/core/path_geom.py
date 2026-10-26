"""3D ENU evaluators for authored flight legs: straight, planar arc, Hermite."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .schema import ArcLeg, HermiteHandle, HermiteLeg, Plane

Vec3 = tuple[float, float, float]


def _add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale(a: Vec3, s: float) -> Vec3:
    return (a[0] * s, a[1] * s, a[2] * s)


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a: Vec3) -> float:
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def _unit(a: Vec3) -> Vec3:
    n = _norm(a)
    if n < 1e-12:
        return (0.0, 0.0, 0.0)
    return (a[0] / n, a[1] / n, a[2] / n)


def lerp3(a: Vec3, b: Vec3, u: float) -> Vec3:
    u = min(1.0, max(0.0, u))
    return (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u)


def plane_normal(plane: Plane) -> Vec3:
    n = _unit((plane.normal_east, plane.normal_up, plane.normal_north))
    return n if _norm(n) >= 0.5 else (0.0, 1.0, 0.0)


def plane_containing(a: Vec3, b: Vec3, preferred: Vec3) -> Vec3:
    """Normal of the plane that contains A and B and is closest to preferred."""
    chord = _sub(b, a)
    length = _norm(chord)
    if length < 1e-9:
        return _unit(preferred) if _norm(preferred) >= 0.5 else (0.0, 1.0, 0.0)
    hat = _scale(chord, 1.0 / length)
    n = _sub(preferred, _scale(hat, _dot(preferred, hat)))
    unit = _unit(n)
    if _norm(unit) >= 0.5:
        return unit
    fallback = _unit(_cross(hat, (0.0, 1.0, 0.0)))
    return fallback if _norm(fallback) >= 0.5 else (1.0, 0.0, 0.0)


def handle_vector(handle: HermiteHandle) -> Vec3:
    heading = math.radians(handle.heading_deg)
    climb = math.radians(handle.climb_deg)
    east = math.sin(heading) * math.cos(climb)
    north = math.cos(heading) * math.cos(climb)
    up = math.sin(climb)
    scale = 3.0 * handle.length_m
    return (east * scale, up * scale, north * scale)


def hermite_from_chord(a: Vec3, b: Vec3):
    """Default Hermite handles along the 3D chord, length chord/3."""
    from .schema import HermiteHandle, HermiteLeg

    delta = _sub(b, a)
    length = _norm(delta)
    heading = math.degrees(math.atan2(delta[0], delta[2])) if length > 1e-9 else 0.0
    horiz = math.hypot(delta[0], delta[2])
    climb = math.degrees(math.atan2(delta[1], horiz)) if horiz > 1e-9 or abs(delta[1]) > 1e-9 else 0.0
    handle = HermiteHandle(heading_deg=heading, climb_deg=climb, length_m=max(length / 3.0, 1.0))
    return HermiteLeg(out=handle, into=handle.model_copy())


def hermite_point(a: Vec3, b: Vec3, path: HermiteLeg, u: float) -> Vec3:
    u = min(1.0, max(0.0, u))
    u2, u3 = u * u, u * u * u
    h00 = 2.0 * u3 - 3.0 * u2 + 1.0
    h10 = u3 - 2.0 * u2 + u
    h01 = -2.0 * u3 + 3.0 * u2
    h11 = u3 - u2
    m0, m1 = handle_vector(path.out), handle_vector(path.into)
    return (
        h00 * a[0] + h10 * m0[0] + h01 * b[0] + h11 * m1[0],
        h00 * a[1] + h10 * m0[1] + h01 * b[1] + h11 * m1[1],
        h00 * a[2] + h10 * m0[2] + h01 * b[2] + h11 * m1[2],
    )


def arc_frame(a: Vec3, b: Vec3, path: ArcLeg):
    """Centre, radius, start radial, in-plane 90°, signed sweep from A to B."""
    preferred = plane_normal(path.plane)
    normal = plane_containing(a, b, preferred)
    chord = _sub(b, a)
    length = _norm(chord)
    if length < 1e-6:
        return None
    half = length * 0.5
    radius = max(float(path.radius_m), half)
    height = math.sqrt(max(0.0, radius * radius - half * half))
    along = _scale(chord, 1.0 / length)
    left = _unit(_cross(along, normal))
    if _norm(left) < 0.5:
        return None
    sign = 1.0 if path.side == "LEFT" else -1.0
    mid = _add(a, _scale(chord, 0.5))
    center = _add(mid, _scale(left, sign * height))
    radial = _unit(_sub(a, center))
    around = _cross(normal, radial)
    to_end = _sub(b, center)
    sweep = math.atan2(_dot(around, to_end), _dot(radial, to_end))
    if abs(sweep) < 1e-9:
        sweep = (1.0 if sign > 0 else -1.0) * 2.0 * math.atan2(half, max(height, 1e-9))
    elif height < 1e-6:
        # Radius at its floor: the ends are diametrically opposite, and atan2
        # always answers +pi there. That flips the half circle to the far side
        # of the chord just as the radius reaches its minimum, so the shape
        # jumps instead of tightening. Keep the side the larger radii bulge to.
        sweep = -sign * math.pi
    if path.major:
        sweep = sweep - 2.0 * math.pi if sweep >= 0.0 else sweep + 2.0 * math.pi
    return center, radius, radial, around, sweep


def arc_point(a: Vec3, b: Vec3, path: ArcLeg, u: float) -> Vec3:
    frame = arc_frame(a, b, path)
    if frame is None:
        return lerp3(a, b, u)
    center, radius, radial, around, sweep = frame
    theta = sweep * min(1.0, max(0.0, u))
    return _add(center, _add(_scale(radial, radius * math.cos(theta)),
                             _scale(around, radius * math.sin(theta))))


def path_point(a: Vec3, b: Vec3, path, u: float) -> Vec3:
    kind = getattr(path, "kind", "STRAIGHT")
    if kind == "ARC":
        return arc_point(a, b, path, u)
    if kind == "HERMITE":
        return hermite_point(a, b, path, u)
    return lerp3(a, b, u)
