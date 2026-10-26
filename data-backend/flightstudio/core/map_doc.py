"""2D map presentation stored beside a path, not inside it.

The flight geometry stays on the PathDocument. Line style, a time-keyed map
camera (centre, zoom, rotation) and labelled markers live in ``{id}.2d.json``
so a shot can be copied without the overlay, and the overlay can be edited
without rewriting a long recording.
"""

from __future__ import annotations

from enum import StrEnum
from pydantic import BaseModel, Field, field_validator

MAP_SCHEMA_VERSION = 1


class LineDash(StrEnum):
    SOLID = "SOLID"
    DASH = "DASH"
    DOT = "DOT"


class LineStyle(BaseModel):
    """One stroke for every authored leg, straight or smooth."""

    color: str = "#4ea1ff"
    width_px: float = Field(default=3.0, ge=0.5, le=20.0)
    opacity: float = Field(default=0.95, ge=0.05, le=1.0)
    dash: LineDash = LineDash.SOLID

    @field_validator("color")
    @classmethod
    def _hex_color(cls, value: str) -> str:
        return normalize_hex_color(value)


class MapCameraKeyframe(BaseModel):
    """Where the 2D map is looking at one instant of path time."""

    time_offset: float = Field(ge=0.0)
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    zoom: float = Field(default=14.0, ge=2.0, le=22.0)
    rotation_deg: float = 0.0


class MarkerIcon(StrEnum):
    PIN = "PIN"
    NOTE = "NOTE"
    FLAG = "FLAG"
    AIRPORT = "AIRPORT"


class LabelDisplay(StrEnum):
    HIDDEN = "HIDDEN"
    RIGHT = "RIGHT"
    LEFT = "LEFT"
    ABOVE = "ABOVE"
    BELOW = "BELOW"


class LabelWeight(StrEnum):
    NORMAL = "NORMAL"
    BOLD = "BOLD"


def normalize_hex_color(value: str) -> str:
    text = value.strip()
    if len(text) == 4 and text.startswith("#") and all(c in "0123456789abcdefABCDEF" for c in text[1:]):
        return "#" + "".join(c * 2 for c in text[1:])
    if not (len(text) == 7 and text.startswith("#")
            and all(c in "0123456789abcdefABCDEF" for c in text[1:])):
        raise ValueError("color must be a #rrggbb hex value")
    return text.lower()


class LabelStyle(BaseModel):
    """How the marker's text is drawn on the map. HIDDEN keeps the pin only."""

    display: LabelDisplay = LabelDisplay.RIGHT
    color: str = "#dfe4ec"
    size_px: float = Field(default=12.0, ge=8.0, le=32.0)
    weight: LabelWeight = LabelWeight.NORMAL
    gap_px: float = Field(default=6.0, ge=0.0, le=48.0)

    @field_validator("color")
    @classmethod
    def _hex_color(cls, value: str) -> str:
        return normalize_hex_color(value)


class MapMarker(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    text: str = ""
    icon: MarkerIcon = MarkerIcon.PIN
    outline: bool = False
    label: LabelStyle = Field(default_factory=LabelStyle)
    # Data URL (image/png or image/jpeg). Kept in this file so one overlay
    # travels with the shot.
    picture: str | None = None
    # Optional: hide until this path time during 2D play. None is always on.
    time_offset: float | None = Field(default=None, ge=0.0)


class MapDocument(BaseModel):
    path_id: str
    schema_version: int = MAP_SCHEMA_VERSION
    line: LineStyle = Field(default_factory=LineStyle)
    map_keyframes: list[MapCameraKeyframe] = Field(default_factory=list)
    markers: list[MapMarker] = Field(default_factory=list)

    @field_validator("map_keyframes")
    @classmethod
    def _sorted_cameras(cls, value: list[MapCameraKeyframe]) -> list[MapCameraKeyframe]:
        return sorted(value, key=lambda k: k.time_offset)


def empty_map_document(path_id: str) -> MapDocument:
    return MapDocument(path_id=path_id)


def _lerp(a: float, b: float, u: float) -> float:
    return a + (b - a) * u


def _lerp_heading(a: float, b: float, u: float) -> float:
    delta = (b - a + 180.0) % 360.0 - 180.0
    return (a + delta * u) % 360.0


def map_view_at(keyframes: list[MapCameraKeyframe], t: float) -> MapCameraKeyframe | None:
    """Interpolated map camera at path time t. None if no keys are authored."""
    if not keyframes:
        return None
    frames = sorted(keyframes, key=lambda k: k.time_offset)
    if t <= frames[0].time_offset:
        return frames[0]
    if t >= frames[-1].time_offset:
        return frames[-1]
    for start, end in zip(frames, frames[1:]):
        if t > end.time_offset:
            continue
        span = end.time_offset - start.time_offset
        u = 0.0 if span <= 1e-9 else (t - start.time_offset) / span
        return MapCameraKeyframe(
            time_offset=t,
            lat=_lerp(start.lat, end.lat, u),
            lon=_lerp(start.lon, end.lon, u),
            zoom=_lerp(start.zoom, end.zoom, u),
            rotation_deg=_lerp_heading(start.rotation_deg, end.rotation_deg, u),
        )
    return frames[-1]


def leaflet_dash(style: LineStyle) -> str | None:
    if style.dash is LineDash.DASH:
        return "8 6"
    if style.dash is LineDash.DOT:
        return "1 6"
    return None
