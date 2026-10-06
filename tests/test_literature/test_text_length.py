"""Length thresholds weigh a Chinese character as 2.5 characters of English.

The thresholds (300 to screen on an abstract, 200 for layer 3 to check a claim, 300 to show an
excerpt) were set for English. A 150-character Chinese abstract, about 100 English words, fell
under all three: 14 of 47 thin Chinese records in one sample had 120-199 characters of abstract.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.literature.bibtex import bibtex_key
from backend.literature.schemas import LiteratureItem
from backend.literature.screener import LiteratureScreener
from backend.literature.text_length import weighted_length
from backend.verification.orchestrator import VerificationOrchestrator
from backend.verification.schemas import VerificationResult
from backend.writing.prompts import _body_excerpt_for_prompt

ZH_ABSTRACT = "本研究提出基于图结构优化的检索增强生成框架，构建多模态知识图谱整合法规条款的语义关联。" * 3  # ~135 chars


def test_chinese_characters_weigh_two_and_a_half():
    assert weighted_length("abcd") == 4
    assert weighted_length("检索") == 5
    assert weighted_length("RAG 检索") == 4 + 5


@pytest.mark.asyncio
async def test_a_short_chinese_abstract_is_screened_on_the_abstract():
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content='{"decision": "include", "reason": "r"}'))
    item = LiteratureItem(title="海关领域的检索增强生成", abstract=ZH_ABSTRACT, source="crossref")
    _, rows = await LiteratureScreener(llm).run(topic="检索增强生成", items=[item], language="zh")
    assert rows[0]["basis"] == "abstract"


@pytest.mark.asyncio
async def test_a_short_chinese_abstract_is_enough_to_check_a_claim():
    orchestrator = VerificationOrchestrator()
    item = LiteratureItem(title="海关领域的检索增强生成", abstract=ZH_ABSTRACT, source="crossref")
    with patch.object(orchestrator.support_checker, "check", new=AsyncMock(return_value={})), \
         patch.object(orchestrator.existence_checker, "check", new=AsyncMock(
             return_value=VerificationResult(title=item.title, doi=None, layer1_ok=True))):
        _, issues, _ = await orchestrator.run([item], f"海关研究构建了知识图谱 [cite:{bibtex_key(item)}]。")
    assert [i.action for i in issues] == ["kept"]


def test_a_short_chinese_excerpt_is_shown_to_the_writer():
    assert _body_excerpt_for_prompt({"body_excerpt": ZH_ABSTRACT, "abstract": ""}) == ZH_ABSTRACT
