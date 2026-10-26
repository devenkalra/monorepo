"""Build a segment from picks — SEGMENT_MODEL.md section 7.2.

The fitter is a constructor, not the representation. It writes a control
polygon into a SplineSegment and leaves its inputs in ``construction`` so
the operator can re-open them. Evaluation never reads that block.

A re-fit discards direct control-point edits and per-point weights. The
fitter varies its control count with the tolerance, so there is often no
correspondence to re-apply them to; the warning names how many would go.
"""

from __future__ import annotations

from dataclasses import dataclass

from .bspline import fit_bspline
from .path_geom import Vec3, _norm, _sub
from .program import (
    Construction,
    ControlPoint,
    GeoPoint,
    PathProgram,
    SplineSegment,
)
from .program_geom import enu_point
from .units import metres_to_feet, offset_latlon

# How close a control point has to sit to ``produced`` to count as unchanged.
# A few centimetres — below what a drag would move, above float noise.
HULL_MATCH_M = 0.05


@dataclass(frozen=True)
class RefitWarning:
    """What a re-fit would throw away."""

    control_edits: int
    weight_edits: int

    @property
    def detail(self) -> str:
        parts = []
        if self.control_edits:
            parts.append(f"{self.control_edits} control-point edit"
                         f"{'s' if self.control_edits != 1 else ''}")
        if self.weight_edits:
            parts.append(f"{self.weight_edits} weight"
                         f"{'s' if self.weight_edits != 1 else ''}")
        if not parts:
            return "the hull still matches the construction"
        return f"re-fitting discards {' and '.join(parts)}"


def _to_geopoint(program: PathProgram, point: Vec3) -> GeoPoint:
    lat, lon = offset_latlon(program.origin.lat, program.origin.lon,
                             point[2], point[0])
    return GeoPoint(lat=lat, lon=lon, alt_ft_msl=metres_to_feet(point[1]))


def hull_divergence(segment: SplineSegment,
                    produced: list[tuple[float, float, float]] | None = None,
                    program: PathProgram | None = None) -> RefitWarning:
    """How far the current hull has drifted from what the construction wrote.

    Compares ENU positions when a program is given; otherwise compares the
    stored ``produced`` list against itself via the segment's construction.
    Weights that are no longer 1.0 count as edits because the fitter always
    writes unweighted hulls.
    """
    if produced is None:
        if segment.construction is None:
            return RefitWarning(0, 0)
        produced = segment.construction.produced
    weight_edits = sum(1 for point in segment.control_points
                       if abs(point.weight - 1.0) > 1e-9)
    if not produced:
        # Nothing to compare positions against; any current control counts.
        return RefitWarning(len(segment.control_points), weight_edits)
    if program is None:
        # Without a frame we can only compare counts: a different length is
        # definitely an edit, a matching length is assumed untouched.
        control_edits = 0 if len(segment.control_points) == len(produced) else (
            max(len(segment.control_points), len(produced))
        )
        return RefitWarning(control_edits, weight_edits)

    current = [enu_point(program, point) for point in segment.control_points]
    if len(current) != len(produced):
        return RefitWarning(max(len(current), len(produced)), weight_edits)
    moved = sum(1 for a, b in zip(current, produced)
                if _norm(_sub(a, b)) > HULL_MATCH_M)
    return RefitWarning(moved, weight_edits)


def fit_spline_from_points(
    program: PathProgram,
    points: list[GeoPoint],
    tolerance_m: float = 50.0,
    *,
    name: str = "",
    existing: SplineSegment | None = None,
) -> tuple[SplineSegment, RefitWarning]:
    """Construct a SplineSegment by fitting a clamped cubic through the picks.

    Returns the new segment and a warning about what a re-fit of ``existing``
    would discard. Pass ``existing`` when re-opening a construction; leave it
    None for a first build.
    """
    if len(points) < 2:
        raise ValueError("fitting a spline needs at least two points")
    warning = (hull_divergence(existing, program=program) if existing
               else RefitWarning(0, 0))

    enu = [enu_point(program, point) for point in points]
    fitted = fit_bspline(enu, tolerance_m)
    controls = []
    for ctrl in fitted.ctrl:
        geo = _to_geopoint(program, ctrl)
        controls.append(ControlPoint(
            lat=geo.lat, lon=geo.lon, alt_ft_msl=geo.alt_ft_msl, weight=1.0,
        ))
    # Recompute once so the stored GeoPoints round-trip to the same ENU the
    # fitter produced — lat/lon quantisation would otherwise make
    # ``produced`` disagree with the hull on the very next compare.
    produced = [enu_point(program, point) for point in controls]
    extras = {}
    if existing is not None:
        extras = {
            "id": existing.id,
            "name": name or existing.name,
            "velocity": existing.velocity,
            "on_ground": existing.on_ground,
            "end": existing.end,
            "pinned": set(existing.pinned),
            "constraints": list(existing.constraints),
        }
    elif name:
        extras["name"] = name
    segment = SplineSegment(
        control_points=controls,
        degree=fitted.degree,
        knots=list(fitted.knots),
        construction=Construction(
            kind="FIT_POINTS",
            points=list(points),
            tolerance_m=tolerance_m,
            produced=[(p[0], p[1], p[2]) for p in produced],
        ),
        **extras,
    )
    return segment, warning


def construction_still_matches(segment: SplineSegment,
                               program: PathProgram) -> bool:
    """True when a re-fit would change nothing the operator can see."""
    warning = hull_divergence(segment, program=program)
    return warning.control_edits == 0 and warning.weight_edits == 0
