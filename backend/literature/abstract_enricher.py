"""Fill thin abstracts from OpenAlex by DOI, before papers are fetched and screened.

Each searcher keeps the abstract its own source returns, and CrossRef carries few for Chinese
papers. In a sample of 47 thin Chinese records, OpenAlex held an abstract of 200+ characters
for 6 of the 29 from CrossRef; Semantic Scholar and CrossRef itself held none. So only
OpenAlex is asked, fifty DOIs per request, and only a longer abstract replaces the one we have.
"""
import logging

import httpx

from backend.literature.schemas import LiteratureItem
from backend.literature.searchers.openalex import _reconstruct_abstract, openalex_params
from backend.literature.text_length import weighted_length

logger = logging.getLogger(__name__)

_WORKS = "https://api.openalex.org/works"
_BATCH = 50
# the screener's threshold: below it a paper is judged on its title
_THIN = 300


def _norm_doi(doi: str) -> str:
    return doi.strip().lower().removeprefix("https://doi.org/").removeprefix("http://doi.org/")


async def _fetch(client: httpx.AsyncClient, dois: list[str]) -> dict[str, str]:
    params = openalex_params(**{"filter": "doi:" + "|".join(dois), "select": "doi,abstract_inverted_index",
                                "per-page": _BATCH})
    resp = await client.get(_WORKS, params=params)
    resp.raise_for_status()
    return {
        _norm_doi(work.get("doi") or ""): _reconstruct_abstract(work.get("abstract_inverted_index"))
        for work in resp.json().get("results", [])
    }


async def enrich_abstracts(items: list[LiteratureItem]) -> tuple[list[LiteratureItem], int]:
    """Return the items with thin abstracts filled where OpenAlex has a longer one, and how many."""
    thin = sorted({_norm_doi(i.doi) for i in items if i.doi and weighted_length(i.abstract) < _THIN})
    found: dict[str, str] = {}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            for start in range(0, len(thin), _BATCH):
                found.update(await _fetch(client, thin[start:start + _BATCH]))
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("[abstracts] OpenAlex lookup failed after %d found: %s", len(found), exc)

    enriched: list[LiteratureItem] = []
    filled = 0
    for item in items:
        new = found.get(_norm_doi(item.doi)) if item.doi else None
        if new and weighted_length(new) > weighted_length(item.abstract):
            item = item.model_copy(update={"abstract": new, "abstract_via": "openalex"})
            filled += 1
        enriched.append(item)
    logger.info("[abstracts] thin=%d filled=%d", len(thin), filled)
    return enriched, filled
