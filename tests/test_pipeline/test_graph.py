import pytest

from backend.pipeline.graph import _should_gate, paper_graph
from backend.pipeline.states import GateStatus, PaperState, Phase


def test_should_gate_full_auto_skips():
    state = PaperState(
        task_id="t", topic="x", collab_mode="full_auto", gate_status=GateStatus.PENDING
    )
    assert _should_gate(state) == "continue"


def test_should_gate_key_gates_on_scoping():
    state = PaperState(
        task_id="t",
        topic="x",
        collab_mode="key_gates",
        current_phase=Phase.SCOPING,
        gate_status=GateStatus.PENDING,
    )
    assert _should_gate(state) == "wait_gate"


def test_should_gate_approved_continues():
    state = PaperState(
        task_id="t",
        topic="x",
        collab_mode="key_gates",
        current_phase=Phase.SCOPING,
        gate_status=GateStatus.APPROVED,
    )
    assert _should_gate(state) == "continue"


def test_graph_compiles():
    assert paper_graph is not None


async def test_graph_full_auto_runs_to_end():
    from unittest.mock import AsyncMock, patch
    from backend.verification.schemas import VerificationSummary

    state = PaperState(task_id="test-id", topic="测试", collab_mode="full_auto")

    with (
        patch("backend.pipeline.graph.ScopingAgent") as MockScoping,
        patch("backend.pipeline.graph.LiteratureCrew") as MockCrew,
        patch("backend.pipeline.graph.SynthesisAgent") as MockSynthesis,
        patch("backend.pipeline.graph.OutlineAgent") as MockOutline,
        patch("backend.pipeline.graph.SectionWriter") as MockWriter,
        patch("backend.pipeline.verify_and_revise.VerificationOrchestrator") as MockOrch,
    ):
        MockScoping.return_value.run = AsyncMock(return_value={"research_questions": ["RQ1"], "keywords": ["测试"]})
        MockCrew.return_value.run = AsyncMock(return_value=[])
        MockSynthesis.return_value.run = AsyncMock(return_value="综合文本")
        MockOutline.return_value.run = AsyncMock(return_value=[{"title": "引言", "summary": "背景"}])
        MockWriter.return_value.run = AsyncMock(return_value={"引言": "内容"})
        summary = VerificationSummary(total=0, passed=0, warned=0, removed=0)
        MockOrch.return_value.run_with_support = AsyncMock(return_value=([], [], summary, {}))

        result = await paper_graph.ainvoke(state)

    assert result["current_phase"] == Phase.EXPORT


async def test_graph_key_gates_stops_at_scoping():
    """key_gates 模式下，流水線應在 SCOPING 阶段暂停等待门控"""
    state = PaperState(task_id="test-gate", topic="測試門控", collab_mode="key_gates")
    result = await paper_graph.ainvoke(state)
    # 應在 SCOPING 阶段暂停（gate_status=PENDING，current_phase=SCOPING）
    assert result["gate_status"] == GateStatus.PENDING
    assert result["current_phase"] == Phase.SCOPING


# 追加到 tests/test_pipeline/test_graph.py 末尾

from unittest.mock import AsyncMock, patch
from backend.literature.schemas import LiteratureItem


@pytest.mark.asyncio
async def test_node_literature_calls_crew_and_populates_state():
    """full_auto 模式下，node_literature 应调用 LiteratureCrew 并写入 literature。"""
    from backend.pipeline.graph import node_literature
    from backend.pipeline.states import PaperState, Phase, GateStatus

    mock_items = [
        LiteratureItem(title="Found Paper", source="arxiv", citation_count=100, quality_score=55.0)
    ]

    state = PaperState(
        task_id="t1",
        topic="deep learning",
        language="en",
        collab_mode="full_auto",
        current_phase=Phase.LITERATURE,
        gate_status=GateStatus.SKIPPED,
        keywords=["deep learning"],
    )

    with patch("backend.pipeline.graph.LiteratureCrew") as MockCrew:
        mock_crew_instance = AsyncMock()
        mock_crew_instance.run.return_value = mock_items
        MockCrew.return_value = mock_crew_instance

        result = await node_literature(state)

    assert result["current_phase"] == Phase.CLEANING
    assert len(result["literature"]) == 1
    assert result["literature"][0]["title"] == "Found Paper"


@pytest.mark.asyncio
async def test_node_verification_populates_verified_citations():
    from backend.pipeline.graph import node_verification
    from backend.pipeline.states import PaperState, Phase, GateStatus
    from backend.verification.schemas import VerificationSummary
    from unittest.mock import AsyncMock, patch

    state = PaperState(
        task_id="v1",
        topic="deep learning",
        language="en",
        collab_mode="full_auto",
        current_phase=Phase.VERIFICATION,
        gate_status=GateStatus.SKIPPED,
        literature=[
            {
                "title": "Good Paper",
                "source": "arxiv",
                "doi": "10.1/good",
                "citation_count": 100,
                "abstract": "deep learning",
                "quality_score": 60.0,
            }
        ],
        synthesis="deep learning overview",
    )

    mock_summary = VerificationSummary(total=1, passed=1, warned=0, removed=0)

    with patch("backend.pipeline.verify_and_revise.VerificationOrchestrator") as MockOrch:
        mock_orch = AsyncMock()
        mock_orch.run_with_support.return_value = ([], [], mock_summary, {})
        MockOrch.return_value = mock_orch

        result = await node_verification(state)

    assert result["current_phase"] == Phase.EXPORT
    assert "verified_citations" in result
    assert "citation_issues" in result
    assert result["smart_pause"] is False


@pytest.mark.asyncio
async def test_node_verification_smart_pause_when_high_failure():
    from backend.pipeline.graph import node_verification
    from backend.pipeline.states import PaperState, Phase, GateStatus
    from backend.verification.schemas import VerificationSummary
    from unittest.mock import AsyncMock, patch

    state = PaperState(
        task_id="v2",
        topic="test",
        language="en",
        collab_mode="full_auto",
        current_phase=Phase.VERIFICATION,
        gate_status=GateStatus.SKIPPED,
        literature=[],
    )

    mock_summary = VerificationSummary(total=10, passed=6, warned=1, removed=3)

    with patch("backend.pipeline.verify_and_revise.VerificationOrchestrator") as MockOrch:
        mock_orch = AsyncMock()
        mock_orch.run_with_support.return_value = ([], [], mock_summary, {})
        MockOrch.return_value = mock_orch

        result = await node_verification(state)

    assert result["smart_pause"] is True


@pytest.mark.asyncio
async def test_node_scoping_calls_scoping_agent():
    from backend.pipeline.graph import node_scoping
    from backend.pipeline.states import PaperState, Phase, GateStatus
    from unittest.mock import AsyncMock, patch

    state = PaperState(
        task_id="s1", topic="深度学习", language="zh", collab_mode="full_auto",
        current_phase=Phase.SCOPING, gate_status=GateStatus.SKIPPED,
    )

    with patch("backend.pipeline.graph.ScopingAgent") as MockAgent:
        mock_agent = MockAgent.return_value
        mock_agent.run = AsyncMock(return_value={
            "research_questions": ["RQ1", "RQ2"],
            "keywords": ["深度学习", "神经网络"],
        })
        result = await node_scoping(state)

    assert result["current_phase"] == Phase.LITERATURE
    assert result["research_questions"] == ["RQ1", "RQ2"]
    assert result["keywords"] == ["深度学习", "神经网络"]


@pytest.mark.asyncio
async def test_node_trends_calls_synthesis_agent():
    from backend.pipeline.graph import node_trends
    from backend.pipeline.states import PaperState, Phase, GateStatus
    from unittest.mock import AsyncMock, patch

    state = PaperState(
        task_id="s2", topic="深度学习", language="zh", collab_mode="full_auto",
        current_phase=Phase.TRENDS, gate_status=GateStatus.SKIPPED,
        literature=[{"title": "Paper A", "source": "arxiv", "abstract": "test"}],
    )

    with patch("backend.pipeline.graph.SynthesisAgent") as MockAgent:
        mock_agent = MockAgent.return_value
        mock_agent.run = AsyncMock(return_value="综合分析文本")
        result = await node_trends(state)

    assert result["current_phase"] == Phase.ANGLE
    assert result["synthesis"] == "综合分析文本"


@pytest.mark.asyncio
async def test_node_outline_calls_outline_agent():
    from backend.pipeline.graph import node_outline
    from backend.pipeline.states import PaperState, Phase, GateStatus
    from unittest.mock import AsyncMock, patch

    state = PaperState(
        task_id="s3", topic="深度学习", language="zh", collab_mode="full_auto",
        current_phase=Phase.OUTLINE, gate_status=GateStatus.SKIPPED,
        synthesis="综合分析", research_questions=["RQ1"],
    )

    mock_outline = [{"title": "引言", "summary": "背景介绍"}]

    with patch("backend.pipeline.graph.OutlineAgent") as MockAgent:
        mock_agent = MockAgent.return_value
        mock_agent.run = AsyncMock(return_value=mock_outline)
        result = await node_outline(state)

    assert result["current_phase"] == Phase.WRITING
    assert result["outline"] == mock_outline


@pytest.mark.asyncio
async def test_node_writing_calls_section_writer():
    from backend.pipeline.graph import node_writing
    from backend.pipeline.states import PaperState, Phase, GateStatus
    from unittest.mock import AsyncMock, patch

    state = PaperState(
        task_id="s4", topic="深度学习", language="zh", collab_mode="full_auto",
        current_phase=Phase.WRITING, gate_status=GateStatus.SKIPPED,
        outline=[{"title": "引言", "summary": "背景"}],
        synthesis="综合",
        literature=[],
    )

    with patch("backend.pipeline.graph.SectionWriter") as MockWriter:
        mock_writer = MockWriter.return_value
        mock_writer.run = AsyncMock(return_value={"引言": "引言内容文本"})
        result = await node_writing(state)

    assert result["current_phase"] == Phase.VERIFICATION
    assert result["sections"] == {"引言": "引言内容文本"}


@pytest.mark.asyncio
async def test_node_export_generates_latex_and_markdown():
    from backend.pipeline.graph import node_export
    from backend.pipeline.states import PaperState, Phase, GateStatus

    state = PaperState(
        task_id="e1",
        topic="深度学习",
        language="zh",
        collab_mode="full_auto",
        current_phase=Phase.EXPORT,
        gate_status=GateStatus.SKIPPED,
        outline=[{"title": "引言", "summary": "背景"}],
        sections={"引言": "引言内容"},
        verified_citations=[],
    )

    result = await node_export(state)

    assert result["current_phase"] == Phase.EXPORT
    assert result["gate_status"] == GateStatus.APPROVED
    assert "\\documentclass" in result["latex_content"]
    assert result["markdown_content"].startswith("# 深度学习")


@pytest.mark.asyncio
async def test_node_verification_reports_uncited_claims_separately():
    """Uncited claims are not citations: they must not become citation_issues rows."""
    from unittest.mock import AsyncMock, patch

    from backend.pipeline.graph import node_verification
    from backend.pipeline.states import GateStatus, PaperState, Phase
    from backend.verification.schemas import VerificationSummary
    from backend.verification.uncited import UncitedClaim

    state = PaperState(
        task_id="v3", topic="t", language="en", collab_mode="full_auto",
        current_phase=Phase.VERIFICATION, gate_status=GateStatus.SKIPPED,
        sections={"Results": "Output fell 12% in mandated firms."},
    )
    claim = UncitedClaim("Results", "Output fell 12% in mandated firms.", "specific statistic")
    no_op = AsyncMock(return_value=None)
    with (
        patch("backend.pipeline.verify_and_revise.VerificationOrchestrator") as MockOrch,
        patch("backend.pipeline.verify_and_revise.UncitedClaimChecker") as MockUncited,
        patch("backend.pipeline.verify_and_revise.settings.revise_flagged_claims", False),
        patch("backend.pipeline.graph._save_phase_result", no_op),
        patch("backend.pipeline.graph.publish_progress", no_op),
    ):
        MockOrch.return_value.run_with_support = AsyncMock(
            return_value=([], [], VerificationSummary(total=0, passed=0, warned=0, removed=0), {})
        )
        MockUncited.return_value.check = AsyncMock(return_value=[claim])
        result = await node_verification(state)

    assert result["uncited_claims"] == [claim.as_dict()]
    assert result["citation_issues"] == []


def _revision_fixture(collab_mode: str):
    from backend.pipeline.states import GateStatus, PaperState, Phase

    before = "Output fell 12% in mandated firms."
    state = PaperState(
        task_id="rv", topic="t", language="en", collab_mode=collab_mode,
        current_phase=Phase.VERIFICATION, gate_status=GateStatus.SKIPPED,
        sections={"Results": f"{before}\n\nOther paragraph."},
        outline=[{"title": "Results", "summary": ""}],
    )
    return state, before


async def _run_with_revision(collab_mode: str, kind: str = "unsupported"):
    from unittest.mock import AsyncMock, patch

    from backend.pipeline.graph import node_verification
    from backend.verification.layer3_support import UNSUPPORTED, Claim, SupportVerdict
    from backend.verification.schemas import VerificationSummary
    from backend.verification.uncited import UncitedClaim
    from backend.writing.revision import Revision

    state, before = _revision_fixture(collab_mode)
    after = "Output fell 12% in mandated firms [cite:K2022Remote]."
    summary = VerificationSummary(total=0, passed=0, warned=0, removed=0)
    clean = ([], [], summary, {})
    unsupported = {"K2022Remote": [SupportVerdict(Claim("K2022Remote", before), UNSUPPORTED, "overstated")]}
    first = ([], [], summary, unsupported) if kind == "unsupported" else clean
    uncited = [UncitedClaim("Results", before, "specific statistic")] if kind == "uncited" else []

    async def propose(sections, problems, *args):
        return [
            Revision(id=1, section=p.section, before=before, after=after,
                     problems=[{"sentence": p.sentence, "kind": p.kind, "reason": p.reason}])
            for p in problems
        ]

    no_op = AsyncMock(return_value=None)
    with (
        patch("backend.pipeline.verify_and_revise.VerificationOrchestrator") as MockOrch,
        patch("backend.pipeline.verify_and_revise.UncitedClaimChecker") as MockUncited,
        patch("backend.pipeline.verify_and_revise.RevisionAgent") as MockAgent,
        patch("backend.pipeline.graph._save_phase_result", no_op),
        patch("backend.pipeline.graph.publish_progress", no_op),
    ):
        MockOrch.return_value.run_with_support = AsyncMock(side_effect=[first, clean])
        MockUncited.return_value.check = AsyncMock(side_effect=[uncited, []])
        MockAgent.return_value.propose = AsyncMock(side_effect=propose)
        result = await node_verification(state)
    return result, MockOrch.return_value.run_with_support, before, after


@pytest.mark.asyncio
async def test_full_auto_applies_unsupported_fixes_and_reverifies():
    result, run, before, after = await _run_with_revision("full_auto", "unsupported")
    assert result["sections"]["Results"] == f"{after}\n\nOther paragraph."
    assert result["revisions"][0]["status"] == "applied"
    assert result["revisions"][0]["resolved"] is True  # the second pass no longer flags it
    assert run.await_count == 2


@pytest.mark.asyncio
async def test_full_auto_only_proposes_fixes_for_uncited_claims():
    """At ~0.4 precision the uncited check flags sound prose; rewriting it unasked does harm."""
    result, run, before, after = await _run_with_revision("full_auto", "uncited")
    assert result["sections"]["Results"].startswith(before)
    assert result["revisions"][0]["status"] == "proposed"
    assert run.await_count == 1


@pytest.mark.asyncio
async def test_key_gates_only_proposes_and_leaves_the_text_alone():
    result, run, before, after = await _run_with_revision("key_gates", "unsupported")
    assert result["sections"]["Results"].startswith(before)
    assert result["revisions"][0]["status"] == "proposed"
    assert run.await_count == 1


@pytest.mark.asyncio
async def test_node_prisma_reports_without_removing_any_paper():
    from unittest.mock import AsyncMock, patch

    from backend.pipeline.graph import node_prisma
    from backend.pipeline.states import PaperState

    literature = [{"title": f"Paper {i}", "source": "arxiv"} for i in range(5)]
    state = PaperState(
        task_id="p1", topic="t", language="en", collab_mode="full_auto",
        literature=literature,
        cleaning_report={"total_before": 7, "total_after": 5, "removed_dup": 1, "excluded_by_llm": 1},
    )
    with patch("backend.pipeline.graph.publish_progress", AsyncMock(return_value=None)):
        result = await node_prisma(state)
    assert "literature" not in result
    assert "Studies included: 5" in result["prisma_flow"]


@pytest.mark.asyncio
async def test_node_cleaning_adds_screened_citation_chain_papers_and_reports_them():
    from unittest.mock import AsyncMock, patch

    from backend.literature.schemas import LiteratureItem
    from backend.pipeline.graph import node_cleaning

    searched = {"title": "Searched paper", "source": "arxiv", "abstract": "a" * 80}
    chained = LiteratureItem(title="Chained classic", source="semantic_scholar", abstract="b" * 80)
    state = PaperState(task_id="c1", topic="t", language="en", collab_mode="full_auto",
                       keywords=["k"], literature=[searched])
    no_op = AsyncMock(return_value=None)
    with (
        patch("backend.pipeline.graph.PaperContentFetcher") as Fetcher,
        patch("backend.pipeline.graph.LiteratureScreener") as Screener,
        patch("backend.pipeline.graph.chain_and_screen",
              AsyncMock(return_value=([chained], [{"title": "Chained classic"}], 3))) as chain,
        patch("backend.pipeline.graph._save_phase_result", no_op),
        patch("backend.pipeline.graph.publish_progress", no_op),
    ):
        Fetcher.return_value.run = AsyncMock(side_effect=lambda items: items)
        Screener.return_value.run = AsyncMock(side_effect=lambda topic, items, language: (items, []))
        result = await node_cleaning(state)

    assert [lit["title"] for lit in result["literature"]] == ["Searched paper", "Chained classic"]
    report = result["cleaning_report"]
    assert report["chained_candidates"] == 3 and report["chained_included"] == 1
    assert report["excluded_by_llm"] == 2  # the two chained candidates screening turned away
    assert chain.await_args.args[2] == ["t", "k"]  # topic and keywords steer the ranking


@pytest.mark.asyncio
async def test_node_verification_attaches_the_review_without_touching_the_text():
    from unittest.mock import AsyncMock, MagicMock, patch

    from backend.pipeline.graph import node_verification
    from backend.verification.schemas import VerificationSummary

    state = PaperState(task_id="rv2", topic="t", language="en", collab_mode="full_auto",
                       current_phase=Phase.VERIFICATION, gate_status=GateStatus.SKIPPED,
                       sections={"Results": "Output fell 12%."})
    review = {"comments": [{"section": "Results", "quote": "Output fell 12%.", "issue": "i",
                            "severity": "major", "suggestion": "s"}], "limitations": ["l"], "dropped_unquoted": 0}
    reviewer = MagicMock()
    reviewer.return_value.review = AsyncMock(return_value=review)
    no_op = AsyncMock(return_value=None)
    with (
        patch("backend.pipeline.verify_and_revise.VerificationOrchestrator") as MockOrch,
        patch("backend.pipeline.verify_and_revise.UncitedClaimChecker") as MockUncited,
        patch("backend.pipeline.graph.ReviewAgent", reviewer),
        patch("backend.pipeline.graph.ReviewPanel", reviewer),
        patch("backend.pipeline.graph._save_phase_result", no_op),
        patch("backend.pipeline.graph.publish_progress", no_op),
    ):
        MockOrch.return_value.run_with_support = AsyncMock(
            return_value=([], [], VerificationSummary(total=0, passed=0, warned=0, removed=0), {}))
        MockUncited.return_value.check = AsyncMock(return_value=[])
        result = await node_verification(state)

    assert result["review"] == review
    assert result["sections"] == state.sections  # suggestions only


@pytest.mark.asyncio
async def test_review_outline_is_shaped_by_the_citation_taxonomy():
    from unittest.mock import AsyncMock, MagicMock, patch

    from backend.pipeline.graph import node_outline

    taxonomy = [{"id": 1, "keys": ["K1", "K2"], "titles": ["T1"], "terms": ["graph"]},
                {"id": 2, "keys": ["K3"], "titles": ["T3"], "terms": ["text"]}]
    agent = MagicMock()
    agent.return_value.run = AsyncMock(return_value=[
        {"title": "Intro", "summary": "s"}, {"title": "Graph methods", "summary": "s", "clusters": [1, 2]},
    ])
    no_op = AsyncMock(return_value=None)
    for paper_type, expect_graph in (("review", True), ("general", False)):
        state = PaperState(task_id="o1", topic="t", language="en", collab_mode="full_auto",
                           paper_type=paper_type, literature=[{"title": "P", "source": "arxiv"}])
        with (
            patch("backend.pipeline.graph.OutlineAgent", agent),
            patch("backend.pipeline.graph.build_taxonomy", AsyncMock(return_value=taxonomy)) as build,
            patch("backend.pipeline.graph.settings.citation_graph_outline", True),
            patch("backend.pipeline.graph._save_phase_result", no_op),
            patch("backend.pipeline.graph.publish_progress", no_op),
        ):
            result = await node_outline(state)
        assert build.await_count == (1 if expect_graph else 0)
        if expect_graph:
            assert result["taxonomy"] == taxonomy
            assert result["outline"][1]["cluster_keys"] == ["K1", "K2", "K3"]
            assert "graph" in agent.return_value.run.await_args.kwargs["taxonomy_block"]
