import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.writing.angle import AngleAgent


@pytest.mark.asyncio
async def test_angle_raises_on_llm_error():
    # a canned default angle would pass the gate as if it came from this topic's literature
    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=Exception("429 rate limit"))
    with pytest.raises(RuntimeError, match="429"):
        await AngleAgent(llm=llm).run(topic="t", synthesis="s", research_questions=[], language="en")


@pytest.mark.asyncio
async def test_angle_raises_on_invalid_json():
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content="not json"))
    with pytest.raises(RuntimeError, match="JSONDecodeError"):
        await AngleAgent(llm=llm).run(topic="t", synthesis="s", research_questions=[], language="en")


@pytest.mark.asyncio
async def test_angle_surfaces_a_bad_api_key_distinctly():
    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=Exception("401 invalid api_key"))
    with pytest.raises(RuntimeError, match="API key"):
        await AngleAgent(llm=llm).run(topic="t", synthesis="s", research_questions=[], language="en")
