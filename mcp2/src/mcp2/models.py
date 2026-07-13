from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


EntityType = str
Direction = Literal["out", "in", "either"]


class SchemaRelation(BaseModel):
    name: str
    source_type: str
    target_type: str


class KGSchema(BaseModel):
    entity_types: list[str] = Field(default_factory=list)
    relations: list[SchemaRelation] = Field(default_factory=list)

    def relation_names(self) -> set[str]:
        return {r.name for r in self.relations}


class EntityRecord(BaseModel):
    uuid: UUID
    entity_type: str
    display_name: str
    properties: dict[str, Any] = Field(default_factory=dict)


class RelationRecord(BaseModel):
    subject_uuid: UUID
    relationship: str
    object_uuid: UUID | None = None
    literal_value: Any | None = None


class ToolResult(BaseModel):
    NEW_E: list[str] = Field(default_factory=list)
    NEW_F: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
