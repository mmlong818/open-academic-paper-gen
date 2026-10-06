"""Citation-graph taxonomy that shapes review outlines."""
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from backend.literature.citation_graph import (
    build_taxonomy,
    cluster,
    fetch_reference_sets,
    similarity_matrix,
    taxonomy_block,
)
from backend.literature.bibtex import bibtex_key
from backend.literature.schemas import LiteratureItem

GROUP_A = "Graph neural networks message passing molecular property prediction atoms bonds"
GROUP_B = "Retrieval augmented generation hallucination language models documents grounding"


def _item(i, text, **kw):
    return LiteratureItem(**{"title": f"Paper {i} {text.split()[0]}", "source": "openalex",
                             "abstract": text, "doi": f"10.1/p{i}", **kw})


def test_direct_citation_raises_similarity_beyond_text():
    items = [_item(0, GROUP_A), _item(1, GROUP_B), _item(2, GROUP_B)]
    ids = ["a", "b", "c"]
    refs = [{"b"}, {"x"}, {"y"}]  # paper 0 cites paper 1 across the topical divide
    sim = similarity_matrix(items, ids, refs)
    assert sim[0][1] > sim[0][2]


def test_papers_without_citation_data_fall_back_to_text():
    items = [_item(0, GROUP_A), _item(1, GROUP_A), _item(2, GROUP_B)]
    sim = similarity_matrix(items, [None] * 3, [set()] * 3)
    assert sim[0][1] > sim[0][2]


def test_two_obvious_groups_come_apart_and_tiny_groups_are_merged():
    items = [_item(i, GROUP_A) for i in range(5)] + [_item(i, GROUP_B) for i in range(5, 10)]
    sim = similarity_matrix(items, [None] * 10, [set()] * 10)
    groups = cluster(sim, k=4)  # asks for 4, but groups under 3 are folded into their neighbours
    assert sorted(sorted(g) for g in groups) == [[0, 1, 2, 3, 4], [5, 6, 7, 8, 9]]


@pytest.mark.asyncio
@respx.mock
async def test_fetch_maps_batch_results_and_retries_rate_limits():
    items = [_item(0, GROUP_A), _item(1, GROUP_A, doi=None)]  # the second has no S2 id at all
    route = respx.post("https://api.semanticscholar.org/graph/v1/paper/batch").mock(side_effect=[
        httpx.Response(429),
        httpx.Response(200, json=[{"paperId": "pid0", "references": [{"paperId": "r1"}, {"paperId": None}]}]),
    ])
    ids, refs = await fetch_reference_sets(items, retry_wait=0)
    assert ids == ["pid0", None] and refs == [{"r1"}, set()]
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_taxonomy_describes_each_group_with_keys_titles_and_terms():
    items = [_item(i, GROUP_A) for i in range(8)] + [_item(i, GROUP_B) for i in range(8, 16)]
    with patch("backend.literature.citation_graph.fetch_reference_sets",
               AsyncMock(return_value=([None] * 16, [set()] * 16))):
        taxonomy = await build_taxonomy(items, k=2)
    assert len(taxonomy) == 2
    assert {len(t["keys"]) for t in taxonomy} == {8}
    assert all(t["titles"] and t["terms"] for t in taxonomy)
    block = taxonomy_block(taxonomy, "en")
    assert "[1]" in block and "[2]" in block and taxonomy[0]["titles"][0] in block


@pytest.mark.asyncio
async def test_small_pools_get_no_taxonomy():
    assert await build_taxonomy([_item(i, GROUP_A) for i in range(5)]) == []


def test_outline_prompt_carries_the_taxonomy_only_when_given():
    from backend.writing.prompts import build_outline_prompt

    for language in ("en", "zh"):
        plain = build_outline_prompt("t", "s", ["q"], language)
        guided = build_outline_prompt("t", "s", ["q"], language, taxonomy_block="[1] terms: graph")
        assert "[1] terms: graph" in guided and '"clusters"' in guided
        assert '"clusters"' not in plain


def test_sections_tied_to_groups_draw_those_papers_first():
    from backend.writing.section_writer import select_relevant_papers

    lit = [LiteratureItem(title=f"Equivariant molecular model {i}", source="arxiv",
                          abstract="equivariant molecular models " * 3) for i in range(20)]
    lit.append(LiteratureItem(title="Unrelated wording entirely", source="arxiv", abstract="nothing shared"))
    section = {"title": "Equivariant molecular models", "summary": "", "cluster_keys": [bibtex_key(lit[-1])]}
    chosen = select_relevant_papers(section, lit, top_k=5)
    assert chosen[0].title == "Unrelated wording entirely"  # the group's paper leads despite no word overlap
    assert len(chosen) == 5


def test_graph_outline_is_off_by_default():
    from backend.core.config import Settings

    assert Settings(_env_file=None).citation_graph_outline is False
