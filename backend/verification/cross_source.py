"""Look a paper up in a second database by title, for papers nothing else anchors.

A DOI (CrossRef / doi.org) or an arXiv id already anchors a record, so only papers with neither
are searched again - on OpenAlex (CrossRef when OpenAlex is where the record came from), then arXiv.
"""
import difflib
import logging
import re
import xml.etree.ElementTree as ET

import httpx

from backend.core.config import polite_pool_params
from backend.literature.searchers.openalex import openalex_params
from backend.verification.metadata_match import _CJK, _same_person, _surname

logger = logging.getLogger(__name__)

_OPENALEX = "https://api.openalex.org/works"
_CROSSREF = "https://api.crossref.org/works"
_ARXIV = "https://export.arxiv.org/api/query"
_ATOM = "{http://www.w3.org/2005/Atom}"
_TITLE_SIMILARITY = 0.9
_ANCHORED_SOURCES = {"arxiv", "upload", ""}


def needs_lookup(source: str, doi: str | None) -> bool:
    return not doi and source not in _ANCHORED_SOURCES


def _norm(title: str) -> str:
    return re.sub(r"[^0-9a-z一-鿿]+", " ", title.lower()).strip()


def _matches(title: str, authors: list[str], cand_title: str, cand_first: str) -> bool:
    if difflib.SequenceMatcher(None, _norm(title), _norm(cand_title)).ratio() < _TITLE_SIMILARITY:
        return False
    if not authors or not cand_first or bool(_CJK.search(authors[0])) != bool(_CJK.search(cand_first)):
        return True
    return _surname(authors[0]) == _surname(cand_first) or _same_person(authors[0], cand_first)


def _filter_value(title: str) -> str:
    # ":" "," and "|" belong to OpenAlex's filter syntax
    return re.sub(r"\s+", " ", re.sub(r"[:,|]", " ", title)).strip()


async def _openalex(client: httpx.AsyncClient, title: str) -> list[tuple[str, str]]:
    # the title field: full-text search ranks well-cited papers mentioning the words first
    resp = await client.get(_OPENALEX, params=openalex_params(**{"filter": f"title.search:{_filter_value(title)}",
                                                                 "per-page": 5, "select": "title,authorships"}))
    resp.raise_for_status()
    return [(w.get("title") or "", ((w.get("authorships") or [{}])[0].get("author") or {}).get("display_name", ""))
            for w in resp.json().get("results", [])]


async def _crossref(client: httpx.AsyncClient, title: str) -> list[tuple[str, str]]:
    resp = await client.get(_CROSSREF, params={"query.bibliographic": title, "rows": 5,
                                               "select": "title,author", **polite_pool_params()})
    resp.raise_for_status()
    return [((w.get("title") or [""])[0], ((w.get("author") or [{}])[0]).get("family", ""))
            for w in resp.json().get("message", {}).get("items", [])]


async def _arxiv(client: httpx.AsyncClient, title: str) -> list[tuple[str, str]]:
    # conference papers without a DOI (ICLR, NeurIPS) often live on arXiv and nowhere else
    resp = await client.get(_ARXIV, params={"search_query": f'ti:"{_filter_value(title)}"', "max_results": 3})
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    return [((e.findtext(f"{_ATOM}title") or "").strip(), (e.findtext(f"{_ATOM}author/{_ATOM}name") or "").strip())
            for e in root.findall(f"{_ATOM}entry")]


async def found_elsewhere(client: httpx.AsyncClient, title: str, authors: list[str], source: str) -> bool | None:
    """True if another database has the paper; False only if every one asked answered and none did.

    None when a lookup failed without a match elsewhere: undecided, never held against the paper.
    """
    lookups = [_crossref if source == "openalex" else _openalex, _arxiv]
    failed = False
    for lookup in lookups:
        try:
            candidates = await lookup(client, title)
        except (httpx.HTTPError, ValueError, ET.ParseError) as exc:
            logger.warning("[cross-source] %s failed for %r: %s", lookup.__name__, title[:60], exc)
            failed = True
            continue
        if any(_matches(title, authors, t, a) for t, a in candidates):
            return True
    return None if failed else False
