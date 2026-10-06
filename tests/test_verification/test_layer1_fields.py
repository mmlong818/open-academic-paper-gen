"""Layer 1 compares authors, year and pages with CrossRef, not only the title.

A DOI can resolve to another paper than the record describes (a mislinked OpenAlex or
Semantic Scholar record, a preprint mixed with its published version); the title check
alone let those through, and from GB/T 7714 on the record's own volume and pages are
exported. Rules: first author differing or no author in common is
critical; year may differ by one (online first); start pages 5 or more apart are critical.
"""
import httpx
import pytest
import respx

from backend.verification.layer1_existence import ExistenceChecker
from backend.verification.schemas import CitationStatus

DOI = "10.1162/tacl_a_00276"
URL = "https://api.crossref.org/works/10.1162%2Ftacl_a_00276"


def _crossref(authors, year=2019, page="453-466"):
    return {"message": {"title": ["Natural Questions"], "author": authors,
                        "published": {"date-parts": [[year]]}, "page": page}}


async def _check(crossref, authors, year=2019, pages="453-466", title="Natural Questions", doi=DOI):
    respx.get(URL).mock(return_value=httpx.Response(200, json=crossref))
    return await ExistenceChecker().check(title=title, authors=authors, doi=doi, year=year, pages=pages)


KWIAT = [{"family": "Kwiatkowski", "given": "Tom"}, {"family": "Palomaki", "given": "Jennimaria"}]


@respx.mock
@pytest.mark.asyncio
async def test_matching_authors_year_and_pages_pass():
    result = await _check(_crossref(KWIAT), ["Tom Kwiatkowski", "Palomaki, Jennimaria"])
    assert result.status == CitationStatus.PASSED, result.issues


@respx.mock
@pytest.mark.asyncio
async def test_no_author_in_common_warns_the_doi_may_be_another_paper():
    result = await _check(_crossref(KWIAT), ["Jane Smith", "Wei Chen"])
    assert result.status == CitationStatus.WARNED
    assert any("Authors do not match" in i for i in result.issues)


@respx.mock
@pytest.mark.asyncio
async def test_a_different_first_author_warns():
    result = await _check(_crossref(KWIAT), ["Palomaki, Jennimaria", "Tom Kwiatkowski"])
    assert any("First author" in i for i in result.issues)


@respx.mock
@pytest.mark.asyncio
async def test_pinyin_against_chinese_characters_is_not_compared():
    crossref = _crossref([{"family": "Zhang", "given": "Yiying"}])
    result = await _check(crossref, ["张艺潆"])
    assert not any("uthor" in i for i in result.issues)


@respx.mock
@pytest.mark.asyncio
async def test_chinese_names_match_by_family_name():
    crossref = _crossref([{"family": "张", "given": "艺潆"}])
    result = await _check(crossref, ["张艺潆"])
    assert result.status == CitationStatus.PASSED, result.issues


@respx.mock
@pytest.mark.asyncio
async def test_a_year_one_apart_passes_and_three_apart_warns():
    assert (await _check(_crossref(KWIAT, year=2020), ["Tom Kwiatkowski"])).status == CitationStatus.PASSED
    respx.reset()
    result = await _check(_crossref(KWIAT, year=2022), ["Tom Kwiatkowski"])
    assert any("Year" in i for i in result.issues)


@respx.mock
@pytest.mark.asyncio
async def test_start_pages_five_apart_warn_and_four_apart_pass():
    assert (await _check(_crossref(KWIAT, page="457-470"), ["Tom Kwiatkowski"])).status == CitationStatus.PASSED
    respx.reset()
    result = await _check(_crossref(KWIAT, page="458-470"), ["Tom Kwiatkowski"])
    assert any("Pages" in i for i in result.issues)


@pytest.mark.asyncio
async def test_a_malformed_doi_warns_without_asking_crossref():
    with respx.mock(assert_all_called=False) as mock:
        result = await ExistenceChecker().check(title="t", authors=["A B"], doi="arXiv:2005.11401", year=2020)
        assert mock.calls.call_count == 0
    assert any("DOI format" in i for i in result.issues)


@pytest.mark.asyncio
async def test_a_year_in_the_future_warns_even_without_a_doi():
    result = await ExistenceChecker().check(title="t", authors=["A B"], doi=None, year=2099)
    assert result.status == CitationStatus.WARNED
    assert any("future" in i for i in result.issues)


@respx.mock
@pytest.mark.asyncio
async def test_whole_pinyin_names_in_the_family_field_match_in_either_order():
    # real CrossRef records: the whole name sits in "family", given/family order varies
    crossref = _crossref([{"family": "Wu Runze"}, {"family": "Li Hao"}, {"family": "Mei Hongbo"}])
    result = await _check(crossref, ["Wu Runze", "Hao Li"])
    assert result.status == CitationStatus.PASSED, result.issues
    respx.reset()
    crossref = _crossref([{"family": "ZHANG Baoyi"}, {"family": "TANG Jiacheng"}])
    result = await _check(crossref, ["ZHANG Baoyi", "TANG Jiacheng"])
    assert result.status == CitationStatus.PASSED, result.issues
