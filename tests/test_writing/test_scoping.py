import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.writing.scoping import ScopingAgent


@pytest.mark.asyncio
async def test_scoping_returns_research_questions_and_keywords():
    mock_response = """## 研究问题
- 深度学习如何提升医学影像诊断精度？
- 卷积神经网络在病理切片分析中的局限是什么？
- 数据不足问题如何通过迁移学习解决？

## 关键词
- 深度学习
- 医学影像
- 卷积神经网络
- 迁移学习
- 图像分割"""

    with patch("backend.writing.scoping.fast_llm") as MockLLM:
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content=mock_response))
        MockLLM.return_value = mock_llm

        agent = ScopingAgent()
        result = await agent.run(topic="深度学习在医学影像中的应用", language="zh")

    assert "research_questions" in result
    assert "keywords" in result
    assert len(result["research_questions"]) >= 2
    assert len(result["keywords"]) >= 3


@pytest.mark.asyncio
async def test_scoping_parses_english_response():
    mock_response = """## Research Questions
- How does deep learning improve diagnostic accuracy?
- What are the limitations of CNNs in pathology?

## Keywords
- deep learning
- medical imaging
- CNN
- transfer learning"""

    with patch("backend.writing.scoping.fast_llm") as MockLLM:
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content=mock_response))
        MockLLM.return_value = mock_llm

        agent = ScopingAgent()
        result = await agent.run(topic="deep learning in medical imaging", language="en")

    assert len(result["research_questions"]) >= 2
    assert len(result["keywords"]) >= 3


@pytest.mark.asyncio
async def test_scoping_raises_on_llm_error():
    # a placeholder question would pass the gate as if scoping had worked
    with patch("backend.writing.scoping.fast_llm") as MockLLM:
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("API Error"))
        MockLLM.return_value = mock_llm

        agent = ScopingAgent()
        with pytest.raises(RuntimeError, match="API Error"):
            await agent.run(topic="test topic", language="zh")


def test_chinese_scoping_asks_for_english_keywords_too():
    # English sources return nothing for Chinese terms; the crew routes the English ones to them
    from backend.writing.prompts import build_scoping_prompt
    prompt = build_scoping_prompt(topic="检索增强生成在知识密集型问答中的应用", language="zh")
    assert "英文关键词" in prompt


@pytest.mark.asyncio
async def test_chinese_and_english_keyword_lists_are_both_kept():
    reply = """## 研究问题
- RAG 如何降低幻觉？

## 中文关键词
- 检索增强生成
- 知识密集型问答

## 英文关键词
- Retrieval-augmented generation
- Knowledge-intensive question answering"""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content=reply))
    result = await ScopingAgent(llm=llm).run(topic="t", language="zh")
    assert result["keywords"] == ["检索增强生成", "知识密集型问答",
                                  "Retrieval-augmented generation", "Knowledge-intensive question answering"]
