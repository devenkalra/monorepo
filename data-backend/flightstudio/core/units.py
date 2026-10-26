"""Units and frame conventions, per design section 2.2.

Everything stored and exchanged is feet MSL and degrees true. Metres appear only
inside geometry, and the camera's own distance unit appears only at the
SimConnect boundary.
"""

from __future__ import annotations

import math

FEET_PER_METRE = 3.280839895
METRES_PER_FOOT = 1.0 / FEET_PER_METRE
EARTH_RADIUS_M = 6_371_000.0
GRAVITY_MS2 = 9.80665
KNOTS_PER_MS = 1.943844

# Measured, not documented. See design section 3.7: the 6DOF distance parameter
# is neither feet nor metres. Re-measure with spike/calibrate_units.py if the
# camera ever lands in the wrong place on a different aircraft.
CAMERA_UNITS_PER_METRE = 1.0 / 1.309


def metres_to_camera_units(metres: float) -> float:
    return metres * CAMERA_UNITS_PER_METRE


def camera_units_to_metres(units: float) -> float:
    return units / CAMERA_UNITS_PER_METRE


def to_sim_attitude(pitch_deg: float, bank_deg: float) -> tuple[float, float]:
    """Nose-up and right-wing-down positive, into PLANE PITCH/BANK DEGREES.

    The simvars are the reverse on both axes: positive pitch is nose down and
    positive bank is left wing down. Readback cannot reveal this, so it was
    settled with screenshots (spike/probe_attitude_signs.py).
    """
    return -pitch_deg, -bank_deg


def from_sim_attitude(pitch_deg: float, bank_deg: float) -> tuple[float, float]:
    return -pitch_deg, -bank_deg


def world_to_body(north: float, east: float, up: float,
                  heading_deg: float, pitch_deg: float, bank_deg: float) -> tuple[float, float, float]:
    """A world vector in the aircraft's axes: (right, up, forward).

    Attitude is ours: heading true, pitch nose-up positive, bank right-wing-
    down positive, applied yaw then pitch then roll. The axes are the sim's
    body frame (X right, Y up, Z forward), so a forward speed is body Z.
    """
    theta, phi = math.radians(pitch_deg), math.radians(bank_deg)
    right, up, along = ned_to_body(north, east, up, heading_deg)
    forward = along * math.cos(theta) + up * math.sin(theta)
    up_pitched = -along * math.sin(theta) + up * math.cos(theta)
    return (
        right * math.cos(phi) - up_pitched * math.sin(phi),
        right * math.sin(phi) + up_pitched * math.cos(phi),
        forward,
    )


def body_rates(heading_rate: float, pitch_rate: float, bank_rate: float,
               pitch_deg: float, bank_deg: float) -> tuple[float, float, float]:
    """Euler-angle rates to body rates about (right, up, forward), same units in and out.

    Pitch rate about the right axis is nose-up positive, yaw rate about the up
    axis is right-turn positive, roll rate about the forward axis is right-
    wing-down positive. The standard kinematic relation, with our frame.
    """
    theta, phi = math.radians(pitch_deg), math.radians(bank_deg)
    pitch = pitch_rate * math.cos(phi) + heading_rate * math.cos(theta) * math.sin(phi)
    yaw = heading_rate * math.cos(theta) * math.cos(phi) - pitch_rate * math.sin(phi)
    roll = bank_rate - heading_rate * math.sin(theta)
    return pitch, yaw, roll


def feet_to_metres(feet: float) -> float:
    return feet * METRES_PER_FOOT


def metres_to_feet(metres: float) -> float:
    return metres * FEET_PER_METRE


def normalise_heading(degrees: float) -> float:
    return degrees % 360.0


def wrap_heading_180(degrees: float) -> float:
    """Heading in (−180, 180] — the range CameraSetRelative6DOF actually applies.

    The solver reports 0…360. A look left is then 270, and a look back is 180;
    the sim ignores both and the camera stays put. −90 and −180 are the same
    directions and take (report, 2026-10-12).
    """
    return ((degrees + 180.0) % 360.0) - 180.0


def heading_delta(from_deg: float, to_deg: float) -> float:
    """Shortest signed turn, so 350 -> 10 is +20 rather than -340.

    Design section 2.2: avoids the aircraft spinning the long way round north.
    """
    return ((to_deg - from_deg + 180.0) % 360.0) - 180.0


def interpolate_heading(from_deg: float, to_deg: float, fraction: float) -> float:
    return normalise_heading(from_deg + heading_delta(from_deg, to_deg) * fraction)


def unwrap_degrees(values: list[float]) -> list[float]:
    """Make a heading series continuous so it can be interpolated as numbers.

    350 followed by 10 becomes 350 then 370. Without this, splining the raw
    series would swing the nose 340 degrees the wrong way around north.
    """
    if not values:
        return []
    running = [values[0]]
    for value in values[1:]:
        running.append(running[-1] + heading_delta(running[-1], value))
    return running


def offset_latlon(lat: float, lon: float, north_m: float, east_m: float) -> tuple[float, float]:
    """Displace a position by a local north/east offset in metres."""
    d_lat = math.degrees(north_m / EARTH_RADIUS_M)
    d_lon = math.degrees(east_m / (EARTH_RADIUS_M * math.cos(math.radians(lat))))
    return lat + d_lat, lon + d_lon


def local_offset(
    from_lat: float, from_lon: float, to_lat: float, to_lon: float
) -> tuple[float, float]:
    """North/east metres from one position to another. Flat-earth, fine over a take."""
    north = math.radians(to_lat - from_lat) * EARTH_RADIUS_M
    east = math.radians(to_lon - from_lon) * EARTH_RADIUS_M * math.cos(math.radians(from_lat))
    return north, east


def ground_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    north, east = local_offset(lat1, lon1, lat2, lon2)
    return math.hypot(north, east)


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    north, east = local_offset(lat1, lon1, lat2, lon2)
    return normalise_heading(math.degrees(math.atan2(east, north)))


def ned_to_body(
    north_m: float, east_m: float, up_m: float, heading_deg: float
) -> tuple[float, float, float]:
    """World offset to aircraft body frame: X right, Y up, Z forward."""
    h = math.radians(heading_deg)
    forward = north_m * math.cos(h) + east_m * math.sin(h)
    right = -north_m * math.sin(h) + east_m * math.cos(h)
    return right, up_m, forward


def body_to_ned(
    right_m: float, up_m: float, forward_m: float, heading_deg: float
) -> tuple[float, float, float]:
    h = math.radians(heading_deg)
    north = forward_m * math.cos(h) - right_m * math.sin(h)
    east = forward_m * math.sin(h) + right_m * math.cos(h)
    return north, east, up_m
