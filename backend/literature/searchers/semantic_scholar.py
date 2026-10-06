# backend/literature/searchers/semantic_scholar.py
import httpx
from backend.literature.schemas import LiteratureItem, SearchQuery
from backend.core.config import settings

_BASE = "https://api.semanticscholar.org/graph/v1/paper/search"
_FIELDS = "paperId,title,authors,year,citationCount,externalIds,abstract,venue,url"
_TIMEOUT = 30.0


class SemanticScholarSearcher:
    async def search(self, query: SearchQuery) -> list[LiteratureItem]:
        params = {
            "query": " ".join(query.keywords),
            "fields": _FIELDS,
            "limit": query.max_results,
        }
        headers = {}
        key = settings.semantic_scholar_api_key
        if key:
            headers["x-api-key"] = key
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(_BASE, params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return []

        items = []
        for paper in data.get("data", []):
            doi = (paper.get("externalIds") or {}).get("DOI")
            items.append(
                LiteratureItem(
                    title=paper.get("title", ""),
                    authors=[a["name"] for a in paper.get("authors", [])],
                    year=paper.get("year"),
                    doi=doi,
                    abstract=paper.get("abstract") or "",
                    citation_count=paper.get("citationCount") or 0,
                    journal=paper.get("venue") or None,
                    source="semantic_scholar",
                    source_id=paper.get("paperId", ""),
                    url=paper.get("url", ""),
                    raw=paper,
                )
            )
        return items
