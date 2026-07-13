from __future__ import annotations

from typing import Protocol
from uuid import UUID

from ..models import EntityRecord, KGSchema, RelationRecord


class GraphRepository(Protocol):
    async def get_schema(self) -> KGSchema: ...

    async def search_entities(self, name_query: str) -> list[EntityRecord]: ...

    async def get_entity(self, entity_uuid: UUID) -> EntityRecord | None: ...

    async def get_outgoing_relations(
        self, entity_uuid: UUID, relationship: str | None = None
    ) -> list[RelationRecord]: ...

    async def get_incoming_relations(
        self, entity_uuid: UUID, relationship: str | None = None
    ) -> list[RelationRecord]: ...
