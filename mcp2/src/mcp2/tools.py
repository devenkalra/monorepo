from __future__ import annotations

from typing import Any, Callable
from uuid import UUID

from .models import Direction, EntityRecord, RelationRecord, ToolResult
from .repository.base import GraphRepository
from .serialization import fact_to_triple
from .session import QuerySession


class ToolError(RuntimeError):
    pass


class MCPToolHandler:
    def __init__(self, repository: GraphRepository):
        self.repository = repository

    async def resolve_name_to_aliases(
        self,
        session: QuerySession,
        name: str,
        on_status_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> list[str]:
        entities = await self.repository.search_entities(name)
        aliases: list[str] = []
        for entity in entities:
            alias = session.alias_map.alias_for(entity.uuid, entity.entity_type)
            aliases.append(alias)
            if on_status_event is not None:
                on_status_event(
                    {
                        "phase": "entity_resolve",
                        "message": f"Matched '{name}' to {entity.display_name}",
                    }
                )
        return aliases

    async def get_entities(
        self,
        session: QuerySession,
        entity_ids: list[str],
        on_status_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> ToolResult:
        key = tuple(sorted(entity_ids))
        if str(key) in session.fetched_entities:
            #if on_status_event is not None:
            #    on_status_event({"phase": "entity_fetch", "message": "Skipping entity fetch (already fetched)"})
            return ToolResult()
        session.fetched_entities.add(str(key))

        result = ToolResult()
        for alias in entity_ids:
            entity_uuid = session.uuid_for_alias(alias)
            if not entity_uuid:
                result.errors.append(f"Unknown alias: {alias}")
                if on_status_event is not None:
                    on_status_event({"phase": "entity_fetch", "message": "Unknown entity reference from planner"})
                continue

            if entity_uuid in session.fetched_entity_ids:
                await self._get_entity_cached(
                    session,
                    entity_uuid,
                    on_status_event=on_status_event,
                    context="entity",
                )
                continue

            entity = await self._get_entity_cached(
                session,
                entity_uuid,
                on_status_event=on_status_event,
                context="entity",
            )
            if not entity:
                result.errors.append(f"Entity not found: {alias}")
                if on_status_event is not None:
                    on_status_event({"phase": "entity_fetch", "message": "Entity not found"})
                continue

            session.fetched_entity_ids.add(entity_uuid)

            if on_status_event is not None:
                on_status_event({"phase": "entity_fetch", "message": f"Got entity: {entity.display_name}"})

            if entity_uuid not in session.exposed_entity_ids:
                session.exposed_entity_ids.add(entity_uuid)
                result.NEW_E.append(f"{alias}={entity.display_name}")

            for k, v in entity.properties.items():
                if session.fact_dedup.add_if_new(entity.uuid, k, v):
                    result.NEW_F.append(fact_to_triple(alias, k, v))

            if on_status_event is not None:
                on_status_event({"phase": "relation_expand", "message": f"Expanding outgoing relations for: {entity.display_name}"})
            outgoing = await self.repository.get_outgoing_relations(entity_uuid)
            if on_status_event is not None:
                on_status_event({"phase": "relation_expand", "message": f"Expanding incoming relations for: {entity.display_name}"})
            incoming = await self.repository.get_incoming_relations(entity_uuid)
            await self._collect_relation_facts(session, result, outgoing, on_status_event=on_status_event)
            await self._collect_relation_facts(session, result, incoming, on_status_event=on_status_event)

        return result

    async def traverse_relation(
        self,
        session: QuerySession,
        entity_id: str,
        relationship: str,
        direction: Direction,
        on_status_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> ToolResult:
        if relationship not in session.current_schema.relation_names():
            raise ToolError(f"Unsupported relationship '{relationship}'")

        entity_uuid = session.uuid_for_alias(entity_id)
        if not entity_uuid:
            raise ToolError(f"Unknown alias: {entity_id}")

        entity = await self._get_entity_cached(
            session,
            entity_uuid,
            on_status_event=on_status_event,
            context="entity",
        )
        entity_display = entity.display_name if entity else "selected entity"

        traversal_key = (entity_id, relationship, direction)
        if traversal_key in session.executed_traversals:
            if on_status_event is not None:
                on_status_event({"phase": "relation_expand", "message": "Skipping traversal (already executed)"})
            return ToolResult()
        session.executed_traversals.add(traversal_key)

        rels: list[RelationRecord] = []
        if direction in ("out", "either"):
            if on_status_event is not None:
                on_status_event(
                    {
                        "phase": "relation_expand",
                        "message": f"Loading outgoing {relationship} relations for {entity_display}",
                    }
                )
            rels.extend(await self.repository.get_outgoing_relations(entity_uuid, relationship=relationship))
        if direction in ("in", "either"):
            if on_status_event is not None:
                on_status_event(
                    {
                        "phase": "relation_expand",
                        "message": f"Loading incoming {relationship} relations for {entity_display}",
                    }
                )
            rels.extend(await self.repository.get_incoming_relations(entity_uuid, relationship=relationship))

        result = ToolResult()
        await self._collect_relation_facts(session, result, rels, on_status_event=on_status_event)
        return result

    async def _collect_relation_facts(
        self,
        session: QuerySession,
        result: ToolResult,
        relations: list[RelationRecord],
        on_status_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        for rel in relations:
            subject = rel.subject_uuid
            subject_entity = await self._get_entity_cached(
                session,
                subject,
                on_status_event=on_status_event,
                context="related entity",
            )
            if not subject_entity:
                continue
            subject_alias = session.alias_map.alias_for(subject, subject_entity.entity_type)
            if subject not in session.exposed_entity_ids:
                session.exposed_entity_ids.add(subject)
                result.NEW_E.append(f"{subject_alias}={subject_entity.display_name}")

            if rel.object_uuid is not None:
                object_entity = await self._get_entity_cached(
                    session,
                    rel.object_uuid,
                    on_status_event=on_status_event,
                    context="related entity",
                )
                if not object_entity:
                    continue
                object_alias = session.alias_map.alias_for(rel.object_uuid, object_entity.entity_type)
                if rel.object_uuid not in session.exposed_entity_ids:
                    session.exposed_entity_ids.add(rel.object_uuid)
                    result.NEW_E.append(f"{object_alias}={object_entity.display_name}")
                if session.fact_dedup.add_if_new(subject, rel.relationship, rel.object_uuid):
                    result.NEW_F.append(fact_to_triple(subject_alias, rel.relationship, object_alias))
            else:
                if session.fact_dedup.add_if_new(subject, rel.relationship, rel.literal_value):
                    result.NEW_F.append(fact_to_triple(subject_alias, rel.relationship, rel.literal_value))

    async def _get_entity_cached(
        self,
        session: QuerySession,
        entity_uuid: UUID,
        on_status_event: Callable[[dict[str, Any]], None] | None = None,
        context: str = "entity",
    ) -> EntityRecord | None:
        if entity_uuid in session.entity_cache:
            cached = session.entity_cache[entity_uuid]
            #if on_status_event is not None:
            #    cached_name = cached.display_name if cached else "entity"
            #    on_status_event(
            #        {
            #            "phase": "entity_fetch",
            #            "message": f"Skipping fetch for {context}: {cached_name} (already in cache)",
            #        }
            #    )
            return cached

        #if on_status_event is not None:
        #    on_status_event({"phase": "entity_fetch", "message": f"Getting {context} details..."})
        entity = await self.repository.get_entity(entity_uuid)
        session.entity_cache[entity_uuid] = entity
        return entity
