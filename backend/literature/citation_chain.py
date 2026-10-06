"""T2.2 — expand the screened pool along the citation links of its strongest papers.

Keyword search finds papers that use the query's words; the works a field's strongest
papers keep citing - its classics - may use none of them. The seeds' references and
citations are pulled from Semantic Scholar, papers already in the pool are skipped, and
candidates linked to more seeds rank first (co-citation is the best signal that a paper
is must-cite), then by citation count. The caller screens the candidates exactly like
the searched papers. Every network failure degrades to fewer candidates, never an error.
"""
import asyncio
import logging
import re
from collections import defaultdict

import httpx

from backend.literature.content_fetcher import arxiv_id
from backend.literature.dedup import _normalise_title
from backend.literature.schemas import LiteratureItem
from backend.literature.scorer import score_items
from backend.core.config import settings

logger = logging.getLogger(__name__)

_S2 = "https://api.semanticscholar.org/graph/v1/paper"
_FIELDS = "paperId,title,authors,year,citationCount,externalIds,abstract,venue,url"
# (endpoint, row field, limit). References are fetched whole - the classics sit there, and
# at 100 a 227-reference survey lost Lewis 2020 and DPR. Citations of a highly cited paper
# run to thousands; the first 100 are enough to catch follow-up work.
_LINKS = (("references", "citedPaper", 1000), ("citations", "citingPaper", 100))
_MIN_ABSTRACT_CHARS = 50
_TIMEOUT = 20.0
_ARXIV_VERSION = re.compile(r"v\d+$")


def s2_id(item: LiteratureItem) -> str:
    """The Semantic Scholar identifier for an item, or "" if it has none.

    arXiv papers go by their arXiv id: S2 found no links at all for a 10.48550/arXiv DOI.
    """
    arxiv = arxiv_id(item)
    if arxiv:
        return f"ARXIV:{_ARXIV_VERSION.sub('', arxiv)}"
    if item.doi:
        return f"DOI:{item.doi}"
    if item.source == "semantic_scholar" and item.source_id:
        return item.source_id
    return ""


class CitationChainExpander:
    def __init__(self, retry_wait: float = 2.0) -> None:
        self._retry_wait = retry_wait
        self._semaphore = asyncio.Semaphore(2)  # S2 without a key allows about one request a second
        key = settings.semantic_scholar_api_key
        self._headers = {"x-api-key": key} if key else {}

    async def expand(
        self,
        seeds: list[LiteratureItem],
        existing: list[LiteratureItem],
        max_seeds: int = 8,
        # With references fetched whole there are ~1000 candidates; on the eval pools raising
        # the cut from 40 to 60 brought 1-2 more hand-listed classics per topic into screening.
        max_new: int = 60,
        topic_terms: list[str] | None = None,
    ) -> list[LiteratureItem]:
        chosen = [s for s in sorted(seeds, key=lambda s: s.quality_score, reverse=True) if s2_id(s)][:max_seeds]
        if not chosen:
            return []
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            linked = await asyncio.gather(*[self._linked_papers(client, s2_id(s)) for s in chosen])

        known_dois = {(i.doi or "").lower() for i in existing if i.doi}
        known_titles = {_normalise_title(i.title) for i in existing}
        candidates: dict[str, dict] = {}
        links: dict[str, set[str]] = defaultdict(set)
        for seed, papers in zip(chosen, linked):
            for paper in papers:
                if not _usable(paper, known_dois, known_titles):
                    continue
                candidates[paper["paperId"]] = paper
                links[paper["paperId"]].add(seed.title)

        # Generic tools (Adam, random forests) are cited by everything; with few shared links
        # they outranked the field's own papers on citation count alone.
        terms = _terms(topic_terms or [])
        ranked = sorted(
            candidates,
            key=lambda pid: (
                len(links[pid]),
                not terms or _mentions(candidates[pid], terms),
                candidates[pid].get("citationCount") or 0,
            ),
            reverse=True,
        )[:max_new]
        logger.info("[chain] seeds=%d candidates=%d kept=%d", len(chosen), len(candidates), len(ranked))
        return [_to_item(candidates[pid], sorted(links[pid])) for pid in ranked]

    async def _linked_papers(self, client: httpx.AsyncClient, paper_id: str) -> list[dict]:
        papers: list[dict] = []
        for endpoint, field, limit in _LINKS:
            url = f"{_S2}/{paper_id}/{endpoint}"
            data = await self._get(client, url, {"fields": _FIELDS, "limit": limit})
            papers.extend(row[field] for row in data.get("data") or [] if row.get(field))
        return papers

    async def _get(self, client: httpx.AsyncClient, url: str, params: dict) -> dict:
        for attempt in range(2):
            try:
                async with self._semaphore:
                    resp = await client.get(url, params=params, headers=self._headers)
            except httpx.HTTPError as exc:
                logger.debug("[chain] %s failed: %s", url, exc)
                return {}
            if resp.status_code == 429 and attempt == 0:
                await asyncio.sleep(self._retry_wait)
                continue
            if resp.status_code != 200:
                logger.debug("[chain] %s status=%d", url, resp.status_code)
                return {}
            return resp.json()
        return {}


_WORD = re.compile(r"[a-z][a-z0-9\-]{3,}")
_CJK_RUN = re.compile(r"[一-鿿]{2,}")


def _terms(phrases: list[str]) -> set[str]:
    text = " ".join(phrases).lower()
    words = set(_WORD.findall(text))
    for run in _CJK_RUN.findall(text):
        words.update(run[i:i + 2] for i in range(len(run) - 1))
    return words


def _mentions(paper: dict, terms: set[str]) -> bool:
    text = f"{paper.get('title') or ''} {paper.get('abstract') or ''}".lower()
    return any(term in text for term in terms)


def _usable(paper: dict, known_dois: set[str], known_titles: set[str]) -> bool:
    title = (paper.get("title") or "").strip()
    doi = ((paper.get("externalIds") or {}).get("DOI") or "").lower()
    return bool(
        paper.get("paperId") and title
        and len((paper.get("abstract") or "").strip()) >= _MIN_ABSTRACT_CHARS
        and _normalise_title(title) not in known_titles
        and not (doi and doi in known_dois)
    )


def _to_item(paper: dict, seed_titles: list[str]) -> LiteratureItem:
    ids = paper.get("externalIds") or {}
    return LiteratureItem(
        title=paper["title"],
        authors=[a["name"] for a in paper.get("authors") or [] if a.get("name")],
        year=paper.get("year"),
        doi=ids.get("DOI"),
        abstract=paper.get("abstract") or "",
        citation_count=paper.get("citationCount") or 0,
        journal=paper.get("venue") or None,
        source="semantic_scholar",
        source_id=paper["paperId"],
        url=paper.get("url") or "",
        raw={"chained_from": seed_titles, "chain_links": len(seed_titles)},
    )


async def chain_and_screen(
    retained: list[LiteratureItem],
    pool: list[LiteratureItem],
    topic_terms: list[str],
    fetcher,
    screener,
    topic: str,
    language: str,
) -> tuple[list[LiteratureItem], list[dict], int]:
    """Expand along citations, then fetch, screen and score the candidates like searched papers.

    Returns (papers kept, screening rows, number of candidates screened).
    """
    candidates = await CitationChainExpander().expand(retained, existing=pool, topic_terms=topic_terms)
    if not candidates:
        return [], [], 0
    candidates = await fetcher.run(candidates)
    kept, rows = await screener.run(topic=topic, items=candidates, language=language)
    return score_items(kept), rows, len(candidates)
