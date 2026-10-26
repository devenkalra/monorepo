"""Starter paths, so a new document opens as something that already flies.

An empty map is a bad starting point for this editor: a usable shot needs a
flight path and a camera path that agree about timing, and hand-placing the
first of each is tedious. These are meant to be edited, not used as-is.
"""

from __future__ import annotations

import math

from .locations import LOCATIONS
from .schema import (
    BodyPosition,
    CameraKeyframe,
    Easing,
    Entity,
    FlightKeyframe,
    LookAtAircraft,
    PathDocument,
    PathMeta,
    PlaybackMode,
)
from .units import offset_latlon


def banking_climb(lat: float, lon: float, alt_ft: float, heading: float,
                  duration: float = 36.0, legs: int = 5,
                  radius: float = 3000.0, sweep_deg: float = 70.0,
                  climb_ft: float = 900.0) -> list[FlightKeyframe]:
    """A climbing right-hand turn starting ahead of the given point."""
    bearing = math.radians(heading)
    base_lat, base_lon = offset_latlon(
        lat, lon, 600.0 * math.cos(bearing), 600.0 * math.sin(bearing)
    )
    # The turn centre sits one radius off the starting right wing.
    centre_north = radius * math.cos(bearing + math.pi / 2)
    centre_east = radius * math.sin(bearing + math.pi / 2)
    sweep = math.radians(sweep_deg)

    frames: list[FlightKeyframe] = []
    for index in range(legs):
        fraction = index / (legs - 1)
        angle = bearing - math.pi / 2 + sweep * fraction
        point_lat, point_lon = offset_latlon(
            base_lat, base_lon,
            centre_north + radius * math.cos(angle),
            centre_east + radius * math.sin(angle),
        )
        frames.append(FlightKeyframe(
            time_offset=duration * fraction,
            lat=point_lat,
            lon=point_lon,
            alt_ft_msl=alt_ft + 120.0 + climb_ft * fraction,
        ))
    return frames


def orbit_camera(duration: float = 36.0) -> list[CameraKeyframe]:
    """Walks the azimuth one way around the subject at a near-constant radius.

    Doubling back would spline the camera straight through the airframe.
    """
    return [
        CameraKeyframe(time_offset=0.0,
                       position=BodyPosition(ref="CG", x_m=-70.0, y_m=25.0, z_m=-130.0),
                       look_at=LookAtAircraft(ref="CG"),
                       easing=Easing(ease_out=1.0), fov_deg=60.0),
        CameraKeyframe(time_offset=duration * 0.35,
                       position=BodyPosition(ref="CG", x_m=135.0, y_m=20.0, z_m=-35.0),
                       look_at=LookAtAircraft(ref="CG")),
        CameraKeyframe(time_offset=duration * 0.70,
                       position=BodyPosition(ref="CG", x_m=50.0, y_m=12.0, z_m=135.0),
                       look_at=LookAtAircraft(ref="NOSE")),
        CameraKeyframe(time_offset=duration,
                       position=BodyPosition(ref="CG", x_m=-70.0, y_m=45.0, z_m=120.0),
                       look_at=LookAtAircraft(ref="CG"),
                       easing=Easing(ease_in=1.0)),
    ]


def starter_path(path_id: str, lat: float, lon: float, alt_ft: float,
                 heading: float, duration: float = 36.0,
                 entity: Entity = Entity.USER_AIRCRAFT) -> PathDocument:
    return PathDocument(
        meta=PathMeta(
            path_id=path_id,
            duration_seconds=duration,
            playback_mode=PlaybackMode.POSE_INJECTION,
            entity=entity,
            output_fps=30,
        ),
        flight_keyframes=banking_climb(lat, lon, alt_ft, heading, duration),
        camera_keyframes=orbit_camera(duration),
    )


def starter_at(path_id: str, location: str, duration: float = 36.0,
               entity: Entity = Entity.USER_AIRCRAFT) -> PathDocument:
    place = LOCATIONS[location]
    return starter_path(path_id, place.lat, place.lon, place.alt_ft_msl,
                        place.heading_deg_true, duration, entity)
