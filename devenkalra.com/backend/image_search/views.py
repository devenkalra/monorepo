from urllib.parse import quote

from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from core.http_client import WebFetchError
from image_search.bing import SAFE_SEARCH, search_images
from image_search.quality import (
    MIME_BY_EXT,
    build_download_zip,
    fetch_download_bytes,
    image_ext,
    parse_download_items,
    probe_quality,
    probe_sizes,
    safe_stem,
)


class ImageSearchAuthMixin:
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]


def _int_param(request, name, default, *, minimum=0, maximum=None):
    raw = request.query_params.get(name, default)
    try:
        value = int(raw or default)
    except (TypeError, ValueError):
        raise ValueError(name)
    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


class ImageSearchView(ImageSearchAuthMixin, APIView):
    @extend_schema(tags=["image-search"])
    def get(self, request):
        query = (request.query_params.get("q") or "").strip()
        if not query:
            return Response({"error": "Missing query"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            offset = _int_param(request, "offset", 0, minimum=0)
            count = _int_param(request, "count", 35, minimum=1, maximum=50)
            min_width = _int_param(request, "min_width", 0, minimum=0)
            min_height = _int_param(request, "min_height", 0, minimum=0)
        except ValueError:
            return Response({"error": "Invalid numeric parameter"}, status=status.HTTP_400_BAD_REQUEST)
        size = request.query_params.get("size") or ""
        aspect = request.query_params.get("aspect") or ""
        date = request.query_params.get("date") or ""
        safe = (request.query_params.get("safe") or "moderate").strip().lower()
        if safe not in SAFE_SEARCH:
            safe = "moderate"
        try:
            payload = search_images(
                query,
                offset=offset,
                count=count,
                size=size,
                aspect=aspect,
                date=date,
                safe=safe,
                min_width=min_width,
                min_height=min_height,
            )
        except WebFetchError as exc:
            return Response(
                {"error": f"Bing request failed: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(payload)


class ImageSizesView(ImageSearchAuthMixin, APIView):
    @extend_schema(tags=["image-search"])
    def post(self, request):
        urls = request.data.get("urls") or []
        if not isinstance(urls, list):
            return Response({"error": "urls must be a list"}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"sizes": probe_sizes([str(u) for u in urls[:80]])})


class ImageQualityView(ImageSearchAuthMixin, APIView):
    @extend_schema(tags=["image-search"])
    def post(self, request):
        items = request.data.get("items") or []
        if not isinstance(items, list):
            return Response({"error": "items must be a list"}, status=status.HTTP_400_BAD_REQUEST)
        cleaned = []
        for item in items[:40]:
            if isinstance(item, dict) and item.get("url"):
                cleaned.append(item)
        return Response({"quality": probe_quality(cleaned)})


class ImageDownloadView(ImageSearchAuthMixin, APIView):
    @extend_schema(tags=["image-search"])
    def post(self, request):
        items = parse_download_items(request.data if isinstance(request.data, dict) else {})
        if not items:
            return Response({"error": "Missing url"}, status=status.HTTP_400_BAD_REQUEST)
        fetched = fetch_download_bytes(items)
        if len(items) == 1:
            item, data = fetched[0]
            if not data:
                return Response(
                    {"error": "Could not download image"},
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            url = item["url"]
            ext = image_ext(data, url)
            name = f"{safe_stem(item.get('title') or '', url)}{ext}"
            mime = MIME_BY_EXT.get(ext, "application/octet-stream")
            response = HttpResponse(data, content_type=mime)
            response["Content-Disposition"] = (
                f'attachment; filename="{name}"; filename*=UTF-8\'\'{quote(name)}'
            )
            return response
        zdata = build_download_zip(fetched)
        if not zdata:
            return Response(
                {"error": "Could not download the selected images"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        response = HttpResponse(zdata, content_type="application/zip")
        response["Content-Disposition"] = 'attachment; filename="bing-images.zip"'
        return response
