from unittest.mock import AsyncMock, patch

import pytest

from backend.literature.bibtex import bibtex_key
from backend.literature.schemas import LiteratureItem
from backend.verification.layer3_support import SUPPORTED, UNSUPPORTED, SupportVerdict
from backend.verification.orchestrator import VerificationOrchestrator, extract_claims
from backend.verification.schemas import CitationStatus, VerificationResult

ABSTRACT = "Deep learning neural network models for open-domain question answering. " * 5


def _lit(title: str, doi: str | None = None, year: int = 2024) -> LiteratureItem:
    return LiteratureItem(
        title=title,
        authors=["Jane Smith"],
        year=year,
        doi=doi,
        citation_count=100,
        source="arxiv",
        abstract=ABSTRACT,
    )


def _cite(item: LiteratureItem, sentence: str = "Recall improves markedly") -> str:
    return f"{sentence} [cite:{bibtex_key(item)}]."


def _no_support(orchestrator: VerificationOrchestrator):
    """Silence layer 3 so a test can isolate layer 0/1 behaviour."""
    return patch.object(orchestrator.support_checker, "check", new=AsyncMock(return_value={}))


# ---------------------------------------------------------------- layer 0 / layer 1

@pytest.mark.asyncio
async def test_cited_paper_that_passes_every_layer_is_counted_once():
    orchestrator = VerificationOrchestrator()
    item = _lit("Good Paper", doi="10.1/good")

    with (
        _no_support(orchestrator),
        patch.object(orchestrator.existence_checker, "check", new=AsyncMock(
            return_value=VerificationResult(title="Good Paper", doi="10.1/good", layer1_ok=True)
        )),
    ):
        verified, issues, summary = await orchestrator.run([item], _cite(item))

    assert len(verified) == 1
    assert summary.total == 1
    assert summary.passed == 1
    assert [i.action for i in issues] == ["kept"]
    assert summary.smart_pause_triggered is False


@pytest.mark.asyncio
async def test_uncited_paper_is_never_verified_but_stays_in_the_pool():
    orchestrator = VerificationOrchestrator()
    item = _lit("Unused Paper", doi="10.1/unused")
    existence = AsyncMock(return_value=VerificationResult(title="Unused Paper", layer1_ok=True))

    with _no_support(orchestrator), patch.object(orchestrator.existence_checker, "check", new=existence):
        verified, issues, summary = await orchestrator.run([item], "A body with no markers.")

    existence.assert_not_called()
    assert summary.total == 0
    assert verified == [item]
    assert issues == []


@pytest.mark.asyncio
async def test_dead_doi_removes_the_paper_from_the_bibliography():
    orchestrator = VerificationOrchestrator()
    item = _lit("Bad Paper", doi="10.9/bad")

    with (
        _no_support(orchestrator),
        patch.object(orchestrator.existence_checker, "check", new=AsyncMock(
            return_value=VerificationResult(
                title="Bad Paper", doi="10.9/bad",
                status=CitationStatus.REMOVED, layer1_ok=False,
                issues=["DOI not found"],
            )
        )),
    ):
        verified, issues, summary = await orchestrator.run([item], _cite(item))

    assert verified == []
    assert summary.removed == 1
    assert [i.action for i in issues] == ["removed"]
    assert issues[0].stage == "retrieval", "a dead DOI is a bad record from retrieval, not a writing slip"


@pytest.mark.asyncio
async def test_marker_with_no_matching_paper_is_flagged_as_hallucinated():
    orchestrator = VerificationOrchestrator()

    with _no_support(orchestrator):
        _, issues, summary = await orchestrator.run([], "A claim [cite:Ghost2024Nothing].")

    assert summary.removed == 1
    assert issues[0].layer == "layer0"
    assert "hallucinated" in issues[0].reason
    assert issues[0].stage == "writing"


@pytest.mark.asyncio
async def test_smart_pause_triggers_above_threshold():
    orchestrator = VerificationOrchestrator()
    items = [_lit(f"Paper{i} on retrieval", doi=f"10.1/{i}", year=2000 + i) for i in range(10)]
    context = " ".join(_cite(item) for item in items)

    good = VerificationResult(title="T", layer1_ok=True)
    bad = VerificationResult(
        title="T", status=CitationStatus.REMOVED, layer1_ok=False, issues=["dead doi"]
    )
    calls = [0]

    async def three_bad_then_good(**kwargs):
        calls[0] += 1
        return bad if calls[0] <= 3 else good

    with _no_support(orchestrator), patch.object(
        orchestrator.existence_checker, "check", side_effect=three_bad_then_good
    ):
        _, _, summary = await orchestrator.run(items, context)

    assert summary.total == 10
    assert summary.removed == 3
    assert summary.smart_pause_triggered is True


# ---------------------------------------------------------------- layer 3 integration

def _verdict(item: LiteratureItem, context: str, verdict: str) -> dict:
    claim = extract_claims(context)[bibtex_key(item)][0]
    return {bibtex_key(item): [SupportVerdict(claim=claim, verdict=verdict, reason="off topic")]}


@pytest.mark.asyncio
async def test_unsupported_claim_warns_even_when_the_doi_is_valid():
    orchestrator = VerificationOrchestrator()
    item = _lit("Real Paper", doi="10.1/real")
    context = _cite(item)

    with (
        patch.object(orchestrator.support_checker, "check",
                     new=AsyncMock(return_value=_verdict(item, context, UNSUPPORTED))),
        patch.object(orchestrator.existence_checker, "check", new=AsyncMock(
            return_value=VerificationResult(title="Real Paper", doi="10.1/real", layer1_ok=True)
        )),
    ):
        verified, issues, summary = await orchestrator.run([item], context)

    assert summary.warned == 1
    assert summary.passed == 0
    assert verified == [item], "an unsupported claim must not drop a real paper from the bibliography"
    assert [i.layer for i in issues] == ["layer3"]
    assert issues[0].stage == "writing"
    assert "does not support the claim" in issues[0].reason
    assert "Recall improves markedly" in issues[0].reason


@pytest.mark.asyncio
async def test_supported_claim_leaves_the_citation_passing():
    orchestrator = VerificationOrchestrator()
    item = _lit("Real Paper", doi="10.1/real")
    context = _cite(item)

    with (
        patch.object(orchestrator.support_checker, "check",
                     new=AsyncMock(return_value=_verdict(item, context, SUPPORTED))),
        patch.object(orchestrator.existence_checker, "check", new=AsyncMock(
            return_value=VerificationResult(title="Real Paper", doi="10.1/real", layer1_ok=True)
        )),
    ):
        _, issues, summary = await orchestrator.run([item], context)

    assert summary.passed == 1
    assert [i.action for i in issues] == ["kept"]


@pytest.mark.asyncio
async def test_a_dead_doi_and_an_unsupported_claim_still_count_as_one_citation():
    orchestrator = VerificationOrchestrator()
    item = _lit("Bad Paper", doi="10.9/bad")
    context = _cite(item)

    with (
        patch.object(orchestrator.support_checker, "check",
                     new=AsyncMock(return_value=_verdict(item, context, UNSUPPORTED))),
        patch.object(orchestrator.existence_checker, "check", new=AsyncMock(
            return_value=VerificationResult(
                title="Bad Paper", doi="10.9/bad",
                status=CitationStatus.REMOVED, layer1_ok=False, issues=["DOI not found"],
            )
        )),
    ):
        _, issues, summary = await orchestrator.run([item], context)

    assert (summary.passed, summary.warned, summary.removed) == (0, 0, 1)
    assert summary.total == 1
    assert [i.layer for i in issues] == ["layer1"]


@pytest.mark.asyncio
async def test_run_passes_language_through_to_the_support_checker():
    orchestrator = VerificationOrchestrator()
    item = _lit("Real Paper")
    support = AsyncMock(return_value={})

    with (
        patch.object(orchestrator.support_checker, "check", new=support),
        patch.object(orchestrator.existence_checker, "check", new=AsyncMock(
            return_value=VerificationResult(title="Real Paper", layer1_ok=True)
        )),
    ):
        await orchestrator.run([item], _cite(item), language="zh")

    assert support.await_args.args[2] == "zh"


# ---------------------------------------------------------------- one row per citation

def _verdicts(item: LiteratureItem, context: str, sentences: list[str]) -> dict:
    claim = extract_claims(context)[bibtex_key(item)][0]
    from dataclasses import replace
    return {bibtex_key(item): [
        SupportVerdict(claim=replace(claim, sentence=s), verdict=UNSUPPORTED, reason="")
        for s in sentences
    ]}


@pytest.mark.asyncio
async def test_several_unsupported_claims_still_produce_one_issue_row():
    """The UI counts issue rows as 'citations the body makes'; one paper must occupy one row."""
    orchestrator = VerificationOrchestrator()
    item = _lit("Real Paper", doi="10.1/real")
    context = _cite(item)
    sentences = ["First bogus claim.", "Second bogus claim.", "Third bogus claim.", "Fourth."]

    with (
        patch.object(orchestrator.support_checker, "check",
                     new=AsyncMock(return_value=_verdicts(item, context, sentences))),
        patch.object(orchestrator.existence_checker, "check", new=AsyncMock(
            return_value=VerificationResult(title="Real Paper", doi="10.1/real", layer1_ok=True)
        )),
    ):
        _, issues, summary = await orchestrator.run([item], context)

    assert len(issues) == 1
    assert summary.warned == 1
    assert "does not support 4 claims" in issues[0].reason
    assert "First bogus claim." in issues[0].reason
    assert "(+1 more)" in issues[0].reason, "claims beyond the first three must be counted, not dropped"


@pytest.mark.asyncio
async def test_title_mismatch_and_unsupported_claim_merge_into_one_row():
    orchestrator = VerificationOrchestrator()
    item = _lit("Real Paper", doi="10.1/real")
    context = _cite(item)

    with (
        patch.object(orchestrator.support_checker, "check",
                     new=AsyncMock(return_value=_verdict(item, context, UNSUPPORTED))),
        patch.object(orchestrator.existence_checker, "check", new=AsyncMock(
            return_value=VerificationResult(
                title="Real Paper", doi="10.1/real",
                status=CitationStatus.WARNED, layer1_ok=False,
                issues=["Title mismatch with CrossRef record"],
            )
        )),
    ):
        _, issues, summary = await orchestrator.run([item], context)

    assert len(issues) == 1
    assert summary.warned == 1
    assert issues[0].layer == "layer1+layer3"
    assert issues[0].stage == "retrieval+writing"
    assert "Title mismatch" in issues[0].reason
    assert "does not support the claim" in issues[0].reason


@pytest.mark.asyncio
async def test_issue_rows_match_cited_count_across_a_mixed_batch():
    orchestrator = VerificationOrchestrator()
    items = [_lit(f"Paper{i} on retrieval", doi=f"10.1/{i}", year=2000 + i) for i in range(5)]
    context = " ".join(_cite(item) for item in items)
    support = {
        bibtex_key(items[0]): [
            SupportVerdict(claim=c, verdict=UNSUPPORTED, reason="")
            for c in extract_claims(context)[bibtex_key(items[0])]
        ],
    }

    with (
        patch.object(orchestrator.support_checker, "check", new=AsyncMock(return_value=support)),
        patch.object(orchestrator.existence_checker, "check", new=AsyncMock(
            return_value=VerificationResult(title="T", layer1_ok=True)
        )),
    ):
        _, issues, summary = await orchestrator.run(items, context)

    assert len(issues) == summary.total == 5
    assert summary.passed + summary.warned + summary.removed == 5


def test_multi_key_marker_yields_every_key_not_one_hallucinated_blob():
    from backend.verification.orchestrator import extract_cite_keys

    text = "Equivariant models dominate [cite:Batzner2022E, cite:Batatia2022MACE]. Next."
    assert extract_cite_keys(text) == {"Batzner2022E", "Batatia2022MACE"}
    claims = extract_claims(text)
    assert set(claims) == {"Batzner2022E", "Batatia2022MACE"}
    assert claims["Batatia2022MACE"][0].sentence.startswith("Equivariant models dominate")


TABLE_SECTION = """Earlier prose names a baseline [cite:Base2019A].

| Study | Main contribution | Limitation relevant to this review |
|---|---|---|
| Allen et al. (2015) [cite:Allen2015How] | Reviews telecommuting research | Predates pandemic remote work |
| Šmite et al. [cite:Smite2022Work] | Synthesizes 22 company surveys | Tech-sector concentration |

Closing prose sentence cites a follow-up [cite:Close2020X].
"""


def test_table_row_becomes_one_claim_without_commentary_columns():
    claims = extract_claims(TABLE_SECTION)
    sentence = claims["Allen2015How"][0].sentence
    assert "Main contribution: Reviews telecommuting research" in sentence
    assert "[cite:Allen2015How]" in sentence
    assert "Predates pandemic" not in sentence  # the writer's limitation column is not the source's claim
    assert "Smite2022Work" not in sentence  # neighbouring rows stay out of this claim
    assert claims["Allen2015How"][0].context == ""


def test_table_rows_do_not_bleed_into_prose_claims():
    claims = extract_claims(TABLE_SECTION)
    assert claims["Base2019A"][0].sentence == "Earlier prose names a baseline [cite:Base2019A]."
    closing = claims["Close2020X"][0]
    assert closing.sentence == "Closing prose sentence cites a follow-up [cite:Close2020X]."
    assert "|" not in closing.context  # the table is not the sentence before it


def test_chinese_commentary_columns_are_dropped_too():
    text = (
        "|代表性研究|可见贡献|与本研究相关的局限|对机制的支持|\n"
        "|---|---|---|---|\n"
        "|张（2019）[cite:张2019]|揭示角色转换与多重压力|未检验深层身份焦虑|支持具身路径|\n"
    )
    sentence = extract_claims(text)["张2019"][0].sentence
    assert "可见贡献: 揭示角色转换与多重压力" in sentence
    assert "未检验深层身份焦虑" not in sentence
    assert "支持具身路径" not in sentence


def test_marker_inside_a_dropped_column_keeps_the_full_row():
    text = (
        "| Approach | Remaining limitation |\n|---|---|\n"
        "| Graph RAG | Alignment is unresolved [cite:Walk2025X] |\n"
    )
    sentence = extract_claims(text)["Walk2025X"][0].sentence
    assert "[cite:Walk2025X]" in sentence


@pytest.mark.asyncio
async def test_run_with_support_also_returns_the_layer3_verdicts():
    orchestrator = VerificationOrchestrator()
    item = _lit("Real Paper", doi="10.1/real")
    context = _cite(item)
    verdicts = _verdict(item, context, UNSUPPORTED)

    with (
        patch.object(orchestrator.support_checker, "check", new=AsyncMock(return_value=verdicts)),
        patch.object(orchestrator.existence_checker, "check", new=AsyncMock(
            return_value=VerificationResult(title="Real Paper", doi="10.1/real", layer1_ok=True)
        )),
    ):
        *_, support = await orchestrator.run_with_support([item], context)

    assert support == verdicts
