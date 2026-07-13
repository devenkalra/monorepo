from __future__ import annotations

import asyncio
import os
from uuid import uuid4

from .mcp_server import MCPServerRuntime, build_fastmcp_app
from .models import EntityRecord, KGSchema, RelationRecord, SchemaRelation
from .repository.in_memory import InMemoryGraphRepository
from .web_server import run_web_server


def _build_demo_repo() -> InMemoryGraphRepository:
    schema = KGSchema(
        entity_types=["Person", "Org", "Place"],
        relations=[
            SchemaRelation(name="child_of", source_type="Person", target_type="Person"),
            SchemaRelation(name="spouse_of", source_type="Person", target_type="Person"),
            SchemaRelation(name="works_at", source_type="Person", target_type="Org"),
            SchemaRelation(name="student_of", source_type="Person", target_type="Org"),
        ],
    )

    deven_id = uuid4()
    riya_id = uuid4()
    rahul_id = uuid4()
    columbia_id = uuid4()

    entities = [
        EntityRecord(uuid=deven_id, entity_type="Person", display_name="Deven Kalra", properties={"gender": "Male"}),
        EntityRecord(uuid=riya_id, entity_type="Person", display_name="Riya Kalra", properties={"gender": "Female"}),
        EntityRecord(uuid=rahul_id, entity_type="Person", display_name="Rahul Kalra", properties={"gender": "Male"}),
        EntityRecord(uuid=columbia_id, entity_type="Org", display_name="Columbia University", properties={"category": "University"}),
    ]

    relations = [
        RelationRecord(subject_uuid=riya_id, relationship="child_of", object_uuid=deven_id),
        RelationRecord(subject_uuid=rahul_id, relationship="child_of", object_uuid=deven_id),
        RelationRecord(subject_uuid=riya_id, relationship="student_of", object_uuid=columbia_id),
    ]

    return InMemoryGraphRepository(schema=schema, entities=entities, relations=relations)


async def _smoke_demo() -> None:
    repo = _build_demo_repo()
    runtime = MCPServerRuntime(repo)
    result = await runtime.answer_question_once("Who is Riya's sister?")
    print(result["answer"])


def main() -> None:
    repo = _build_demo_repo()
    runtime = MCPServerRuntime(repo)

    run_mode = os.environ.get("MCP2_MODE", "demo")
    if run_mode == "demo":
        asyncio.run(_smoke_demo())
        return

    if run_mode == "web":
        host = os.environ.get("MCP2_WEB_HOST", "127.0.0.1")
        port = int(os.environ.get("MCP2_WEB_PORT", "8787"))
        model = os.environ.get("MCP2_DEFAULT_MODEL", "gpt-4.1-mini")
        backend_base_url = os.environ.get("MCP2_BACKEND_BASE_URL", "https://bldrdojo.com/api/")
        run_web_server(
            runtime=runtime,
            host=host,
            port=port,
            default_model=model,
            backend_base_url=backend_base_url,
        )
        return

    app = build_fastmcp_app(runtime)
    app.run()


if __name__ == "__main__":
    main()
