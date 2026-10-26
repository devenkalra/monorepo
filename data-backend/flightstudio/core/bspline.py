"""Clamped cubic B-spline and NURBS evaluation.

The fitter still produces an unweighted B-spline; the program model's
``SplineSegment`` stores per-point weights and evaluates as a NURBS, so a
weight of one everywhere is exactly the same curve the fitter wrote.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

DEGREE = 3
Vec3 = tuple[float, float, float]


def chord_params(points: list[Vec3]) -> list[float]:
    params = [0.0]
    for i in range(1, len(points)):
        params.append(params[-1] + math.dist(points[i], points[i - 1]))
    total = params[-1]
    if total < 1e-9:
        n = max(1, len(points) - 1)
        return [i / n for i in range(len(points))]
    return [p / total for p in params]


def clamped_knots(n_ctrl: int, degree: int = DEGREE) -> list[float]:
    interior = n_ctrl - degree - 1
    if interior <= 0:
        return [0.0] * (degree + 1) + [1.0] * (degree + 1)
    mids = [(j + 1) / (interior + 1) for j in range(interior)]
    return [0.0] * (degree + 1) + mids + [1.0] * (degree + 1)


def find_span(n_ctrl: int, degree: int, u: float, knots: list[float]) -> int:
    if u >= knots[n_ctrl]:
        return n_ctrl - 1
    if u <= knots[degree]:
        return degree
    low, high = degree, n_ctrl
    mid = (low + high) // 2
    while u < knots[mid] or u >= knots[mid + 1]:
        if u < knots[mid]:
            high = mid
        else:
            low = mid
        mid = (low + high) // 2
    return mid


def basis_funs(span: int, u: float, degree: int, knots: list[float]) -> list[float]:
    left = [0.0] * (degree + 1)
    right = [0.0] * (degree + 1)
    n = [0.0] * (degree + 1)
    n[0] = 1.0
    for j in range(1, degree + 1):
        left[j] = u - knots[span + 1 - j]
        right[j] = knots[span + j] - u
        saved = 0.0
        for r in range(j):
            denom = right[r + 1] + left[j - r]
            temp = n[r] / denom if abs(denom) > 1e-15 else 0.0
            n[r] = saved + right[r + 1] * temp
            saved = left[j - r] * temp
        n[j] = saved
    return n


@dataclass(frozen=True)
class NurbsCurve:
    """A NURBS curve in local metres. Weights of one everywhere is a B-spline."""

    ctrl: list[Vec3]
    weights: list[float]
    knots: list[float]
    degree: int

    def __post_init__(self):
        if len(self.ctrl) != len(self.weights):
            raise ValueError("each control point needs a weight")
        if len(self.knots) != len(self.ctrl) + self.degree + 1:
            raise ValueError("knot vector length does not match degree and control count")

    def point_at(self, u: float) -> Vec3:
        u = min(1.0, max(0.0, u))
        n_ctrl = len(self.ctrl)
        span = find_span(n_ctrl, self.degree, u, self.knots)
        basis = basis_funs(span, u, self.degree, self.knots)
        east = up = north = weight_sum = 0.0
        for i, value in enumerate(basis):
            point = self.ctrl[span - self.degree + i]
            mass = value * self.weights[span - self.degree + i]
            east += mass * point[0]
            up += mass * point[1]
            north += mass * point[2]
            weight_sum += mass
        if weight_sum < 1e-15:
            return self.ctrl[0]
        return (east / weight_sum, up / weight_sum, north / weight_sum)

    def tangent_at(self, u: float) -> Vec3:
        """Unit tangent by central difference.

        Exact enough for pose and for the solver's own Jacobian steps, and
        free of the basis-derivative bookkeeping that only matters when the
        derivative itself is the deliverable.
        """
        u = min(1.0, max(0.0, u))
        step = 1e-5
        low = max(0.0, u - step)
        high = min(1.0, u + step)
        if high - low < 1e-12:
            return (0.0, 0.0, 1.0)
        a, b = self.point_at(low), self.point_at(high)
        delta = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        length = math.sqrt(delta[0] ** 2 + delta[1] ** 2 + delta[2] ** 2)
        if length < 1e-12:
            return (0.0, 0.0, 1.0)
        return (delta[0] / length, delta[1] / length, delta[2] / length)


@dataclass
class FittedBSpline:
    ctrl: list[Vec3]
    knots: list[float]
    degree: int
    params: list[float]

    def point_at(self, u: float) -> Vec3:
        u = min(1.0, max(0.0, u))
        n_ctrl = len(self.ctrl)
        span = find_span(n_ctrl, self.degree, u, self.knots)
        basis = basis_funs(span, u, self.degree, self.knots)
        east = up = north = 0.0
        for i, weight in enumerate(basis):
            point = self.ctrl[span - self.degree + i]
            east += weight * point[0]
            up += weight * point[1]
            north += weight * point[2]
        return (east, up, north)


def _ls_fit(points: list[Vec3], params: list[float], n_ctrl: int, degree: int,
            smooth_m: float = 0.0) -> FittedBSpline:
    knots = clamped_knots(n_ctrl, degree)
    m = len(points)
    matrix = np.zeros((m, n_ctrl))
    for j, u in enumerate(params):
        span = find_span(n_ctrl, degree, u, knots)
        basis = basis_funs(span, u, degree, knots)
        for i, weight in enumerate(basis):
            matrix[j, span - degree + i] = weight
    targets = np.asarray(points, dtype=float)
    # Clamped ends: first and last control points sit on the first and last targets.
    fixed = np.zeros((m, 3))
    fixed += np.outer(matrix[:, 0], targets[0])
    fixed += np.outer(matrix[:, -1], targets[-1])
    rhs = targets - fixed
    if n_ctrl <= 2:
        ctrl = [tuple(targets[0]), tuple(targets[-1])]
        return FittedBSpline(ctrl, knots, degree, params)
    interior = matrix[:, 1:-1]
    n_int = n_ctrl - 2
    if smooth_m > 0.0 and n_int > 0:
        # Second-difference penalty on the control polygon. Interiors pull
        # the curve; they do not pin it. Larger smooth_m prefers a fairer
        # cubic over hugging every target.
        extra = np.zeros((n_ctrl - 2, n_int))
        extra_rhs = np.zeros((n_ctrl - 2, 3))
        for mid in range(1, n_ctrl - 1):
            row = mid - 1
            for col, coeff in ((mid - 1, 1.0), (mid, -2.0), (mid + 1, 1.0)):
                if col == 0:
                    extra_rhs[row] -= coeff * targets[0]
                elif col == n_ctrl - 1:
                    extra_rhs[row] -= coeff * targets[-1]
                else:
                    extra[row, col - 1] += coeff
        extra *= smooth_m
        extra_rhs *= smooth_m
        interior = np.vstack([interior, extra])
        rhs = np.vstack([rhs, extra_rhs])
    solved, *_ = np.linalg.lstsq(interior, rhs, rcond=None)
    ctrl = [tuple(targets[0])]
    ctrl.extend(tuple(row) for row in solved)
    ctrl.append(tuple(targets[-1]))
    return FittedBSpline(ctrl, knots, degree, params)


def _ctrl_limit(n_points: int, degree: int) -> int:
    """Never enough control points to interpolate every interior."""
    minimum = degree + 1
    if n_points <= 4:
        return minimum
    return min(max(minimum, n_points - 2), 12)


def _smooth_weight(points: list[Vec3], tolerance_m: float) -> float:
    """Map allowed miss onto a light fairing weight.

    Using tolerance_m itself as the least-squares weight (50, 10, …) made
    the cubic collapse onto the start–end chord, so interiors did not pull.
    Scale by path length so a 50 m tolerance on a 400 m span still bows.
    """
    if tolerance_m <= 0.0:
        return 0.0
    span = 0.0
    for index in range(1, len(points)):
        span += math.dist(points[index], points[index - 1])
    return min(2.0, max(0.05, 2.0 * tolerance_m / max(span, 1.0)))


def fit_bspline(points: list[Vec3], tolerance_m: float, degree: int = DEGREE) -> FittedBSpline:
    if len(points) < 2:
        raise ValueError("a B-spline span needs at least two waypoints")
    params = chord_params(points)
    if len(points) == 2:
        a, b = np.asarray(points[0], float), np.asarray(points[1], float)
        delta = b - a
        ctrl = [tuple(a), tuple(a + delta / 3.0), tuple(a + 2.0 * delta / 3.0), tuple(b)]
        return FittedBSpline(ctrl, clamped_knots(4, degree), degree, params)

    n_ctrl = degree + 1
    limit = _ctrl_limit(len(points), degree)
    smooth = _smooth_weight(points, tolerance_m)
    fitted = _ls_fit(points, params, n_ctrl, degree, smooth_m=smooth)
    while n_ctrl < limit:
        err = max(math.dist(fitted.point_at(params[j]), points[j]) for j in range(len(points)))
        if err <= tolerance_m:
            break
        n_ctrl += 1
        fitted = _ls_fit(points, params, n_ctrl, degree, smooth_m=smooth)
    return fitted
