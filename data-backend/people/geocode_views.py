"""
Geocoding API using OpenStreetMap Nominatim.
Provides forward (place name -> coords + elevation) and reverse (coords -> place name) geocoding.
"""
import io
import math
import time
import requests
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
import socket

from .utils import save_file_deduplicated

# Force IPv4 DNS resolution for requests inside the Docker container to avoid IPv6 routing errors
_orig_getaddrinfo = socket.getaddrinfo
def _getaddrinfo_ipv4(*args, **kwargs):
    responses = _orig_getaddrinfo(*args, **kwargs)
    return [r for r in responses if r[0] == socket.AF_INET]
socket.getaddrinfo = _getaddrinfo_ipv4

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


OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
MAP_ZOOM = 15
MAP_SIZE = 512
TILE_SIZE = 256


def _latlon_to_global_pixels(lat, lon, zoom):
    n = 2 ** zoom
    x = (float(lon) + 180.0) / 360.0 * n * TILE_SIZE
    lat_rad = math.radians(float(lat))
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n * TILE_SIZE
    return x, y


def _fetch_tile(z, x, y):
    from PIL import Image

    n = 2 ** z
    x = int(x) % n
    y = max(0, min(n - 1, int(y)))
    r = requests.get(
        OSM_TILE_URL.format(z=z, x=x, y=y),
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    r.raise_for_status()
    return Image.open(io.BytesIO(r.content)).convert("RGB")


def render_location_map_png(lat, lon, zoom=MAP_ZOOM, size=MAP_SIZE):
    """Stitch OSM tiles into a PNG centered on lat/lon with a marker."""
    from PIL import Image, ImageDraw

    cx, cy = _latlon_to_global_pixels(lat, lon, zoom)
    half = size / 2.0
    left = cx - half
    top = cy - half
    x0 = math.floor(left / TILE_SIZE)
    y0 = math.floor(top / TILE_SIZE)
    x1 = math.floor((left + size - 1) / TILE_SIZE)
    y1 = math.floor((top + size - 1) / TILE_SIZE)
    mosaic = Image.new(
        "RGB",
        ((x1 - x0 + 1) * TILE_SIZE, (y1 - y0 + 1) * TILE_SIZE),
        (230, 230, 230),
    )
    for ty in range(int(y0), int(y1) + 1):
        for tx in range(int(x0), int(x1) + 1):
            tile = _fetch_tile(zoom, tx, ty)
            mosaic.paste(tile, ((tx - int(x0)) * TILE_SIZE, (ty - int(y0)) * TILE_SIZE))
    crop_x = int(left - x0 * TILE_SIZE)
    crop_y = int(top - y0 * TILE_SIZE)
    image = mosaic.crop((crop_x, crop_y, crop_x + size, crop_y + size))
    draw = ImageDraw.Draw(image)
    mx = my = size / 2.0
    radius = 8
    draw.ellipse((mx - radius - 2, my - radius - 2, mx + radius + 2, my + radius + 2), fill=(255, 255, 255))
    draw.ellipse((mx - radius, my - radius, mx + radius, my + radius), fill=(220, 38, 38))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def geocode_map_thumbnail(request):
    """
    Build a map thumbnail for coordinates and store it like an uploaded attachment.
    Query/body: lat, lon, optional q/name for caption
    Returns: { url, thumbnail_url, filename, caption, latitude, longitude, sha256 }
    """
    params = request.query_params if request.method == "GET" else request.data
    try:
        lat = float(params.get("lat", ""))
        lon = float(params.get("lon", ""))
    except (ValueError, TypeError):
        return Response(
            {"error": "Invalid or missing 'lat' and 'lon' parameters"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return Response({"error": "Coordinates out of range"}, status=status.HTTP_400_BAD_REQUEST)

    name = str(params.get("q") or params.get("name") or "Map").strip() or "Map"
    try:
        png = render_location_map_png(lat, lon)
    except requests.RequestException as e:
        return Response({"error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    uploaded = SimpleUploadedFile("map.png", png, content_type="image/png")
    result = save_file_deduplicated(uploaded)
    result["filename"] = "map.png"
    result["caption"] = name
    result["latitude"] = lat
    result["longitude"] = lon
    return Response(result)
