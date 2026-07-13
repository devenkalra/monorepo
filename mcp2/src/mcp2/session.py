from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from .dedup import FactDeduplicator
from .models import EntityRecord, KGSchema


TYPE_PREFIX: dict[str, str] = {
    "Person": "p",
    "Organization": "o",
    "Org": "o",
    "Place": "l",
    "Location": "l",
    "Event": "e",
    "Document": "d",
}


@dataclass
class EntityAliasMap:
    uuid_to_alias: dict[UUID, str] = field(default_factory=dict)
    alias_to_uuid: dict[str, UUID] = field(default_factory=dict)
    type_counters: dict[str, int] = field(default_factory=dict)

    def alias_for(self, entity_uuid: UUID, entity_type: str) -> str:
        if entity_uuid in self.uuid_to_alias:
            return self.uuid_to_alias[entity_uuid]

        prefix = TYPE_PREFIX.get(entity_type, "x")
        next_num = self.type_counters.get(prefix, 0) + 1
        self.type_counters[prefix] = next_num
        alias = f"{prefix}{next_num}"

        self.uuid_to_alias[entity_uuid] = alias
        self.alias_to_uuid[alias] = entity_uuid
        return alias


@dataclass
class QuerySession:
    original_question: str
    current_schema: KGSchema
    query_id: str = field(default_factory=lambda: str(uuid4()))
    alias_map: EntityAliasMap = field(default_factory=EntityAliasMap)
    fact_dedup: FactDeduplicator = field(default_factory=FactDeduplicator)
    exposed_entity_ids: set[UUID] = field(default_factory=set)
    executed_traversals: set[tuple[str, str, str]] = field(default_factory=set)
    fetched_entities: set[str] = field(default_factory=set)
    fetched_entity_ids: set[UUID] = field(default_factory=set)
    entity_cache: dict[UUID, EntityRecord | None] = field(default_factory=dict)
    previous_response_id: str | None = None
    trace: list[dict[str, Any]] = field(default_factory=list)

    def uuid_for_alias(self, alias: str) -> UUID | None:
        return self.alias_map.alias_to_uuid.get(alias)

    def alias_for_uuid(self, entity_uuid: UUID) -> str | None:
        return self.alias_map.uuid_to_alias.get(entity_uuid)
