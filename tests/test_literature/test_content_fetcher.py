"""PDF text starts with title pages, affiliations and licences; the excerpt must skip them."""
from backend.literature.content_fetcher import _trim_front_matter

HEADER = "TYPE Original Research PUBLISHED 13 September 2024 COPYRIGHT © 2024 Author. " * 20


def test_starts_at_inline_introduction_heading():
    text = HEADER + "Finland Introduction: This article reviews hybrid work."
    assert _trim_front_matter(text).startswith("Introduction: This article")


def test_starts_at_bare_abstract_heading():
    text = "Springfield, USA * author@example.edu Abstract The paradigm shifts of offices"
    assert _trim_front_matter(text).startswith("Abstract The paradigm")


def test_abstract_beats_a_later_introduction():
    text = HEADER + "Abstract: We study X. 1 Introduction Work matters."
    assert _trim_front_matter(text).startswith("Abstract: We study X.")


def test_chinese_bracketed_abstract_heading():
    text = "教育研究 第 2 卷 版权所有 张琳 西安音乐学院 DOI:10.32629/er  [ 摘   要 ]  在新时期的快速发展中"
    assert _trim_front_matter(text).startswith("[ 摘   要 ]")


def test_chinese_colon_abstract_heading():
    text = "项目支持：四川省大学生创新创业训练项目 Doi:10.55375 摘要:焦虑是大学生群体中常见的心理健康问题。"
    assert _trim_front_matter(text).startswith("摘要:焦虑是")


def test_lowercase_abstract_in_prose_is_not_a_heading():
    text = "We learn an abstract representation of molecules. Results follow."
    assert _trim_front_matter(text) == text


def test_heading_far_into_the_text_is_ignored():
    text = "Body text without headings. " * 400 + "References Introduction: cited title"
    assert _trim_front_matter(text) == text


# ---------------------------------------------------------------- where the PDF comes from

from unittest.mock import AsyncMock, patch  # noqa: E402

from backend.literature.content_fetcher import _enrich_one, pdf_candidates  # noqa: E402
from backend.literature.schemas import LiteratureItem  # noqa: E402

BODY = "Abstract: " + "Real body text about the method and its results. " * 20


def _item(**kw) -> LiteratureItem:
    return LiteratureItem(**{"title": "T", "source": "openalex", "abstract": "short abstract", **kw})


def test_candidates_try_s2_then_the_retrieved_pdf_url():
    item = _item(doi="10.1/x", url="https://journal.org/paper.pdf")
    assert pdf_candidates(item, s2_pdf="https://s2.org/x.pdf") == [
        "https://s2.org/x.pdf", "https://journal.org/paper.pdf",
    ]


def test_arxiv_items_get_their_pdf_from_the_arxiv_id():
    item = _item(source="arxiv", source_id="2504.05324v1", url="https://arxiv.org/abs/2504.05324v1")
    assert pdf_candidates(item, s2_pdf="") == ["https://arxiv.org/pdf/2504.05324v1"]


def test_arxiv_doi_also_yields_an_arxiv_pdf():
    item = _item(doi="10.48550/arXiv.1704.01212")
    assert pdf_candidates(item, s2_pdf="") == ["https://arxiv.org/pdf/1704.01212"]


def test_landing_pages_are_not_treated_as_pdfs():
    assert pdf_candidates(_item(url="https://doi.org/10.1/x"), s2_pdf="") == []


async def test_item_without_doi_still_gets_a_body_from_its_arxiv_pdf():
    item = _item(source="arxiv", source_id="2504.05324v1")
    with patch("backend.literature.content_fetcher._fetch_pdf_text", AsyncMock(return_value=(BODY, []))) as fetch:
        enriched = await _enrich_one(item, client=None)
    fetch.assert_awaited_once_with("https://arxiv.org/pdf/2504.05324v1", None)
    assert enriched.body_excerpt == BODY


async def test_falls_back_to_the_next_candidate_when_a_download_fails():
    item = _item(doi="10.1/x", url="https://journal.org/paper.pdf")
    with (
        patch("backend.literature.content_fetcher._fetch_s2_meta",
              AsyncMock(return_value={"openAccessPdf": {"url": "https://s2.org/x.pdf"}})),
        patch("backend.literature.content_fetcher._fetch_pdf_text", AsyncMock(side_effect=[("", []), (BODY, [])])),
    ):
        enriched = await _enrich_one(item, client=None)
    assert enriched.body_excerpt == BODY


async def test_full_text_is_kept_beyond_the_short_excerpt():
    long_body = "Abstract: " + "Methods and results with specific numbers. " * 200  # ~8,600 chars
    item = _item(source="arxiv", source_id="2504.05324v1")
    with patch("backend.literature.content_fetcher._fetch_pdf_text", AsyncMock(return_value=(long_body, []))):
        enriched = await _enrich_one(item, client=None)
    assert len(enriched.body_excerpt) == 2000  # screening and writing keep the short excerpt
    assert enriched.full_text == long_body  # layer 3 can search the whole text


async def test_no_pdf_means_no_full_text():
    item = _item(doi="10.1/x")
    with (
        patch("backend.literature.content_fetcher._fetch_s2_meta", AsyncMock(return_value={})),
        patch("backend.literature.content_fetcher._fetch_pdf_text", AsyncMock(return_value=("", []))),
    ):
        enriched = await _enrich_one(item, client=None)
    assert enriched.full_text == ""
