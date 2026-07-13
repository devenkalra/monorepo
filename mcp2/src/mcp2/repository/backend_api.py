from __future__ import annotations

import re
from typing import Any, Callable
from uuid import UUID

import requests

from ..models import EntityRecord, KGSchema, RelationRecord, SchemaRelation


def _canonical_relationship(name: str) -> str:
    rel = (name or "").strip().casefold()
    if rel.startswith("is_"):
        rel = rel[3:]
    return rel


_UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)


def _redact_identifiers(text: str) -> str:
    return _UUID_PATTERN.sub("<id>", text)


class BackendAPIGraphRepository:
    """Graph repository backed by data-backend REST APIs.

    This repository delegates storage/traversal to the data-backend service
    (which can itself be backed by Neo4j), while exposing the generic
    GraphRepository interface used by mcp2 controller/tools.
    """

    def __init__(
        self,
        base_url: str,
        access_token: str | None = None,
        timeout_seconds: int = 30,
        schema_relations: list[str] | None = None,
        on_status_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        normalized = base_url.rstrip("/")
        if normalized.endswith("/api"):
            normalized = normalized[: -len("/api")]
        self.base_url = normalized
        self.access_token = access_token
        self.timeout_seconds = timeout_seconds
        defaults = ["child_of", "spouse_of", "works_at", "student_of", "lives_at", "parent_of"]
        self._schema_relations = schema_relations or defaults
        self._on_status_event = on_status_event

    def set_status_callback(self, callback: Callable[[dict[str, Any]], None] | None) -> None:
        self._on_status_event = callback

    def _emit_status(self, message: str, **extra: Any) -> None:
        if self._on_status_event is None:
            return
        payload: dict[str, Any] = {"phase": "backend_call", "message": message}
        payload.update(extra)
        self._on_status_event(payload)

    async def get_schema(self) -> KGSchema:
        relations = [
            SchemaRelation(name=r, source_type="Entity", target_type="Entity")
            for r in self._schema_relations
        ]
        return KGSchema(
            entity_types=["Person", "Org", "Place", "Event", "Document", "Unknown"],
            relations=relations,
        )

    async def search_entities(self, name_query: str) -> list[EntityRecord]:
        if not name_query.strip():
            return []
        self._emit_status(f"Searching entities: {name_query}", operation="search_entities", query=name_query)
        response = self._request(
            method="GET",
            path="/api/entities/",
            params={"search": name_query, "page_size": 20},
        )
        if response is None:
            return []

        payload = self._safe_json(response)
        if not isinstance(payload, dict):
            return []

        results = payload.get("results", [])
        out: list[EntityRecord] = []
        for row in results if isinstance(results, list) else []:
            if not isinstance(row, dict):
                continue
            entity_id = row.get("id")
            try:
                entity_uuid = UUID(str(entity_id))
            except Exception:
                continue
            out.append(
                EntityRecord(
                    uuid=entity_uuid,
                    entity_type=str(row.get("type") or "Unknown"),
                    display_name=str(row.get("display") or entity_id),
                    properties={},
                )
            )
        return out

    async def get_entity(self, entity_uuid: UUID) -> EntityRecord | None:
        response = self._request(method="GET", path=f"/api/entities/{entity_uuid}/")
        if response is None:
            return None

        payload = self._safe_json(response)
        if not isinstance(payload, dict):
            return None

        entity_type = str(payload.get("type") or "Unknown")
        display = str(payload.get("display") or payload.get("name") or str(entity_uuid))
        self._emit_status(f"Got entity: {display}", operation="get_entity", entity_id=str(entity_uuid))
        properties: dict[str, Any] = {}
        ignored_scalar_fields = {
            "id",
            "type",
            "display",
            "created_at",
            "updated_at",
            "user",
            "text_block",
            "entity_text_block",
            "outgoing_text_block",
            "incoming_text_block",
        }
        for key, value in payload.items():
            if key in ignored_scalar_fields:
                continue
            if isinstance(value, (dict, list)):
                continue
            if value is None:
                continue
            properties[key] = value

        return EntityRecord(
            uuid=entity_uuid,
            entity_type=entity_type,
            display_name=display,
            properties=properties,
        )

    async def get_outgoing_relations(
        self,
        entity_uuid: UUID,
        relationship: str | None = None,
    ) -> list[RelationRecord]:
        return await self._get_relations(entity_uuid, direction="outgoing", relationship=relationship)

    async def get_incoming_relations(
        self,
        entity_uuid: UUID,
        relationship: str | None = None,
    ) -> list[RelationRecord]:
        return await self._get_relations(entity_uuid, direction="incoming", relationship=relationship)

    async def _get_relations(
        self,
        entity_uuid: UUID,
        direction: str,
        relationship: str | None,
    ) -> list[RelationRecord]:
        rel_hint = relationship or "*"
        self._emit_status(
            f"Loading {direction} relations ({rel_hint})",
            operation="get_relations",
            entity_id=str(entity_uuid),
            direction=direction,
            relationship=rel_hint,
        )
        response = self._request(
            method="GET",
            path=f"/api/entities/{entity_uuid}/relations/",
            params={"direction": direction},
        )
        if response is None:
            return []

        payload = self._safe_json(response)
        if not isinstance(payload, dict):
            return []

        rows = payload.get("outgoing" if direction == "outgoing" else "incoming", [])
        out: list[RelationRecord] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            rel_name = _canonical_relationship(str(row.get("relation_type") or ""))
            if relationship and rel_name != relationship.casefold():
                continue
            ent = row.get("entity", {}) if isinstance(row.get("entity"), dict) else {}
            neighbor_id = ent.get("id")
            try:
                neighbor_uuid = UUID(str(neighbor_id))
            except Exception:
                continue

            if direction == "outgoing":
                out.append(
                    RelationRecord(subject_uuid=entity_uuid, relationship=rel_name, object_uuid=neighbor_uuid)
                )
            else:
                out.append(
                    RelationRecord(subject_uuid=neighbor_uuid, relationship=rel_name, object_uuid=entity_uuid)
                )

            if rel_name and rel_name not in self._schema_relations:
                self._schema_relations.append(rel_name)

        return out

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> requests.Response | None:
        headers = {"Accept": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        try:
            query_suffix = ""
            if params:
                query_parts = [f"{k}={v}" for k, v in params.items()]
                query_suffix = "?" + "&".join(query_parts)
            redacted_path = _redact_identifiers(path)
            redacted_suffix = _redact_identifiers(query_suffix)
            #self._emit_status(
            #    f"REST call: {method} {self.base_url}{redacted_path}{redacted_suffix}",
            #    operation="rest_call",
            #    method=method,
            #    path=path,
            #    params=params or {},
            #)
            response = requests.request(
                method=method,
                url=f"{self.base_url}{path}",
                headers=headers,
                params=params,
                json=json_body,
                timeout=self.timeout_seconds,
            )
            if not response.ok:
                self._emit_status(
                    f"REST error: {method} {path} -> HTTP {response.status_code}",
                    operation="rest_error",
                    method=method,
                    path=path,
                    status_code=response.status_code,
                )
                return None
            #self._emit_status(
            #                f"REST success: {method} {path}",
            #                operation="rest_success",
            #                method=method,
            #                path=path,
            #                status_code=response.status_code,
            #            )
            return response
        except requests.RequestException:
            self._emit_status(
                f"REST network error: {method} {path}",
                operation="rest_network_error",
                method=method,
                path=path,
            )
            return None

    @staticmethod
    def _safe_json(response: requests.Response) -> Any:
        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            try:
                return response.json()
            except ValueError:
                return {"raw": response.text}
        return {"raw": response.text}
