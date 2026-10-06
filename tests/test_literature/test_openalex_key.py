"""OpenAlex requests carry the API key when one is configured.

Since 2026-02-13 OpenAlex bills calls against a daily budget: without a key it is small,
a free key gives $1/day (searches $1 per 1,000). Runs without one hit 429 within the day.
"""
import httpx
import pytest
import respx

from backend.literature.abstract_enricher import enrich_abstracts
from backend.literature.schemas import LiteratureItem, SearchQuery
from backend.literature.searchers.openalex import OpenAlexSearcher
from backend.verification.cross_source import found_elsewhere

WORKS = "https://api.openalex.org/works"


@pytest.fixture
def key(monkeypatch):
    # the backend reads .env through Settings only; os.environ never sees it
    from backend.core.config import settings
    monkeypatch.setattr(settings, "openalex_api_key", "test-key")


@respx.mock
@pytest.mark.asyncio
async def test_every_openalex_call_carries_the_key(key):
    route = respx.get(WORKS).mock(return_value=httpx.Response(200, json={"results": []}))
    respx.get("https://export.arxiv.org/api/query").mock(return_value=httpx.Response(200, text="<feed/>"))
    await OpenAlexSearcher().search(SearchQuery(keywords=["rag"], language="zh"))  # zh adds a fallback call
    await enrich_abstracts([LiteratureItem(title="t", doi="10.1/x", source="crossref")])
    async with httpx.AsyncClient() as client:
        await found_elsewhere(client, "A title", [], "semantic_scholar")
    assert route.call_count >= 4
    assert all(call.request.url.params.get("api_key") == "test-key" for call in route.calls)


@respx.mock
@pytest.mark.asyncio
async def test_without_a_key_none_is_sent(monkeypatch):
    from backend.core.config import settings
    monkeypatch.setattr(settings, "openalex_api_key", "")
    route = respx.get(WORKS).mock(return_value=httpx.Response(200, json={"results": []}))
    await OpenAlexSearcher().search(SearchQuery(keywords=["rag"], language="en"))
    assert "api_key" not in route.calls[0].request.url.params


def test_the_keys_come_from_settings_which_read_dotenv():
    from backend.core.config import Settings
    fields = Settings.model_fields
    assert "openalex_api_key" in fields and "semantic_scholar_api_key" in fields
