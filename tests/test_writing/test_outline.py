import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.writing.outline import OutlineAgent


VALID_JSON_RESPONSE = """[
  {"title": "引言", "summary": "介绍研究背景和动机。"},
  {"title": "相关工作", "summary": "综述现有方法。"},
  {"title": "方法", "summary": "描述提出的方法。"},
  {"title": "实验", "summary": "展示实验结果。"},
  {"title": "结论", "summary": "总结贡献和未来工作。"}
]"""


@pytest.mark.asyncio
async def test_outline_returns_list_of_dicts():
    with patch("backend.writing.outline.fast_llm") as MockLLM:
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content=VALID_JSON_RESPONSE))
        MockLLM.return_value = mock_llm

        agent = OutlineAgent()
        result = await agent.run(
            topic="深度学习",
            synthesis="综合分析...",
            research_questions=["RQ1", "RQ2"],
            language="zh",
        )

    assert isinstance(result, list)
    assert len(result) >= 3
    assert all("title" in item and "summary" in item for item in result)


@pytest.mark.asyncio
async def test_outline_handles_json_with_markdown_fence():
    fenced = f"```json\n{VALID_JSON_RESPONSE}\n```"
    with patch("backend.writing.outline.fast_llm") as MockLLM:
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content=fenced))
        MockLLM.return_value = mock_llm

        agent = OutlineAgent()
        result = await agent.run(
            topic="test", synthesis="s", research_questions=[], language="en"
        )

    assert isinstance(result, list)
    assert len(result) >= 3


@pytest.mark.asyncio
async def test_outline_raises_on_invalid_json():
    """A canned outline passed off as generated is worse than a visible failure."""
    with patch("backend.writing.outline.fast_llm") as MockLLM:
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="Not valid JSON"))
        MockLLM.return_value = mock_llm

        agent = OutlineAgent()
        with pytest.raises(RuntimeError, match="JSONDecodeError"):
            await agent.run(
                topic="test", synthesis="s", research_questions=[], language="zh"
            )


@pytest.mark.asyncio
async def test_outline_raises_on_llm_error():
    with patch("backend.writing.outline.fast_llm") as MockLLM:
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("API Error"))
        MockLLM.return_value = mock_llm

        agent = OutlineAgent()
        with pytest.raises(RuntimeError, match="API Error"):
            await agent.run(
                topic="test", synthesis="s", research_questions=[], language="en"
            )


@pytest.mark.asyncio
async def test_outline_surfaces_a_bad_api_key_distinctly():
    with patch("backend.writing.outline.fast_llm") as MockLLM:
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("401 invalid api_key"))
        MockLLM.return_value = mock_llm

        agent = OutlineAgent()
        with pytest.raises(RuntimeError, match="API key"):
            await agent.run(
                topic="test", synthesis="s", research_questions=[], language="en"
            )
