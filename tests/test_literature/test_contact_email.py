"""Crossref and OpenAlex calls carry the polite-pool mailto only when CONTACT_EMAIL is set.

No address is built in: a placeholder would put every installation's traffic under one
address that nobody reads.
"""
import httpx
import pytest
import respx

from backend.literature.schemas import SearchQuery
from backend.literature.searchers.crossref import CrossRefSearcher
from backend.literature.searchers.openalex import OpenAlexSearcher
from backend.verification.cross_source import found_elsewhere

CROSSREF = "https://api.crossref.org/works"
OPENALEX = "https://api.openalex.org/works"


def _routes():
    crossref = respx.get(CROSSREF).mock(return_value=httpx.Response(200, json={"message": {"items": []}}))
    openalex = respx.get(OPENALEX).mock(return_value=httpx.Response(200, json={"results": []}))
    respx.get("https://export.arxiv.org/api/query").mock(return_value=httpx.Response(200, text="<feed/>"))
    return crossref, openalex


async def _call_everything():
    await CrossRefSearcher().search(SearchQuery(keywords=["rag"], language="en"))
    await OpenAlexSearcher().search(SearchQuery(keywords=["rag"], language="en"))
    async with httpx.AsyncClient() as client:
        await found_elsewhere(client, "A title", [], "semantic_scholar")
        await found_elsewhere(client, "A title", [], "openalex")


@respx.mock
@pytest.mark.asyncio
async def test_the_configured_address_is_sent(monkeypatch):
    from backend.core.config import settings
    monkeypatch.setattr(settings, "contact_email", "me@example.org")
    crossref, openalex = _routes()
    await _call_everything()
    calls = crossref.calls + openalex.calls
    assert crossref.call_count >= 2 and openalex.call_count >= 2
    assert all(call.request.url.params.get("mailto") == "me@example.org" for call in calls)


@respx.mock
@pytest.mark.asyncio
async def test_without_an_address_no_mailto_is_sent(monkeypatch):
    from backend.core.config import settings
    monkeypatch.setattr(settings, "contact_email", "")
    crossref, openalex = _routes()
    await _call_everything()
    assert all("mailto" not in call.request.url.params for call in crossref.calls + openalex.calls)
