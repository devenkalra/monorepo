from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from ..models import EntityRecord, KGSchema, RelationRecord


class InMemoryGraphRepository:
    def __init__(
        self,
        schema: KGSchema,
        entities: list[EntityRecord] | None = None,
        relations: list[RelationRecord] | None = None,
    ) -> None:
        self._schema = schema
        self._entities: dict[UUID, EntityRecord] = {}
        self._by_lower_name: dict[str, list[UUID]] = defaultdict(list)
        self._outgoing: dict[UUID, list[RelationRecord]] = defaultdict(list)
        self._incoming: dict[UUID, list[RelationRecord]] = defaultdict(list)

        for entity in entities or []:
            self.add_entity(entity)
        for relation in relations or []:
            self.add_relation(relation)

    def add_entity(self, entity: EntityRecord) -> None:
        self._entities[entity.uuid] = entity
        self._by_lower_name[entity.display_name.casefold()].append(entity.uuid)

    def add_relation(self, relation: RelationRecord) -> None:
        self._outgoing[relation.subject_uuid].append(relation)
        if relation.object_uuid is not None:
            self._incoming[relation.object_uuid].append(relation)

    async def get_schema(self) -> KGSchema:
        return self._schema

    async def search_entities(self, name_query: str) -> list[EntityRecord]:
        q = name_query.casefold().strip()
        if not q:
            return []
        exact = self._by_lower_name.get(q, [])
        if exact:
            return [self._entities[eid] for eid in exact]

        matches: list[EntityRecord] = []
        for entity in self._entities.values():
            if q in entity.display_name.casefold():
                matches.append(entity)
        return matches

    async def get_entity(self, entity_uuid: UUID) -> EntityRecord | None:
        return self._entities.get(entity_uuid)

    async def get_outgoing_relations(
        self, entity_uuid: UUID, relationship: str | None = None
    ) -> list[RelationRecord]:
        rels = self._outgoing.get(entity_uuid, [])
        if relationship is None:
            return list(rels)
        return [r for r in rels if r.relationship == relationship]

    async def get_incoming_relations(
        self, entity_uuid: UUID, relationship: str | None = None
    ) -> list[RelationRecord]:
        rels = self._incoming.get(entity_uuid, [])
        if relationship is None:
            return list(rels)
        return [r for r in rels if r.relationship == relationship]
