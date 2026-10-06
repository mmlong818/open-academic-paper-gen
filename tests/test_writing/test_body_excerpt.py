"""Body-text excerpts must reach the section-writing prompt, not stop at screening."""
from unittest.mock import MagicMock, patch

import pytest

from backend.literature.schemas import LiteratureItem
from backend.writing.prompts import (
    _EXCERPT_MAX_CHARS,
    _body_excerpt_for_prompt,
    _format_literature_block,
)
from backend.writing.section_writer import SectionWriter, _to_lit_dict

ABSTRACT = "We study transformer scaling. " * 20  # ~600 chars
BODY = ABSTRACT + "1. Introduction. Our ablation removes layer norm and loses 3.1 BLEU. " * 5


def test_excerpt_dropped_when_it_only_repeats_the_abstract():
    # content_fetcher falls back to the abstract when there is no open-access PDF
    assert _body_excerpt_for_prompt({"abstract": ABSTRACT, "body_excerpt": ABSTRACT}) == ""


def test_excerpt_dropped_when_it_is_a_prefix_of_the_abstract():
    assert _body_excerpt_for_prompt({"abstract": ABSTRACT, "body_excerpt": ABSTRACT[:400]}) == ""


def test_excerpt_dropped_when_too_short_to_be_body_text():
    assert _body_excerpt_for_prompt({"abstract": "short", "body_excerpt": "tiny excerpt"}) == ""


def test_real_body_text_survives_even_though_it_contains_the_abstract():
    kept = _body_excerpt_for_prompt({"abstract": ABSTRACT, "body_excerpt": BODY})
    assert "1. Introduction" in kept
    assert "loses 3.1 BLEU" in kept


def test_excerpt_is_truncated_to_budget():
    long_body = "A unique body sentence. " * 200
    kept = _body_excerpt_for_prompt({"abstract": "", "body_excerpt": long_body})
    assert len(kept) == _EXCERPT_MAX_CHARS + 3
    assert kept.endswith("...")


def test_literature_block_renders_excerpt_line():
    block = _format_literature_block([
        {"authors_str": "Smith, J.", "year": 2024, "title": "Scaling", "abstract": ABSTRACT,
         "body_excerpt": BODY},
    ])
    assert "Full-text excerpt:" in block
    assert "loses 3.1 BLEU" in block


def test_literature_block_omits_excerpt_line_when_it_duplicates_abstract():
    block = _format_literature_block([
        {"authors_str": "Smith, J.", "year": 2024, "title": "Scaling", "abstract": ABSTRACT,
         "body_excerpt": ABSTRACT},
    ])
    assert "Full-text excerpt:" not in block
    assert "Abstract:" in block


def test_to_lit_dict_carries_body_excerpt():
    item = LiteratureItem(title="T", abstract=ABSTRACT, body_excerpt=BODY, source="arxiv")
    assert _to_lit_dict(item)["body_excerpt"] == BODY


@pytest.mark.asyncio
async def test_section_prompt_receives_body_text():
    captured: list[str] = []

    async def capture(prompt):
        captured.append(prompt)
        return MagicMock(content="section body")

    item = LiteratureItem(
        title="Scaling", authors=["Jane Smith"], year=2024,
        abstract=ABSTRACT, body_excerpt=BODY, source="arxiv",
    )

    with patch("backend.writing.section_writer.strong_llm") as MockLLM:
        mock_llm = MagicMock()
        mock_llm.ainvoke = capture
        MockLLM.return_value = mock_llm

        await SectionWriter().run(
            outline=[{"title": "Related Work", "summary": "prior scaling studies"}],
            synthesis="s",
            literature=[item],
            language="en",
        )

    assert len(captured) == 1
    assert "loses 3.1 BLEU" in captured[0], "body excerpt never reached the writing prompt"
