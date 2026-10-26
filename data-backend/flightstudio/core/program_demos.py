"""Built-in PathPrograms for stage 6 read-only playback.

These are the same shapes the harness exercises, so a path opened here and
one drawn there can be compared side by side. Editing still lives in the
harness until stage 7.
"""

from __future__ import annotations

from .program import (
    ArcSegment,
    ControlPoint,
    Direction,
    GeoPoint,
    HermiteHandle,
    HermiteSegment,
    LineToSegment,
    MoveToSegment,
    PathProgram,
    SplineSegment,
    VelocityProfile,
)

BERKELEY = GeoPoint(lat=37.8716, lon=-122.2727, alt_ft_msl=2000.0)


def _v(speed: float = 100.0, inherit: bool = True) -> VelocityProfile:
    return VelocityProfile(c0=speed, inherit_entry=inherit)


DEMOS: dict[str, object] = {}


def demo(name: str):
    def wrap(fn):
        DEMOS[name] = fn
        return fn
    return wrap


@demo("figure-eight")
def figure_eight() -> PathProgram:
    return PathProgram(origin=BERKELEY, segments=[
        LineToSegment(name="Entry", heading_deg=0.0, distance_m=1200.0,
                      velocity=_v(100.0, False)),
        ArcSegment(name="Left loop", side="LEFT", radius_m=700.0, sweep_deg=360.0,
                   velocity=_v()),
        ArcSegment(name="Right loop", side="RIGHT", radius_m=700.0, sweep_deg=360.0,
                   velocity=_v()),
        LineToSegment(name="Exit", distance_m=1200.0, inherit_direction=True,
                      velocity=_v()),
    ])


@demo("circuit")
def circuit() -> PathProgram:
    return PathProgram(origin=BERKELEY, segments=[
        LineToSegment(name="North straight", heading_deg=0.0, distance_m=3000.0,
                      velocity=_v(100.0, False)),
        ArcSegment(name="Right turn", side="RIGHT", radius_m=800.0, sweep_deg=180.0,
                   velocity=_v()),
        LineToSegment(name="South straight", distance_m=3000.0, inherit_direction=True,
                      velocity=_v()),
        ArcSegment(name="Right turn home", side="RIGHT", radius_m=800.0, sweep_deg=180.0,
                   velocity=_v()),
    ])


@demo("cut")
def cut() -> PathProgram:
    return PathProgram(origin=BERKELEY, segments=[
        LineToSegment(name="Before the cut", heading_deg=0.0, distance_m=2500.0,
                      velocity=_v(100.0, False)),
        MoveToSegment(
            name="Cut to the far side",
            to=GeoPoint(lat=37.82, lon=-122.34, alt_ft_msl=4500.0),
            tangent=Direction(heading_deg=90.0), speed_ms=100.0,
        ),
        LineToSegment(name="After the cut", distance_m=2500.0, inherit_direction=True,
                      velocity=_v()),
    ])


@demo("hermite")
def hermite() -> PathProgram:
    return PathProgram(origin=BERKELEY, segments=[
        LineToSegment(name="Run-up", heading_deg=0.0, distance_m=800.0,
                      velocity=_v(100.0, False)),
        HermiteSegment(
            name="S-bend",
            to=GeoPoint(lat=37.9000, lon=-122.2500, alt_ft_msl=2500.0),
            into=HermiteHandle(heading_deg=120.0, length_m=700.0),
            velocity=_v(),
        ),
        LineToSegment(name="Carry on", distance_m=1200.0, inherit_direction=True,
                      velocity=_v()),
    ])


@demo("spline")
def spline() -> PathProgram:
    return PathProgram(origin=BERKELEY, segments=[
        SplineSegment(
            name="Coast",
            control_points=[
                ControlPoint(lat=37.8716, lon=-122.2727, alt_ft_msl=2000.0),
                ControlPoint(lat=37.8800, lon=-122.2550, alt_ft_msl=2200.0),
                ControlPoint(lat=37.8950, lon=-122.2500, alt_ft_msl=2100.0),
                ControlPoint(lat=37.9100, lon=-122.2600, alt_ft_msl=2000.0),
            ],
            velocity=_v(100.0, False),
        ),
    ])


def list_demos() -> list[dict]:
    return [{"id": name, "label": name.replace("-", " ")} for name in DEMOS]


def build_demo(name: str) -> PathProgram:
    try:
        return DEMOS[name]()
    except KeyError as exc:
        raise ValueError(f"Unknown program demo {name!r}. "
                         f"Choose one of: {', '.join(DEMOS)}.") from exc
