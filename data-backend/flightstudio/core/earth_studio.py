"""Google Earth Studio project (.esp) for a solved flight path.

File > Import or drag the file into Earth Studio. The Earth Studio camera is
the cinematic camera (world position, pan from look heading, tilt from look
pitch). With no cinematic keys it follows the aircraft instead.
.esp is the importable project; .esb is the same format with KMLs bundled.
"""

from __future__ import annotations

from .camera_path import SolvedCameraPath
from .flight_path import SolvedFlightPath
from .schema import PathDocument

FT_TO_M = 0.3048

LON_MIN, LON_MAX = -180.0, 180.0
LAT_MIN, LAT_MAX = -90.0, 90.0
ALT_MIN, ALT_MAX = -500.0, 65117481.0
PAN_MIN, PAN_MAX = 0.0, 360.0
TILT_MIN, TILT_MAX = 0.0, 180.0
FOV_MIN, FOV_MAX = 0.0, 180.0
DEFAULT_FOV_DEG = 60.0
# GES interpolates lat/lon/pan linearly. A 1 s step drifts from the solver
# (and the in-app 3D view) on a tight orbit. Quarter-second keys stay close
# without writing one key per output frame.
KEY_STEP_S = 0.25


def _rel(value: float, lo: float, hi: float) -> float:
    return (value - lo) / (hi - lo)


def _unwrap_heading(degrees: list[float]) -> list[float]:
    out: list[float] = []
    prev: float | None = None
    for raw in degrees:
        heading = raw % 360.0
        if prev is not None:
            while heading - prev > 180.0:
                heading -= 360.0
            while heading - prev < -180.0:
                heading += 360.0
        out.append(heading)
        prev = heading
    return out


def _keys(times: list[float], values: list[float]) -> list[dict]:
    return [{"time": t, "value": v} for t, v in zip(times, values)]


def _channel(
    type_name: str,
    keyframes: list[dict],
    *,
    lo: float | None = None,
    hi: float | None = None,
    logarithmic: bool | None = None,
) -> dict:
    value: dict = {"relative": keyframes[0]["value"] if keyframes else 0.0}
    if lo is not None:
        value["minValueRange"] = lo
    if hi is not None:
        value["maxValueRange"] = hi
    if logarithmic is not None:
        value["logarithmic"] = logarithmic
    return {
        "type": type_name,
        "value": value,
        "keyframes": keyframes,
        "inTimeline": True,
    }


def _ges_heading_pitch(camera: SolvedCameraPath | None, t: float, pose, view):
    """Same world heading / pitch the 3D view uses (preview camera_track)."""
    if view is None or camera is None:
        return pose.heading_deg_true, pose.pitch_deg
    _lat, _lon, _alt, heading, pitch = view
    return heading, pitch


def _fov_deg(camera: SolvedCameraPath | None, t: float) -> float:
    if camera is None:
        return DEFAULT_FOV_DEG
    return camera.fov_at(t, DEFAULT_FOV_DEG)


def earth_studio_document(document: PathDocument) -> dict:
    """Build an importable Earth Studio project that flies the solved track."""
    if len(document.flight_keyframes) < 2:
        raise ValueError("Need a flight path with at least two waypoints.")
    flight = SolvedFlightPath.from_document(document)
    origin = flight.pose_at(0.0)
    camera = (
        SolvedCameraPath(document.camera_keyframes, origin.lat, origin.lon)
        if document.camera_keyframes
        else None
    )
    duration_s = max(document.duration, 1e-6)
    fps = max(1, min(120, int(document.meta.output_fps or 30)))
    frame_count = max(1, round(duration_s * fps))
    times_s = {0.0, duration_s}
    t = KEY_STEP_S
    while t < duration_s - 1e-9:
        times_s.add(t)
        t += KEY_STEP_S
    for key in document.flight_keyframes:
        if 0.0 <= key.time_offset <= duration_s:
            times_s.add(key.time_offset)
    for key in document.camera_keyframes:
        if 0.0 <= key.time_offset <= duration_s:
            times_s.add(key.time_offset)
    times = [sample / duration_s for sample in sorted(times_s)]

    lons: list[float] = []
    lats: list[float] = []
    alts: list[float] = []
    headings: list[float] = []
    tilts: list[float] = []
    fovs: list[float] = []
    for time01 in times:
        t = duration_s * time01
        pose = flight.pose_at(t)
        view = camera.world_view_at(t, pose) if camera else None
        if view is not None:
            lat, lon, alt_ft, _h, _p = view
        else:
            lat, lon, alt_ft = pose.lat, pose.lon, pose.alt_ft_msl
        heading, pitch = _ges_heading_pitch(camera, t, pose, view)
        lons.append(_rel(lon, LON_MIN, LON_MAX))
        lats.append(_rel(lat, LAT_MIN, LAT_MAX))
        alts.append(_rel(alt_ft * FT_TO_M, ALT_MIN, ALT_MAX))
        headings.append(heading)
        tilt = min(TILT_MAX, max(TILT_MIN, 90.0 + pitch))
        tilts.append(_rel(tilt, TILT_MIN, TILT_MAX))
        fov = min(FOV_MAX, max(FOV_MIN, _fov_deg(camera, t)))
        fovs.append(_rel(fov, FOV_MIN, FOV_MAX))

    pans = [_rel(h, PAN_MIN, PAN_MAX) for h in _unwrap_heading(headings)]

    return {
        "modelVersion": 18,
        "settings": {
            "name": document.meta.path_id,
            "frameRate": fps,
            "dimensions": {"width": 1920, "height": 1080},
            "duration": frame_count,
            "timeFormat": "frames",
        },
        "scenes": [
            {
                "animationModel": {
                    "roving": False,
                    "logarithmic": False,
                    "groupedPosition": True,
                },
                "duration": frame_count,
                "attributes": [
                    {
                        "type": "cameraGroup",
                        "inTimeline": True,
                        "attributes": [
                            {
                                "type": "cameraPositionGroup",
                                "inTimeline": True,
                                "attributes": [
                                    {
                                        "type": "position",
                                        "inTimeline": True,
                                        "attributes": [
                                            _channel("longitude", _keys(times, lons)),
                                            _channel("latitude", _keys(times, lats)),
                                            _channel(
                                                "altitude",
                                                _keys(times, alts),
                                                lo=ALT_MIN,
                                                hi=ALT_MAX,
                                                logarithmic=False,
                                            ),
                                        ],
                                    }
                                ],
                            },
                            {
                                "type": "cameraRotationGroup",
                                "inTimeline": True,
                                "attributes": [
                                    _channel(
                                        "rotationX",
                                        _keys(times, pans),
                                        lo=PAN_MIN,
                                        hi=PAN_MAX,
                                    ),
                                    _channel(
                                        "rotationY",
                                        _keys(times, tilts),
                                        lo=TILT_MIN,
                                        hi=TILT_MAX,
                                    ),
                                    {"type": "rotationZ", "value": {"relative": 0.0}},
                                ],
                            },
                            {
                                "type": "cameraLensGroup",
                                "inTimeline": True,
                                "attributes": [
                                    _channel(
                                        "fov",
                                        _keys(times, fovs),
                                        lo=FOV_MIN,
                                        hi=FOV_MAX,
                                    ),
                                ],
                            },
                        ],
                    }
                ],
                "cameraExport": {"logarithmic": False, "modelVersion": 2},
            }
        ],
        "playbackManager": {"range": {"start": 0, "end": frame_count}},
    }
