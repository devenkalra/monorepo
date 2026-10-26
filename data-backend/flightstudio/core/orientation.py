"""Orientation maths for camera framing, per design section 3.2.

World axes here are X east, Y up, Z north, which makes heading = atan2(x, z) and
pitch = asin(y) for a unit forward vector. That parametrisation was confirmed
empirically against the simulator during the section 3.5 spike.

The important subtlety: SimConnect takes the camera's pitch, bank and heading
*relative to the aircraft*, so a world-stable camera has to be counter-rotated
by the aircraft's own attitude. Everything below exists to do that correctly.
"""

from __future__ import annotations

import math

Vec3 = tuple[float, float, float]
Matrix = tuple[Vec3, Vec3, Vec3]  # columns: right, up, forward


def normalise(v: Vec3) -> Vec3:
    length = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if length < 1e-12:
        return (0.0, 0.0, 1.0)
    return (v[0] / length, v[1] / length, v[2] / length)


def dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def subtract(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def basis_from_angles(pitch_deg: float, bank_deg: float, heading_deg: float) -> Matrix:
    """Right, up and forward vectors for an attitude."""
    p = math.radians(pitch_deg)
    h = math.radians(heading_deg)
    b = math.radians(bank_deg)

    forward = (math.cos(p) * math.sin(h), math.sin(p), math.cos(p) * math.cos(h))
    level_right = (math.cos(h), 0.0, -math.sin(h))
    level_up = (-math.sin(p) * math.sin(h), math.cos(p), -math.sin(p) * math.cos(h))

    cos_b, sin_b = math.cos(b), math.sin(b)
    right = tuple(level_right[i] * cos_b + level_up[i] * sin_b for i in range(3))
    up = tuple(level_up[i] * cos_b - level_right[i] * sin_b for i in range(3))
    return right, up, forward


def aircraft_basis(pitch_deg: float, bank_deg: float, heading_deg: float) -> Matrix:
    """Basis for an aircraft attitude given right-wing-down positive.

    `basis_from_angles` rolls the other way, which is the sense the camera's
    relative angles must be expressed in. Passing an aircraft bank straight in
    rolls the camera's horizon by twice the bank (spike/probe_camera_bank.py).
    """
    return basis_from_angles(pitch_deg, -bank_deg, heading_deg)


def angles_from_basis(basis: Matrix) -> tuple[float, float, float]:
    """Inverse of basis_from_angles. Returns pitch, bank, heading in degrees."""
    _right, up, forward = basis
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, forward[1]))))
    heading = math.degrees(math.atan2(forward[0], forward[2]))

    level = basis_from_angles(pitch, 0.0, heading)
    bank = math.degrees(math.atan2(-dot(up, level[0]), dot(up, level[1])))
    return pitch, bank, heading % 360.0


def relative_angles(aircraft: Matrix, camera: Matrix) -> tuple[float, float, float]:
    """Camera attitude expressed in the aircraft's frame."""
    columns = []
    for camera_axis in camera:
        columns.append((
            dot(aircraft[0], camera_axis),
            dot(aircraft[1], camera_axis),
            dot(aircraft[2], camera_axis),
        ))
    return angles_from_basis((columns[0], columns[1], columns[2]))


class FramingDiagnostic(Exception):
    """Raised when a camera keyframe cannot be resolved (design section 3.2)."""


def camera_basis(forward: Vec3, up_hint: Vec3, degenerate_fallback: Vec3 | None = None) -> tuple[Matrix, str | None]:
    """Resolve an over-specified look-at plus up vector into one orientation.

    The look-at direction fixes two degrees of freedom and the up vector
    supplies the third. Only the component of up perpendicular to the view axis
    matters; the parallel part is discarded silently, which is the normal case.
    A warning is returned only when up is so close to the view axis that roll
    becomes undefined.
    """
    f = normalise(forward)
    warning = None

    perpendicular = subtract(up_hint, tuple(dot(up_hint, f) * f[i] for i in range(3)))
    if math.sqrt(dot(perpendicular, perpendicular)) < 0.09:  # within about 5 degrees
        warning = (
            "up vector is nearly parallel to the view direction; roll is undefined"
        )
        fallback = degenerate_fallback or (0.0, 0.0, 1.0)
        perpendicular = subtract(fallback, tuple(dot(fallback, f) * f[i] for i in range(3)))
        if math.sqrt(dot(perpendicular, perpendicular)) < 1e-6:
            perpendicular = cross(f, (1.0, 0.0, 0.0))

    u = normalise(perpendicular)
    r = cross(u, f)
    return (r, u, f), warning
