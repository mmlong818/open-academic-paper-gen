"""T2.2 — expand the screened pool along citation links of its strongest papers."""
import httpx
import pytest
import respx

from backend.literature.citation_chain import CitationChainExpander, s2_id
from backend.literature.schemas import LiteratureItem

S2 = "https://api.semanticscholar.org/graph/v1/paper"
ABSTRACT = "A substantive abstract describing the method and its findings in some detail. "


def _item(title, **kw):
    return LiteratureItem(**{"title": title, "source": "openalex", "abstract": ABSTRACT, **kw})


def _paper(pid, title, cites=10, doi=None, abstract=ABSTRACT):
    return {"paperId": pid, "title": title, "year": 2020, "citationCount": cites,
            "authors": [{"name": "A Author"}], "externalIds": {"DOI": doi} if doi else {},
            "abstract": abstract, "venue": "V", "url": f"https://s2/{pid}"}


def test_s2_id_prefers_doi_then_arxiv_then_s2_paper_id():
    assert s2_id(_item("a", doi="10.1/X")) == "DOI:10.1/X"
    assert s2_id(_item("a", source="arxiv", source_id="2504.05324v1")) == "ARXIV:2504.05324"
    assert s2_id(_item("a", source="semantic_scholar", source_id="abc123")) == "abc123"
    assert s2_id(_item("a")) == ""


@pytest.mark.asyncio
@respx.mock
async def test_candidates_linked_to_more_seeds_rank_first_and_known_papers_are_skipped():
    seeds = [_item("Seed one", doi="10.1/s1", quality_score=90), _item("Seed two", doi="10.1/s2", quality_score=80)]
    shared = _paper("p1", "Classic shared paper", cites=50)
    single = _paper("p2", "Only one seed cites this", cites=5000)
    known = _paper("p3", "Seed two", cites=99)  # already in the pool, by title
    for sid, refs in (("DOI:10.1/s1", [shared, single]), ("DOI:10.1/s2", [shared, known])):
        respx.get(f"{S2}/{sid}/references").mock(
            return_value=httpx.Response(200, json={"data": [{"citedPaper": p} for p in refs]}))
        respx.get(f"{S2}/{sid}/citations").mock(return_value=httpx.Response(200, json={"data": []}))

    found = await CitationChainExpander(retry_wait=0).expand(seeds, existing=seeds, max_new=10)

    assert [f.title for f in found] == ["Classic shared paper", "Only one seed cites this"]
    assert found[0].source == "semantic_scholar"
    assert found[0].raw["chain_links"] == 2


@pytest.mark.asyncio
@respx.mock
async def test_candidates_without_an_abstract_are_dropped_and_the_cap_holds():
    seed = _item("Seed", doi="10.1/s")
    papers = [_paper(f"p{i}", f"Paper {i}", cites=i) for i in range(5)] + [_paper("x", "No abstract", abstract=None)]
    respx.get(f"{S2}/DOI:10.1/s/references").mock(
        return_value=httpx.Response(200, json={"data": [{"citedPaper": p} for p in papers]}))
    respx.get(f"{S2}/DOI:10.1/s/citations").mock(return_value=httpx.Response(200, json={"data": []}))

    found = await CitationChainExpander(retry_wait=0).expand([seed], existing=[seed], max_new=3)

    assert [f.title for f in found] == ["Paper 4", "Paper 3", "Paper 2"]


@pytest.mark.asyncio
@respx.mock
async def test_rate_limit_is_retried_once_and_failures_yield_nothing():
    seed = _item("Seed", doi="10.1/s")
    respx.get(f"{S2}/DOI:10.1/s/references").mock(side_effect=[
        httpx.Response(429), httpx.Response(200, json={"data": [{"citedPaper": _paper("p", "Found")}]}),
    ])
    respx.get(f"{S2}/DOI:10.1/s/citations").mock(return_value=httpx.Response(500))

    found = await CitationChainExpander(retry_wait=0).expand([seed], existing=[seed])

    assert [f.title for f in found] == ["Found"]


@pytest.mark.asyncio
async def test_no_usable_seed_means_no_request():
    assert await CitationChainExpander(retry_wait=0).expand([_item("no ids")], existing=[]) == []


def test_arxiv_doi_is_looked_up_by_its_arxiv_id():
    """S2 files arXiv papers under ARXIV ids; a 10.48550 DOI lookup returned no links at all."""
    assert s2_id(_item("a", doi="10.48550/arXiv.2312.10997")) == "ARXIV:2312.10997"


@pytest.mark.asyncio
@respx.mock
async def test_off_topic_candidates_rank_below_on_topic_ones():
    seed = _item("Seed", doi="10.1/s")
    generic = _paper("g", "Adam: A Method for Stochastic Optimization", cites=170000,
                     abstract="We introduce an algorithm for first-order gradient-based optimization of objectives.")
    topical = _paper("t", "Neural message passing for molecular property prediction", cites=40,
                     abstract="Graph neural networks predict molecular properties from atoms and bonds.")
    respx.get(f"{S2}/DOI:10.1/s/references").mock(
        return_value=httpx.Response(200, json={"data": [{"citedPaper": generic}, {"citedPaper": topical}]}))
    respx.get(f"{S2}/DOI:10.1/s/citations").mock(return_value=httpx.Response(200, json={"data": []}))

    found = await CitationChainExpander(retry_wait=0).expand(
        [seed], existing=[seed], topic_terms=["graph neural networks", "molecular property prediction"])

    assert [f.title for f in found] == [topical["title"], generic["title"]]


@pytest.mark.asyncio
async def test_chain_and_screen_fetches_screens_and_scores_the_candidates():
    from unittest.mock import AsyncMock, MagicMock, patch

    from backend.literature.citation_chain import chain_and_screen

    cand = [_item("Chained A"), _item("Chained B")]
    fetcher = MagicMock(); fetcher.run = AsyncMock(return_value=cand)
    screener = MagicMock(); screener.run = AsyncMock(return_value=([cand[0]], [{"title": "Chained A"}]))
    with patch("backend.literature.citation_chain.CitationChainExpander") as Expander:
        Expander.return_value.expand = AsyncMock(return_value=cand)
        kept, rows, n = await chain_and_screen([], [], ["t"], fetcher, screener, "topic", "en")
    assert [k.title for k in kept] == ["Chained A"] and n == 2 and rows == [{"title": "Chained A"}]
    assert kept[0].quality_score > 0  # scored like the searched papers


@pytest.mark.asyncio
@respx.mock
async def test_references_are_fetched_whole_citations_capped():
    """At limit=100 a 227-reference survey lost Lewis 2020 and DPR; one call with 1000 gets them."""
    seed = _item("Seed", doi="10.1/s")
    refs = respx.get(f"{S2}/DOI:10.1/s/references").mock(return_value=httpx.Response(200, json={"data": []}))
    cits = respx.get(f"{S2}/DOI:10.1/s/citations").mock(return_value=httpx.Response(200, json={"data": []}))
    await CitationChainExpander(retry_wait=0).expand([seed], existing=[seed])
    assert refs.calls.last.request.url.params["limit"] == "1000"
    assert cits.calls.last.request.url.params["limit"] == "100"
