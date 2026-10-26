"""Work a segment's parameters backwards from its constraints — SEGMENT_MODEL.md section 4.

The evaluator runs forwards: parameters in, geometry out. This runs the other
way. Given somewhere the curve must pass through, it moves the parameters the
operator has not pinned until it does.

Three things make that tractable rather than a general optimisation problem.

It is local. A segment solves against the pen it inherits, the pen advances,
and the next segment solves against that — a chain of small problems, one per
segment, not one big system (section 4.5). An upstream edit still cascades,
because the pen it hands down has moved.

The common cases are closed form. Dragging an endpoint is one or two
unknowns with an exact answer, and those are the cases running under the
operator's hand, so they must not iterate. Everything else falls back to
Levenberg-Marquardt warm-started from the stored values, which is the second
reason section 4.1 stores values rather than holes.

Discrete parameters are enumerated, not descended. An arc's `side` is a
branch; LM cannot walk from one to the other, so both get tried.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .path_geom import Vec3, _dot, _norm, _sub, _unit
from .program import (
    ArcSegment,
    HermiteSegment,
    LineToSegment,
    MoveToSegment,
    PathProgram,
    SplineSegment,
)
from .program_geom import (
    MIN_HORIZONTAL,
    ArcGeometry,
    Pen,
    ProgramError,
    SegmentGeometry,
    SolvedProgram,
    direction_angles,
    direction_vector,
    enu_point,
    evaluate,
    segment_geometry,
    start_pen,
)

# Five centimetres. Below anything a map shows, and far below what the
# geodetic flattening in units.py is good for, so calling it "hit" is honest.
RESIDUAL_TOLERANCE_M = 0.05
MAX_ITERATIONS = 60
# Columns of the Jacobian below this fraction of the largest are taken as
# dependent. Loose enough to catch a parameter that barely moves the curve,
# which in practice is as useless to the operator as one that cannot.
RANK_TOLERANCE = 1e-7

# A representative step for each parameter, in its own units. Without these
# the normal equations mix degrees against kilometres and condition badly;
# with them every column of the Jacobian is roughly the metres of movement a
# one-step change produces.
PARAMETER_SCALE: dict[str, float] = {
    "heading_deg": 1.0, "climb_deg": 1.0, "distance_m": 10.0,
    "radius_m": 10.0, "sweep_deg": 1.0, "tilt_deg": 1.0, "rise_per_turn_m": 10.0,
    "to.lat": 1e-4, "to.lon": 1e-4, "to.alt_ft_msl": 50.0,
    "tangent.heading_deg": 1.0, "tangent.climb_deg": 1.0, "speed_ms": 5.0,
    "out.heading_deg": 1.0, "out.climb_deg": 1.0, "out.length_m": 10.0,
    "into.heading_deg": 1.0, "into.climb_deg": 1.0, "into.length_m": 10.0,
    "lat": 1e-4, "lon": 1e-4, "alt_ft_msl": 50.0, "weight": 0.1,
}

# Kept inside what the schema accepts, so a trial step can never produce a
# segment pydantic refuses to build.
PARAMETER_BOUNDS: dict[str, tuple[float, float]] = {
    "distance_m": (1e-3, math.inf),
    "radius_m": (1e-3, math.inf),
    "sweep_deg": (0.0, math.inf),
    "tilt_deg": (-89.9, 89.9),
    "climb_deg": (-90.0, 90.0),
    "tangent.climb_deg": (-90.0, 90.0),
    "to.lat": (-90.0, 90.0),
    "to.lon": (-180.0, 180.0),
    "speed_ms": (1e-3, math.inf),
    "out.climb_deg": (-90.0, 90.0),
    "into.climb_deg": (-90.0, 90.0),
    "out.length_m": (1e-3, math.inf),
    "into.length_m": (1e-3, math.inf),
    "lat": (-90.0, 90.0),
    "lon": (-180.0, 180.0),
    "weight": (1e-3, math.inf),
}

UNCONSTRAINED = "UNCONSTRAINED"
DETERMINED = "DETERMINED"
UNDER_DETERMINED = "UNDER_DETERMINED"
CONTRADICTORY = "CONTRADICTORY"


@dataclass(frozen=True)
class Solvability:
    """What the solver could and could not do with one segment.

    Under-determined is a working state, not a failure: the solver takes the
    solution nearest the seed and the editor says how many pins would nail it
    down. Contradictory is the other thing entirely, and the rank is what
    tells them apart — pins that cannot all be met versus pins that leave
    room.
    """

    index: int
    segment_id: str
    free: list[str] = field(default_factory=list)
    equations: int = 0
    rank: int = 0
    residual_m: float = 0.0
    state: str = UNCONSTRAINED
    method: str = "none"

    @property
    def short_by(self) -> int:
        """Directions the parameters can still move without affecting the fit."""
        return max(0, len(self.free) - self.rank)

    @property
    def detail(self) -> str:
        if self.state == UNCONSTRAINED:
            return f"{len(self.free)} free, nothing constrained"
        head = f"{len(self.free)} free, {self.equations} constrained"
        if self.state == DETERMINED:
            return f"{head} — solved"
        if self.state == UNDER_DETERMINED:
            return f"{head} — under-determined by {self.short_by}, nearest solution taken"
        return (f"{head} — these pins cannot all be met, "
                f"closest misses by {self.residual_m:.1f} m")


@dataclass(frozen=True)
class SolveOutcome:
    program: PathProgram
    solved: SolvedProgram
    reports: list[Solvability]

    @property
    def worst_residual_m(self) -> float:
        return max((report.residual_m for report in self.reports), default=0.0)


# ------------------------------------------------------------- parameters


def _scale_of(name: str) -> float:
    """A representative step for this parameter. Spline pins share a leaf name."""
    if name in PARAMETER_SCALE:
        return PARAMETER_SCALE[name]
    leaf = name.rsplit(".", 1)[-1]
    return PARAMETER_SCALE.get(leaf, 1.0)


def _bounds_of(name: str) -> tuple[float, float]:
    if name in PARAMETER_BOUNDS:
        return PARAMETER_BOUNDS[name]
    leaf = name.rsplit(".", 1)[-1]
    return PARAMETER_BOUNDS.get(leaf, (-math.inf, math.inf))


def _get(segment, name: str) -> float:
    target = segment
    for part in name.split("."):
        target = target[int(part)] if part.isdigit() else getattr(target, part)
    return target


def _set(segment, name: str, value: float) -> None:
    low, high = _bounds_of(name)
    target = segment
    parts = name.split(".")
    for part in parts[:-1]:
        target = target[int(part)] if part.isdigit() else getattr(target, part)
    setattr(target, parts[-1], min(high, max(low, value)))


def free_parameters(segment) -> list[str]:
    """The continuous parameters the solver may move on this segment.

    Narrower than the table in section 4.3, because a parameter can be out of
    play for reasons other than being pinned. A `rise_per_turn_m` of None is
    not a value the solver may nudge — it means "whatever keeps the join
    smooth", and materialising a number there would quietly discard that. The
    same goes for a MoveTo that re-seeds nothing, a LineTo that carries
    straight on from the pen, and a Hermite whose out handle defaults from
    the pen.

    A MoveTo's ``speed_ms`` is left out too. Section 4.3 counts it, but no
    POINT constraint can be met by changing it, so carrying it here would
    leave every MoveTo reported as under-determined by one for a freedom
    that is not withheld from anything.
    """
    if isinstance(segment, LineToSegment):
        names = ["distance_m"]
        if not segment.inherit_direction:
            names[:0] = ["heading_deg", "climb_deg"]
    elif isinstance(segment, ArcSegment):
        names = ["radius_m", "sweep_deg", "tilt_deg"]
        if segment.rise_per_turn_m is not None:
            names.append("rise_per_turn_m")
    elif isinstance(segment, MoveToSegment):
        names = ["to.lat", "to.lon", "to.alt_ft_msl"]
        if segment.tangent is not None:
            names += ["tangent.heading_deg", "tangent.climb_deg"]
    elif isinstance(segment, HermiteSegment):
        names = ["to.lat", "to.lon", "to.alt_ft_msl",
                 "into.heading_deg", "into.climb_deg", "into.length_m"]
        if segment.out is not None:
            names[3:3] = ["out.heading_deg", "out.climb_deg", "out.length_m"]
    elif isinstance(segment, SplineSegment):
        names = []
        for index in range(len(segment.control_points)):
            names += [f"control_points.{index}.lat",
                      f"control_points.{index}.lon",
                      f"control_points.{index}.alt_ft_msl",
                      f"control_points.{index}.weight"]
    else:  # pragma: no cover - the union has no other members
        names = []
    return [name for name in names if name not in segment.pinned]


# -------------------------------------------------------------- residuals


def constraint_targets(program: PathProgram, segment) -> list[tuple[float, Vec3, bool, bool]]:
    return [
        (constraint.at, enu_point(program, constraint),
         constraint.lock_horizontal, constraint.lock_vertical)
        for constraint in segment.constraints
    ]


def _residuals(geometry: SegmentGeometry, targets) -> list[float]:
    """How far the curve misses each constraint, in metres, axis by axis."""
    out: list[float] = []
    for at, target, horizontal, vertical in targets:
        east, up, north = geometry.point_at(at)
        if horizontal:
            out.append(east - target[0])
            out.append(north - target[2])
        if vertical:
            out.append(up - target[1])
    return out


def _residual_norm(values: list[float]) -> float:
    return math.sqrt(sum(value * value for value in values))


class _Trial:
    """Evaluates one segment repeatedly against trial parameter values."""

    def __init__(self, program: PathProgram, pen: Pen, segment, index: int, targets):
        self.program = program
        self.pen = pen
        self.segment = segment.model_copy(deep=True)
        self.index = index
        self.targets = targets
        self.width = sum(2 * int(horizontal) + int(vertical)
                         for _, _, horizontal, vertical in targets)

    def at(self, names: list[str], values: list[float]) -> list[float]:
        for name, value in zip(names, values):
            _set(self.segment, name, value)
        try:
            geometry, _ = segment_geometry(self.program, self.pen, self.segment, self.index)
        except ProgramError:
            # A trial step can wander somewhere the evaluator refuses — an arc
            # tilted edge-on, say. Report it as a bad fit of the same width as
            # a real one, so the search backs off instead of aborting a solve
            # that was otherwise converging.
            return [1e6] * self.width
        return _residuals(geometry, self.targets)


# ----------------------------------------------------------- linear algebra


def _solve_linear(matrix: list[list[float]], rhs: list[float]) -> list[float] | None:
    """Gaussian elimination with partial pivoting, for the n<=9 normal equations."""
    size = len(rhs)
    rows = [row[:] + [rhs[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda r: abs(rows[r][column]))
        if abs(rows[pivot][column]) < 1e-14:
            return None
        rows[column], rows[pivot] = rows[pivot], rows[column]
        for below in range(column + 1, size):
            factor = rows[below][column] / rows[column][column]
            if factor:
                for col in range(column, size + 1):
                    rows[below][col] -= factor * rows[column][col]
    out = [0.0] * size
    for row in range(size - 1, -1, -1):
        total = rows[row][size] - sum(rows[row][c] * out[c] for c in range(row + 1, size))
        out[row] = total / rows[row][row]
    return out


def matrix_rank(matrix: list[list[float]]) -> int:
    """Rank by elimination. Distinguishes "needs more pins" from "pins conflict"."""
    rows = [row[:] for row in matrix]
    if not rows or not rows[0]:
        return 0
    largest = max((abs(value) for row in rows for value in row), default=0.0)
    if largest == 0.0:
        return 0
    threshold = largest * RANK_TOLERANCE
    rank = 0
    columns = len(rows[0])
    for column in range(columns):
        pivot = max(range(rank, len(rows)), key=lambda r: abs(rows[r][column]), default=None)
        if pivot is None or abs(rows[pivot][column]) <= threshold:
            continue
        rows[rank], rows[pivot] = rows[pivot], rows[rank]
        for below in range(rank + 1, len(rows)):
            factor = rows[below][column] / rows[rank][column]
            if factor:
                for col in range(column, columns):
                    rows[below][col] -= factor * rows[rank][col]
        rank += 1
        if rank == len(rows):
            break
    return rank


def _jacobian(trial: _Trial, names: list[str], values: list[float]) -> list[list[float]]:
    """Central differences in scaled units, so a column is metres per step."""
    columns = []
    for position, name in enumerate(names):
        step = _scale_of(name) * 1e-4
        low, high = _bounds_of(name)
        up = min(high, values[position] + step)
        down = max(low, values[position] - step)
        span = up - down
        if span <= 0.0:
            columns.append(None)
            continue
        ahead = trial.at(names, [*values[:position], up, *values[position + 1:]])
        behind = trial.at(names, [*values[:position], down, *values[position + 1:]])
        columns.append([(a - b) / span * _scale_of(name)
                        for a, b in zip(ahead, behind)])
    trial.at(names, values)
    height = max((len(column) for column in columns if column), default=0)
    return [[(columns[c][r] if columns[c] else 0.0) for c in range(len(names))]
            for r in range(height)]


# ---------------------------------------------------------------- the solve


def _levenberg_marquardt(trial: _Trial, names: list[str],
                         seed: list[float]) -> tuple[list[float], list[list[float]]]:
    """Warm-started least squares. Returns the best values and the Jacobian there."""
    values = list(seed)
    residual = trial.at(names, values)
    cost = sum(value * value for value in residual)
    damping = 1e-3
    jacobian = _jacobian(trial, names, values)
    settled = RESIDUAL_TOLERANCE_M ** 2 * 1e-2

    for _ in range(MAX_ITERATIONS):
        if cost <= settled:
            break
        size = len(names)
        normal = [[sum(row[i] * row[j] for row in jacobian) for j in range(size)]
                  for i in range(size)]
        gradient = [-sum(row[i] * residual[r] for r, row in enumerate(jacobian))
                    for i in range(size)]
        if all(abs(value) < 1e-12 for value in gradient):
            break

        improved = False
        for _ in range(12):
            damped = [[normal[i][j] + (damping * max(normal[i][i], 1e-9) if i == j else 0.0)
                       for j in range(size)] for i in range(size)]
            step = _solve_linear(damped, gradient)
            if step is None:
                damping *= 8.0
                continue
            candidate = [values[i] + step[i] * _scale_of(names[i])
                         for i in range(size)]
            trial_residual = trial.at(names, candidate)
            trial_cost = sum(value * value for value in trial_residual)
            if trial_cost < cost:
                # Read the accepted values back off the segment: a step can be
                # clamped at a bound, and the solver must carry what was
                # actually used, not what it asked for.
                values = [_get(trial.segment, name) for name in names]
                residual, cost, improved = trial_residual, trial_cost, True
                damping = max(damping / 3.0, 1e-9)
                break
            damping *= 8.0
        if not improved:
            break
        jacobian = _jacobian(trial, names, values)

    trial.at(names, values)
    return values, jacobian


def _closed_form(trial: _Trial, segment, pen: Pen, names: list[str]) -> list[float] | None:
    """Exact answers for the cases that run under the operator's hand.

    Each is verified by the caller against the same residual the numeric path
    uses, so a case that turns out not to apply costs one evaluation and falls
    through to LM rather than producing a wrong answer.
    """
    targets = trial.targets
    if len(targets) != 1:
        return None
    at, target, horizontal, vertical = targets[0]

    if isinstance(segment, LineToSegment) and at == 1.0:
        delta = _sub(target, pen.point)
        if horizontal and vertical and names == ["heading_deg", "climb_deg", "distance_m"]:
            # Drag an endpoint: the leg simply points at it.
            distance = _norm(delta)
            if distance < 1e-6:
                return None
            heading, climb = direction_angles(_unit(delta))
            return [heading, climb, distance]
        if names == ["distance_m"] and horizontal and vertical:
            # Direction held, so the best the leg can do is stop abeam the
            # target: the projection onto its own ray.
            direction = (pen.tangent if segment.inherit_direction
                         else direction_vector(segment.heading_deg, segment.climb_deg))
            reach = _dot(delta, direction)
            return [reach] if reach > 0.0 else None
        if names == ["climb_deg"] and vertical and not horizontal:
            # "Be at this altitude by the end", with the ground track fixed.
            rise = (target[1] - pen.point[1]) / segment.distance_m
            if abs(rise) > 1.0:
                return None
            return [math.degrees(math.asin(rise))]

    if isinstance(segment, ArcSegment) and names == ["sweep_deg"]:
        geometry, _ = segment_geometry(trial.program, pen, segment, trial.index)
        if not isinstance(geometry, ArcGeometry):
            return None  # pragma: no cover
        return _sweep_to(geometry, target, at, segment.sweep_deg)

    if isinstance(segment, (HermiteSegment, MoveToSegment)) and at == 1.0:
        # The end (or jump target) is free and the constraint is the end:
        # put it there. Handles and tangents stay where they were — that is
        # the nearest seed-preserving answer; anything more needs LM.
        if (horizontal and vertical
                and names == ["to.lat", "to.lon", "to.alt_ft_msl"]):
            constraint = segment.constraints[0]
            return [constraint.lat, constraint.lon, constraint.alt_ft_msl]

    if isinstance(segment, SplineSegment) and at == 0.0:
        # Clamped: the first control point sits on the curve's start.
        if (horizontal and vertical
                and names == ["control_points.0.lat", "control_points.0.lon",
                              "control_points.0.alt_ft_msl"]):
            constraint = segment.constraints[0]
            return [constraint.lat, constraint.lon, constraint.alt_ft_msl]

    if isinstance(segment, SplineSegment) and at == 1.0:
        last = len(segment.control_points) - 1
        if (horizontal and vertical
                and names == [f"control_points.{last}.lat",
                              f"control_points.{last}.lon",
                              f"control_points.{last}.alt_ft_msl"]):
            constraint = segment.constraints[0]
            return [constraint.lat, constraint.lon, constraint.alt_ft_msl]

    return None


def _sweep_to(geometry: ArcGeometry, target: Vec3, at: float,
              stored_deg: float) -> list[float] | None:
    """The sweep that brings the curve round to a target, in closed form.

    The angle is read straight off the circle, which leaves the turn count
    free: every sweep a full turn apart lands in the same place. Taking the
    one nearest the stored value keeps a three-turn helix three turns long
    instead of collapsing it to the first crossing.
    """
    if at <= 0.0:
        return None
    offset = _sub(target, geometry.center)
    along = _dot(offset, geometry.radial)
    across = _dot(offset, geometry.circular)
    if math.hypot(along, across) < MIN_HORIZONTAL:
        return None
    angle = math.degrees(math.atan2(across, along)) % 360.0
    turns = round((stored_deg * at - angle) / 360.0)
    sweep = (angle + 360.0 * turns) / at
    return [sweep] if sweep >= 0.0 else [angle / at]


def solve_segment(program: PathProgram, pen: Pen, segment,
                  index: int) -> tuple[object, Solvability]:
    """Fit one segment to its own constraints. Returns a copy and a report."""
    names = free_parameters(segment)
    targets = constraint_targets(program, segment)
    report = Solvability(index=index, segment_id=segment.id, free=names)
    if not targets:
        return segment, report

    equations = sum(constraint.equations for constraint in segment.constraints)
    if not names:
        # Everything is pinned. Nothing to move, but the operator still wants
        # to know whether what they pinned is actually where the curve goes.
        geometry, _ = segment_geometry(program, pen, segment, index)
        residual = _residual_norm(_residuals(geometry, targets))
        return segment, Solvability(
            index=index, segment_id=segment.id, free=[], equations=equations,
            rank=0, residual_m=residual, method="none",
            state=DETERMINED if residual <= RESIDUAL_TOLERANCE_M else CONTRADICTORY,
        )

    best: tuple[float, object, list[list[float]], str] | None = None
    for branch in _branches(segment):
        trial = _Trial(program, pen, branch, index, targets)
        seed = [_get(trial.segment, name) for name in names]
        method = "numeric"

        exact = _closed_form(trial, trial.segment, pen, names)
        if exact is not None and _residual_norm(trial.at(names, exact)) <= RESIDUAL_TOLERANCE_M:
            values = [_get(trial.segment, name) for name in names]
            jacobian = _jacobian(trial, names, values)
            method = "closed form"
        else:
            values, jacobian = _levenberg_marquardt(trial, names, seed)

        residual = _residual_norm(trial.at(names, values))
        # A tie goes to the stored branch: the shape must not flip sides
        # under the operator's hand because two fits came out level.
        if best is None or residual < best[0] - RESIDUAL_TOLERANCE_M:
            best = (residual, trial.segment, jacobian, method)

    residual, solved_segment, jacobian, method = best
    rank = matrix_rank(jacobian)
    if residual > RESIDUAL_TOLERANCE_M:
        state = CONTRADICTORY
    elif rank < len(names):
        state = UNDER_DETERMINED
    else:
        state = DETERMINED
    return solved_segment, Solvability(
        index=index, segment_id=segment.id, free=names, equations=equations,
        rank=rank, residual_m=residual, state=state, method=method,
    )


def _branches(segment):
    """The discrete settings to try. Stored value first, so ties keep it."""
    if isinstance(segment, ArcSegment) and "side" not in segment.pinned:
        other = "RIGHT" if segment.side == "LEFT" else "LEFT"
        return [segment, segment.model_copy(deep=True, update={"side": other})]
    return [segment]


def solve(program: PathProgram) -> SolveOutcome:
    """Solve every constrained segment in order, carrying the pen between them.

    A chain of local solves, not a global system, so the cost is linear in
    segment count. An upstream edit still reaches downstream: it moves the pen
    that the next segment solves against.
    """
    solved = program.model_copy(deep=True)
    pen = start_pen(solved)
    reports: list[Solvability] = []

    for index, segment in enumerate(solved.segments):
        fitted, report = solve_segment(solved, pen, segment, index)
        solved.segments[index] = fitted
        reports.append(report)
        _, pen = segment_geometry(solved, pen, fitted, index)

    # Re-walk rather than collecting geometry above. The seam bookkeeping
    # belongs to the evaluator and should live in exactly one place; a second
    # pass over a solved program is cheap and cannot disagree with it.
    return SolveOutcome(program=solved, solved=evaluate(solved), reports=reports)
