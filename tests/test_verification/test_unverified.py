"""A cited paper with no text to check a claim against is 'unverified', not 'passed'.

On a Chinese review all 15 cited papers had neither an abstract nor full text. Layer 3 had
nothing to judge nine of them against, yet the panel counted every one under "通过核验".
"""
from unittest.mock import AsyncMock, patch

import pytest

from backend.literature.bibtex import bibtex_key
from backend.literature.schemas import LiteratureItem
from backend.verification.orchestrator import VerificationOrchestrator
from backend.verification.schemas import VerificationResult


def _run(orchestrator, item):
    context = f"海关领域研究已利用多模态知识图谱处理法规冲突 [cite:{bibtex_key(item)}]。"
    return orchestrator.run([item], context)


def _patched(orchestrator, item):
    return (
        patch.object(orchestrator.support_checker, "check", new=AsyncMock(return_value={})),
        patch.object(orchestrator.existence_checker, "check", new=AsyncMock(
            return_value=VerificationResult(title=item.title, doi=item.doi, layer1_ok=True))),
    )


@pytest.mark.asyncio
async def test_a_title_only_paper_is_unverified():
    orchestrator = VerificationOrchestrator()
    item = LiteratureItem(title="国产大语言模型检索增强生成技术在海关领域的应用研究", source="crossref", doi="10.1/x")
    support, existence = _patched(orchestrator, item)
    with support, existence:
        _, issues, summary = await _run(orchestrator, item)
    assert [i.action for i in issues] == ["unverified"]
    assert "未核对" in issues[0].reason or "not checked" in issues[0].reason
    assert summary.passed == 0


@pytest.mark.asyncio
async def test_a_paper_with_an_abstract_still_passes():
    orchestrator = VerificationOrchestrator()
    item = LiteratureItem(title="RAG", source="arxiv", abstract="Retrieval-augmented generation. " * 20)
    support, existence = _patched(orchestrator, item)
    with support, existence:
        _, issues, summary = await _run(orchestrator, item)
    assert [i.action for i in issues] == ["kept"] and summary.passed == 1


@pytest.mark.asyncio
async def test_nothing_is_unverified_when_the_support_check_is_off():
    orchestrator = VerificationOrchestrator()
    item = LiteratureItem(title="t", source="crossref")
    support, existence = _patched(orchestrator, item)
    with support, existence, patch("backend.verification.orchestrator.settings.verify_citation_support", False):
        _, issues, _ = await _run(orchestrator, item)
    assert [i.action for i in issues] == ["kept"]
