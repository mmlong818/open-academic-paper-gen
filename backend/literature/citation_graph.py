"""Citation-graph taxonomy that shapes review outlines.

A review outline written from a synthesis text alone tends to walk through papers or
research questions instead of the field's structure. Here the screened pool is grouped
by how its papers relate: direct citations and shared references among them (from one
Semantic Scholar batch call), blended with title-and-abstract similarity. Papers S2
cannot place fall back to text alone. k-medoids clustering gives up to 4-7 groups, each
described by representative titles and distinctive terms; the outline prompt then
organises the body around them. Standard library only; every failure yields no taxonomy.
"""
import asyncio
import logging
import math
import re
from collections import Counter

import httpx

from backend.literature.bibtex import bibtex_key
from backend.literature.citation_chain import s2_id
from backend.literature.schemas import LiteratureItem
from backend.core.config import settings

logger = logging.getLogger(__name__)

_S2_BATCH = "https://api.semanticscholar.org/graph/v1/paper/batch"
_BATCH_MAX = 500
_MIN_POOL = 12
_MIN_GROUP = 3
_TITLES_PER_GROUP = 5
_TERMS_PER_GROUP = 6

_WORD = re.compile(r"[a-z][a-z\-]{3,}")
_CJK_RUN = re.compile(r"[一-鿿]{2,}")
_STOPWORDS = {
    "with", "from", "that", "this", "these", "those", "their", "which", "using", "based", "study",
    "approach", "method", "methods", "results", "paper", "propose", "proposed", "show", "also",
    "into", "such", "than", "more", "have", "been", "were", "they", "between", "while", "through",
}


async def fetch_reference_sets(
    items: list[LiteratureItem], retry_wait: float = 3.0
) -> tuple[list[str | None], list[set[str]]]:
    """Each item's S2 paperId and the set of paperIds it references (None / empty if unknown)."""
    wanted = [(i, s2_id(item)) for i, item in enumerate(items) if s2_id(item)]
    paper_ids: list[str | None] = [None] * len(items)
    refs: list[set[str]] = [set() for _ in items]
    key = settings.semantic_scholar_api_key
    headers = {"x-api-key": key} if key else {}
    async with httpx.AsyncClient(timeout=60) as client:
        for start in range(0, len(wanted), _BATCH_MAX):
            chunk = wanted[start:start + _BATCH_MAX]
            rows = await _post_batch(client, [sid for _, sid in chunk], headers, retry_wait)
            for (index, _), row in zip(chunk, rows):
                if row:
                    paper_ids[index] = row.get("paperId")
                    refs[index] = {r["paperId"] for r in row.get("references") or [] if r and r.get("paperId")}
    return paper_ids, refs


async def _post_batch(client: httpx.AsyncClient, ids: list[str], headers: dict, retry_wait: float) -> list:
    for attempt in range(3):
        try:
            resp = await client.post(_S2_BATCH, params={"fields": "paperId,references.paperId"},
                                     json={"ids": ids}, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("[graph] batch request failed: %s", exc)
            return []
        if resp.status_code == 429 and attempt < 2:
            await asyncio.sleep(retry_wait)
            continue
        if resp.status_code != 200:
            logger.warning("[graph] batch status=%d", resp.status_code)
            return []
        return resp.json()
    return []


def _tokens(item: LiteratureItem) -> list[str]:
    text = f"{item.title} {item.abstract}".lower()
    words = [w for w in _WORD.findall(text) if w not in _STOPWORDS]
    for run in _CJK_RUN.findall(text):
        words.extend(run[i:i + 2] for i in range(len(run) - 1))
    return words


def _tfidf(items: list[LiteratureItem]) -> list[dict[str, float]]:
    docs = [Counter(_tokens(i)) for i in items]
    df = Counter(t for d in docs for t in d)
    n = len(items)
    vectors = []
    for d in docs:
        v = {t: c * math.log(1 + n / df[t]) for t, c in d.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vectors.append({t: x / norm for t, x in v.items()})
    return vectors


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(t, 0.0) for t, x in a.items())


def _citation_link(i: int, j: int, paper_ids: list[str | None], refs: list[set[str]]) -> float | None:
    """1 for a direct citation, else shared-reference overlap; None if either lacks data."""
    if not refs[i] or not refs[j]:
        return None
    if (paper_ids[j] and paper_ids[j] in refs[i]) or (paper_ids[i] and paper_ids[i] in refs[j]):
        return 1.0
    return len(refs[i] & refs[j]) / len(refs[i] | refs[j])


def similarity_matrix(
    items: list[LiteratureItem], paper_ids: list[str | None], refs: list[set[str]]
) -> list[list[float]]:
    vectors = _tfidf(items)
    n = len(items)
    sim = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            text = _cosine(vectors[i], vectors[j])
            link = _citation_link(i, j, paper_ids, refs)
            sim[i][j] = sim[j][i] = text if link is None else (text + link) / 2
    return sim


def cluster(sim: list[list[float]], k: int, rounds: int = 20) -> list[list[int]]:
    """k-medoids with farthest-first seeding; groups under _MIN_GROUP are folded into their nearest.

    Average-linkage clustering chained a 127-paper RAG pool into one group of 119: on a topic
    whose papers all share its vocabulary, similarities are uniformly low and linkage keeps
    merging into the largest group. Medoids seeded far apart keep the groups distinct.
    """
    n = len(sim)

    def s(a: int, b: int) -> float:
        return 1.0 if a == b else sim[a][b]

    medoids = [max(range(n), key=lambda i: sum(sim[i]))]
    while len(medoids) < min(k, n):
        medoids.append(min((i for i in range(n) if i not in medoids),
                           key=lambda i: max(s(i, m) for m in medoids)))
    groups: list[list[int]] = []
    for _ in range(rounds):
        groups = [[] for _ in medoids]
        for i in range(n):
            groups[max(range(len(medoids)), key=lambda g: s(i, medoids[g]))].append(i)
        groups = [g for g in groups if g]
        updated = [max(g, key=lambda c: sum(s(c, o) for o in g)) for g in groups]
        if updated == medoids:
            break
        medoids = updated

    def linkage(a: list[int], b: list[int]) -> float:
        return sum(s(x, y) for x in a for y in b) / (len(a) * len(b))

    large = [g for g in groups if len(g) >= _MIN_GROUP] or [max(groups, key=len)]
    for g in groups:
        if any(g is big for big in large):
            continue
        max(large, key=lambda big: linkage(g, big)).extend(g)
    return sorted(large, key=len, reverse=True)


def _describe(items: list[LiteratureItem], members: list[int], sim: list[list[float]], all_df: Counter) -> dict:
    central = sorted(members, key=lambda m: sum(sim[m][o] for o in members), reverse=True)
    group_df = Counter(t for m in members for t in set(_tokens(items[m])))
    n = len(items)
    terms = sorted(group_df, key=lambda t: group_df[t] / len(members) * math.log(n / all_df[t]), reverse=True)
    return {
        "keys": [bibtex_key(items[m]) for m in members],
        "titles": [items[m].title for m in central[:_TITLES_PER_GROUP]],
        "terms": terms[:_TERMS_PER_GROUP],
    }


async def build_taxonomy(items: list[LiteratureItem], k: int | None = None) -> list[dict]:
    if len(items) < _MIN_POOL:
        return []
    paper_ids, refs = await fetch_reference_sets(items)
    sim = similarity_matrix(items, paper_ids, refs)
    k = k or max(4, min(7, round(math.sqrt(len(items) / 4))))
    all_df = Counter(t for item in items for t in set(_tokens(item)))
    groups = cluster(sim, k)
    linked = sum(1 for r in refs if r)
    logger.info("[graph] papers=%d with_references=%d groups=%d", len(items), linked, len(groups))
    return [{"id": i, **_describe(items, g, sim, all_df)} for i, g in enumerate(groups, 1)]


def taxonomy_block(taxonomy: list[dict], language: str) -> str:
    lines = []
    for group in taxonomy:
        titles = "; ".join(group["titles"])
        terms = ", ".join(group["terms"])
        if language == "zh":
            lines.append(f"[{group['id']}] 关键词：{terms}（共 {len(group['keys'])} 篇）\n    代表文献：{titles}")
        else:
            lines.append(f"[{group['id']}] terms: {terms} ({len(group['keys'])} papers)\n    representative: {titles}")
    return "\n".join(lines)
