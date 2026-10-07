"""Every cited claim is judged, and each paper's row says how its claims were judged.

Layer 3 judged at most six claims per paper and dropped the rest without a word: on a real
review, 10 of 92 citations (11%) went unjudged, all on the three most-cited papers. A batch
that failed, or a paper without text, left nothing on the row either.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.literature.bibtex import bibtex_key
from backend.literature.schemas import LiteratureItem
from backend.verification.layer3_support import SUPPORTED, UNCLEAR, Claim, SupportChecker, SupportVerdict
from backend.verification.orchestrator import VerificationOrchestrator, extract_claims
from backend.verification.schemas import VerificationResult

ABSTRACT = "We evaluate retrieval augmentation on open-domain QA. " * 10


def _claims(n: int) -> dict[str, list[Claim]]:
    return {"Smith2024": [Claim(key="Smith2024", sentence=f"Claim number {i} [cite:Smith2024].") for i in range(n)]}


def _reply(n: int = 6) -> MagicMock:
    return MagicMock(content="[" + ",".join(['{"verdict": "supported", "reason": ""}'] * n) + "]")


@pytest.mark.asyncio
async def test_every_claim_is_judged_in_batches():
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=_reply())
    item = LiteratureItem(title="RAG", abstract=ABSTRACT, source="arxiv")

    result = await SupportChecker(llm=llm).check(_claims(10), {"Smith2024": item})

    assert len(result["Smith2024"]) == 10
    assert [v.claim.sentence for v in result["Smith2024"]] == [c.sentence for c in _claims(10)["Smith2024"]]
    assert llm.ainvoke.call_count == 2


@pytest.mark.asyncio
async def test_a_failed_batch_loses_only_its_own_claims():
    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=[_reply(), RuntimeError("rate limited")])
    item = LiteratureItem(title="RAG", abstract=ABSTRACT, source="arxiv")

    result = await SupportChecker(llm=llm).check(_claims(10), {"Smith2024": item})

    assert len(result["Smith2024"]) == 6


async def _run(item: LiteratureItem, sentences: list[str], verdicts: list[str]):
    key = bibtex_key(item)
    context = " ".join(f"{s} [cite:{key}]." for s in sentences) + " A made-up source [cite:Ghost2099Nothing]."
    claims = extract_claims(context)[key]
    support = {key: [SupportVerdict(claim=c, verdict=v, reason="") for c, v in zip(claims, verdicts)]}
    orchestrator = VerificationOrchestrator()
    with (
        patch.object(orchestrator.support_checker, "check", new=AsyncMock(return_value=support)),
        patch.object(orchestrator.existence_checker, "check", new=AsyncMock(
            return_value=VerificationResult(title=item.title, doi=item.doi, layer1_ok=True))),
    ):
        return await orchestrator.run([item], context)


@pytest.mark.asyncio
async def test_each_row_counts_judged_unclear_and_unjudged_claims():
    item = LiteratureItem(title="RAG", abstract=ABSTRACT, source="arxiv", authors=["Jane Smith"], year=2024)
    _, issues, _ = await _run(item, ["Recall improves", "Latency drops", "Cost falls"], [SUPPORTED, UNCLEAR])

    row = next(i for i in issues if i.title == "RAG")
    assert row.evidence == "abstract"
    assert row.claims.model_dump() == {"total": 3, "judged": 1, "unclear": 1, "unjudged": 1}


@pytest.mark.asyncio
async def test_a_paper_without_text_has_all_its_claims_unjudged():
    item = LiteratureItem(title="Title Only", source="crossref", doi="10.1/x", authors=["Jane Smith"], year=2024)
    _, issues, _ = await _run(item, ["Recall improves", "Latency drops"], [])

    row = next(i for i in issues if i.title == "Title Only")
    assert row.evidence == "none"
    assert row.claims.model_dump() == {"total": 2, "judged": 0, "unclear": 0, "unjudged": 2}


@pytest.mark.asyncio
async def test_a_hallucinated_key_has_no_claim_coverage():
    item = LiteratureItem(title="RAG", abstract=ABSTRACT, source="arxiv", authors=["Jane Smith"], year=2024)
    _, issues, _ = await _run(item, ["Recall improves"], [SUPPORTED])

    ghost = next(i for i in issues if i.layer == "layer0")
    assert ghost.claims is None and ghost.evidence == ""
