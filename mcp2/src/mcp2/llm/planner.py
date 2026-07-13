from __future__ import annotations

import re
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from ..serialization import expand_fact_row


ActionType = Literal["fetch_entities", "traverse_relation", "answer"]


class PlannerAction(BaseModel):
    action: ActionType
    entities: list[str] = Field(default_factory=list)
    entity: str | None = None
    relationship: str | None = None
    direction: Literal["out", "in", "either"] | None = None
    answer: str | None = None


class PlannerContext(BaseModel):
    question: str
    schema_text: str
    known_entities: list[str] = Field(default_factory=list)
    known_facts: list[str] = Field(default_factory=list)
    new_entities: list[str] = Field(default_factory=list)
    new_facts: list[str] = Field(default_factory=list)


class Planner(Protocol):
    async def next_action(self, context: PlannerContext, previous_response_id: str | None) -> tuple[PlannerAction, str | None]:
        ...


class RuleBasedPlanner:
    """Simple non-LLM planner used in tests and local debugging."""

    async def next_action(self, context: PlannerContext, previous_response_id: str | None) -> tuple[PlannerAction, str | None]:
        q = context.question.casefold()
        if "sister" in q or "sibling" in q:
            return _plan_sibling(context), None
        if "who went to" in q or "who studies at" in q:
            return _plan_student(context), None
        return PlannerAction(action="answer", answer="No answer strategy available."), None


def _plan_sibling(context: PlannerContext) -> PlannerAction:
    entity_rows = list(dict.fromkeys(context.known_entities + context.new_entities))
    fact_rows = list(dict.fromkeys(context.known_facts + context.new_facts))
    fact_triples = []
    for fact in fact_rows:
        fact_triples.extend(expand_fact_row(fact))
    known_entities = "\n".join(entity_rows)
    requires_female = "sister" in context.question.casefold()

    if not known_entities:
        m = re.search(r"who\s+is\s+(.+?)'s\s+(?:sister|sibling)", context.question, flags=re.IGNORECASE)
        if m:
            name = m.group(1).strip()
        else:
            tokens = context.question.replace("?", "").split()
            name = " ".join(tokens[2:]) if len(tokens) >= 3 else context.question
        return PlannerAction(action="fetch_entities", entities=[name])

    parent_aliases = []
    subject_alias = None
    for line in entity_rows:
        if "=" in line and subject_alias is None:
            subject_alias = line.split("=", 1)[0]

    for subject, relation, obj in fact_triples:
        if relation == "child_of" and subject_alias and subject == subject_alias:
            if obj not in parent_aliases:
                parent_aliases.append(obj)

    if subject_alias and not parent_aliases:
        return PlannerAction(action="traverse_relation", entity=subject_alias, relationship="child_of", direction="out")

    if parent_aliases:
        parent = parent_aliases[0]
        sibling_facts = []
        for subject, relation, obj in fact_triples:
            if relation == "child_of" and parent == obj:
                sibling_facts.append((subject, relation, obj))
        if len(sibling_facts) < 2:
            return PlannerAction(action="traverse_relation", entity=parent, relationship="child_of", direction="in")

        gender_map: dict[str, str] = {}
        for subject, relation, obj in fact_triples:
            if relation == "gender":
                gender_map[subject] = obj.casefold()

        siblings = []
        for subject, _, _ in sibling_facts:
            if subject != subject_alias and subject not in siblings:
                siblings.append(subject)

        for sib in siblings:
            if not requires_female:
                return PlannerAction(action="answer", answer=f"{sib}")
            if gender_map.get(sib) == "female":
                return PlannerAction(action="answer", answer=f"{sib}")

        unknown_gender = [sib for sib in siblings if sib not in gender_map]
        if requires_female and unknown_gender:
            return PlannerAction(action="fetch_entities", entities=unknown_gender)

        if requires_female:
            return PlannerAction(action="answer", answer="No sister of this person can be identified from the available graph facts.")
        return PlannerAction(action="answer", answer="No sibling of this person can be identified from the available graph facts.")

    if requires_female:
        return PlannerAction(action="answer", answer="No sister of this person can be identified from the available graph facts.")
    return PlannerAction(action="answer", answer="No sibling of this person can be identified from the available graph facts.")


def _plan_student(context: PlannerContext) -> PlannerAction:
    entities = list(dict.fromkeys(context.known_entities + context.new_entities))
    facts = list(dict.fromkeys(context.known_facts + context.new_facts))
    fact_triples = []
    for fact in facts:
        fact_triples.extend(expand_fact_row(fact))

    if not entities:
        tokens = context.question.replace("?", "").split()
        org_name = " ".join(tokens[3:]) if len(tokens) > 3 else context.question
        return PlannerAction(action="fetch_entities", entities=[org_name])

    org_alias = None
    for line in entities:
        if "=" in line and line.casefold().find("columbia") >= 0:
            org_alias = line.split("=", 1)[0]
            break
    if org_alias is None and entities:
        org_alias = entities[0].split("=", 1)[0]

    if org_alias and not any(relation == "student_of" and org_alias == obj for _, relation, obj in fact_triples):
        return PlannerAction(action="traverse_relation", entity=org_alias, relationship="student_of", direction="in")

    for subject, relation, obj in fact_triples:
        if relation == "student_of" and org_alias == obj:
            return PlannerAction(action="answer", answer=subject)

    return PlannerAction(action="answer", answer="No one identifiable from available facts.")
