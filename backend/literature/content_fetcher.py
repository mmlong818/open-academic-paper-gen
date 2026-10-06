"""Fetches full-text excerpts for literature items via Semantic Scholar + PDF download."""
import asyncio
import io
import logging
import re
from typing import TYPE_CHECKING

import httpx

from backend.literature.paper_cache import cache_key, current, load_cached, merge_cached, store_cached
from backend.literature.schemas import LiteratureItem
from backend.core.config import settings

logger = logging.getLogger(__name__)

_S2_BASE = "https://api.semanticscholar.org/graph/v1/paper"
_S2_FIELDS = "abstract,openAccessPdf,tldr"
_FETCH_SEMAPHORE = asyncio.Semaphore(3)
_PDF_MAX_CHARS = 2000
# Full text is kept for layer 3's passage search: the results a claim cites sit in the
# methods and experiments, well past the 2000-char excerpt. The whole PDF is read; a body longer
# than head + tail keeps its first 40000 chars and the 10000 before its references. Read whole,
# 27 of 60 papers ran past 40000, and the start alone lost the conclusion in 17 of 53; it sits a
# median 2.1k chars (p90 8.3k) before the references, so the tail keeps it in 51 of 53.
_PDF_MAX_PAGES = 60
_HEAD_CHARS = 40000
_TAIL_CHARS = 10000
GAP = "\n[...]\n"
_REFERENCES_HEADING = re.compile(
    r"(?:^|\n)\s*(?:\d+\.?\s*|[IVX]+\.\s*)?(?:References|REFERENCES|Bibliography|BIBLIOGRAPHY|参考文献)[:：]?\s*\n"
)
# Headings further in than this are references or body text, not the start of the paper.
_HEADING_WINDOW = 5000
# Capitalised headings followed by punctuation or a capitalised word, so prose such as
# "an abstract representation" does not match.
_ABSTRACT_HEADING = re.compile(
    r"\b(?:Abstract|ABSTRACT)\b(?=\s*[:.\-–—]|\s+[A-Z])"
    r"|[\[【]\s*摘\s*要|摘\s*要\s*[:：\]】]"
)
_INTRO_HEADING = re.compile(
    r"\b(?:\d\.?\s*)?(?:Introduction|INTRODUCTION)\b(?=\s*[:.\-–—]|\s+[A-Z])"
    r"|引\s*言"
)
_HTTP_TIMEOUT = 15


def _s2_headers() -> dict[str, str]:
    key = settings.semantic_scholar_api_key
    return {"x-api-key": key} if key else {}


async def _fetch_s2_meta(doi: str, client: httpx.AsyncClient) -> dict:
    """Return Semantic Scholar paper fields dict, or {} on failure."""
    url = f"{_S2_BASE}/DOI:{doi}?fields={_S2_FIELDS}"
    try:
        resp = await client.get(url, headers=_s2_headers(), timeout=_HTTP_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
        logger.debug("[s2] DOI=%s status=%d", doi, resp.status_code)
    except Exception as exc:
        logger.debug("[s2] DOI=%s error=%s", doi, exc)
    return {}


async def _fetch_pdf_text(pdf_url: str, client: httpx.AsyncClient) -> tuple[str, list[list[int]]]:
    """Download a PDF: its body from the Abstract to the references, cut by _join_pages, and its page offsets."""
    try:
        resp = await client.get(pdf_url, timeout=_HTTP_TIMEOUT, follow_redirects=True)
        if resp.status_code != 200:
            return "", []
        ct = resp.headers.get("content-type", "")
        if "pdf" not in ct and not pdf_url.lower().endswith(".pdf"):
            return "", []
        from pypdf import PdfReader  # lazy import
        reader = PdfReader(io.BytesIO(resp.content))
        return _join_pages([page.extract_text() or "" for page in reader.pages[:_PDF_MAX_PAGES]])
    except Exception as exc:
        logger.debug("[pdf] url=%s error=%s", pdf_url, exc)
        return "", []


def references_start(text: str) -> int:
    """Where the reference list starts: the last References heading past the first third, else the end.

    Earlier hits are a heading-like line in the front matter or a table of contents."""
    starts = [m.start() for m in _REFERENCES_HEADING.finditer(text)]
    return next((s for s in reversed(starts) if s > len(text) / 3), len(text))


def _join_pages(
    page_texts: list[str], head: int = _HEAD_CHARS, tail: int = _TAIL_CHARS,
) -> tuple[str, list[list[int]]]:
    """The body from its Abstract to its references, with [offset, PDF page] for each page it keeps.

    A body longer than head + tail keeps its first `head` and last `tail` chars, joined by GAP.
    """
    page_texts = [t.replace("\x00", "") for t in page_texts]  # pypdf emits NUL; Postgres text rejects it
    raw = "".join(page_texts)
    start = len(raw) - len(_trim_front_matter(raw))
    end = start + references_start(raw[start:])
    while start < end and raw[start].isspace():
        start += 1
    while end > start and raw[end - 1].isspace():
        end -= 1
    if end - start <= head + tail:
        spans = [(start, end)]
    else:
        spans = [(start, start + head)] + ([(end - tail, end)] if tail else [])
    return _cut(raw, page_texts, spans)


def _cut(raw: str, page_texts: list[str], spans: list[tuple[int, int]]) -> tuple[str, list[list[int]]]:
    """The spans of raw joined by GAP, and [offset into the result, PDF page] for every page they touch."""
    pieces: list[str] = []
    pages: list[list[int]] = []
    offset = 0
    for a, b in spans:
        if pieces:
            pieces.append(GAP)
            offset += len(GAP)
        page_start = 0
        for number, page_text in enumerate(page_texts, 1):
            page_end = page_start + len(page_text)
            if page_end > a and page_start < b:
                pages.append([offset + max(0, page_start - a), number])
            page_start = page_end
        pieces.append(raw[a:b])
        offset += b - a
    return "".join(pieces), pages


def _trim_front_matter(text: str) -> str:
    """Start the text at its Abstract heading, else its Introduction, else leave it be.

    Abstract is preferred because layer 3 judges against the excerpt alone once one
    exists: starting at the Introduction would drop the abstract from the evidence.
    """
    window = text[:_HEADING_WINDOW]
    for heading in (_ABSTRACT_HEADING, _INTRO_HEADING):
        m = heading.search(window)
        if m:
            return text[m.start():]
    return text


_ARXIV_DOI = re.compile(r"(?i)^10\.48550/arxiv\.(.+)$")


def arxiv_id(item: LiteratureItem) -> str:
    if item.source == "arxiv" and item.source_id:
        return item.source_id
    m = _ARXIV_DOI.match((item.doi or "").strip())
    return m.group(1) if m else ""


def _looks_like_pdf(url: str) -> bool:
    path = url.lower().split("?")[0]
    return path.endswith(".pdf") or "/pdf/" in path


def pdf_candidates(item: LiteratureItem, s2_pdf: str) -> list[str]:
    """Open-access PDF URLs to try, best first.

    Semantic Scholar's openAccessPdf needs a DOI, so on its own it reached only a fraction
    of the pool: of 120 cited papers without a body excerpt, 32 already carried an
    OpenAlex PDF URL and 19 were DOI-less arXiv papers whose PDF follows from their id.
    """
    urls = [s2_pdf, item.url if _looks_like_pdf(item.url) else ""]
    aid = arxiv_id(item)
    if aid:
        urls.append(f"https://arxiv.org/pdf/{aid}")
    unique: list[str] = []
    for url in urls:
        if url and url not in unique:
            unique.append(url)
    return unique


async def _enrich_one(item: LiteratureItem, client: httpx.AsyncClient) -> LiteratureItem:
    """Fetch body_excerpt for a single item. Returns item with body_excerpt filled."""
    async with _FETCH_SEMAPHORE:
        doi = (item.doi or "").strip()
        meta = await _fetch_s2_meta(doi, client) if doi else {}

        # 1. Try to get a richer abstract from S2 (often more complete than OpenAlex)
        s2_abstract: str = (meta.get("abstract") or "").strip()

        # 2. Try each known open-access PDF in turn for actual body text
        s2_pdf: str = ((meta.get("openAccessPdf") or {}).get("url") or "").strip()
        body, pages = "", []
        for pdf_url in pdf_candidates(item, s2_pdf):
            body, pages = await _fetch_pdf_text(pdf_url, client)
            if len(body) >= 300:
                break

        if not doi and len(body) < 300:
            # nothing fetched for a DOI-less item: keep it as it was
            return item

        # Decide best excerpt: PDF body > S2 abstract > original abstract
        if len(body) >= 300:
            excerpt = body[:_PDF_MAX_CHARS]
        elif len(s2_abstract) >= len(item.abstract or ""):
            excerpt = s2_abstract
        else:
            excerpt = item.abstract or ""

        return item.model_copy(update={
            "body_excerpt": excerpt,
            "full_text": body if len(body) >= 300 else "",
            "full_text_pages": pages if len(body) >= 300 else [],
            "abstract": s2_abstract or item.abstract,
        })


class PaperContentFetcher:
    """Concurrently enriches LiteratureItems with full-text excerpts."""

    async def run(self, items: list[LiteratureItem]) -> list[LiteratureItem]:
        if not items:
            return items
        cached = await _load(items)
        merged = [merge_cached(item, cached[k]) if (k := cache_key(item)) in cached else item for item in items]
        # full text in the cache: nothing left to fetch
        todo = [i for i, item in enumerate(items) if not (cached.get(cache_key(item)) or {}).get("full_text")]
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            fetched = await asyncio.gather(*[_enrich_one(merged[i], client) for i in todo])
        for i, item in zip(todo, fetched):
            merged[i] = item
        await _store(list(fetched))
        fetched_body = sum(1 for item in merged if len(item.body_excerpt) >= 300)
        logger.info(
            "[content_fetcher] total=%d cache_hits=%d with_body_excerpt(>=300)=%d",
            len(items), len(items) - len(todo), fetched_body,
        )
        return merged


async def _load(items: list[LiteratureItem]) -> dict[str, dict]:
    keys = sorted({k for item in items if (k := cache_key(item))})
    if not settings.paper_cache or not keys:
        return {}
    try:
        return {k: current(row) for k, row in (await load_cached(keys)).items()}
    except Exception as exc:  # the cache is a convenience, never a reason to stop
        logger.warning("[paper_cache] load failed, fetching everything: %s", exc)
        return {}


async def _store(items: list[LiteratureItem]) -> None:
    if not settings.paper_cache or not items:
        return
    try:
        stored = await store_cached(items)
        logger.info("[paper_cache] stored=%d", stored)
    except Exception as exc:
        logger.warning("[paper_cache] store failed: %s", exc)
