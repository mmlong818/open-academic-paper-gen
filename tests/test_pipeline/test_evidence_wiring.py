"""The evidence table is built beside the trends synthesis, exported on request, and reaches the
section writer only behind settings.evidence_table_in_writing."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.api.routes.export import export_evidence
from backend.core.config import settings
from backend.db.models import TaskStatus
from backend.literature.bibtex import bibtex_key
from backend.literature.schemas import LiteratureItem
from backend.pipeline.states import GateStatus, PaperState, Phase
from backend.writing.section_writer import SectionWriter

ROW = {"key": "Smith2024G", "title": "GraphMol", "year": 2024, "task": "property prediction",
       "method": "message passing", "data": "QM9", "metric": "", "finding": "", "limitation": "", "dropped": 0}


@pytest.mark.asyncio
async def test_trends_saves_the_evidence_table_with_the_synthesis():
    from backend.pipeline.graph import node_trends

    state = PaperState(task_id="e1", topic="t", language="en", collab_mode="full_auto",
                       current_phase=Phase.TRENDS, gate_status=GateStatus.SKIPPED,
                       literature=[{"title": "GraphMol", "source": "arxiv", "abstract": "x"}])
    with (
        patch("backend.pipeline.graph.SynthesisAgent") as synthesis,
        patch("backend.pipeline.graph.EvidenceExtractor") as extractor,
    ):
        synthesis.return_value.run = AsyncMock(return_value="synth")
        extractor.return_value.run = AsyncMock(return_value=[ROW])
        result = await node_trends(state)

    assert result["synthesis"] == "synth"
    assert result["evidence_table"] == [ROW]


def _writer_llm() -> MagicMock:
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content="text"))
    return llm


@pytest.mark.asyncio
async def test_the_writer_sees_a_paper_row_only_when_given_the_table():
    item = LiteratureItem(title="GraphMol", source="arxiv", abstract="Message passing on QM9.")
    row = {**ROW, "key": bibtex_key(item)}
    outline = [{"title": "Methods", "summary": "graph models"}]

    llm = _writer_llm()
    await SectionWriter(llm=llm).run(outline=outline, synthesis="s", literature=[item], language="en",
                                     evidence={row["key"]: row})
    assert "Evidence row: Task: property prediction; Method: message passing; Data: QM9" in llm.ainvoke.call_args.args[0]

    llm = _writer_llm()
    await SectionWriter(llm=llm).run(outline=outline, synthesis="s", literature=[item], language="en")
    assert "Evidence row" not in llm.ainvoke.call_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", [False, True])
async def test_node_writing_passes_the_table_only_behind_the_flag(flag):
    from backend.pipeline.graph import node_writing

    state = PaperState(task_id="e2", topic="t", language="en", collab_mode="full_auto",
                       current_phase=Phase.WRITING, gate_status=GateStatus.SKIPPED,
                       outline=[{"title": "Intro", "summary": "s"}], evidence_table=[ROW])
    with (
        patch.object(settings, "evidence_table_in_writing", flag),
        patch("backend.pipeline.graph.SectionWriter") as writer,
    ):
        writer.return_value.run = AsyncMock(return_value={"Intro": "text"})
        await node_writing(state)

    passed = writer.return_value.run.call_args.kwargs["evidence"]
    assert passed == ({"Smith2024G": ROW} if flag else None)


async def _export(fmt, snapshot):
    task = SimpleNamespace(topic="t", language="zh", status=TaskStatus.running, state_snapshot=snapshot)
    with patch("backend.api.routes.export.get_task", AsyncMock(return_value=task)):
        return await export_evidence(task_id="00000000-0000-0000-0000-000000000001", fmt=fmt, session=None)


@pytest.mark.asyncio
async def test_the_table_exports_before_the_task_completes():
    assert (await _export("markdown", {"evidence_table": [ROW]})).startswith("| 文献 | 年份 | 任务")
    assert (await _export("csv", {"evidence_table": [ROW]})).startswith("文献,年份,任务")


@pytest.mark.asyncio
async def test_no_table_or_an_unknown_format_is_an_error():
    with pytest.raises(HTTPException) as err:
        await _export("markdown", {})
    assert err.value.status_code == 404
    with pytest.raises(HTTPException) as err:
        await _export("xlsx", {"evidence_table": [ROW]})
    assert err.value.status_code == 422


@pytest.mark.asyncio
async def test_the_angle_node_saves_a_novelty_diagnosis_beside_the_angle():
    from backend.pipeline.graph import node_angle

    angle = {"writing_angle": "w", "contribution": "c", "gap": "g"}
    diagnosis = {"levels": {}, "pseudo": [], "closest": [], "dropped_keys": 0, "objection": "o"}
    state = PaperState(task_id="n1", topic="t", language="en", collab_mode="full_auto",
                       current_phase=Phase.ANGLE, gate_status=GateStatus.SKIPPED, synthesis="s",
                       literature=[{"title": "P", "source": "arxiv", "abstract": "a"}])
    with (
        patch("backend.pipeline.graph.AngleAgent") as agent,
        patch("backend.pipeline.graph.NoveltyDiagnoser") as diagnoser,
    ):
        agent.return_value.run = AsyncMock(return_value=angle)
        diagnoser.return_value.run = AsyncMock(return_value=diagnosis)
        result = await node_angle(state)

    assert result["angle"] == angle, "the diagnosis never rewrites the angle"
    assert result["novelty"] == diagnosis
