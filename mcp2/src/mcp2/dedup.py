from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass
class FactDeduplicator:
    exposed_facts: set[tuple[UUID, str, str]] = field(default_factory=set)

    def add_if_new(self, subject_uuid: UUID, relationship: str, object_or_literal: Any) -> bool:
        normalized = (subject_uuid, relationship, str(object_or_literal))
        if normalized in self.exposed_facts:
            return False
        self.exposed_facts.add(normalized)
        return True
