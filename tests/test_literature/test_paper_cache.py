"""Cross-task paper cache: what one task fetched, the next
reuses. Only abstracts, full text and metadata are kept, never task data; a paper cached without full
text is fetched again, so a PDF that failed once is retried."""
from unittest.mock import AsyncMock, patch

import pytest

from backend.core.config import settings
from backend.literature.content_fetcher import PaperContentFetcher
from backend.literature.paper_cache import FULL_TEXT_VERSION, cache_key, merge_cached, to_row
from backend.literature.schemas import LiteratureItem

BODY = "Abstract: " + "Real body text about the method and its results. " * 20


def _item(**kw) -> LiteratureItem:
    return LiteratureItem(**{"title": "T", "source": "openalex", "abstract": "short", **kw})


def test_keys_come_from_the_doi_or_the_arxiv_id():
    assert cache_key(_item(doi="https://doi.org/10.1/ABC")) == "doi:10.1/abc"
    assert cache_key(_item(source="arxiv", source_id="2504.05324v2")) == "arxiv:2504.05324"
    assert cache_key(_item()) is None


def test_a_row_keeps_content_and_metadata_only():
    row = to_row(_item(doi="10.1/x", full_text=BODY, full_text_pages=[[0, 1]], body_excerpt=BODY[:2000],
                       volume="12", pages="1-9", citation_count=40))
    assert row["key"] == "doi:10.1/x" and row["full_text"] == BODY and row["full_text_pages"] == [[0, 1]]
    assert row["meta"] == {"volume": "12", "pages": "1-9", "full_text_version": FULL_TEXT_VERSION}
    assert "citation_count" not in row and "title" not in row


def test_merging_fills_only_what_the_item_lacks():
    cached = to_row(_item(doi="10.1/x", abstract="a much longer cached abstract " * 5, full_text=BODY,
                          body_excerpt=BODY[:2000], full_text_pages=[[0, 1]], volume="12"))
    merged = merge_cached(_item(doi="10.1/x", volume="7"), cached)
    assert merged.full_text == BODY and merged.full_text_pages == [[0, 1]] and merged.body_excerpt == BODY[:2000]
    assert merged.abstract.startswith("a much longer")
    assert merged.volume == "7", "the item's own metadata wins"


@pytest.mark.asyncio
async def test_cached_full_text_skips_the_fetch_and_new_fetches_are_stored():
    hit = _item(doi="10.1/hit")
    miss = _item(doi="10.1/miss")
    cached = {"doi:10.1/hit": to_row(_item(doi="10.1/hit", full_text=BODY, body_excerpt=BODY[:2000]))}
    fetched = miss.model_copy(update={"full_text": BODY, "body_excerpt": BODY[:2000]})
    with (
        patch.object(settings, "paper_cache", True),
        patch("backend.literature.content_fetcher.load_cached", AsyncMock(return_value=cached)),
        patch("backend.literature.content_fetcher.store_cached", AsyncMock()) as store,
        patch("backend.literature.content_fetcher._enrich_one", AsyncMock(return_value=fetched)) as enrich,
    ):
        out = await PaperContentFetcher().run([hit, miss])

    assert enrich.await_count == 1 and enrich.call_args.args[0].doi == "10.1/miss"
    assert [i.full_text for i in out] == [BODY, BODY]
    assert [i.doi for i in store.call_args.args[0]] == ["10.1/miss"]


@pytest.mark.asyncio
async def test_a_cached_abstract_without_full_text_still_fetches():
    item = _item(doi="10.1/x")
    cached = {"doi:10.1/x": to_row(_item(doi="10.1/x", abstract="cached abstract " * 20))}
    with (
        patch.object(settings, "paper_cache", True),
        patch("backend.literature.content_fetcher.load_cached", AsyncMock(return_value=cached)),
        patch("backend.literature.content_fetcher.store_cached", AsyncMock()),
        patch("backend.literature.content_fetcher._enrich_one", AsyncMock(side_effect=lambda i, c: i)) as enrich,
    ):
        out = await PaperContentFetcher().run([item])
    assert enrich.await_count == 1
    assert out[0].abstract.startswith("cached abstract")


@pytest.mark.asyncio
async def test_a_cache_failure_falls_back_to_fetching():
    item = _item(doi="10.1/x")
    with (
        patch.object(settings, "paper_cache", True),
        patch("backend.literature.content_fetcher.load_cached", AsyncMock(side_effect=RuntimeError("db down"))),
        patch("backend.literature.content_fetcher.store_cached", AsyncMock(side_effect=RuntimeError("db down"))),
        patch("backend.literature.content_fetcher._enrich_one", AsyncMock(side_effect=lambda i, c: i)) as enrich,
    ):
        out = await PaperContentFetcher().run([item])
    assert enrich.await_count == 1 and out == [item]


def test_nul_characters_never_reach_the_database():
    """pypdf emits NUL, which Postgres text rejects: a real run stored nothing until they were stripped."""
    row = to_row(_item(doi="10.1/x", abstract="abc\x00def", full_text="body\x00text"))
    assert row["abstract"] == "abcdef" and row["full_text"] == "bodytext"
