"""Nominatim place lookup for the waypoint inspector.

Search turns a name into lat/lon. Reverse names the current coordinates.
Requests go through our User-Agent; the browser never talks to OSM directly.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "FlightStudio/1.0 (local path editor)"
_REVERSE_CACHE: dict[tuple[float, float], dict] = {}


def _get_json(url: str) -> object:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Place lookup failed ({exc.code}).") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("Could not reach the place lookup service.") from exc


def _hit(item: dict) -> dict | None:
    try:
        lat = float(item["lat"])
        lon = float(item["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    label = str(item.get("display_name") or "").strip()
    if not label:
        return None
    return {"label": label, "lat": lat, "lon": lon}


def search_places(query: str, *, limit: int = 6, viewbox: str | None = None) -> list[dict]:
    """Forward geocode: place name → coordinates."""
    q = query.strip()
    if len(q) < 2:
        return []
    params: dict[str, str] = {
        "q": q,
        "format": "jsonv2",
        "limit": str(max(1, min(10, limit))),
    }
    if viewbox:
        params["viewbox"] = viewbox
        params["bounded"] = "0"
    data = _get_json(f"{NOMINATIM_SEARCH}?{urllib.parse.urlencode(params)}")
    if not isinstance(data, list):
        return []
    hits = []
    for item in data:
        if isinstance(item, dict) and (hit := _hit(item)):
            hits.append(hit)
    return hits


def reverse_place(lat: float, lon: float) -> dict | None:
    """Reverse geocode: coordinates → place name."""
    key = (round(lat, 4), round(lon, 4))
    if key in _REVERSE_CACHE:
        return _REVERSE_CACHE[key]
    params = urllib.parse.urlencode({
        "lat": f"{lat:.6f}",
        "lon": f"{lon:.6f}",
        "format": "jsonv2",
        "zoom": "10",
    })
    data = _get_json(f"{NOMINATIM_REVERSE}?{params}")
    hit = _hit(data) if isinstance(data, dict) else None
    if hit:
        _REVERSE_CACHE[key] = hit
    return hit
