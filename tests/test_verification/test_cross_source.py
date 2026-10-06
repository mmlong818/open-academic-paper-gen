"""A cited paper with neither a DOI nor an arXiv id is looked up in a second database.

Every record comes from a real database, and a DOI or arXiv id already anchors it. Of 118 cited papers in earlier runs, 6 had neither (4 Semantic Scholar
only, e.g. Lewis 2020 and ReAct; 2 OpenAlex only). Those are searched by title elsewhere.
"""
import httpx
import pytest
import respx

from backend.verification.layer1_existence import ExistenceChecker
from backend.verification.schemas import CitationStatus

OPENALEX = "https://api.openalex.org/works"
CROSSREF = "https://api.crossref.org/works"
ARXIV = "https://export.arxiv.org/api/query"
ARXIV_EMPTY = '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
ARXIV_REACT = ('<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry>'
               '<title>ReAct: Synergizing Reasoning and Acting in Language Models</title>'
               '<author><name>Shunyu Yao</name></author></entry></feed>')
TITLE = "ReAct: Synergizing Reasoning and Acting in Language Models"


def _openalex(title, author):
    return {"results": [{"title": title, "authorships": [{"author": {"display_name": author}}]}]}


async def _check(source, authors=("Shunyu Yao",)):
    return await ExistenceChecker().check(title=TITLE, authors=list(authors), doi=None, year=2023, source=source)


@respx.mock
@pytest.mark.asyncio
async def test_a_semantic_scholar_only_paper_found_on_openalex_passes():
    route = respx.get(OPENALEX).mock(return_value=httpx.Response(200, json=_openalex(TITLE, "Shunyu Yao")))
    result = await _check("semantic_scholar")
    assert result.status == CitationStatus.PASSED, result.issues
    # the title field, not full-text search, and without the colon the filter syntax reserves
    assert route.calls[0].request.url.params["filter"].startswith("title.search:ReAct Synergizing")


@respx.mock
@pytest.mark.asyncio
async def test_not_found_elsewhere_warns_to_check_by_hand():
    respx.get(OPENALEX).mock(return_value=httpx.Response(200, json=_openalex("Something else entirely", "A B")))
    respx.get(ARXIV).mock(return_value=httpx.Response(200, text=ARXIV_EMPTY))
    result = await _check("semantic_scholar")
    assert result.status == CitationStatus.WARNED
    assert any("one database" in i for i in result.issues)


@respx.mock
@pytest.mark.asyncio
async def test_same_title_with_another_first_author_does_not_confirm():
    respx.get(OPENALEX).mock(return_value=httpx.Response(200, json=_openalex(TITLE, "Jane Smith")))
    respx.get(ARXIV).mock(return_value=httpx.Response(200, text=ARXIV_EMPTY))
    assert (await _check("semantic_scholar")).status == CitationStatus.WARNED


@respx.mock
@pytest.mark.asyncio
async def test_an_openalex_only_paper_is_looked_up_on_crossref():
    route = respx.get(CROSSREF).mock(return_value=httpx.Response(200, json={"message": {"items": [
        {"title": [TITLE], "author": [{"family": "Yao", "given": "Shunyu"}]}]}}))
    result = await _check("openalex")
    assert result.status == CitationStatus.PASSED, result.issues
    assert route.called


@pytest.mark.asyncio
async def test_arxiv_papers_and_papers_with_a_doi_are_not_looked_up():
    with respx.mock(assert_all_called=False) as mock:
        await _check("arxiv")
        assert mock.calls.call_count == 0


@respx.mock
@pytest.mark.asyncio
async def test_a_failed_lookup_does_not_condemn_the_paper():
    respx.get(OPENALEX).mock(side_effect=httpx.ConnectError("down"))
    respx.get(ARXIV).mock(return_value=httpx.Response(200, text=ARXIV_EMPTY))
    # one source could not be asked and none confirmed: undecided, not condemned
    assert (await _check("semantic_scholar")).status == CitationStatus.PASSED


@respx.mock
@pytest.mark.asyncio
async def test_a_paper_openalex_lacks_is_found_on_arxiv():
    # real case: ReAct (ICLR 2023, no DOI) is on Semantic Scholar and arXiv but not OpenAlex
    respx.get(OPENALEX).mock(return_value=httpx.Response(200, json={"results": []}))
    respx.get(ARXIV).mock(return_value=httpx.Response(200, text=ARXIV_REACT))
    assert (await _check("semantic_scholar")).status == CitationStatus.PASSED
