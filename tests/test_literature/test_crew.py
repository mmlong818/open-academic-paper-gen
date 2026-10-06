# tests/test_literature/test_crew.py
import pytest
from unittest.mock import AsyncMock
from backend.literature.schemas import LiteratureItem, SearchQuery
from backend.literature.crew import LiteratureCrew


def _make_item(title: str, doi: str | None = None, citation_count: int = 0, source: str = "arxiv") -> LiteratureItem:
    return LiteratureItem(title=title, doi=doi, citation_count=citation_count, source=source)


@pytest.mark.asyncio
async def test_crew_aggregates_results_from_all_searchers():
    fake_results = {
        0: [_make_item("Paper A", doi="10.1/a", citation_count=1000)],
        1: [_make_item("Paper B", doi="10.2/b", citation_count=50)],
        2: [_make_item("Paper C", doi="10.3/c", citation_count=200)],
    }

    crew = LiteratureCrew()
    mocks = []
    for i in range(3):
        m = AsyncMock()
        m.search.return_value = fake_results.get(i, [])
        mocks.append(m)
    crew._en_searchers = mocks

    query = SearchQuery(keywords=["deep learning"], language="en")
    results = await crew.run(query)
    assert len(results) == 3


@pytest.mark.asyncio
async def test_crew_deduplicates_across_sources():
    shared_doi = "10.1/shared"
    item1 = _make_item("Paper X", doi=shared_doi, citation_count=500, source="semantic_scholar")
    item2 = _make_item("Paper X duplicate", doi=shared_doi, citation_count=500, source="openalex")

    m1 = AsyncMock()
    m1.search.return_value = [item1]
    m2 = AsyncMock()
    m2.search.return_value = [item2]

    crew = LiteratureCrew()
    crew._en_searchers = [m1, m2]

    query = SearchQuery(keywords=["test"], language="en")
    results = await crew.run(query)
    assert len(results) == 1


@pytest.mark.asyncio
async def test_crew_applies_quality_scores():
    item = _make_item("High Cited", doi="10.1/x", citation_count=5000)
    m = AsyncMock()
    m.search.return_value = [item]

    crew = LiteratureCrew()
    crew._en_searchers = [m]

    query = SearchQuery(keywords=["test"], language="en")
    results = await crew.run(query)
    assert len(results) == 1, "more results than the stub returned means the real searchers ran"
    assert results[0].quality_score > 0


@pytest.mark.asyncio
async def test_crew_handles_searcher_failure_gracefully():
    bad_searcher = AsyncMock()
    bad_searcher.search.side_effect = Exception("network error")
    good_searcher = AsyncMock()
    good_searcher.search.return_value = [_make_item("Good Paper")]

    crew = LiteratureCrew()
    crew._en_searchers = [bad_searcher, good_searcher]

    query = SearchQuery(keywords=["test"], language="en")
    results = await crew.run(query)
    assert len(results) == 1


@pytest.mark.asyncio
async def test_crew_sorts_by_quality_score_descending():
    items = [
        _make_item("Low", citation_count=10),
        _make_item("High", citation_count=10000),
        _make_item("Mid", citation_count=1000),
    ]
    m = AsyncMock()
    m.search.return_value = items

    crew = LiteratureCrew()
    crew._en_searchers = [m]

    query = SearchQuery(keywords=["test"], language="en")
    results = await crew.run(query)
    assert len(results) == 3, "more results than the stub returned means the real searchers ran"
    scores = [r.quality_score for r in results]
    assert scores == sorted(scores, reverse=True)


def _recording_searcher(items: list[LiteratureItem]) -> AsyncMock:
    searcher = AsyncMock()
    searcher.search.return_value = items
    return searcher


def _queried_keywords(searcher: AsyncMock) -> set[str]:
    return {kw for call in searcher.search.call_args_list for kw in call.args[0].keywords}


@pytest.mark.asyncio
async def test_each_keyword_goes_to_the_sources_that_can_read_it():
    # A Chinese review asked Semantic Scholar and arXiv only in Chinese and got nothing back,
    # so the field's English literature (Lewis 2020, DPR) never entered the pool.
    zh = _recording_searcher([_make_item("中文论文", doi="10.1/zh")])
    en = _recording_searcher([_make_item("English paper", doi="10.1/en")])
    crew = LiteratureCrew()
    crew._zh_searchers, crew._en_searchers = [zh], [en]

    query = SearchQuery(keywords=["检索增强生成", "知识密集型问答", "Retrieval-augmented generation", "Dense passage retrieval"],
                        language="zh")
    results = await crew.run(query)

    assert _queried_keywords(zh) == {"检索增强生成", "知识密集型问答"}
    assert _queried_keywords(en) == {"Retrieval-augmented generation", "Dense passage retrieval"}
    # OpenAlex filters to Chinese-language works when the query says zh
    assert {call.args[0].language for call in en.search.call_args_list} == {"en"}
    assert {call.args[0].language for call in zh.search.call_args_list} == {"zh"}
    assert {r.title for r in results} == {"中文论文", "English paper"}


@pytest.mark.asyncio
async def test_chinese_only_keywords_leave_the_english_sources_alone():
    zh = _recording_searcher([_make_item("中文论文")])
    en = _recording_searcher([])
    crew = LiteratureCrew()
    crew._zh_searchers, crew._en_searchers = [zh], [en]

    await crew.run(SearchQuery(keywords=["检索增强生成"], language="zh"))
    assert en.search.call_count == 0
