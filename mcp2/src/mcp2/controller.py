from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .llm.planner import Planner, PlannerAction, PlannerContext
from .serialization import compact_fact_rows, serialize_schema
from .session import QuerySession
from .tools import MCPToolHandler, ToolError


@dataclass
class QueryResult:
    answer: str
    trace: list[dict]
    entities: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)


class IterativeQAController:
    def __init__(self, tool_handler: MCPToolHandler, max_steps: int = 14, rebase_every: int = 0):
        self.tool_handler = tool_handler
        self.max_steps = max_steps
        self.rebase_every = rebase_every

    async def run_question(
        self,
        question: str,
        planner: Planner,
        on_trace_event: Callable[[dict], None] | None = None,
        on_status_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> QueryResult:
        schema = await self.tool_handler.repository.get_schema()
        session = QuerySession(original_question=question, current_schema=schema)

        known_entities: list[str] = []
        known_facts: list[str] = []
        new_entities: list[str] = []
        new_facts: list[str] = []

        def emit(event: dict) -> None:
            session.trace.append(event)
            if on_trace_event is not None:
                on_trace_event(event)

        def emit_status(message: str, **extra: Any) -> None:
            if on_status_event is None:
                return
            payload: dict[str, Any] = {"message": message}
            payload.update(extra)
            on_status_event(payload)

        emit_status("Initializing query", phase="init")

        for step in range(1, self.max_steps + 1):
            context = PlannerContext(
                question=question,
                schema_text=serialize_schema(schema),
                known_entities=known_entities,
                known_facts=known_facts,
                new_entities=new_entities,
                new_facts=new_facts,
            )

            action, response_id = await planner.next_action(context, session.previous_response_id)
            session.previous_response_id = response_id or session.previous_response_id
            emit({"step": step, "action": action.model_dump()})
            emit_status(
                f"Planner selected action: {action.action}",
                phase="planner",
                step=step,
                action=action.action,
            )

            new_entities = []
            new_facts = []

            if action.action == "answer":
                answer = self._render_aliases_to_names(action.answer or "", session, known_entities)
                emit({"event": "final_answer", "answer": answer})
                emit_status("Final answer generated", phase="complete", step=step)
                return QueryResult(answer=answer, trace=session.trace, entities=known_entities, facts=known_facts)

            if action.action == "fetch_entities":
                aliases: list[str] = []
                for token in action.entities:
                    token = token.strip()
                    if not token:
                        continue
                    if session.uuid_for_alias(token):
                        aliases.append(token)
                        display_name = self._display_name_for_alias(token, known_entities)
                        emit_status(f"Using known entity: {display_name}", phase="entity_fetch", step=step)
                        continue
                    emit_status(f"Resolving entity name: {token}", phase="entity_fetch", step=step)
                    matched_aliases = await self.tool_handler.resolve_name_to_aliases(
                        session,
                        token,
                        on_status_event=on_status_event,
                    )
                    aliases.extend(matched_aliases)

                if not aliases:
                    emit({"warning": "No entities resolved for fetch_entities"})
                    emit_status("No entities resolved for fetch action", phase="entity_fetch", step=step)
                    continue

                emit_status(
                    f"Fetching {len(aliases)} entity record(s)",
                    phase="entity_fetch",
                    step=step,
                )
                result = await self.tool_handler.get_entities(session, aliases, on_status_event=on_status_event)
                new_entities = result.NEW_E
                new_facts = compact_fact_rows(result.NEW_F)
                emit(
                    {
                        "tool": "get_entities",
                        "input": {"entity_ids": aliases},
                        "NEW_E": new_entities,
                        "NEW_F": new_facts,
                        "errors": result.errors,
                    }
                )
                emit_status(
                    f"Entity fetch complete (+{len(new_entities)} entities, +{len(new_facts)} facts)",
                    phase="entity_fetch",
                    step=step,
                )

            elif action.action == "traverse_relation":
                if not action.entity or not action.relationship or not action.direction:
                    emit({"error": "Invalid traverse_relation payload"})
                    emit_status("Invalid relation traversal payload from planner", phase="relation_expand", step=step)
                    continue
                try:
                    relation_entity_name = self._display_name_for_alias(action.entity, known_entities)
                    emit_status(
                        f"Expanding relations: {action.direction} {action.relationship} from {relation_entity_name}",
                        phase="relation_expand",
                        step=step,
                    )
                    result = await self.tool_handler.traverse_relation(
                        session,
                        entity_id=action.entity,
                        relationship=action.relationship,
                        direction=action.direction,
                        on_status_event=on_status_event,
                    )
                except ToolError as exc:
                    emit({"tool": "traverse_relation", "error": str(exc)})
                    emit_status(f"Relation expansion error: {exc}", phase="relation_expand", step=step)
                    continue

                new_entities = result.NEW_E
                new_facts = compact_fact_rows(result.NEW_F)
                emit(
                    {
                        "tool": "traverse_relation",
                        "input": {
                            "entity_id": action.entity,
                            "relationship": action.relationship,
                            "direction": action.direction,
                        },
                        "NEW_E": new_entities,
                        "NEW_F": new_facts,
                        "errors": result.errors,
                    }
                )
                emit_status(
                    f"Relation expansion complete (+{len(new_entities)} entities, +{len(new_facts)} facts)",
                    phase="relation_expand",
                    step=step,
                )

            else:
                emit({"error": f"Unsupported planner action: {action.action}"})
                emit_status(f"Unsupported planner action: {action.action}", phase="planner", step=step)

            if new_entities:
                known_entities.extend(x for x in new_entities if x not in known_entities)
            if new_facts:
                known_facts = compact_fact_rows(known_facts + new_facts)
            if self.rebase_every > 0 and step % self.rebase_every == 0:
                # Optional compaction hook: preserve same aliases/facts and reset response chain.
                session.previous_response_id = None
                emit({"event": "rebase", "known_entities": len(known_entities), "known_facts": len(known_facts)})
                emit_status("Rebasing planner context", phase="rebase", step=step)

        return QueryResult(
            answer="No final answer produced before step limit.",
            trace=session.trace,
            entities=known_entities,
            facts=known_facts,
        )

    @staticmethod
    def _render_aliases_to_names(answer: str, session: QuerySession, known_entities: list[str]) -> str:
        resolved = answer
        for mapping in known_entities:
            if "=" not in mapping:
                continue
            alias, name = mapping.split("=", 1)
            resolved = resolved.replace(alias, name)
        return resolved

    @staticmethod
    def _display_name_for_alias(alias: str, known_entities: list[str]) -> str:
        for mapping in known_entities:
            if "=" not in mapping:
                continue
            known_alias, name = mapping.split("=", 1)
            if known_alias == alias:
                return name
        return alias
