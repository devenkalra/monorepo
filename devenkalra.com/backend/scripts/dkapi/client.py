"""HTTP client and resource helpers for the devenkalra.com API."""

from __future__ import annotations

import os
from typing import Any, Optional
from urllib.parse import urljoin

import requests


class ApiError(Exception):
    """Raised when the API returns a non-success status."""

    def __init__(
        self,
        status_code: int,
        detail: Any,
        response: Optional[requests.Response] = None,
    ):
        self.status_code = status_code
        self.detail = detail
        self.response = response
        super().__init__(f"HTTP {status_code}: {detail}")


class Resource:
    """Generic CRUD resource bound to a Client."""

    def __init__(self, client: "Client", path: str, id_field: str = "id"):
        self._client = client
        self.path = path.strip("/")
        self.id_field = id_field

    def list(self, **params: Any) -> Any:
        return self._client.request("GET", f"{self.path}/", params=params or None)

    def get(self, resource_id: Any) -> Any:
        return self._client.request("GET", f"{self.path}/{resource_id}/")

    def create(self, **data: Any) -> Any:
        return self._client.request("POST", f"{self.path}/", json=data)

    def update(self, resource_id: Any, **data: Any) -> Any:
        """Partial update (PATCH)."""
        return self._client.request("PATCH", f"{self.path}/{resource_id}/", json=data)

    def replace(self, resource_id: Any, **data: Any) -> Any:
        """Full replace (PUT)."""
        return self._client.request("PUT", f"{self.path}/{resource_id}/", json=data)

    def delete(self, resource_id: Any) -> Any:
        return self._client.request("DELETE", f"{self.path}/{resource_id}/")


class ReadOnlyResource:
    """List/get only (e.g. blog endpoints)."""

    def __init__(self, client: "Client", path: str):
        self._client = client
        self.path = path.strip("/")

    def list(self, **params: Any) -> Any:
        return self._client.request("GET", f"{self.path}/", params=params or None)

    def get(self, resource_id: Any) -> Any:
        return self._client.request("GET", f"{self.path}/{resource_id}/")


class PageDataResource:
    """GET/POST JSON blob keyed by page slug."""

    def __init__(self, client: "Client"):
        self._client = client

    def get(self, page_slug: str) -> Any:
        return self._client.request("GET", f"page-data/{page_slug}/")

    def set(self, page_slug: str, data: dict) -> Any:
        return self._client.request("POST", f"page-data/{page_slug}/", json=data)


class MenuResource:
    """Public nested menu tree (read-only)."""

    def __init__(self, client: "Client"):
        self._client = client

    def get(self) -> Any:
        return self._client.request("GET", "menu/")


class CommentsResource:
    def __init__(self, client: "Client"):
        self._client = client

    def list(self, post_slug: str) -> Any:
        return self._client.request("GET", f"blog/posts/{post_slug}/comments/")

    def create(self, post_slug: str, content: str) -> Any:
        return self._client.request(
            "POST",
            f"blog/posts/{post_slug}/comments/",
            json={"content": content},
        )


class Client:
    """
    API client.

    Auth: pass ``token`` or set env ``DK_API_TOKEN``.
    Base URL: pass ``base_url`` or set env ``DK_API_BASE``
    (default ``https://devenkalra.com/api``).
    """

    def __init__(
        self,
        token: Optional[str] = None,
        base_url: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ):
        self.base_url = (base_url or os.environ.get("DK_API_BASE") or "https://devenkalra.com/api").rstrip("/") + "/"
        self.token = token if token is not None else os.environ.get("DK_API_TOKEN", "")
        self.session = session or requests.Session()

        # Full CRUD (ViewSets)
        self.pages = Resource(self, "pages", id_field="slug")
        self.menu_items = Resource(self, "menu-items")
        self.projects = Resource(self, "projects")
        self.ideas = Resource(self, "ideas")
        self.books = Resource(self, "books")
        self.tracks = Resource(self, "tracks")
        self.recipes = Resource(self, "recipes")

        # Read-only blog
        self.blog_categories = ReadOnlyResource(self, "blog/categories")
        self.blog_tags = ReadOnlyResource(self, "blog/tags")
        self.blog_posts = ReadOnlyResource(self, "blog/posts")
        self.comments = CommentsResource(self)

        # Special endpoints
        self.menu = MenuResource(self)
        self.page_data = PageDataResource(self)

    @classmethod
    def from_env(cls) -> "Client":
        return cls()

    @classmethod
    def login(
        cls,
        username: str,
        password: str,
        base_url: Optional[str] = None,
    ) -> "Client":
        """Create a client by logging in (returns token-authenticated client)."""
        client = cls(token="", base_url=base_url)
        data = client.request(
            "POST",
            "auth/login/",
            json={"username": username, "password": password},
            auth=False,
        )
        token = data.get("token")
        if not token:
            raise ApiError(500, "Login response missing token")
        client.token = token
        return client

    def _headers(self, auth: bool = True) -> dict:
        headers = {"Accept": "application/json"}
        if auth and self.token:
            headers["Authorization"] = f"Token {self.token}"
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: Optional[dict] = None,
        auth: bool = True,
    ) -> Any:
        url = urljoin(self.base_url, path.lstrip("/"))
        response = self.session.request(
            method,
            url,
            headers=self._headers(auth=auth),
            json=json,
            params=params,
            timeout=60,
        )

        if response.status_code == 204:
            return None

        try:
            payload = response.json() if response.content else None
        except ValueError:
            payload = response.text

        if not response.ok:
            detail = payload
            if isinstance(payload, dict) and "detail" in payload:
                detail = payload["detail"]
            raise ApiError(response.status_code, detail, response)

        return payload
