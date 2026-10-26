"""Shape an evaluated PathProgram for a client.

Shared by the harness endpoint and the standalone HTML renderer, so the two
can never disagree about what a program draws.

This is not the stage 5 preview. That one has to emit the existing sample
format from section 2, keyed the way the current player expects. Samples here
are spaced by distance and carry their time alongside, which is what a harness
wants and what a retime makes cheap to recompute.
"""

from __future__ import annotations

import math

from .core.program import ArcSegment, HermiteSegment, PathProgram, SplineSegment
from .core.program_construct import hull_divergence
from .core.program_geom import (
    ArcGeometry,
    HermiteGeometry,
    SolvedProgram,
    SplineGeometry,
    direction_angles,
    sample_by_distance,
)
from .core.program_solve import Solvability, solve
from .core.program_time import TimedProgram, validate_timing

DEFAULT_STEP_M = 20.0
MIN_STEP_M = 2.0
MAX_STEP_M = 500.0
# A long helix at a fine step can ask for millions of points and wedge the
# browser, so the step is widened to hold the count rather than refused.
MAX_SAMPLES = 20000


def choose_step(solved: SolvedProgram, requested_m: float) -> float:
    step = min(MAX_STEP_M, max(MIN_STEP_M, float(requested_m)))
    if solved.length_m / step > MAX_SAMPLES:
        step = solved.length_m / MAX_SAMPLES
    return step


def _point(solved: SolvedProgram, vector) -> dict:
    lat, lon, alt_ft = solved.to_latlon(vector)
    return {"lat": lat, "lon": lon, "alt_ft": round(alt_ft, 2)}


def _solvability(report: Solvability) -> dict:
    return {
        "state": report.state,
        "free": report.free,
        "equations": report.equations,
        "rank": report.rank,
        "short_by": report.short_by,
        "residual_m": round(report.residual_m, 4),
        "method": report.method,
        "detail": report.detail,
    }


def _segment_summary(timed: TimedProgram, index: int, source, geometry,
                     report: Solvability) -> dict:
    solved = timed.solved
    drawn = geometry.length_m > 0.0
    heading, climb = direction_angles(geometry.tangent_at(1.0)) if drawn else (0.0, 0.0)
    entry_heading, entry_climb = (
        direction_angles(geometry.tangent_at(0.0)) if drawn else (0.0, 0.0)
    )
    duration = timed.segment_duration(index)
    start_s = timed.segment_start_s(index)
    profile = timed.profiles[index]
    summary = {
        "id": geometry.segment_id,
        "kind": geometry.kind,
        "name": source.name or "",
        "length_m": round(geometry.length_m, 3),
        "seam": geometry.seam,
        "start": _point(solved, geometry.start),
        "end": _point(solved, geometry.end),
        "entry": {"heading": round(entry_heading, 3), "climb": round(entry_climb, 3)},
        "exit": {"heading": round(heading, 3), "climb": round(climb, 3)},
        "timing": {
            "start_s": round(start_s, 4),
            "duration_s": round(duration, 4),
            "dwell_s": round(source.end.dwell_s, 4),
            # The speeds actually flown, after inheritance resolved them.
            "entry_speed_ms": round(profile.entry_speed, 3) if profile else None,
            "exit_speed_ms": round(profile.exit_speed, 3) if profile else None,
        },
        "solvability": _solvability(report),
    }
    if isinstance(geometry, ArcGeometry):
        # The centre and the resolved rise are derived, not authored, so the
        # harness can show what the parameters actually produced.
        summary["arc"] = {
            "center": _point(solved, geometry.center),
            "radius_m": round(geometry.radius_m, 3),
            "turns": round(geometry.sweep_rad / (2.0 * math.pi), 4),
            "rise_per_turn_m": round(geometry.rise_per_rad_m * 2.0 * math.pi, 3),
            "rise_is_default": isinstance(source, ArcSegment)
            and source.rise_per_turn_m is None,
        }
    if isinstance(geometry, HermiteGeometry) and isinstance(source, HermiteSegment):
        # Handle tips in lat/lon, so the map can draw the gizmo without
        # knowing the cubic's 3× length convention.
        out_tip = (
            geometry.start[0] + geometry.out_tangent[0] / 3.0,
            geometry.start[1] + geometry.out_tangent[1] / 3.0,
            geometry.start[2] + geometry.out_tangent[2] / 3.0,
        )
        into_tip = (
            geometry.end[0] - geometry.into_tangent[0] / 3.0,
            geometry.end[1] - geometry.into_tangent[1] / 3.0,
            geometry.end[2] - geometry.into_tangent[2] / 3.0,
        )
        summary["hermite"] = {
            "out_default": source.out is None,
            "out_tip": _point(solved, out_tip),
            "into_tip": _point(solved, into_tip),
        }
    if isinstance(geometry, SplineGeometry) and isinstance(source, SplineSegment):
        warning = hull_divergence(source, program=timed.program)
        summary["spline"] = {
            "degree": source.degree,
            "controls": [_point(solved, point) for point in geometry.controls],
            "weights": [round(point.weight, 4) for point in source.control_points],
            "construction": (
                None if source.construction is None else {
                    "kind": source.construction.kind,
                    "tolerance_m": source.construction.tolerance_m,
                    "point_count": len(source.construction.points),
                    "matches": warning.control_edits == 0 and warning.weight_edits == 0,
                    "refit_warning": warning.detail,
                }
            ),
        }
    return summary


def _timed_samples(timed: TimedProgram, rows: list[dict]) -> list[dict]:
    """Put a time, a speed and a bank on every sample, and add rows for dwells.

    Bank is the point of carrying it here: it is the quantity a seam would
    spike, so plotting it is how you see that one did not.

    Dwells need rows of their own because sampling is by distance and a hold
    covers none. Without them a six-second hold is a single point on a time
    axis, which reads as a glitch rather than as stopping.
    """
    index_of = {geometry.segment_id: index
                for index, geometry in enumerate(timed.solved.segments)}
    for row in rows:
        index = index_of[row["segment_id"]]
        seconds = timed.time_at(index, row["u"])
        row["t"] = round(seconds, 4)
        row["speed_ms"] = round(timed.ground_speed_at(seconds), 3)
        row["bank"] = round(timed.bank_deg_at(seconds), 3)
        row["hold"] = False

    out: list[dict] = []
    for position, row in enumerate(rows):
        out.append(row)
        last_of_segment = (position == len(rows) - 1
                           or rows[position + 1]["segment_id"] != row["segment_id"])
        dwell = timed.program.segments[index_of[row["segment_id"]]].end.dwell_s
        if not last_of_segment or dwell <= 0.0:
            continue
        for edge in (0.0, dwell):
            out.append({**row, "t": round(row["t"] + edge, 4),
                        "speed_ms": 0.0, "bank": 0.0, "hold": True,
                        "break_before": False})
    return out


def segment_summaries(timed: TimedProgram, outcome) -> list[dict]:
    """Per-segment facts for the harness and the stage-7 map gizmos / popup.

    Shared so ``program_preview`` and ``preview_program`` cannot disagree about
    centres, Hermite tips, spline hulls or solvability.
    """
    program = outcome.program
    return [
        _segment_summary(timed, index, source, geometry, report)
        for index, (source, geometry, report)
        in enumerate(zip(program.segments, outcome.solved.segments, outcome.reports))
    ]


def program_preview(program: PathProgram, step_m: float = DEFAULT_STEP_M) -> dict:
    """Solve, time and describe a program: per-segment facts plus samples.

    The solve comes first and the rest runs on what it produced, so a
    constrained segment is timed and drawn as it actually ends up rather than
    as it was stored. The solved program goes back in the payload for the
    same reason: the editor has to show the numbers the curve really has.
    """
    outcome = solve(program)
    program, solved = outcome.program, outcome.solved
    timed = TimedProgram(program, solved)
    step = choose_step(solved, step_m)
    return {
        "schema_version": program.schema_version,
        "origin": {
            "lat": program.origin.lat,
            "lon": program.origin.lon,
            "alt_ft_msl": program.origin.alt_ft_msl,
        },
        "length_m": round(solved.length_m, 3),
        "duration_s": round(timed.duration_s, 4),
        "flying_s": round(timed.flying_s, 4),
        "dwell_total_s": round(timed.dwell_total_s, 4),
        "seam_times": [round(seam, 4) for seam in timed.seam_times],
        "step_m": round(step, 3),
        "segments": segment_summaries(timed, outcome),
        "samples": _timed_samples(timed, sample_by_distance(solved, step_m=step)),
        "issues": validate_timing(program),
        # Constraints move parameters, so what came in is not what gets drawn.
        "solved_program": program.model_dump(mode="json"),
        "constrained": any(segment.constraints for segment in program.segments),
    }
