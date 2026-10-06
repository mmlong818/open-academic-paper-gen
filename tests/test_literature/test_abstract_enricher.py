"""Records without a usable abstract get OpenAlex's, looked up by DOI.

CrossRef carries few abstracts for Chinese papers. In a sample of 47 thin Chinese records,
OpenAlex held an abstract of 200+ characters for 6 of the 29 that came from CrossRef;
Semantic Scholar and CrossRef itself held none.
"""
import httpx
import pytest
import respx

from backend.literature.abstract_enricher import enrich_abstracts
from backend.literature.schemas import LiteratureItem

WORKS = "https://api.openalex.org/works"
LONG = "海关 领域 涉及 多源 异构 数据 整合 与 复杂 法规 演进 管理 的 双重 挑战 " * 6


def _inverted(text: str) -> dict:
    index: dict[str, list[int]] = {}
    for pos, word in enumerate(text.split()):
        index.setdefault(word, []).append(pos)
    return index


@respx.mock
@pytest.mark.asyncio
async def test_a_thin_abstract_is_filled_from_openalex_by_doi():
    route = respx.get(WORKS).mock(return_value=httpx.Response(200, json={"results": [
        {"doi": "https://doi.org/10.1/abc", "abstract_inverted_index": _inverted(LONG)},
    ]}))
    items = [LiteratureItem(title="海关", doi="10.1/ABC", source="crossref"),
             LiteratureItem(title="有摘要", doi="10.1/full", source="crossref", abstract="摘要" * 200)]
    enriched, filled = await enrich_abstracts(items)
    assert filled == 1
    assert enriched[0].abstract.startswith("海关 领域") and enriched[0].abstract_via == "openalex"
    assert enriched[1] is items[1]  # already long enough: not asked for
    assert "doi:10.1/abc" in route.calls[0].request.url.params["filter"]
    assert "10.1/full" not in route.calls[0].request.url.params["filter"]


@respx.mock
@pytest.mark.asyncio
async def test_a_shorter_abstract_never_replaces_the_one_we_have():
    respx.get(WORKS).mock(return_value=httpx.Response(200, json={"results": [
        {"doi": "https://doi.org/10.1/abc", "abstract_inverted_index": _inverted("短")},
    ]}))
    item = LiteratureItem(title="t", doi="10.1/abc", source="crossref", abstract="较长的已有摘要" * 5)
    enriched, filled = await enrich_abstracts([item])
    assert filled == 0 and enriched[0] is item


@respx.mock
@pytest.mark.asyncio
async def test_dois_are_asked_for_fifty_at_a_time():
    route = respx.get(WORKS).mock(return_value=httpx.Response(200, json={"results": []}))
    items = [LiteratureItem(title=f"t{i}", doi=f"10.1/{i}", source="crossref") for i in range(120)]
    await enrich_abstracts(items)
    assert route.call_count == 3


@respx.mock
@pytest.mark.asyncio
async def test_a_failed_lookup_leaves_the_records_as_they_were():
    respx.get(WORKS).mock(side_effect=httpx.ConnectError("down"))
    items = [LiteratureItem(title="t", doi="10.1/abc", source="crossref")]
    enriched, filled = await enrich_abstracts(items)
    assert filled == 0 and enriched == items
