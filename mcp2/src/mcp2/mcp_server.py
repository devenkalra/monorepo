from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from .controller import IterativeQAController
from .llm.planner import RuleBasedPlanner
from .repository.base import GraphRepository
from .session import QuerySession
from .tools import MCPToolHandler

try:
    from mcp.server.fastmcp import FastMCP
except Exception:  # pragma: no cover
    FastMCP = None


class StartQueryInput(BaseModel):
    question: str


class StartQueryOutput(BaseModel):
    query_id: str


class GetEntitiesInput(BaseModel):
    query_id: str
    entity_ids: list[str] = Field(default_factory=list)


class TraverseInput(BaseModel):
    query_id: str
    entity_id: str
    relationship: str
    direction: str


@dataclass
class MCPServerRuntime:
    repository: GraphRepository
    tool_handler: MCPToolHandler = field(init=False)
    controller: IterativeQAController = field(init=False)
    sessions: dict[str, QuerySession] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.tool_handler = MCPToolHandler(self.repository)
        self.controller = IterativeQAController(self.tool_handler)

    async def start_query(self, question: str) -> QuerySession:
        schema = await self.repository.get_schema()
        session = QuerySession(original_question=question, current_schema=schema)
        self.sessions[session.query_id] = session
        return session

    async def get_entities(self, query_id: str, entity_ids: list[str]) -> dict[str, Any]:
        session = self._session_or_raise(query_id)
        result = await self.tool_handler.get_entities(session, entity_ids)
        return result.model_dump()

    async def traverse_relation(self, query_id: str, entity_id: str, relationship: str, direction: str) -> dict[str, Any]:
        session = self._session_or_raise(query_id)
        result = await self.tool_handler.traverse_relation(
            session,
            entity_id=entity_id,
            relationship=relationship,
            direction=direction,
        )
        return result.model_dump()

    async def answer_question_once(self, question: str) -> dict[str, Any]:
        planner = RuleBasedPlanner()
        result = await self.controller.run_question(question, planner)
        return {
            "answer": result.answer,
            "trace": result.trace,
            "entities": result.entities,
            "facts": result.facts,
        }

    def _session_or_raise(self, query_id: str) -> QuerySession:
        session = self.sessions.get(query_id)
        if not session:
            raise ValueError(f"Unknown query_id: {query_id}")
        return session


def build_fastmcp_app(runtime: MCPServerRuntime):
    if FastMCP is None:
        raise RuntimeError("mcp.server.fastmcp is not installed in this environment")

    app = FastMCP("IterativeKGQA")

    @app.tool()
    async def start_query(input: StartQueryInput) -> StartQueryOutput:
        session = await runtime.start_query(input.question)
        return StartQueryOutput(query_id=session.query_id)

    @app.tool()
    async def get_entities(input: GetEntitiesInput) -> dict[str, Any]:
        return await runtime.get_entities(input.query_id, input.entity_ids)

    @app.tool()
    async def traverse_relation(input: TraverseInput) -> dict[str, Any]:
        return await runtime.traverse_relation(
            input.query_id,
            input.entity_id,
            input.relationship,
            input.direction,
        )

    @app.tool()
    async def answer(question: str) -> dict[str, Any]:
        return await runtime.answer_question_once(question)

    return app
