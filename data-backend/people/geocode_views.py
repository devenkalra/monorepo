"""
Geocoding API using OpenStreetMap Nominatim.
Provides forward (place name -> coords + elevation) and reverse (coords -> place name) geocoding.
"""
import time
import requests
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
OPEN_ELEVATION_BASE = "https://api.open-elevation.com/api/v1"
USER_AGENT = "BldrDojo/1.0 (contact@bldrdojo.com)"
MIN_DELAY = 1.1  # Nominatim usage policy: max 1 request per second
_last_request = 0.0


def _rate_limit():
    global _last_request
    elapsed = time.time() - _last_request
    if elapsed < MIN_DELAY:
        time.sleep(MIN_DELAY - elapsed)
    _last_request = time.time()


def _lookup_elevation(lat: float, lon: float):
    """Look up elevation (meters) for coordinates. Returns None on failure."""
    try:
        r = requests.get(
            f"{OPEN_ELEVATION_BASE}/lookup",
            params={"locations": f"{lat},{lon}"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        results = data.get("results", [])
        if results and "elevation" in results[0]:
            return float(results[0]["elevation"])
    except (requests.RequestException, (KeyError, ValueError, TypeError)):
        pass
    return None


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def geocode_forward(request):
    """
    Geocode a place name to coordinates and elevation.
    Query params: q (place name/address)
    Returns: { latitude, longitude, name, elevation? }
    """
    q = request.query_params.get("q", "").strip()
    if not q:
        return Response({"error": "Missing 'q' parameter"}, status=status.HTTP_400_BAD_REQUEST)

    _rate_limit()
    try:
        r = requests.get(
            f"{NOMINATIM_BASE}/search",
            params={"format": "jsonv2", "q": q, "limit": "1"},
            headers={"User-Agent": USER_AGENT},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        if not data:
            return Response({"error": "No results found"}, status=status.HTTP_404_NOT_FOUND)
        hit = data[0]
        lat = float(hit["lat"])
        lon = float(hit["lon"])
        name = hit.get("display_name", q)

        # Look up elevation for the coordinates
        elevation = _lookup_elevation(lat, lon)

        result = {
            "latitude": lat,
            "longitude": lon,
            "name": name,
        }
        if elevation is not None:
            result["elevation"] = elevation

        return Response(result)
    except requests.RequestException as e:
        return Response({"error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def geocode_reverse(request):
    """
    Reverse geocode coordinates to a place name.
    Query params: lat, lon
    Returns: { name }
    """
    try:
        lat = float(request.query_params.get("lat", ""))
        lon = float(request.query_params.get("lon", ""))
    except (ValueError, TypeError):
        return Response({"error": "Invalid or missing 'lat' and 'lon' parameters"}, status=status.HTTP_400_BAD_REQUEST)

    _rate_limit()
    try:
        r = requests.get(
            f"{NOMINATIM_BASE}/reverse",
            params={"format": "jsonv2", "lat": lat, "lon": lon, "zoom": "14", "addressdetails": "1"},
            headers={"User-Agent": USER_AGENT},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        name = data.get("display_name", "")
        return Response({"name": name})
    except requests.RequestException as e:
        return Response({"error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
