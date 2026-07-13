from __future__ import annotations

from typing import Any

from .constants import RELATION_SCHEMA


RELATION_PHRASE_MAP: dict[str, str] = {}
for item in RELATION_SCHEMA:
    key = str(item.get("key", "")).upper()
    reverse_key = str(item.get("reverseKey", "")).upper()
    name = str(item.get("name", "")).strip().lower()
    reverse_name = str(item.get("reverseName", "")).strip().lower()
    if key and name:
        RELATION_PHRASE_MAP[key] = name
    if reverse_key and reverse_name:
        RELATION_PHRASE_MAP[reverse_key] = reverse_name


def relation_phrase(relation_type: str) -> str:
    key = (relation_type or "").upper()
    phrase = RELATION_PHRASE_MAP.get(key)
    if phrase:
        return phrase
    return key.replace("_", " ").strip().lower()


def _normalize_relation_clause(phrase: str) -> str:
    cleaned = (phrase or "").strip().lower()
    if not cleaned:
        return "is related to"

    direct_verbs = (
        "is ",
        "has ",
        "works ",
        "lives ",
        "acted ",
        "directed ",
        "gave ",
        "contains",
        "inspired",
        "studies ",
    )
    if cleaned.startswith(direct_verbs):
        return cleaned

    if cleaned.endswith((" of", " at", " in", " on", " for", " to")):
        return f"is {cleaned}"

    role_like = {
        "author",
        "actor",
        "director",
        "student",
        "teacher",
        "member",
        "manager",
        "resident",
    }
    if cleaned in role_like:
        return f"is {cleaned} of"

    return f"is {cleaned}"


def join_human(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _clean(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _human_key(key: str) -> str:
    return key.replace("_", " ").strip()


def _value_to_phrase(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        cleaned = [str(v).strip() for v in value if str(v).strip()]
        return join_human(cleaned) if cleaned else ""
    if isinstance(value, dict):
        return ""
    text = str(value).strip()
    return text


def build_entity_sentences(entity: dict[str, Any]) -> list[str]:
    display = _clean(entity.get("display")) or "This entity"
    entity_type = _clean(entity.get("type")) or "Entity"

    lines: list[str] = []

    description = _clean(entity.get("description"))
    tags = entity.get("tags") if isinstance(entity.get("tags"), list) else []
    tags = [str(t).strip() for t in tags if str(t).strip()]

    if entity_type == "Person":
        intro = f"{display} is a person"
        if tags:
            intro += f" with tags {join_human(tags)}"
        lines.append(f"{intro}.")
    else:
        intro = f"{display} is a {entity_type}"
        if tags:
            intro += f" with tags {join_human(tags)}"
        lines.append(f"{intro}.")

    if description:
        lines.append(f"{display} description is {description}.")

    if entity_type == "Person":
        first_name = _clean(entity.get("first_name"))
        last_name = _clean(entity.get("last_name"))
        if first_name or last_name:
            full = (first_name + " " + last_name).strip()
            if full and full.casefold() != display.casefold():
                lines.append(f"Their full name is {full}.")

        dob = _clean(entity.get("dob"))
        if dob:
            lines.append(f"They were born on {dob}.")

        gender = _clean(entity.get("gender"))
        if gender and gender.casefold() != "unspecified":
            lines.append(f"Gender is {gender}.")

        profession = _clean(entity.get("profession"))
        if profession:
            lines.append(f"Profession is {profession}.")

        emails = entity.get("emails") if isinstance(entity.get("emails"), list) else []
        emails = [str(v).strip() for v in emails if str(v).strip()]
        if emails:
            lines.append(f"Their email addresses are {join_human(emails)}.")

        phones = entity.get("phones") if isinstance(entity.get("phones"), list) else []
        phones = [str(v).strip() for v in phones if str(v).strip()]
        if phones:
            lines.append(f"Their phone numbers are {join_human(phones)}.")

    if entity_type == "Org":
        name = _clean(entity.get("name"))
        if name:
            lines.append(f"Organization name is {name}.")
        kind = _clean(entity.get("kind"))
        if kind:
            lines.append(f"{display} is categorized as {kind}.")

    if entity_type == "Location":
        city = _clean(entity.get("city"))
        state = _clean(entity.get("state"))
        country = _clean(entity.get("country"))
        parts = [p for p in [city, state, country] if p]
        if parts:
            lines.append(f"{display} is in {join_human(parts)}.")
        address1 = _clean(entity.get("address1"))
        if address1:
            lines.append(f"Primary address is {address1}.")

    if entity_type in {"Movie", "Book"}:
        year = _clean(entity.get("year"))
        if year:
            lines.append(f"{display} year is {year}.")
        language = _clean(entity.get("language"))
        if language:
            lines.append(f"{display} language is {language}.")
        country = _clean(entity.get("country"))
        if country:
            lines.append(f"{display} country is {country}.")

    if entity_type == "Asset":
        value = _clean(entity.get("value"))
        if value:
            lines.append(f"{display} value is {value}.")
        acquired_on = _clean(entity.get("acquired_on"))
        if acquired_on:
            lines.append(f"{display} was acquired on {acquired_on}.")

    if entity_type == "Note":
        date = _clean(entity.get("date"))
        if date:
            lines.append(f"{display} note date is {date}.")

    handled = {
        "id",
        "type",
        "display",
        "description",
        "tags",
        "urls",
        "photos",
        "attachments",
        "locations",
        "is_encrypted",
        "first_name",
        "last_name",
        "dob",
        "gender",
        "profession",
        "emails",
        "phones",
        "name",
        "kind",
        "city",
        "state",
        "country",
        "address1",
        "year",
        "language",
        "value",
        "acquired_on",
        "date",
        "created_at",
        "updated_at",
        "user",
        "encrypted_data",
    }

    for key, value in entity.items():
        if key in handled:
            continue
        phrase_value = _value_to_phrase(value)
        if not phrase_value:
            continue
        lines.append(f"{display} {_human_key(key)} is {phrase_value}.")

    return lines


def relation_sentence(subject_name: str, relation_type: str, target_name: str) -> str:
    phrase = _normalize_relation_clause(relation_phrase(relation_type))
    return f"{subject_name} {phrase} {target_name}."


def build_relationship_sentences(subject_name: str, outgoing: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for rel in outgoing:
        relation_type = str(rel.get("relation_type", "")).upper()
        target = rel.get("entity", {}) if isinstance(rel.get("entity"), dict) else {}
        target_name = str(target.get("display") or target.get("name") or target.get("id") or "Unknown").strip()
        if not relation_type or not target_name:
            continue
        lines.append(relation_sentence(subject_name=subject_name, relation_type=relation_type, target_name=target_name))
    return lines


def _summarize_outgoing_relations(outgoing: list[dict[str, Any]]) -> list[str]:
    grouped: dict[str, list[str]] = {}
    for rel in outgoing:
        if not isinstance(rel, dict):
            continue
        relation_type = str(rel.get("relation_type", "")).upper().strip()
        if not relation_type:
            continue
        target = rel.get("entity", {}) if isinstance(rel.get("entity"), dict) else {}
        target_name = str(target.get("display") or target.get("name") or target.get("id") or "").strip()
        if not target_name:
            continue
        bucket = grouped.setdefault(relation_type, [])
        if target_name not in bucket:
            bucket.append(target_name)

    if not grouped:
        return []

    lines: list[str] = []
    for relation_type, targets in grouped.items():
        joined_targets = join_human(targets)
        if relation_type == "IS_CHILD_OF":
            lines.append(f"They are the child of {joined_targets}.")
            continue
        if relation_type == "IS_PARENT_OF":
            lines.append(f"They are the parent of {joined_targets}.")
            continue
        if relation_type == "WORKS_AT":
            lines.append(f"They work at {joined_targets}.")
            continue
        if relation_type == "LIVES_AT":
            lines.append(f"They live at {joined_targets}.")
            continue

        phrase = _normalize_relation_clause(relation_phrase(relation_type))
        if phrase.startswith("is "):
            phrase = "are " + phrase[3:]
        lines.append(f"They {phrase} {joined_targets}.")

    return lines


def build_text_block(
    entity: dict[str, Any],
    outgoing: list[dict[str, Any]],
    incoming: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    subject_name = str(entity.get("display") or entity.get("name") or entity.get("id") or "Entity").strip()
    entity_lines = build_entity_sentences(entity)
    outgoing_lines = build_relationship_sentences(subject_name=subject_name, outgoing=outgoing)
    outgoing_summary_lines = _summarize_outgoing_relations(outgoing)

    incoming_lines: list[str] = []
    for rel in incoming or []:
        relation_type = str(rel.get("relation_type", "")).upper()
        source = rel.get("entity", {}) if isinstance(rel.get("entity"), dict) else {}
        source_name = str(source.get("display") or source.get("name") or source.get("id") or "Unknown").strip()
        if not relation_type or not source_name:
            continue
        incoming_lines.append(relation_sentence(subject_name=source_name, relation_type=relation_type, target_name=subject_name))

    relation_lines = outgoing_lines

    text_lines: list[str] = []
    if entity_lines:
        text_lines.extend(entity_lines)
    if outgoing_summary_lines:
        text_lines.extend(outgoing_summary_lines)
    elif outgoing_lines:
        text_lines.extend(outgoing_lines)
    if not text_lines:
        text_lines.append("No entity attributes or outgoing relationships found.")

    text_block = "\n".join(text_lines)

    return {
        "entity_sentences": entity_lines,
        "relationship_sentences": relation_lines,
        "outgoing_relationship_sentences": outgoing_lines,
        "incoming_relationship_sentences": incoming_lines,
        "text_block": text_block,
    }
