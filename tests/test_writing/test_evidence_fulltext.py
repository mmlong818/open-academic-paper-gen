"""The evidence table reads a paper's results, discussion, limitations and conclusion when it has full text.

On 40 sampled papers the limitation cell was right in 2 and misplaced in 10: the extractor saw the
abstract and the first 1500 chars, and a paper rarely states its own limitations there.
"""
import logging
from unittest.mock import MagicMock

import pytest

from backend.literature.content_fetcher import GAP
from backend.literature.schemas import LiteratureItem
from backend.writing.evidence_table import EvidenceExtractor, source_text

ABSTRACT = "We propose GraphMol, a message-passing network for molecular property prediction. " * 4
FILLER = "Background on earlier architectures and their training data. " * 40
LIMITS = "Limitations\nGraphMol needs 3D coordinates, which are unavailable for most screening libraries."
CONCLUSION = "6 Conclusion\nGraphMol halves the error of prior message-passing networks on QM9."


def _paper(full_text: str = "") -> LiteratureItem:
    return LiteratureItem(title="GraphMol", source="arxiv", abstract=ABSTRACT, full_text=full_text)


def test_without_full_text_the_source_is_the_abstract_and_excerpt_as_before():
    item = _paper().model_copy(update={"body_excerpt": "Body excerpt. " * 200})
    assert source_text(item) == (ABSTRACT.strip() + "\n" + item.body_excerpt.strip())[:1500]


def test_with_full_text_the_source_carries_the_limitations_and_conclusion_from_the_end():
    full = "Abstract: " + ABSTRACT + "\n1 Introduction\n" + FILLER * 3 + GAP + FILLER + "\n" + LIMITS + "\n" + CONCLUSION
    text = source_text(_paper(full))
    assert text.startswith(ABSTRACT.strip()[:100])
    assert "unavailable for most screening libraries" in text and "halves the error" in text
    assert "Background on earlier architectures" not in text


def test_each_section_is_cut_to_its_budget():
    full = "Abstract: " + ABSTRACT + "\n" + FILLER + "\nLimitations\n" + "x " * 5000 + "\n" + CONCLUSION
    text = source_text(_paper(full))
    assert len(text) < 5200 and "halves the error" in text


def test_full_text_without_these_sections_falls_back_to_the_abstract_and_excerpt():
    item = _paper("Abstract: " + ABSTRACT + "\n" + FILLER).model_copy(update={"body_excerpt": "Excerpt. " * 50})
    assert source_text(item) == (ABSTRACT.strip() + "\n" + item.body_excerpt.strip())[:1500]


def _row_reply(n: int) -> str:
    return "[" + ",".join(f'{{"i": {i}, "task": "t", "method": "m", "data": "", "metric": "", '
                          f'"finding": "", "limitation": ""}}' for i in range(1, n + 1)) + "]"


@pytest.mark.asyncio
async def test_papers_go_five_to_a_batch():
    calls = []

    async def reply(prompt):
        calls.append(prompt)
        return MagicMock(content=_row_reply(5))

    llm = MagicMock()
    llm.ainvoke = reply
    items = [LiteratureItem(title=f"Paper {i}", source="arxiv", abstract=ABSTRACT) for i in range(12)]
    rows = await EvidenceExtractor(llm).run(items, "en")
    assert len(calls) == 3 and len(rows) == 12


@pytest.mark.asyncio
async def test_an_unparseable_batch_is_logged_and_tried_once_more(caplog):
    attempts = {}

    async def reply(prompt):
        n = attempts[prompt] = attempts.get(prompt, 0) + 1
        return MagicMock(content="sorry" if n == 1 else _row_reply(1))

    llm = MagicMock()
    llm.ainvoke = reply
    with caplog.at_level(logging.WARNING, logger="backend.writing.evidence_table"):
        rows = await EvidenceExtractor(llm).run([LiteratureItem(title="P", source="arxiv", abstract=ABSTRACT)], "en")
    assert len(rows) == 1 and list(attempts.values()) == [2]
    assert "no rows" in caplog.text


@pytest.mark.asyncio
async def test_rows_missing_from_a_reply_are_asked_for_again():
    """One reply in about fourteen parsed only rows 1 and 5 of five, and three papers lost their row."""
    replies = iter(["[" + _row_reply(5)[1:].split("},")[0] + "}]", _row_reply(5)])

    async def reply(prompt):
        return MagicMock(content=next(replies))

    llm = MagicMock()
    llm.ainvoke = reply
    items = [LiteratureItem(title=f"Paper {i}", source="arxiv", abstract=ABSTRACT) for i in range(5)]
    assert len(await EvidenceExtractor(llm).run(items, "en")) == 5


@pytest.mark.asyncio
async def test_a_batch_failing_twice_costs_only_its_rows():
    async def reply(prompt):
        if "Paper 7" in prompt:
            raise RuntimeError("rate limited")
        return MagicMock(content=_row_reply(5))

    llm = MagicMock()
    llm.ainvoke = reply
    items = [LiteratureItem(title=f"Paper {i}", source="arxiv", abstract=ABSTRACT) for i in range(10)]
    assert len(await EvidenceExtractor(llm).run(items, "en")) == 5
