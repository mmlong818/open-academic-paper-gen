"""Full text keeps the end of the body as well as its start, and drops the references.

Read whole, 27 of 60 papers ran past the 40000-char cap, which kept only the start: the conclusion
was lost in 17 of 53, the limitations in 6 of 31. The conclusion sits a median 2.1k chars (p90 8.3k)
before the references, so the first 40000 chars and the last 10000 before the references keep it
in 51 of 53. Short papers lose their reference list, which layer 3 could match a claim against.
"""
from unittest.mock import AsyncMock, patch

import pytest

from backend.core.config import settings
from backend.literature.content_fetcher import GAP, PaperContentFetcher, _join_pages, references_start
from backend.literature.paper_cache import FULL_TEXT_VERSION, to_row
from backend.literature.schemas import LiteratureItem
from backend.verification.evidence import claim_pages, select_evidence
from backend.verification.layer3_support import Claim

REFS = "\nReferences\n[1] A. Author. Some cited title. 2020.\n[2] B. Author. Another title. 2021.\n"


def test_the_last_references_heading_ends_the_body():
    text = "Abstract: x\nRelated work, see References\n" + "body " * 100 + REFS
    assert text[references_start(text):].lstrip().startswith("References")


def test_a_references_heading_in_the_first_third_is_not_the_reference_list():
    text = "Abstract: x\nReferences\n" + "body " * 100
    assert references_start(text) == len(text)


def test_a_short_paper_is_kept_whole_without_its_references():
    text, pages = _join_pages(["Abstract: We study X.\n" + "body " * 50, "Conclusion: it works.\n" + REFS])
    assert text.endswith("Conclusion: it works.")
    assert "Some cited title" not in text and GAP not in text
    assert [p for _, p in pages] == [1, 2]


def test_a_long_paper_keeps_its_start_and_the_end_before_the_references():
    start, end = "Abstract: " + "s" * 90, "e" * 40 + "Conclusion: it works."
    text, _ = _join_pages([start, "m" * 500, end + REFS], head=100, tail=61)
    assert text == start + GAP + end


def test_page_offsets_follow_both_parts():
    pages_in = ["Abstract: " + "a" * 90, "b" * 100, "c" * 100, "d" * 100, "Conclusion: it works." + REFS]
    text, pages = _join_pages(pages_in, head=150, tail=121)
    assert [p for _, p in pages] == [1, 2, 4, 5]
    tail_start = text.index(GAP) + len(GAP)
    assert pages[2] == [tail_start, 4]
    assert text[dict((p, o) for o, p in pages)[5]:].startswith("Conclusion")


def _long_paper(tail_sentence: str) -> LiteratureItem:
    filler = "Background material on unrelated architectures and datasets. " * 12
    head = "Abstract: We study retrieval.\n\n" + "\n\n".join([filler] * 4)
    return LiteratureItem(title="T", source="arxiv", full_text=head + GAP + tail_sentence,
                          full_text_pages=[[0, 1], [len(head) + len(GAP), 9]])


def test_layer3_evidence_comes_from_the_start_only():
    """Judged on the end too, layer 3 recognised support 4% less often (80.3 vs 84.0 of 99 claims,
    three runs each): end-of-paper sections sharing the claim's words pushed out the specific ones."""
    item = _long_paper("Our main limitation is that the retriever never sees tables or figures.")
    claim = Claim("K", "The retriever never sees tables or figures [cite:K].")
    assert "never sees tables" not in select_evidence(item, [claim])
    assert claim_pages(item, claim) != [9]


def test_a_cache_row_records_the_full_text_version():
    row = to_row(LiteratureItem(title="T", source="openalex", doi="10.1/x", full_text="body " * 100))
    assert row["meta"]["full_text_version"] == FULL_TEXT_VERSION


@pytest.mark.asyncio
async def test_full_text_cached_by_the_older_cut_is_fetched_again():
    old = {"key": "doi:10.1/old", "abstract": "", "body_excerpt": "x" * 400, "full_text": "x" * 4000,
           "full_text_pages": [[0, 1]], "meta": {"volume": "7"}}
    item = LiteratureItem(title="T", source="openalex", doi="10.1/old")
    fetched = item.model_copy(update={"full_text": "new " * 1000})
    with (
        patch.object(settings, "paper_cache", True),
        patch("backend.literature.content_fetcher.load_cached", AsyncMock(return_value={"doi:10.1/old": old})),
        patch("backend.literature.content_fetcher.store_cached", AsyncMock()),
        patch("backend.literature.content_fetcher._enrich_one", AsyncMock(return_value=fetched)) as enrich,
    ):
        [out] = await PaperContentFetcher().run([item])
    assert enrich.await_count == 1 and out.full_text == "new " * 1000
