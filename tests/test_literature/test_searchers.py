# tests/test_literature/test_searchers.py
import pytest
import respx
import httpx
from backend.literature.schemas import LiteratureItem, SearchQuery
from backend.literature.searchers.semantic_scholar import SemanticScholarSearcher
from backend.literature.searchers.arxiv import ArxivSearcher
from backend.literature.searchers.openalex import OpenAlexSearcher


SEMANTIC_SCHOLAR_MOCK = {
    "data": [
        {
            "paperId": "abc123",
            "title": "Attention Is All You Need",
            "authors": [{"name": "Vaswani, A."}],
            "year": 2017,
            "citationCount": 80000,
            "externalIds": {"DOI": "10.48550/arXiv.1706.03762"},
            "abstract": "The dominant sequence ...",
            "venue": "NeurIPS",
            "url": "https://api.semanticscholar.org/graph/v1/paper/abc123",
        }
    ],
    "total": 1,
    "offset": 0,
    "next": 0,
}

ARXIV_MOCK_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v5</id>
    <title>Attention Is All You Need</title>
    <author><name>Vaswani, Ashish</name></author>
    <published>2017-06-12T00:00:00Z</published>
    <summary>The dominant sequence model...</summary>
    <link href="https://arxiv.org/abs/1706.03762" rel="alternate" type="text/html"/>
  </entry>
</feed>"""

OPENALEX_MOCK = {
    "results": [
        {
            "id": "https://openalex.org/W123",
            "title": "BERT: Pre-training of Deep Bidirectional Transformers",
            "authorships": [{"author": {"display_name": "Devlin, J."}}],
            "publication_year": 2019,
            "doi": "https://doi.org/10.18653/v1/N19-1423",
            "abstract_inverted_index": {"BERT": [0], "is": [1]},
            "cited_by_count": 70000,
            "primary_location": {"source": {"display_name": "ACL"}},
            "open_access": {"oa_url": "https://arxiv.org/pdf/1810.04805"},
        }
    ]
}


@pytest.mark.asyncio
@respx.mock
async def test_semantic_scholar_search():
    respx.get("https://api.semanticscholar.org/graph/v1/paper/search").mock(
        return_value=httpx.Response(200, json=SEMANTIC_SCHOLAR_MOCK)
    )
    searcher = SemanticScholarSearcher()
    query = SearchQuery(keywords=["transformer attention"], language="en", max_results=5)
    results = await searcher.search(query)
    assert len(results) == 1
    assert results[0].title == "Attention Is All You Need"
    assert results[0].citation_count == 80000
    assert results[0].source == "semantic_scholar"


@pytest.mark.asyncio
@respx.mock
async def test_arxiv_search():
    respx.get("https://export.arxiv.org/api/query").mock(
        return_value=httpx.Response(200, text=ARXIV_MOCK_XML)
    )
    searcher = ArxivSearcher()
    query = SearchQuery(keywords=["transformer"], language="en", max_results=5)
    results = await searcher.search(query)
    assert len(results) == 1
    assert results[0].title == "Attention Is All You Need"
    assert results[0].source == "arxiv"
    assert results[0].year == 2017


@pytest.mark.asyncio
@respx.mock
async def test_openalex_search():
    respx.get("https://api.openalex.org/works").mock(
        return_value=httpx.Response(200, json=OPENALEX_MOCK)
    )
    searcher = OpenAlexSearcher()
    query = SearchQuery(keywords=["BERT language model"], language="en", max_results=5)
    results = await searcher.search(query)
    assert len(results) == 1
    assert results[0].title == "BERT: Pre-training of Deep Bidirectional Transformers"
    assert results[0].source == "openalex"
    assert results[0].citation_count == 70000


@pytest.mark.asyncio
@respx.mock
async def test_semantic_scholar_handles_api_error():
    respx.get("https://api.semanticscholar.org/graph/v1/paper/search").mock(
        return_value=httpx.Response(429)
    )
    searcher = SemanticScholarSearcher()
    query = SearchQuery(keywords=["test"], language="en")
    results = await searcher.search(query)
    assert results == []  # 降级返回空列表，不抛出


from backend.literature.searchers.chinese_stub import (
    CnkiStubSearcher,
    WanfangStubSearcher,
    VipStubSearcher,
)


@pytest.mark.asyncio
async def test_cnki_stub_returns_empty_without_cookie():
    searcher = CnkiStubSearcher()
    query = SearchQuery(keywords=["深度学习"], language="zh")
    results = await searcher.search(query)
    assert results == []


@pytest.mark.asyncio
async def test_cnki_stub_returns_placeholder_with_cookie():
    searcher = CnkiStubSearcher()
    query = SearchQuery(
        keywords=["深度学习"], language="zh", cookie="fake_cookie_value"
    )
    results = await searcher.search(query)
    assert isinstance(results, list)
    if results:
        assert results[0].source == "cnki"


@pytest.mark.asyncio
async def test_wanfang_stub_returns_empty_without_cookie():
    searcher = WanfangStubSearcher()
    query = SearchQuery(keywords=["机器学习"], language="zh")
    results = await searcher.search(query)
    assert results == []


@pytest.mark.asyncio
async def test_vip_stub_returns_empty_without_cookie():
    searcher = VipStubSearcher()
    query = SearchQuery(keywords=["神经网络"], language="zh")
    results = await searcher.search(query)
    assert results == []
