from __future__ import annotations

from uuid import uuid4

import pytest

from mcp2.controller import IterativeQAController
from mcp2.llm.openai_responses import OpenAIResponsesPlanner
from mcp2.llm.planner import RuleBasedPlanner
from mcp2.models import EntityRecord, KGSchema, RelationRecord, SchemaRelation
from mcp2.repository.in_memory import InMemoryGraphRepository
from mcp2.session import QuerySession
from mcp2.tools import MCPToolHandler


@pytest.fixture()
def schema() -> KGSchema:
    return KGSchema(
        entity_types=["Person", "Org", "Place"],
        relations=[
            SchemaRelation(name="child_of", source_type="Person", target_type="Person"),
            SchemaRelation(name="spouse_of", source_type="Person", target_type="Person"),
            SchemaRelation(name="works_at", source_type="Person", target_type="Org"),
            SchemaRelation(name="student_of", source_type="Person", target_type="Org"),
        ],
    )


@pytest.mark.asyncio
async def test_sibling_inference_with_gender_rejection(schema: KGSchema) -> None:
    deven = uuid4()
    riya = uuid4()
    rahul = uuid4()

    repo = InMemoryGraphRepository(
        schema,
        entities=[
            EntityRecord(uuid=riya, entity_type="Person", display_name="Riya Kalra", properties={}),
            EntityRecord(uuid=rahul, entity_type="Person", display_name="Rahul Kalra", properties={"gender": "Male"}),
            EntityRecord(uuid=deven, entity_type="Person", display_name="Deven Kalra", properties={}),
        ],
        relations=[
            RelationRecord(subject_uuid=riya, relationship="child_of", object_uuid=deven),
            RelationRecord(subject_uuid=rahul, relationship="child_of", object_uuid=deven),
        ],
    )

    result = await IterativeQAController(MCPToolHandler(repo)).run_question(
        "Who is Riya Kalra's sister?", RuleBasedPlanner()
    )

    assert "No sister" in result.answer
    assert "Rahul" not in result.answer


@pytest.mark.asyncio
async def test_sibling_discovery_through_traversal(schema: KGSchema) -> None:
    deven = uuid4()
    riya = uuid4()
    anita = uuid4()

    repo = InMemoryGraphRepository(
        schema,
        entities=[
            EntityRecord(uuid=riya, entity_type="Person", display_name="Riya Kalra", properties={}),
            EntityRecord(uuid=anita, entity_type="Person", display_name="Anita Kalra", properties={"gender": "Female"}),
            EntityRecord(uuid=deven, entity_type="Person", display_name="Deven Kalra", properties={}),
        ],
        relations=[
            RelationRecord(subject_uuid=riya, relationship="child_of", object_uuid=deven),
            RelationRecord(subject_uuid=anita, relationship="child_of", object_uuid=deven),
        ],
    )

    result = await IterativeQAController(MCPToolHandler(repo)).run_question(
        "Who is Riya Kalra's sister?", RuleBasedPlanner()
    )

    assert "Anita Kalra" in result.answer


@pytest.mark.asyncio
async def test_name_collision_separate_aliases(schema: KGSchema) -> None:
    parent1 = uuid4()
    parent2 = uuid4()
    rahul1 = uuid4()
    rahul2 = uuid4()

    repo = InMemoryGraphRepository(
        schema,
        entities=[
            EntityRecord(uuid=parent1, entity_type="Person", display_name="Parent One", properties={}),
            EntityRecord(uuid=parent2, entity_type="Person", display_name="Parent Two", properties={}),
            EntityRecord(uuid=rahul1, entity_type="Person", display_name="Rahul Kalra", properties={}),
            EntityRecord(uuid=rahul2, entity_type="Person", display_name="Rahul Kalra", properties={}),
        ],
        relations=[
            RelationRecord(subject_uuid=rahul1, relationship="child_of", object_uuid=parent1),
            RelationRecord(subject_uuid=rahul2, relationship="child_of", object_uuid=parent2),
        ],
    )

    tool_handler = MCPToolHandler(repo)
    session = QuerySession(original_question="test", current_schema=schema)
    aliases = await tool_handler.resolve_name_to_aliases(session, "Rahul Kalra")

    assert len(aliases) == 2
    assert aliases[0] != aliases[1]

    out = await tool_handler.get_entities(session, aliases)
    joined = "\n".join(out.NEW_F)
    assert "child_of" in joined
    assert len([e for e in out.NEW_E if e.endswith("Rahul Kalra")]) == 2


@pytest.mark.asyncio
async def test_organization_reasoning(schema: KGSchema) -> None:
    riya = uuid4()
    columbia = uuid4()

    repo = InMemoryGraphRepository(
        schema,
        entities=[
            EntityRecord(uuid=riya, entity_type="Person", display_name="Riya Kalra", properties={}),
            EntityRecord(uuid=columbia, entity_type="Org", display_name="Columbia University", properties={"category": "University"}),
        ],
        relations=[
            RelationRecord(subject_uuid=riya, relationship="student_of", object_uuid=columbia),
        ],
    )

    result = await IterativeQAController(MCPToolHandler(repo)).run_question(
        "Who went to Columbia?", RuleBasedPlanner()
    )

    assert "Riya Kalra" in result.answer


@pytest.mark.asyncio
async def test_unsupported_derived_relation_uses_stored_edge(schema: KGSchema) -> None:
    deven = uuid4()
    riya = uuid4()
    rahul = uuid4()

    repo = InMemoryGraphRepository(
        schema,
        entities=[
            EntityRecord(uuid=riya, entity_type="Person", display_name="Riya Kalra", properties={}),
            EntityRecord(uuid=rahul, entity_type="Person", display_name="Rahul Kalra", properties={}),
            EntityRecord(uuid=deven, entity_type="Person", display_name="Deven Kalra", properties={}),
        ],
        relations=[
            RelationRecord(subject_uuid=riya, relationship="child_of", object_uuid=deven),
            RelationRecord(subject_uuid=rahul, relationship="child_of", object_uuid=deven),
        ],
    )

    result = await IterativeQAController(MCPToolHandler(repo)).run_question(
        "Who is Riya Kalra's sibling?", RuleBasedPlanner()
    )

    trace_text = str(result.trace)
    assert "'relationship': 'child_of'" in trace_text
    assert "'relationship': 'sibling'" not in trace_text


@pytest.mark.asyncio
async def test_duplicate_expansion_deduplicates(schema: KGSchema) -> None:
    deven = uuid4()
    riya = uuid4()

    repo = InMemoryGraphRepository(
        schema,
        entities=[
            EntityRecord(uuid=riya, entity_type="Person", display_name="Riya Kalra", properties={}),
            EntityRecord(uuid=deven, entity_type="Person", display_name="Deven Kalra", properties={}),
        ],
        relations=[
            RelationRecord(subject_uuid=riya, relationship="child_of", object_uuid=deven),
        ],
    )

    tool_handler = MCPToolHandler(repo)
    session = QuerySession(original_question="test", current_schema=schema)

    deven_alias = (await tool_handler.resolve_name_to_aliases(session, "Deven Kalra"))[0]

    first = await tool_handler.traverse_relation(session, deven_alias, "child_of", "in")
    second = await tool_handler.traverse_relation(session, deven_alias, "child_of", "in")

    assert len(first.NEW_E) + len(first.NEW_F) > 0
    assert second.NEW_E == []
    assert second.NEW_F == []


def test_answer_payload_dict_is_normalized_to_string() -> None:
    payload = {
        "action": "answer",
        "answer": {
            "Sohan Lal Kalra": {
                "child_of": ["Deven Kalra", "Savita Sharma"],
            }
        },
    }

    normalized = OpenAIResponsesPlanner._normalize_answer_payload(payload)

    assert normalized["answer"] == "Sohan Lal Kalra"
