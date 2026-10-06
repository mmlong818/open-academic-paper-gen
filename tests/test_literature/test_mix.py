"""The literature follows the task's language mix: 70% / 50% / 20% Chinese.

With English sources added for Chinese topics, a Chinese review's pool fell to 18 Chinese
papers of 175 and its text cited none of them.
"""
import pytest
from unittest.mock import AsyncMock

from backend.literature.crew import LiteratureCrew
from backend.literature.mix import is_chinese, take_by_mix
from backend.literature.schemas import LiteratureItem, SearchQuery
from backend.writing.prompts import build_scoping_prompt


def _items(prefix: str, n: int, zh: bool) -> list[LiteratureItem]:
    title = "检索增强生成研究" if zh else "Retrieval-augmented generation"
    return [LiteratureItem(title=f"{title} {prefix}{i}", source="openalex") for i in range(n)]


def test_chinese_is_told_by_the_title():
    assert is_chinese(LiteratureItem(title="检索增强生成", source="crossref"))
    assert not is_chinese(LiteratureItem(title="RAG for QA", source="arxiv"))


@pytest.mark.parametrize("mix,zh_count", [("zh_major", 7), ("balanced", 5), ("en_major", 2)])
def test_the_cap_is_split_by_the_mix(mix, zh_count):
    ranked = _items("e", 20, zh=False) + _items("z", 20, zh=True)  # all English rank higher
    taken = take_by_mix(ranked, cap=10, mix=mix)
    assert len(taken) == 10
    assert sum(is_chinese(i) for i in taken) == zh_count


def test_a_short_side_is_filled_from_the_other():
    ranked = _items("e", 20, zh=False) + _items("z", 2, zh=True)
    taken = take_by_mix(ranked, cap=10, mix="zh_major")
    assert len(taken) == 10 and sum(is_chinese(i) for i in taken) == 2


def test_order_within_the_cap_is_kept():
    ranked = _items("e", 5, zh=False) + _items("z", 5, zh=True)
    taken = take_by_mix(ranked, cap=4, mix="balanced")
    assert taken == [ranked[0], ranked[1], ranked[5], ranked[6]]


@pytest.mark.asyncio
async def test_the_crew_applies_the_mix_to_its_cap():
    en, zh = AsyncMock(), AsyncMock()
    en.search.return_value = [LiteratureItem(title=f"English paper {i}", source="arxiv", citation_count=1000)
                              for i in range(80)]
    zh.search.return_value = [LiteratureItem(title=f"中文论文{i}", source="crossref") for i in range(80)]
    crew = LiteratureCrew()
    crew._en_searchers, crew._zh_searchers = [en], [zh]
    query = SearchQuery(keywords=["检索增强生成", "Retrieval-augmented generation"], language="zh",
                        max_results=20, source_mix="zh_major")
    results = await crew.run(query)
    assert len(results) == 60
    assert sum(is_chinese(i) for i in results) == 42


def test_english_scoping_asks_for_chinese_keywords_unless_english_leads():
    assert "Chinese keywords" in build_scoping_prompt("RAG for Chinese legal QA", "en", source_mix="balanced")
    assert "Chinese keywords" in build_scoping_prompt("RAG for Chinese legal QA", "en", source_mix="zh_major")
    assert "Chinese keywords" not in build_scoping_prompt("RAG for QA", "en", source_mix="en_major")
