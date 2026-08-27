"""SSRF-aware outbound HTTP helper for server-side web calls.

This is an internal library, not a browser-facing open proxy. Image search,
importers, and similar features should call ``fetch_url`` instead of raw
``urllib.request.urlopen``.
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from email.message import Message
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 20
DEFAULT_MAX_BYTES = 8 * 1024 * 1024


class WebFetchError(Exception):
    """Outbound HTTP failed or was rejected."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass
class WebResponse:
    url: str
    status: int
    headers: dict[str, str]
    body: bytes

    def header(self, name: str, default: str = "") -> str:
        for key, value in self.headers.items():
            if key.lower() == name.lower():
                return value
        return default

    def content_length(self) -> int | None:
        content_range = self.header("Content-Range")
        if "/" in content_range:
            total = content_range.rsplit("/", 1)[-1]
            if total.isdigit() and int(total) > 1:
                return int(total)
        length = self.header("Content-Length")
        if length and length.isdigit() and int(length) > 1:
            return int(length)
        return None


def is_public_http_url(url: str) -> bool:
    """True when url is http(s) and resolves only to public unicast addresses."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
    return True


def _header_map(headers: Message | Mapping[str, str] | None) -> dict[str, str]:
    if headers is None:
        return {}
    if isinstance(headers, Mapping):
        return {str(k): str(v) for k, v in headers.items()}
    return {str(k): str(v) for k, v in headers.items()}


def fetch_url(
    url: str,
    *,
    method: str = "GET",
    headers: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int | None = DEFAULT_MAX_BYTES,
    range_header: str | None = None,
    allow_private: bool = False,
    raise_http_error: bool = True,
) -> WebResponse:
    """GET/HEAD a public URL with timeout, size cap, and SSRF checks.

    Set ``allow_private=True`` only for trusted first-party hosts. Never pass
    user-supplied URLs with that flag. Set ``raise_http_error=False`` when the
    caller wants headers from 4xx/5xx (for example Range Content-Length probes).
    """
    url = (url or "").strip()
    if not allow_private and not is_public_http_url(url):
        raise WebFetchError("URL is not allowed", status=400)

    merged = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "*/*"}
    if headers:
        merged.update(headers)
    if range_header:
        merged["Range"] = range_header

    req = Request(url, headers=merged, method=method.upper())
    try:
        with urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200) or 200
            hdrs = _header_map(resp.headers)
            body = _read_capped(resp, max_bytes)
            final_url = getattr(resp, "url", url) or url
            return WebResponse(url=final_url, status=status, headers=hdrs, body=body)
    except HTTPError as exc:
        hdrs = _header_map(exc.headers)
        body = b""
        try:
            raw = exc.read() if exc.fp else b""
            if max_bytes is not None:
                body = raw[: max_bytes + 1]
                if len(body) > max_bytes:
                    raise WebFetchError("Response too large", status=exc.code)
            else:
                body = raw
        except WebFetchError:
            raise
        except Exception:
            body = b""
        response = WebResponse(url=url, status=exc.code or 0, headers=hdrs, body=body)
        if not raise_http_error:
            return response
        raise WebFetchError(f"HTTP {exc.code}", status=exc.code)
    except (URLError, TimeoutError, ValueError, OSError) as exc:
        raise WebFetchError(str(exc) or "Request failed") from exc


def _read_capped(resp, max_bytes: int | None) -> bytes:
    if max_bytes is None:
        return resp.read()
    length = resp.headers.get("Content-Length")
    if length and length.isdigit() and int(length) > max_bytes:
        raise WebFetchError("Response too large", status=413)
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = resp.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise WebFetchError("Response too large", status=413)
        chunks.append(chunk)
    return b"".join(chunks)
