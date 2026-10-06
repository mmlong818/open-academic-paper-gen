import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.writing.section_writer import SectionWriter
from backend.literature.schemas import LiteratureItem


def _make_item(title: str, abstract: str = "test abstract") -> LiteratureItem:
    return LiteratureItem(title=title, abstract=abstract, source="arxiv")


OUTLINE = [
    {"title": "引言", "summary": "介绍背景。"},
    {"title": "相关工作", "summary": "综述方法。"},
]


@pytest.mark.asyncio
async def test_section_writer_returns_dict_of_sections():
    with patch("backend.writing.section_writer.strong_llm") as MockLLM:
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="章节内容文本。"))
        MockLLM.return_value = mock_llm

        writer = SectionWriter()
        result = await writer.run(
            outline=OUTLINE,
            synthesis="综合分析...",
            literature=[_make_item("Paper A")],
            language="zh",
        )

    assert isinstance(result, dict)
    assert "引言" in result
    assert "相关工作" in result
    assert all(isinstance(v, str) and len(v) > 0 for v in result.values())


@pytest.mark.asyncio
async def test_section_writer_calls_llm_once_per_section():
    call_count = [0]

    async def count_calls(prompt):
        call_count[0] += 1
        return MagicMock(content=f"Content for call {call_count[0]}")

    with patch("backend.writing.section_writer.strong_llm") as MockLLM:
        mock_llm = MagicMock()
        mock_llm.ainvoke = count_calls
        MockLLM.return_value = mock_llm

        writer = SectionWriter()
        await writer.run(
            outline=OUTLINE,
            synthesis="s",
            literature=[],
            language="zh",
        )

    assert call_count[0] == len(OUTLINE)


@pytest.mark.asyncio
async def test_section_writer_handles_llm_error_per_section():
    call_count = [0]

    async def fail_second(prompt):
        call_count[0] += 1
        if call_count[0] == 2:
            raise Exception("API Error")
        return MagicMock(content="Good content")

    with patch("backend.writing.section_writer.strong_llm") as MockLLM:
        mock_llm = MagicMock()
        mock_llm.ainvoke = fail_second
        MockLLM.return_value = mock_llm

        writer = SectionWriter()
        result = await writer.run(
            outline=OUTLINE,
            synthesis="s",
            literature=[],
            language="zh",
        )

    assert len(result) == len(OUTLINE)
    assert all(isinstance(v, str) for v in result.values())


@pytest.mark.asyncio
async def test_section_writer_empty_outline_returns_empty_dict():
    with patch("backend.writing.section_writer.strong_llm") as MockLLM:
        MockLLM.return_value = MagicMock()
        writer = SectionWriter()
        result = await writer.run(
            outline=[],
            synthesis="s",
            literature=[],
            language="zh",
        )

    assert result == {}
