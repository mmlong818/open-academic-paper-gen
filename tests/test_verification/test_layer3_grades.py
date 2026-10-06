"""Finer layer-3 grades and the evidence-grade note.

misaligned — the source's finding runs the other way — warns like unsupported. partial — the core
holds but a part is overstated — is a note on a passing row, not a warning. An unclear verdict on
abstract-only evidence says the full text is needed; it never changes a verdict.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core.config import settings
from backend.literature.bibtex import bibtex_key
from backend.literature.schemas import LiteratureItem
from backend.pipeline.verify_and_revise import VerificationPass, collect_problems
from backend.verification.layer3_support import (
    MISALIGNED,
    PARTIAL,
    UNCLEAR,
    Claim,
    SupportChecker,
    SupportVerdict,
    _parse_verdicts,
)
from backend.verification.orchestrator import VerificationOrchestrator, extract_claims
from backend.verification.schemas import VerificationResult, VerificationSummary
from backend.writing.prompts import build_support_prompt

TEXT = "Graph networks predict molecular properties from 2D structure alone. " * 6


def _item(**extra) -> LiteratureItem:
    return LiteratureItem(title="GNN Paper", authors=["Jane Smith"], year=2024, doi="10.1/gnn",
                          source="arxiv", abstract=TEXT, **extra)


def test_parser_accepts_the_finer_grades():
    raw = '[{"verdict": "partial", "reason": "a"}, {"verdict": "Misaligned", "reason": "b"}]'
    assert _parse_verdicts(raw, 2) == [(PARTIAL, "a"), (MISALIGNED, "b")]


@pytest.mark.parametrize("language", ["en", "zh"])
def test_fine_prompt_offers_partial_and_misaligned_only_when_asked(language):
    args = dict(title="T", evidence="E", claims=[{"sentence": "S", "context": ""}], language=language, key="K")
    fine = build_support_prompt(**args, fine=True)
    plain = build_support_prompt(**args)
    assert '"partial"' in fine and '"misaligned"' in fine
    assert '"partial"' not in plain and '"misaligned"' not in plain


@pytest.mark.asyncio
async def test_checker_asks_for_fine_grades_when_the_setting_is_on():
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content='[{"verdict": "partial", "reason": "r"}]'))
    claims = {"K": [Claim(key="K", sentence="S [cite:K].")]}
    with patch.object(settings, "l3_fine_grades", True):
        result = await SupportChecker(llm=llm).check(claims, {"K": _item()})
    assert '"misaligned"' in llm.ainvoke.call_args.args[0]
    assert result["K"][0].verdict == PARTIAL


async def _run(item: LiteratureItem, verdict: str):
    orchestrator = VerificationOrchestrator()
    context = f"Accuracy needs 3D inputs [cite:{bibtex_key(item)}]."
    claim = extract_claims(context)[bibtex_key(item)][0]
    support = {bibtex_key(item): [SupportVerdict(claim=claim, verdict=verdict, reason="the paper says the reverse")]}
    with (
        patch.object(orchestrator.support_checker, "check", new=AsyncMock(return_value=support)),
        patch.object(orchestrator.existence_checker, "check", new=AsyncMock(
            return_value=VerificationResult(title=item.title, doi=item.doi, layer1_ok=True))),
    ):
        _, issues, summary = await orchestrator.run([item], context)
    return issues[0], summary


@pytest.mark.asyncio
async def test_a_misaligned_claim_warns_like_an_unsupported_one():
    issue, summary = await _run(_item(), MISALIGNED)
    assert summary.warned == 1 and issue.layer == "layer3"
    assert "opposite" in issue.reason and "Accuracy needs 3D inputs" in issue.reason


@pytest.mark.asyncio
async def test_a_partly_supported_claim_passes_with_a_note():
    issue, summary = await _run(_item(), PARTIAL)
    assert summary.passed == 1 and issue.action == "kept"
    assert "部分支撑" in issue.reason and "Accuracy needs 3D inputs" in issue.reason


@pytest.mark.asyncio
async def test_unclear_on_the_abstract_alone_says_the_full_text_is_needed():
    issue, summary = await _run(_item(), UNCLEAR)
    assert summary.passed == 1 and issue.action == "kept"
    assert "需全文" in issue.reason


@pytest.mark.asyncio
async def test_unclear_on_the_full_text_does_not_ask_for_it():
    issue, _ = await _run(_item(full_text=TEXT * 5), UNCLEAR)
    assert "需全文" not in issue.reason


def test_misaligned_claims_are_revised_partial_ones_are_not():
    sections = {"Intro": "Accuracy needs 3D inputs [cite:K]. Graphs help [cite:K]."}
    verdicts = [
        SupportVerdict(Claim("K", "Accuracy needs 3D inputs [cite:K]."), MISALIGNED, "reverse"),
        SupportVerdict(Claim("K", "Graphs help [cite:K]."), PARTIAL, "overstated"),
    ]
    vpass = VerificationPass([], [], VerificationSummary(total=1, passed=1, warned=0, removed=0),
                             {"K": verdicts}, [])
    assert [p.sentence for p in collect_problems(sections, vpass)] == ["Accuracy needs 3D inputs [cite:K]."]
