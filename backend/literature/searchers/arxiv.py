# backend/literature/searchers/arxiv.py
import xml.etree.ElementTree as ET
import httpx
from backend.literature.schemas import LiteratureItem, SearchQuery

_BASE = "https://export.arxiv.org/api/query"
_NS = {"atom": "http://www.w3.org/2005/Atom"}
_TIMEOUT = 30.0


class ArxivSearcher:
    async def search(self, query: SearchQuery) -> list[LiteratureItem]:
        search_query = " AND ".join(f"all:{kw}" for kw in query.keywords)
        params = {
            "search_query": search_query,
            "max_results": query.max_results,
            "sortBy": "relevance",
        }
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(_BASE, params=params)
                resp.raise_for_status()
                root = ET.fromstring(resp.text)
        except Exception:
            return []

        items = []
        for entry in root.findall("atom:entry", _NS):
            title_el = entry.find("atom:title", _NS)
            title = title_el.text.strip() if title_el is not None and title_el.text else ""

            authors = [
                name_el.text.strip()
                for author in entry.findall("atom:author", _NS)
                if (name_el := author.find("atom:name", _NS)) is not None and name_el.text
            ]

            published_el = entry.find("atom:published", _NS)
            year: int | None = None
            if published_el is not None and published_el.text:
                try:
                    year = int(published_el.text[:4])
                except ValueError:
                    pass

            abstract_el = entry.find("atom:summary", _NS)
            abstract = abstract_el.text.strip() if abstract_el is not None and abstract_el.text else ""

            id_el = entry.find("atom:id", _NS)
            arxiv_id = id_el.text.strip() if id_el is not None and id_el.text else ""
            source_id = arxiv_id.split("/abs/")[-1] if "/abs/" in arxiv_id else arxiv_id

            link_el = entry.find("atom:link[@rel='alternate']", _NS)
            url = link_el.get("href", "") if link_el is not None else ""

            items.append(
                LiteratureItem(
                    title=title,
                    authors=authors,
                    year=year,
                    abstract=abstract,
                    pub_type="preprint",
                    source="arxiv",
                    source_id=source_id,
                    url=url,
                    raw={"id": arxiv_id},
                )
            )
        return items
