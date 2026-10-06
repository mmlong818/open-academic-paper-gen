# backend/literature/searchers/base.py
from typing import Protocol
from backend.literature.schemas import LiteratureItem, SearchQuery


class Searcher(Protocol):
    async def search(self, query: SearchQuery) -> list[LiteratureItem]:
        ...
