from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .models import KGSchema


def serialize_schema(schema: KGSchema) -> str:
    entities = ",".join(schema.entity_types)
    rels = ",\n".join(
        f"{r.name}:{r.source_type}->{r.target_type}" for r in schema.relations
    )
    return f"KG_SCHEMA:\nE=[{entities}]\nR=[\n{rels}\n]"


def serialize_entity_mappings(mappings: Iterable[tuple[str, str]]) -> str:
    lines = [f"{alias}={name}" for alias, name in mappings]
    return "\n".join(lines)


def fact_to_triple(subject_alias: str, relationship: str, object_repr: Any) -> str:
    return f"{subject_alias}|{relationship}|{object_repr}"


def parse_fact_row(fact: str) -> tuple[list[str], str, list[str]] | None:
    parts = fact.split("|", 2)
    if len(parts) != 3:
        return None
    subject_part, relationship, object_part = parts
    subjects = [item.strip() for item in subject_part.split(",") if item.strip()]
    objects = [item.strip() for item in object_part.split(",") if item.strip()]
    if not subjects or not objects:
        return None
    return subjects, relationship, objects


def expand_fact_row(fact: str) -> list[tuple[str, str, str]]:
    parsed = parse_fact_row(fact)
    if parsed is None:
        return []
    subjects, relationship, objects = parsed
    return [(subject, relationship, object_repr) for subject in subjects for object_repr in objects]


def compact_fact_rows(facts: Iterable[str]) -> list[str]:
    triples: list[tuple[str, str, str, int]] = []
    passthrough: list[str] = []
    seen_passthrough: set[str] = set()
    seen_triples: set[tuple[str, str, str]] = set()

    for index, fact in enumerate(facts):
        parsed = parse_fact_row(fact)
        if parsed is None:
            if fact not in seen_passthrough:
                seen_passthrough.add(fact)
                passthrough.append(fact)
            continue

        subjects, relationship, objects = parsed
        for subject in subjects:
            for obj in objects:
                triple = (subject, relationship, obj)
                if triple in seen_triples:
                    continue
                seen_triples.add(triple)
                triples.append((subject, relationship, obj, index))

    remaining = triples[:]
    compacted: list[str] = []

    def _pick_best_group() -> tuple[str, str, list[tuple[str, str, str, int]]] | None:
        best_axis: str | None = None
        best_key: str | None = None
        best_items: list[tuple[str, str, str, int]] = []
        best_score = 0
        best_index = 10**9

        by_relation: dict[str, list[tuple[str, str, str, int]]] = {}
        for triple in remaining:
            by_relation.setdefault(triple[1], []).append(triple)

        for relation, relation_triples in by_relation.items():
            subject_groups: dict[str, list[tuple[str, str, str, int]]] = {}
            object_groups: dict[str, list[tuple[str, str, str, int]]] = {}
            for triple in relation_triples:
                subject_groups.setdefault(triple[0], []).append(triple)
                object_groups.setdefault(triple[2], []).append(triple)

            for subject, items in subject_groups.items():
                if len(items) <= 1:
                    continue
                score = len(items) - 1
                earliest = min(item[3] for item in items)
                if score > best_score or (score == best_score and earliest < best_index):
                    best_axis = "subject"
                    best_key = relation + "\0" + subject
                    best_items = items
                    best_score = score
                    best_index = earliest

            for obj, items in object_groups.items():
                if len(items) <= 1:
                    continue
                score = len(items) - 1
                earliest = min(item[3] for item in items)
                if score > best_score or (score == best_score and earliest < best_index):
                    best_axis = "object"
                    best_key = relation + "\0" + obj
                    best_items = items
                    best_score = score
                    best_index = earliest

        if best_axis is None or best_key is None or best_score <= 0:
            return None
        return best_axis, best_key, best_items

    while remaining:
        best = _pick_best_group()
        if best is None:
            for subject, relationship, obj, _ in remaining:
                compacted.append(f"{subject}|{relationship}|{obj}")
            break

        axis, key, items = best
        relation, key_value = key.split("\0", 1)
        ordered_items = sorted(items, key=lambda item: item[3])
        if axis == "subject":
            subject = key_value
            objects: list[str] = []
            for _, _, obj, _ in ordered_items:
                if obj not in objects:
                    objects.append(obj)
            compacted.append(f"{subject}|{relation}|{','.join(objects)}")
        else:
            obj = key_value
            subjects: list[str] = []
            for subject, _, _, _ in ordered_items:
                if subject not in subjects:
                    subjects.append(subject)
            compacted.append(f"{','.join(subjects)}|{relation}|{obj}")

        covered = {(subject, relationship, obj) for subject, relationship, obj, _ in items}
        remaining = [triple for triple in remaining if (triple[0], triple[1], triple[2]) not in covered]

    return passthrough + compacted
