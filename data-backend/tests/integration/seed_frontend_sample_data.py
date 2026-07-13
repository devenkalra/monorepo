from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
from io import BytesIO
from typing import Dict, List, Tuple
from urllib.parse import quote

from e2e.client import E2EApiClient
from e2e.config import load_config


# Valid 1x1 PNG (transparent) to avoid external image dependencies.
_ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+X3mQAAAAASUVORK5CYII="
)


def _require_status(response, expected: Tuple[int, ...], context: str) -> Dict:
    if response.status_code not in expected:
        raise RuntimeError(f"{context} failed: {response.status_code} {response.text}")
    try:
        return response.json() if response.content else {}
    except ValueError:
        return {}


def _upload_file(client: E2EApiClient, filename: str, content: bytes, content_type: str) -> str:
    response = client.post(
        "/api/upload/",
        files={"file": (filename, BytesIO(content), content_type)},
    )
    payload = _require_status(response, (200, 201), f"upload {filename}")
    url = payload.get("url")
    if not url:
        raise RuntimeError(f"Upload missing url for {filename}: {payload}")
    return str(url)


def _create_entity(client: E2EApiClient, endpoint: str, payload: Dict, label: str) -> str:
    response = client.post(endpoint, json=payload)
    data = _require_status(response, (201,), f"create {label}")
    entity_id = data.get("id")
    if not entity_id:
        raise RuntimeError(f"create {label} missing id: {data}")
    return str(entity_id)


def _create_relation(client: E2EApiClient, from_id: str, to_id: str, relation_type: str) -> bool:
    response = client.post(
        "/api/relations/",
        json={
            "from_entity": from_id,
            "to_entity": to_id,
            "relation_type": relation_type,
        },
    )
    if response.status_code in (200, 201):
        return True
    body = (response.text or "").strip().replace("\n", " ")
    if len(body) > 300:
        body = body[:300] + "..."
    print(
        f"Warning: relation {from_id} -> {to_id} ({relation_type}) failed: "
        f"{response.status_code} {body}"
    )
    return False


def _next_short_tag(client: E2EApiClient) -> str:
    response = client.get("/api/tags/")
    if response.status_code != 200:
        return "FD01"

    try:
        payload = response.json() if response.content else []
    except ValueError:
        return "FD01"

    items = payload if isinstance(payload, list) else payload.get("results", [])
    existing = set()
    for item in items:
        if isinstance(item, dict):
            name = item.get("name")
            if isinstance(name, str):
                existing.add(name.strip())

    for idx in range(1, 100):
        candidate = f"FD{idx:02d}"
        if candidate not in existing:
            return candidate
    return "FD99"


def _delete_all_tags(client: E2EApiClient) -> int:
    response = client.get("/api/tags/")
    payload = _require_status(response, (200,), "list tags")

    items = payload if isinstance(payload, list) else payload.get("results", [])
    names: List[str] = []
    for item in items:
        if isinstance(item, dict):
            name = item.get("name")
            if isinstance(name, str) and name.strip():
                names.append(name.strip())

    deleted = 0
    for name in names:
        del_resp = client.delete(f"/api/tags/{quote(name, safe='')}/")
        if del_resp.status_code in (200, 204, 404):
            deleted += 1
            continue
        raise RuntimeError(f"delete tag '{name}' failed: {del_resp.status_code} {del_resp.text}")
    return deleted


def _delete_all_entities(client: E2EApiClient) -> int:
    deleted = 0

    response = client.get("/api/entities/?limit=10000")
    payload = _require_status(response, (200,), "list entities")

    if isinstance(payload, list):
        items = payload
    else:
        items = payload.get("results", []) if isinstance(payload, dict) else []

    for item in items:
        if not isinstance(item, dict):
            continue
        entity_id = item.get("id")
        if not entity_id:
            continue
        del_resp = client.delete(f"/api/entities/{entity_id}/")
        if del_resp.status_code in (200, 204, 404):
            deleted += 1
            continue
        raise RuntimeError(
            f"delete entity '{entity_id}' failed: {del_resp.status_code} {del_resp.text}"
        )

    return deleted


def seed_sample_data(client: E2EApiClient, dataset_tag: str, with_relations: bool) -> Dict[str, List[str]]:
    image_main = _upload_file(client, f"{dataset_tag}_profile.png", _ONE_PIXEL_PNG, "image/png")
    image_alt = _upload_file(client, f"{dataset_tag}_cover.png", _ONE_PIXEL_PNG, "image/png")
    attachment_text = _upload_file(
        client,
        f"{dataset_tag}_brief.txt",
        b"Frontend demo attachment\nContains sample context for interactive testing.\n",
        "text/plain",
    )

    common_fields = {
        "tags": [dataset_tag, "frontend-demo", "sample-data"],
        "urls": [
            "https://example.com/company/atlas-labs",
            "https://example.com/projects/northstar",
        ],
        "photos": [image_main],
        "attachments": [attachment_text],
        "locations": ["HQ - Building A, Floor 5", "Remote - Toronto, ON"],
    }

    created: Dict[str, List[str]] = {
        "people": [],
        "notes": [],
        "locations": [],
        "movies": [],
        "books": [],
        "containers": [],
        "assets": [],
        "orgs": [],
    }

    location_id = _create_entity(
        client,
        "/api/locations/",
        {
            "display": "Atlas HQ",
            "address1": "500 Mission Street",
            "address2": "Floor 5",
            "city": "San Francisco",
            "state": "California",
            "country": "United States",
            "postal_code": "94105",
            **common_fields,
        },
        "location",
    )
    created["locations"].append(location_id)

    org_id = _create_entity(
        client,
        "/api/orgs/",
        {
            "display": "Atlas Labs, Inc.",
            "name": "Atlas Labs, Inc.",
            "kind": "Company",
            "photos": [image_alt],
            **common_fields,
        },
        "org",
    )
    created["orgs"].append(org_id)

    person_1_id = _create_entity(
        client,
        "/api/people/",
        {
            "display": "Dr. Maya Patel",
            "first_name": "Maya",
            "last_name": "Patel",
            "profession": "Product Lead",
            "description": "Leads customer discovery for the Northstar program.",
            "phones": ["+1-415-555-0108", "+1-650-555-0191"],
            **common_fields,
        },
        "person maya",
    )
    created["people"].append(person_1_id)

    person_2_id = _create_entity(
        client,
        "/api/people/",
        {
            "display": "Jordan O'Neill",
            "first_name": "Jordan",
            "last_name": "O'Neill",
            "profession": "ML Engineer",
            "description": "Builds search and recommendation features for people graph.",
            "phones": ["+1-206-555-0134"],
            "photos": [image_alt],
            **common_fields,
        },
        "person jordan",
    )
    created["people"].append(person_2_id)

    person_3_id = _create_entity(
        client,
        "/api/people/",
        {
            "display": "Elena Rossi",
            "first_name": "Elena",
            "last_name": "Rossi",
            "profession": "Content Archivist",
            "description": "Curates media relationships for frontend graph exploration scenarios.",
            "phones": ["+1-310-555-0142"],
            **common_fields,
        },
        "person elena",
    )
    created["people"].append(person_3_id)

    person_4_id = _create_entity(
        client,
        "/api/people/",
        {
            "display": "William Shakespeare",
            "first_name": "William",
            "last_name": "Shakespeare",
            "profession": "Playwright",
            "description": "Canonical author node for Shakespeare-themed graph exploration.",
            "phones": ["+44-20-5555-1600"],
            **common_fields,
        },
        "person shakespeare",
    )
    created["people"].append(person_4_id)

    person_5_id = _create_entity(
        client,
        "/api/people/",
        {
            "display": "George R. R. Martin",
            "first_name": "George",
            "last_name": "Martin",
            "profession": "Novelist",
            "description": "Author of A Song of Ice and Fire.",
            "phones": ["+1-505-555-0196"],
            **common_fields,
        },
        "person grrm",
    )
    created["people"].append(person_5_id)

    person_6_id = _create_entity(
        client,
        "/api/people/",
        {
            "display": "Francis Ford Coppola",
            "first_name": "Francis",
            "last_name": "Coppola",
            "profession": "Director",
            "description": "Director reference for The Godfather relation chain.",
            "phones": ["+1-415-555-1972"],
            **common_fields,
        },
        "person coppola",
    )
    created["people"].append(person_6_id)

    person_7_id = _create_entity(
        client,
        "/api/people/",
        {
            "display": "Peter Dinklage",
            "first_name": "Peter",
            "last_name": "Dinklage",
            "profession": "Actor",
            "description": "Actor node tied to Game of Thrones entries.",
            "phones": ["+1-212-555-2011"],
            **common_fields,
        },
        "person dinklage",
    )
    created["people"].append(person_7_id)

    person_8_id = _create_entity(
        client,
        "/api/people/",
        {
            "display": "Al Pacino",
            "first_name": "Al",
            "last_name": "Pacino",
            "profession": "Actor",
            "description": "Actor node tied to The Godfather entries.",
            "phones": ["+1-323-555-1972"],
            **common_fields,
        },
        "person pacino",
    )
    created["people"].append(person_8_id)

    note_id = _create_entity(
        client,
        "/api/notes/",
        {
            "display": "Q3 Planning Notes",
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "description": "Priorities: relevance tuning, import dedupe, and frontend usability checks.",
            **common_fields,
        },
        "note",
    )
    created["notes"].append(note_id)

    note_2_id = _create_entity(
        client,
        "/api/notes/",
        {
            "display": "Shakespeare and Epic Sagas Research",
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "description": "Compare themes across Shakespeare, Game of Thrones, and The Godfather for graph demos.",
            **common_fields,
        },
        "note media research",
    )
    created["notes"].append(note_2_id)

    movie_id = _create_entity(
        client,
        "/api/movies/",
        {
            "display": "The Godfather",
            "description": "Crime classic used as an anchor title in recommendation demos.",
            "year": 1972,
            "language": "English",
            "country": "United States",
            **common_fields,
        },
        "movie godfather",
    )
    created["movies"].append(movie_id)

    movie_2_id = _create_entity(
        client,
        "/api/movies/",
        {
            "display": "Shakespeare in Love",
            "description": "Shakespeare-related title for richer search and relation traversal.",
            "year": 1998,
            "language": "English",
            "country": "United Kingdom",
            **common_fields,
        },
        "movie shakespeare",
    )
    created["movies"].append(movie_2_id)

    movie_3_id = _create_entity(
        client,
        "/api/movies/",
        {
            "display": "Game of Thrones",
            "description": "Fantasy epic title for partial search and graph navigation demos.",
            "year": 2011,
            "language": "English",
            "country": "United States",
            **common_fields,
        },
        "movie game of thrones",
    )
    created["movies"].append(movie_3_id)

    book_id = _create_entity(
        client,
        "/api/books/",
        {
            "display": "Hamlet",
            "year": 1603,
            "language": "English",
            "country": "England",
            "summary": "Shakespeare tragedy used as a canonical literary seed in relation demos.",
            **common_fields,
        },
        "book hamlet",
    )
    created["books"].append(book_id)

    book_2_id = _create_entity(
        client,
        "/api/books/",
        {
            "display": "A Game of Thrones",
            "year": 1996,
            "language": "English",
            "country": "United States",
            "summary": "Fantasy novel seed to pair with the Game of Thrones adaptation.",
            **common_fields,
        },
        "book game of thrones",
    )
    created["books"].append(book_2_id)

    container_id = _create_entity(
        client,
        "/api/containers/",
        {
            "display": "Archive Box A-17",
            "description": "Physical archive for signed contracts and procurement docs.",
            **common_fields,
        },
        "container",
    )
    created["containers"].append(container_id)

    asset_id = _create_entity(
        client,
        "/api/assets/",
        {
            "display": "Canon EOS R6",
            "description": "Event camera for product launch media.",
            "value": "2499.00",
            "acquired_on": "2025-03-11",
            **common_fields,
        },
        "asset",
    )
    created["assets"].append(asset_id)

    if with_relations:
        # Use schema-valid relation types by entity pair to avoid ValidationError.
        _create_relation(client, person_1_id, person_2_id, "IS_FRIEND_OF")
        _create_relation(client, person_2_id, person_3_id, "IS_FRIEND_OF")
        _create_relation(client, person_4_id, person_5_id, "IS_COLLEAGUE_OF")
        _create_relation(client, person_6_id, person_8_id, "IS_COLLEAGUE_OF")
        _create_relation(client, person_7_id, person_5_id, "IS_COLLEAGUE_OF")
        _create_relation(client, person_1_id, org_id, "WORKS_AT")
        _create_relation(client, person_3_id, org_id, "IS_MEMBER_OF")
        _create_relation(client, person_5_id, org_id, "IS_MEMBER_OF")
        _create_relation(client, person_1_id, note_id, "IS_RELATED_TO")
        _create_relation(client, person_2_id, note_2_id, "IS_RELATED_TO")
        _create_relation(client, person_1_id, movie_id, "ACTED_IN")
        _create_relation(client, person_2_id, movie_2_id, "DIRECTED")
        _create_relation(client, person_3_id, movie_3_id, "ACTED_IN")
        _create_relation(client, movie_id, person_6_id, "HAS_DIRECTOR")
        _create_relation(client, movie_id, person_8_id, "HAS_ACTOR")
        _create_relation(client, movie_3_id, person_7_id, "HAS_ACTOR")
        _create_relation(client, movie_2_id, person_4_id, "HAS_ACTOR")
        _create_relation(client, book_id, person_3_id, "HAS_AS_AUTHOR")
        _create_relation(client, book_id, person_4_id, "HAS_AS_AUTHOR")
        _create_relation(client, book_2_id, person_5_id, "HAS_AS_AUTHOR")
        _create_relation(client, movie_id, movie_2_id, "IS_RELATED_TO")
        _create_relation(client, book_2_id, movie_3_id, "INSPIRED")
        _create_relation(client, note_2_id, book_id, "IS_RELATED_TO")
        _create_relation(client, org_id, movie_3_id, "IS_RELATED_TO")
        _create_relation(client, asset_id, container_id, "IS_LOCATED_IN")
        _create_relation(client, container_id, location_id, "IS_LOCATED_IN")

    return created


def _print_summary(base_url: str, dataset_tag: str, created: Dict[str, List[str]]) -> None:
    total = sum(len(v) for v in created.values())
    print("\nSample data seeded successfully")
    print(f"Base URL: {base_url}")
    print(f"Dataset tag: {dataset_tag}")
    print(f"Total entities: {total}")
    print("\nCreated IDs by type:")
    for key, ids in created.items():
        if ids:
            print(f"- {key}: {', '.join(ids)}")


if __name__ == "__main__":
    cfg = load_config()

    parser = argparse.ArgumentParser(description="Seed frontend demo data using backend APIs.")
    parser.add_argument("--base-url", default=cfg.base_url, help="Backend base URL")
    parser.add_argument("--email", default=cfg.email, help="Login email")
    parser.add_argument("--password", default=cfg.password, help="Login password")
    parser.add_argument("--timeout", type=int, default=cfg.timeout_seconds, help="HTTP timeout in seconds")
    parser.add_argument(
        "--tag",
        default=None,
        help="Tag prefix attached to all seeded entities",
    )
    parser.add_argument(
        "--no-relations",
        action="store_true",
        help="Create entities only, skip relation creation",
    )

    args = parser.parse_args()

    api = E2EApiClient(args.base_url, args.timeout)
    login = api.login(args.email, args.password)
    if login.status_code not in (200, 201):
        raise SystemExit(f"Login failed: {login.status_code} {login.body}")

    deleted_tags = _delete_all_tags(api)
    print(f"Deleted existing tags: {deleted_tags}")

    deleted_entities = _delete_all_entities(api)
    print(f"Deleted existing entities: {deleted_entities}")

    dataset_tag = (args.tag or "").strip() or _next_short_tag(api)
    seeded = seed_sample_data(api, dataset_tag, with_relations=not args.no_relations)
    _print_summary(args.base_url, dataset_tag, seeded)
