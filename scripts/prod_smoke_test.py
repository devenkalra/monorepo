#!/usr/bin/env python3
"""Production smoke tests for bldrdojo.com and devenkalra.com.

Usage:
  python scripts/prod_smoke_test.py --email dkchecking@gmail.com --password '...'
    python scripts/prod_smoke_test.py --bldr-token '<jwt>'
    python scripts/prod_smoke_test.py --bldr-refresh-token '<refresh-jwt>'

The script will:
1) Verify devenkalra.com home page content and media URL.
2) Login to bldrdojo.com as the supplied user.
3) Delete all entities owned by that user.
4) Run basic CRUD checks on /api/entities/.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.cookiejar import CookieJar
from typing import Any


class SmokeFailure(Exception):
    """Raised when any smoke test assertion fails."""


@dataclass
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.text())


class HttpClient:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.cookie_jar = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookie_jar))

    def request(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResponse:
        req_headers = {
            "User-Agent": "bldrdojo-prod-smoke/1.0",
            "Accept": "application/json, text/html, */*",
        }
        if headers:
            req_headers.update(headers)

        data = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            req_headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, method=method.upper(), data=data, headers=req_headers)
        try:
            with self.opener.open(request, timeout=self.timeout) as resp:
                return HttpResponse(
                    status=resp.status,
                    headers={k.lower(): v for k, v in resp.headers.items()},
                    body=resp.read(),
                )
        except urllib.error.HTTPError as exc:
            return HttpResponse(
                status=exc.code,
                headers={k.lower(): v for k, v in exc.headers.items()} if exc.headers else {},
                body=exc.read() if hasattr(exc, "read") else b"",
            )


def ok(msg: str) -> None:
    print(f"[ok] {msg}")


def step(msg: str) -> None:
    print(f"[step] {msg}")


def require(condition: bool, msg: str) -> None:
    if not condition:
        raise SmokeFailure(msg)


def join_url(base: str, path: str) -> str:
    return urllib.parse.urljoin(base.rstrip("/") + "/", path.lstrip("/"))


def parse_entity_list(payload: Any) -> tuple[list[dict[str, Any]], str | None]:
    if isinstance(payload, list):
        return payload, None
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return payload["results"], payload.get("next")
    raise SmokeFailure(f"Unexpected entity list response shape: {type(payload)}")


def check_devenkalra(client: HttpClient, base_url: str, media_url: str) -> None:
    step("Checking devenkalra.com SPA shell")
    home = client.request("GET", base_url)
    require(home.status == 200, f"devenkalra homepage returned {home.status}")
    home_html = home.text()
    require(
        ('id="root"' in home_html) or ("<div id='root'" in home_html),
        "devenkalra homepage does not look like SPA shell (missing root div)",
    )
    ok("devenkalra SPA shell is reachable")

    step("Checking devenkalra page API content for 'Who Am I'")
    page_api = client.request("GET", join_url(base_url, "/api/pages/who-am-i/"))
    require(page_api.status == 200, f"devenkalra page API returned {page_api.status}")
    page_json = page_api.json()
    title = str(page_json.get("title") or "")
    content = str(page_json.get("content") or "")
    require(
        ("Who Am I" in title) or ("Who Am I" in content),
        "devenkalra page API missing 'Who Am I' in title/content",
    )
    ok("devenkalra page API contains 'Who Am I'")

    step("Checking devenkalra media URL")
    media = client.request("GET", media_url)
    require(media.status == 200, f"devenkalra media URL returned {media.status}")
    content_type = media.headers.get("content-type", "")
    require(content_type.startswith("image/"), f"media content type is not image/*: {content_type}")
    require(len(media.body) > 0, "media response body is empty")
    ok(f"devenkalra media served successfully ({content_type})")


def login_bldrdojo(client: HttpClient, base_url: str, email: str, password: str) -> str | None:
    login_url = join_url(base_url, "/api/auth/login/")
    attempts: list[tuple[str, dict[str, str]]] = [
        ("email/password", {"email": email, "password": password}),
        ("username/password", {"username": email, "password": password}),
    ]
    failures: list[str] = []

    for label, payload in attempts:
        resp = client.request("POST", login_url, json_body=payload)
        if resp.status in (200, 201):
            try:
                body = resp.json()
            except Exception:
                body = {}
            token = None
            if isinstance(body, dict):
                token = body.get("access") or body.get("key")
            ok("bldrdojo login succeeded")
            return token
        body_snippet = resp.text().replace("\n", " ").strip()[:240]
        failures.append(f"{label}: status={resp.status}, body={body_snippet or '<empty>'}")

    raise SmokeFailure(
        "bldrdojo login failed for both email/password and username/password payload shapes. "
        + " | ".join(failures)
    )


def refresh_bldrdojo_access_token(client: HttpClient, base_url: str, refresh_token: str) -> str:
    refresh_url = join_url(base_url, "/api/auth/token/refresh/")
    resp = client.request("POST", refresh_url, json_body={"refresh": refresh_token})
    require(resp.status in (200, 201), f"bldrdojo token refresh failed with {resp.status}: {resp.text()[:300]}")

    body = resp.json()
    access = body.get("access") if isinstance(body, dict) else None
    require(bool(access), "bldrdojo token refresh response missing access token")
    ok("bldrdojo access token refreshed")
    return access


def validate_bldrdojo_token(client: HttpClient, base_url: str, token: str) -> bool:
    """Quick token validity check against authenticated user endpoint."""
    whoami_url = join_url(base_url, "/api/auth/user/")
    resp = client.request("GET", whoami_url, headers=auth_headers(token))
    return resp.status == 200


def resolve_bldrdojo_token(
    client: HttpClient,
    base_url: str,
    token_from_args: str | None,
    refresh_token: str | None,
    email: str | None,
    password: str | None,
) -> str:
    """Resolve auth token with fallback chain: bearer -> refresh -> email/password."""
    if token_from_args:
        if validate_bldrdojo_token(client, base_url, token_from_args):
            ok("using supplied bldrdojo bearer token")
            return token_from_args
        print("[warn] supplied bldrdojo bearer token is invalid; trying fallback auth methods")

    if refresh_token:
        try:
            return refresh_bldrdojo_access_token(client, base_url, refresh_token)
        except SmokeFailure as exc:
            print(f"[warn] refresh-token auth failed: {exc}")
            print("[warn] falling back to email/password auth")

    if email and password:
        return login_bldrdojo(client, base_url, email, password)

    raise SmokeFailure(
        "No working bldrdojo authentication method succeeded. "
        "Provide a valid --bldr-token or --bldr-refresh-token, or working --email/--password credentials."
    )


def auth_headers(token: str | None) -> dict[str, str]:
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def fetch_all_entities(client: HttpClient, base_url: str, token: str | None) -> list[dict[str, Any]]:
    entities_url = join_url(base_url, "/api/entities/")
    all_entities: list[dict[str, Any]] = []
    next_url: str | None = entities_url
    while next_url:
        resp = client.request("GET", next_url, headers=auth_headers(token))
        require(resp.status == 200, f"list entities failed with {resp.status}")
        items, next_url = parse_entity_list(resp.json())
        all_entities.extend(items)
    return all_entities


def delete_all_entities(client: HttpClient, base_url: str, token: str | None) -> int:
    entities = fetch_all_entities(client, base_url, token)
    deleted = 0
    for entity in entities:
        entity_id = entity.get("id")
        if not entity_id:
            continue
        delete_url = join_url(base_url, f"/api/entities/{entity_id}/")
        resp = client.request("DELETE", delete_url, headers=auth_headers(token))
        require(resp.status in (200, 202, 204), f"delete entity {entity_id} failed with {resp.status}")
        deleted += 1
    return deleted


def run_bldrdojo_crud(
    client: HttpClient,
    base_url: str,
    token: str | None,
    *,
    cleanup_before: bool = False,
    delete_after: bool = False,
) -> None:
    if cleanup_before:
        step("Cleaning existing entities for test user")
        deleted = delete_all_entities(client, base_url, token)
        ok(f"deleted {deleted} entities for test user")

    marker = "smoke-test-dkchecking"
    create_payload = {
        "type": "Note",
        "display": f"{marker}-create",
        "description": "Created by production smoke test",
        "tags": [marker],
    }

    step("Creating entity")
    create_url = join_url(base_url, "/api/notes/")
    create_resp = client.request("POST", create_url, json_body=create_payload, headers=auth_headers(token))
    require(create_resp.status in (200, 201), f"create entity failed with {create_resp.status}: {create_resp.text()[:300]}")
    created = create_resp.json()
    entity_id = created.get("id")
    require(bool(entity_id), "create entity response missing id")
    ok(f"entity created: {entity_id}")

    detail_url = join_url(base_url, f"/api/entities/{entity_id}/")
    step("Reading created entity")
    read_resp = client.request("GET", detail_url, headers=auth_headers(token))
    require(read_resp.status == 200, f"read entity failed with {read_resp.status}")
    read_body = read_resp.json()
    require(read_body.get("display") == create_payload["display"], "read entity display does not match create payload")
    ok("entity read verified")

    step("Updating entity")
    patch_payload = {
        "display": f"{marker}-updated",
        "description": "Updated by production smoke test",
    }
    patch_resp = client.request("PATCH", detail_url, json_body=patch_payload, headers=auth_headers(token))
    require(patch_resp.status in (200, 202), f"patch entity failed with {patch_resp.status}")

    verify_resp = client.request("GET", detail_url, headers=auth_headers(token))
    require(verify_resp.status == 200, f"verify updated entity failed with {verify_resp.status}")
    verify_body = verify_resp.json()
    require(verify_body.get("display") == patch_payload["display"], "updated display value not persisted")
    ok("entity update verified")

    if delete_after:
        step("Deleting entity")
        delete_resp = client.request("DELETE", detail_url, headers=auth_headers(token))
        require(delete_resp.status in (200, 202, 204), f"delete entity failed with {delete_resp.status}")

        final_read = client.request("GET", detail_url, headers=auth_headers(token))
        require(final_read.status == 404, f"entity should be deleted but GET returned {final_read.status}")
        ok("entity delete verified")
    else:
        ok(f"entity left in place for UI check: {entity_id}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run production smoke tests for bldrdojo.com + devenkalra.com")
    parser.add_argument("--bldr-base", default="https://bldrdojo.com", help="Base URL for bldrdojo API/app")
    parser.add_argument("--deven-base", default="https://devenkalra.com", help="Base URL for devenkalra site")
    parser.add_argument(
        "--deven-media-url",
        default="https://devenkalra.com/api/media/uploads/ywvrj4vp.png",
        help="Media URL expected to be available on devenkalra.com",
    )
    parser.add_argument("--email", help="bldrdojo test account email")
    parser.add_argument("--password", help="bldrdojo test account password")
    parser.add_argument("--bldr-token", help="Pre-issued Bearer token for bldrdojo API (useful for OAuth-only accounts)")
    parser.add_argument("--bldr-refresh-token", help="Refresh token to auto-mint a fresh bldrdojo access token")
    parser.add_argument(
        "--cleanup-before",
        action="store_true",
        help="Delete all current user's entities before running CRUD checks (default: off)",
    )
    parser.add_argument(
        "--delete-after",
        action="store_true",
        help="Delete the created test entity at the end (default: off so entity stays for UI checks)",
    )
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    email = args.email or os.environ.get("SMOKE_TEST_EMAIL")
    password = args.password or os.environ.get("SMOKE_TEST_PASSWORD")
    token_from_args = args.bldr_token or os.environ.get("BLDRDOJO_BEARER_TOKEN")
    refresh_token = args.bldr_refresh_token or os.environ.get("BLDRDOJO_REFRESH_TOKEN")

    if not token_from_args and not refresh_token and (not email or not password):
        print(
            "[fail] Missing bldrdojo auth. Provide --bldr-token (or BLDRDOJO_BEARER_TOKEN) "
            "or --bldr-refresh-token (or BLDRDOJO_REFRESH_TOKEN) "
            "or provide --email/--password (or SMOKE_TEST_EMAIL/SMOKE_TEST_PASSWORD)."
        )
        return 2

    client = HttpClient(timeout=args.timeout)

    try:
        step("Starting devenkalra smoke checks")
        check_devenkalra(client, args.deven_base, args.deven_media_url)

        step("Starting bldrdojo auth + cleanup + CRUD checks")
        token = resolve_bldrdojo_token(
            client,
            args.bldr_base,
            token_from_args,
            refresh_token,
            email,
            password,
        )
        run_bldrdojo_crud(
            client,
            args.bldr_base,
            token,
            cleanup_before=args.cleanup_before,
            delete_after=args.delete_after,
        )

        print("[ok] All smoke checks passed")
        return 0
    except SmokeFailure as exc:
        print(f"[fail] {exc}")
        return 2
    except Exception as exc:
        print(f"[fail] Unexpected error: {exc}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
