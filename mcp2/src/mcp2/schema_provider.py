from __future__ import annotations

from .models import KGSchema
from .repository.base import GraphRepository


class SchemaProvider:
    def __init__(self, repository: GraphRepository):
        self.repository = repository

    async def get_schema(self) -> KGSchema:
        return await self.repository.get_schema()
