import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.writing.synthesis import SynthesisAgent
from backend.literature.schemas import LiteratureItem


def _make_item(title: str, abstract: str) -> LiteratureItem:
    return LiteratureItem(title=title, abstract=abstract, source="arxiv")


@pytest.mark.asyncio
async def test_synthesis_returns_non_empty_string():
    with patch("backend.writing.synthesis.fast_llm") as MockLLM:
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(content="综合分析表明深度学习在医学影像领域取得了显著进展。")
        )
        MockLLM.return_value = mock_llm

        agent = SynthesisAgent()
        items = [
            _make_item("Paper A", "Deep learning improves diagnosis accuracy."),
            _make_item("Paper B", "CNN achieves state-of-the-art results."),
        ]
        result = await agent.run(topic="深度学习", literature=items, language="zh")

    assert isinstance(result, str)
    assert len(result) > 10


@pytest.mark.asyncio
async def test_synthesis_passes_abstracts_to_prompt():
    captured_prompt = []

    async def capture_ainvoke(prompt):
        captured_prompt.append(prompt)
        return MagicMock(content="synthesis text")

    with patch("backend.writing.synthesis.fast_llm") as MockLLM:
        mock_llm = MagicMock()
        mock_llm.ainvoke = capture_ainvoke
        MockLLM.return_value = mock_llm

        agent = SynthesisAgent()
        items = [_make_item("Test Paper", "Abstract content here")]
        await agent.run(topic="test", literature=items, language="en")

    assert len(captured_prompt) == 1
    assert "Abstract content here" in captured_prompt[0]


@pytest.mark.asyncio
async def test_synthesis_handles_empty_literature():
    with patch("backend.writing.synthesis.fast_llm") as MockLLM:
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="No literature found."))
        MockLLM.return_value = mock_llm

        agent = SynthesisAgent()
        result = await agent.run(topic="test", literature=[], language="en")

    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_synthesis_raises_on_llm_error():
    # a placeholder synthesis would pass the gate as if the phase had worked
    with patch("backend.writing.synthesis.fast_llm") as MockLLM:
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("429 rate limit"))
        MockLLM.return_value = mock_llm

        agent = SynthesisAgent()
        items = [_make_item(f"Paper {i}", "abstract") for i in range(25)]
        with pytest.raises(RuntimeError, match="429"):
            await agent.run(topic="test", literature=items, language="zh")
