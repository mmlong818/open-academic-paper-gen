"""Papers without an abstract are screened on their title instead of waved through.

A Chinese review's pool kept 57 of its 63 papers unscreened because CrossRef had no abstract
for them: a Lu Xun essay, option pricing and a figure caption among them.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.literature.schemas import LiteratureItem
from backend.literature.screener import LiteratureScreener
from backend.writing.prisma import review_process_facts


def _llm(decision: str) -> MagicMock:
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content=f'{{"decision": "{decision}", "reason": "r"}}'))
    return llm


@pytest.mark.asyncio
async def test_a_paper_without_an_abstract_is_screened_on_its_title():
    llm = _llm("exclude")
    item = LiteratureItem(title="从追寻到幻灭：浅论鲁迅小说中觉醒的知识分子", source="crossref")
    kept, rows = await LiteratureScreener(llm).run(topic="检索增强生成", items=[item], language="zh")
    assert kept == []
    assert rows[0]["decision"] == "exclude" and rows[0]["basis"] == "title"
    prompt = llm.ainvoke.call_args.args[0]
    assert "鲁迅" in prompt and "只有标题" in prompt


@pytest.mark.asyncio
async def test_a_paper_with_an_abstract_is_screened_on_it():
    llm = _llm("include")
    item = LiteratureItem(title="RAG", abstract="a" * 400, source="arxiv")
    kept, rows = await LiteratureScreener(llm).run(topic="t", items=[item], language="en")
    assert kept == [item] and rows[0]["basis"] == "abstract"
    assert "Title only" not in llm.ainvoke.call_args.args[0]


@pytest.mark.asyncio
async def test_a_record_with_nothing_to_read_is_still_included_unasked():
    llm = _llm("exclude")
    item = LiteratureItem(title="", source="crossref")
    kept, rows = await LiteratureScreener(llm).run(topic="t", items=[item], language="en")
    assert kept == [item] and rows[0]["basis"] == "none"
    llm.ainvoke.assert_not_called()


def test_facts_say_how_many_records_were_screened_on_the_title_alone():
    report = {"total_before": 3, "excluded_by_llm": 1,
              "screening_rows": [{"basis": "title"}, {"basis": "title"}, {"basis": "abstract"}]}
    items = [LiteratureItem(title="a", source="crossref", year=2020)]
    assert "2 of them without an abstract, screened on the title alone" in review_process_facts(report, items, [], "en")
    assert "其中 2 条无摘要，仅按标题筛选" in review_process_facts(report, items, [], "zh")
