"""Page anchors: the PDF page each full-text passage
comes from, so a warning can say where in the source to look. Pages are PDF pages, not printed ones;
the judge's prompt is unchanged."""
from unittest.mock import AsyncMock, patch

import pytest

from backend.literature.content_fetcher import _enrich_one, _join_pages
from backend.literature.schemas import LiteratureItem
from backend.verification.evidence import claim_pages
from backend.verification.layer3_support import UNSUPPORTED, Claim, SupportChecker
from backend.verification.orchestrator import _unsupported_reason
from backend.verification.layer3_support import SupportVerdict

FILLER = "Background material on unrelated architectures and datasets. " * 12
DEEP = "In the ablation, removing layer normalisation cost 3.1 BLEU on the translation benchmark."


def test_pages_are_offsets_into_the_trimmed_text():
    cover = "Journal of Things. Licence CC-BY. " * 5
    text, pages = _join_pages([cover + "Abstract: We study X.\n", "Methods follow here.\n", "Results: 3.1 BLEU.\n"])
    assert text.startswith("Abstract: We study X.")
    assert pages[0] == [0, 1], "the trimmed cover page still starts the text on page 1"
    assert [p for _, p in pages] == [1, 2, 3]
    assert text[pages[2][0]:].startswith("Results: 3.1 BLEU.")


def test_pages_cut_off_by_the_length_cap_are_dropped():
    text, pages = _join_pages(["Abstract: " + "a" * 50, "b" * 50, "c" * 50], head=80, tail=0)
    assert len(text) == 80 and [p for _, p in pages] == [1, 2]


def _item(full: str, pages: list[list[int]]) -> LiteratureItem:
    return LiteratureItem(title="T", source="arxiv", abstract="We study transformers.",
                          full_text=full, full_text_pages=pages)


def _paged() -> tuple[str, list[list[int]]]:
    page_texts = ["Abstract: We study transformers.\n\n" + "\n\n".join([FILLER] * 4)] * 3
    page_texts.append("\n\n".join([FILLER, DEEP, FILLER]))
    return _join_pages(page_texts)


def test_a_claim_is_anchored_to_the_page_of_its_best_passage():
    full, pages = _paged()
    item = _item(full, pages)
    assert claim_pages(item, Claim("K", "Removing layer normalisation cost 3.1 BLEU [cite:K].")) == [4]


def test_no_pages_without_page_data():
    full, _ = _paged()
    assert claim_pages(_item(full, []), Claim("K", "layer normalisation cost 3.1 BLEU")) == []


@pytest.mark.asyncio
async def test_the_checker_attaches_pages_to_each_verdict():
    full, pages = _paged()
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(return_value=type("R", (), {"content": '[{"verdict": "unsupported", "reason": "r"}]'})())
    claim = Claim("K", "Removing layer normalisation cost 3.1 BLEU [cite:K].")
    result = await SupportChecker(llm=llm).check({"K": [claim]}, {"K": _item(full, pages)})
    assert result["K"][0].pages == (4,)


def test_the_warning_names_the_pdf_page():
    verdict = SupportVerdict(Claim("K", "Removing layer normalisation cost 3.1 BLEU."), UNSUPPORTED, "r", pages=(4,))
    assert "(PDF p. 4)" in _unsupported_reason([verdict])
    plain = SupportVerdict(Claim("K", "x."), UNSUPPORTED, "r")
    assert "PDF p." not in _unsupported_reason([plain])


@pytest.mark.asyncio
async def test_the_fetcher_keeps_the_page_offsets():
    body = "Abstract: " + "Real body text about the method and its results. " * 20
    item = LiteratureItem(title="T", source="arxiv", source_id="2504.05324v1", abstract="short")
    with patch("backend.literature.content_fetcher._fetch_pdf_text", AsyncMock(return_value=(body, [[0, 1], [500, 2]]))):
        enriched = await _enrich_one(item, client=None)
    assert enriched.full_text == body and enriched.full_text_pages == [[0, 1], [500, 2]]


def test_nul_characters_are_dropped_before_offsets_are_taken():
    text, pages = _join_pages(["Abstract: one\x00 two\n", "Page\x00 two text\n"])
    assert "\x00" not in text
    assert text[pages[1][0]:].startswith("Page two text")
