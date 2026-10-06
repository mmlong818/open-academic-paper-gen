import pytest
import respx
import httpx
from backend.verification.layer1_existence import ExistenceChecker
from backend.verification.schemas import CitationStatus

CROSSREF_FOUND = {
    "status": "ok",
    "message": {
        "DOI": "10.1038/nature14539",
        "title": ["Deep learning"],
        "author": [{"family": "LeCun", "given": "Y."}],
    },
}

CROSSREF_NOT_FOUND = {"status": "failed", "message": "Resource not found."}
HANDLE_NOT_FOUND = {"responseCode": 100, "handle": "10.9999/fake"}
ARXIV_DOI = "10.48550/arxiv.1704.01212"


@pytest.mark.asyncio
@respx.mock
async def test_layer1_doi_exists():
    respx.get("https://api.crossref.org/works/10.1038%2Fnature14539").mock(
        return_value=httpx.Response(200, json=CROSSREF_FOUND)
    )
    checker = ExistenceChecker()
    result = await checker.check(
        title="Deep learning",
        authors=["LeCun, Y."],
        doi="10.1038/nature14539",
    )
    assert result.layer1_ok is True
    assert result.status == CitationStatus.PASSED


@pytest.mark.asyncio
@respx.mock
async def test_layer1_doi_not_found_crossref():
    respx.get("https://api.crossref.org/works/10.9999%2Ffake").mock(
        return_value=httpx.Response(404, json=CROSSREF_NOT_FOUND)
    )
    respx.get("https://doi.org/api/handles/10.9999/fake").mock(
        return_value=httpx.Response(404, json=HANDLE_NOT_FOUND)
    )
    checker = ExistenceChecker()
    result = await checker.check(
        title="Fake Paper Title",
        authors=["Smith, J."],
        doi="10.9999/fake",
    )
    assert result.layer1_ok is False
    assert result.status == CitationStatus.REMOVED
    assert any("DOI" in issue for issue in result.issues)


@pytest.mark.asyncio
async def test_layer1_no_doi_uses_title_match():
    checker = ExistenceChecker()
    result = await checker.check(
        title="Attention Is All You Need",
        authors=["Vaswani, A."],
        doi=None,
    )
    assert result.status in (CitationStatus.WARNED, CitationStatus.PASSED)


@pytest.mark.asyncio
@respx.mock
async def test_layer1_crossref_timeout_passes_unverified():
    """Cannot verify != invalid: a CrossRef outage must not condemn a real citation."""
    respx.get("https://api.crossref.org/works/10.1%2Ftimeout").mock(
        side_effect=httpx.TimeoutException("timeout")
    )
    checker = ExistenceChecker()
    result = await checker.check(
        title="Timeout Paper",
        authors=["Author, A."],
        doi="10.1/timeout",
    )
    assert result.status == CitationStatus.PASSED
    assert result.layer1_ok is True


@pytest.mark.asyncio
@respx.mock
async def test_layer1_title_fuzzy_match_from_crossref():
    respx.get("https://api.crossref.org/works/10.1038%2Fnature14539").mock(
        return_value=httpx.Response(200, json={
            "status": "ok",
            "message": {
                "DOI": "10.1038/nature14539",
                "title": ["Deep learning survey"],
                "author": [{"family": "LeCun", "given": "Y."}],
            },
        })
    )
    checker = ExistenceChecker()
    result = await checker.check(
        title="Deep learning Survey",
        authors=["LeCun, Y."],
        doi="10.1038/nature14539",
    )
    assert result.layer1_ok is True


@pytest.mark.asyncio
@respx.mock
async def test_layer1_doi_registered_outside_crossref_passes():
    """arXiv DOIs are DataCite-registered: CrossRef 404s them although they resolve."""
    respx.get("https://api.crossref.org/works/10.48550%2Farxiv.1704.01212").mock(
        return_value=httpx.Response(404, json=CROSSREF_NOT_FOUND)
    )
    respx.get(f"https://doi.org/api/handles/{ARXIV_DOI}").mock(
        return_value=httpx.Response(200, json={"responseCode": 1, "handle": ARXIV_DOI})
    )
    result = await ExistenceChecker().check(
        title="Neural Message Passing for Quantum Chemistry", authors=["Gilmer, J."], doi=ARXIV_DOI,
    )
    assert result.status == CitationStatus.PASSED
    assert result.layer1_ok is True


@pytest.mark.asyncio
@respx.mock
async def test_layer1_handle_lookup_failure_passes_unverified():
    respx.get("https://api.crossref.org/works/10.48550%2Farxiv.1704.01212").mock(
        return_value=httpx.Response(404, json=CROSSREF_NOT_FOUND)
    )
    respx.get(f"https://doi.org/api/handles/{ARXIV_DOI}").mock(
        side_effect=httpx.ConnectTimeout("timeout")
    )
    result = await ExistenceChecker().check(title="T", authors=[], doi=ARXIV_DOI)
    assert result.status == CitationStatus.PASSED

