from __future__ import annotations

from typing import Any, Dict, List
from urllib.parse import quote

from .client import E2EApiClient


def _items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return [x for x in payload["results"] if isinstance(x, dict)]
    return []


def cleanup_suite_state(client: E2EApiClient) -> Dict[str, int]:
    """Delete current user's entities and tags before a suite starts."""
    deleted_entities = 0
    deleted_tags = 0

    # Delete entities first; relations cascade via model constraints/signals.
    while True:
        list_resp = client.get("/api/entities/?limit=10000")
        if list_resp.status_code != 200:
            raise RuntimeError(f"suite cleanup list entities failed: {list_resp.status_code} {list_resp.text}")
        entities = _items(client.json_or_empty(list_resp))
        if not entities:
            break

        for entity in entities:
            entity_id = entity.get("id")
            if not entity_id:
                continue
            del_resp = client.delete(f"/api/entities/{entity_id}/")
            if del_resp.status_code not in (200, 204, 404):
                raise RuntimeError(
                    f"suite cleanup delete entity {entity_id} failed: {del_resp.status_code} {del_resp.text}"
                )
            deleted_entities += 1

    # Delete remaining tags for the user.
    while True:
        tags_resp = client.get("/api/tags/")
        if tags_resp.status_code != 200:
            raise RuntimeError(f"suite cleanup list tags failed: {tags_resp.status_code} {tags_resp.text}")
        tags = _items(client.json_or_empty(tags_resp))
        if not tags:
            break

        for tag in tags:
            name = tag.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            del_resp = client.delete(f"/api/tags/{quote(name.strip(), safe='')}/")
            if del_resp.status_code not in (200, 204, 404):
                raise RuntimeError(
                    f"suite cleanup delete tag {name} failed: {del_resp.status_code} {del_resp.text}"
                )
            deleted_tags += 1

    return {
        "entities": deleted_entities,
        "tags": deleted_tags,
    }
