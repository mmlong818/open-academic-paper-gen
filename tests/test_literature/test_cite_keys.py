"""Every paper in the pool gets its own citation key, told apart by content.

Keys are first author + year + first title word, letters only. In five earlier pools, six
keys stood for sixteen papers: four Chinese papers by one author in 2025 (a Chinese title
gives an empty slug) were all Xiaoyang2025, so the writer could reach only one of them.
"""
from unittest.mock import AsyncMock, patch

import pytest

from backend.literature.bibtex import assign_cite_keys, bibtex_key, bibtex_key_from_dict
from backend.literature.schemas import LiteratureItem
from backend.pipeline.graph import node_cleaning
from backend.pipeline.states import PaperState


def _zh(title, doi=None):
    return LiteratureItem(title=title, authors=["Xiaoyang"], year=2025, source="crossref", doi=doi)


def test_distinct_papers_behind_one_key_get_suffixes():
    items = [_zh("整体决定论与局部认知错觉"), _zh("叙事幻觉：决定论视域下的因果错觉"), _zh("命中即先知：多轨预测中的事后筛选")]
    keyed = assign_cite_keys(items)
    assert [bibtex_key(i) for i in keyed] == ["Xiaoyang2025", "Xiaoyang2025b", "Xiaoyang2025c"]


def test_the_same_paper_twice_shares_one_key():
    items = [_zh("同一篇论文", doi="10.1/X"), _zh("同一篇论文（修订版）", doi="10.1/x"), _zh("另一篇论文")]
    assert [bibtex_key(i) for i in assign_cite_keys(items)] == ["Xiaoyang2025", "Xiaoyang2025", "Xiaoyang2025b"]


def test_unique_keys_stay_as_they_were():
    item = LiteratureItem(title="Attention Is All You Need", authors=["Ashish Vaswani"], year=2017, source="arxiv")
    [keyed] = assign_cite_keys([item])
    assert bibtex_key(keyed) == bibtex_key(item) == "Vaswani2017Attention"


def test_the_stored_key_is_what_every_site_uses():
    keyed = assign_cite_keys([_zh("第一篇"), _zh("第二篇")])[1]
    assert bibtex_key(keyed) == bibtex_key_from_dict(keyed.model_dump()) == "Xiaoyang2025b"


def test_records_without_a_stored_key_compute_it_as_before():
    # tasks from before this change: their drafts cite the computed keys
    data = {"title": "第二篇", "authors": ["Xiaoyang"], "year": 2025, "source": "crossref"}
    assert bibtex_key(LiteratureItem(**data)) == bibtex_key_from_dict(data) == "Xiaoyang2025"


@pytest.mark.asyncio
async def test_the_cleaned_pool_carries_unique_keys():
    state = PaperState(task_id="k1", topic="t", language="zh", collab_mode="full_auto", keywords=["k"],
                       literature=[_zh("整体决定论").model_dump(), _zh("叙事幻觉").model_dump()])
    no_op = AsyncMock(return_value=None)
    with (
        patch("backend.pipeline.graph.PaperContentFetcher") as Fetcher,
        patch("backend.pipeline.graph.LiteratureScreener") as Screener,
        patch("backend.pipeline.graph.chain_and_screen", AsyncMock(return_value=([], [], 0))),
        patch("backend.pipeline.graph.enrich_abstracts", AsyncMock(side_effect=lambda items: (items, 0))),
        patch("backend.pipeline.graph._save_phase_result", no_op),
        patch("backend.pipeline.graph.publish_progress", no_op),
    ):
        Fetcher.return_value.run = AsyncMock(side_effect=lambda items: items)
        Screener.return_value.run = AsyncMock(side_effect=lambda topic, items, language: (items, []))
        result = await node_cleaning(state)
    assert [lit["cite_key"] for lit in result["literature"]] == ["Xiaoyang2025", "Xiaoyang2025b"]
