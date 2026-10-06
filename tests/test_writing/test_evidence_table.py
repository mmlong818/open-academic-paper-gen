"""Evidence table of the pool.

Cells come only from each paper's own text: a field the text does not report stays empty, and a
cell naming a number absent from the text is the model's invention and is emptied.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.export.evidence_export import to_csv, to_markdown
from backend.literature.bibtex import bibtex_key
from backend.literature.schemas import LiteratureItem
from backend.writing.evidence_table import FIELDS, EvidenceExtractor, evidence_line
from backend.writing.prompts import _format_literature_block

ABSTRACT = ("We propose GraphMol, a message-passing network for molecular property prediction, "
            "evaluated on QM9 where it reaches a mean absolute error of 0.012 eV. ") * 3


def _item(title: str, abstract: str = ABSTRACT) -> LiteratureItem:
    return LiteratureItem(title=title, authors=["Jane Smith"], year=2024, source="arxiv", abstract=abstract)


def _llm(reply: str) -> MagicMock:
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content=reply))
    return llm


_ROW = ('{"i": 1, "task": "molecular property prediction", "method": "message passing", "data": "QM9", '
        '"metric": "MAE 0.012 eV", "finding": "beats baselines by 35%", "limitation": "not reported"}')


@pytest.mark.asyncio
async def test_rows_carry_the_key_and_every_field():
    item = _item("GraphMol")
    rows = await EvidenceExtractor(_llm(f"[{_ROW}]")).run([item], "en")

    assert len(rows) == 1
    row = rows[0]
    assert row["key"] == bibtex_key(item) and row["title"] == "GraphMol" and row["year"] == 2024
    assert set(FIELDS) <= set(row)
    assert row["data"] == "QM9" and row["metric"] == "MAE 0.012 eV"


@pytest.mark.asyncio
async def test_a_number_absent_from_the_text_empties_its_cell():
    rows = await EvidenceExtractor(_llm(f"[{_ROW}]")).run([_item("GraphMol")], "en")
    assert rows[0]["finding"] == "", "35% is not in the abstract"
    assert rows[0]["dropped"] == 1


@pytest.mark.asyncio
async def test_not_reported_is_stored_empty():
    rows = await EvidenceExtractor(_llm(f"[{_ROW}]")).run([_item("GraphMol")], "en")
    assert rows[0]["limitation"] == ""


@pytest.mark.asyncio
async def test_papers_without_text_are_not_sent():
    llm = _llm("[]")
    rows = await EvidenceExtractor(llm).run([_item("Title only", abstract="")], "en")
    assert rows == []
    llm.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_an_unparseable_reply_yields_no_rows():
    assert await EvidenceExtractor(_llm("sorry, no")).run([_item("GraphMol")], "en") == []


def test_markdown_and_csv_show_empty_cells_as_not_reported():
    rows = [{"key": "Smith2024G", "title": "Graph | Mol", "year": 2024, "task": "prediction",
             **{f: "" for f in FIELDS if f != "task"}, "dropped": 0}]
    md = to_markdown(rows, "zh")
    assert md.splitlines()[0].startswith("| 文献 | 年份 | 任务")
    assert "Graph \\| Mol" in md and "未报告" in md
    csv_text = to_csv(rows, "en")
    assert csv_text.splitlines()[0].startswith("Paper,Year,Task")
    assert "not reported" in csv_text


def test_the_section_prompt_shows_an_evidence_row_only_when_given():
    base = {"title": "GraphMol", "authors_str": "Smith, J.", "year": 2024, "abstract": ABSTRACT}
    row = {"task": "prediction", "method": "message passing", "data": "", "metric": "", "finding": "", "limitation": ""}
    with_row = _format_literature_block([{**base, "evidence": evidence_line(row, "en")}], "en")
    assert "Evidence row: Task: prediction; Method: message passing" in with_row
    assert "Evidence row" not in _format_literature_block([base], "en")
