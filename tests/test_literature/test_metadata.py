"""Records carry the bibliographic fields that checking and citation styles need.

Field-level reference checks (author and year against CrossRef), GB/T 7714 and RIS export
all need volume, issue, pages, publisher and the kind of work; records had none of them.
"""
import httpx
import pytest
import respx

from backend.literature.dedup import deduplicate
from backend.literature.schemas import LiteratureItem, SearchQuery
from backend.literature.searchers.arxiv import ArxivSearcher
from backend.literature.searchers.crossref import CrossRefSearcher
from backend.literature.searchers.openalex import OpenAlexSearcher

QUERY = SearchQuery(keywords=["retrieval"], language="en", max_results=5)

CROSSREF = {"message": {"items": [{
    "DOI": "10.1162/tacl_a_00276", "title": ["Natural Questions"], "author": [{"family": "Kwiatkowski", "given": "Tom"}],
    "published": {"date-parts": [[2019]]}, "container-title": ["TACL"], "volume": "7", "issue": "1",
    "page": "453-466", "publisher": "MIT Press", "type": "journal-article",
}]}}

OPENALEX = {"results": [{
    "id": "https://openalex.org/W1", "title": "Dense Passage Retrieval", "authorships": [], "publication_year": 2020,
    "doi": "https://doi.org/10.18653/v1/2020.emnlp-main.550", "cited_by_count": 10, "type": "article",
    "biblio": {"volume": "1", "issue": None, "first_page": "6769", "last_page": "6781"},
    "primary_location": {"source": {"display_name": "EMNLP", "host_organization_name": "ACL"}},
}]}

ARXIV = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><entry>
<id>http://arxiv.org/abs/2005.11401v4</id><title>Retrieval-Augmented Generation</title>
<author><name>Lewis, Patrick</name></author><published>2020-05-22T00:00:00Z</published>
<summary>RAG.</summary><link href="https://arxiv.org/abs/2005.11401" rel="alternate" type="text/html"/>
</entry></feed>"""


@respx.mock
@pytest.mark.asyncio
async def test_crossref_records_carry_volume_issue_pages_publisher_and_type():
    route = respx.get("https://api.crossref.org/works").mock(return_value=httpx.Response(200, json=CROSSREF))
    item = (await CrossRefSearcher().search(QUERY))[0]
    assert (item.volume, item.issue, item.pages, item.publisher, item.pub_type) == \
        ("7", "1", "453-466", "MIT Press", "journal-article")
    select = route.calls[0].request.url.params["select"]
    assert all(f in select for f in ("volume", "issue", "page", "publisher", "type"))


@respx.mock
@pytest.mark.asyncio
async def test_openalex_records_carry_the_biblio_and_type():
    route = respx.get("https://api.openalex.org/works").mock(return_value=httpx.Response(200, json=OPENALEX))
    item = (await OpenAlexSearcher().search(QUERY))[0]
    assert (item.volume, item.issue, item.pages, item.publisher, item.pub_type) == \
        ("1", "", "6769-6781", "ACL", "article")
    assert "biblio" in route.calls[0].request.url.params["select"]


@respx.mock
@pytest.mark.asyncio
async def test_arxiv_records_are_preprints():
    respx.get("https://export.arxiv.org/api/query").mock(return_value=httpx.Response(200, text=ARXIV))
    assert (await ArxivSearcher().search(QUERY))[0].pub_type == "preprint"


def test_a_duplicate_fills_the_blanks_of_the_record_kept():
    kept = LiteratureItem(title="Natural Questions", source="semantic_scholar", doi="10.1162/tacl_a_00276",
                          abstract="Kept abstract.")
    dup = LiteratureItem(title="Natural Questions", source="crossref", doi="10.1162/TACL_A_00276",
                         abstract="Other abstract.", volume="7", pages="453-466", pub_type="journal-article")
    [merged] = deduplicate([kept, dup])
    assert merged.source == "semantic_scholar" and merged.abstract == "Kept abstract."  # first one wins
    assert (merged.volume, merged.pages, merged.pub_type) == ("7", "453-466", "journal-article")  # blanks filled
