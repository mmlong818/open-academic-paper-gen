import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db
from backend.db.models import TaskStatus
from backend.export.bib_export import export_bibtex, export_ris
from backend.export.evidence_export import to_csv, to_markdown
from backend.export.latex_exporter import LatexExporter
from backend.export.markdown_exporter import MarkdownExporter
from backend.services.task_service import get_task

router = APIRouter(prefix="/api/tasks", tags=["export"])


def _task_to_state(task) -> dict:
    snapshot = task.state_snapshot or {}
    return {
        "topic": task.topic,
        "language": task.language,
        "synthesis": snapshot.get("synthesis", ""),
        "outline": snapshot.get("outline", []),
        "sections": snapshot.get("sections", {}),
        "verified_citations": snapshot.get("verified_citations", []),
        "literature": snapshot.get("literature", []),
    }


def _assert_completed(task) -> None:
    if task.status != TaskStatus.completed:
        raise HTTPException(
            status_code=409,
            detail=f"Task is not completed yet (current status: {task.status.value})",
        )


@router.get("/{task_id}/export/latex", response_class=PlainTextResponse)
async def export_latex(
    task_id: uuid.UUID,
    style: str | None = None,
    session: AsyncSession = Depends(db),
) -> str:
    """?style=gbt7714 | apa7 | numeric; by default GB/T 7714 for Chinese papers, APA 7 for English."""
    task = await get_task(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    _assert_completed(task)
    state = _task_to_state(task)
    try:
        return LatexExporter().export(state, style=style)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{task_id}/export/markdown", response_class=PlainTextResponse)
async def export_markdown(
    task_id: uuid.UUID,
    style: str | None = None,
    session: AsyncSession = Depends(db),
) -> str:
    """?style=gbt7714 | apa7 | numeric; by default GB/T 7714 for Chinese papers, APA 7 for English."""
    task = await get_task(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    _assert_completed(task)
    state = _task_to_state(task)
    try:
        return MarkdownExporter().export(state, style=style)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{task_id}/export/evidence", response_class=PlainTextResponse)
async def export_evidence(
    task_id: uuid.UUID,
    fmt: str = "markdown",
    session: AsyncSession = Depends(db),
) -> str:
    """The evidence table (?fmt=markdown | csv), available once the trends phase has built it."""
    render = {"markdown": to_markdown, "csv": to_csv}.get(fmt)
    if render is None:
        raise HTTPException(status_code=422, detail=f"Unknown evidence format {fmt!r}")
    task = await get_task(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    rows = (task.state_snapshot or {}).get("evidence_table")
    if not rows:
        raise HTTPException(status_code=404, detail="This task has no evidence table")
    return render(rows, task.language)


@router.get("/{task_id}/export/{fmt}", response_class=PlainTextResponse)
async def export_references(
    task_id: uuid.UUID,
    fmt: str,
    session: AsyncSession = Depends(db),
) -> str:
    """The cited references as RIS or BibTeX, for Zotero, EndNote and LaTeX."""
    exporters = {"ris": export_ris, "bibtex": export_bibtex}
    if fmt not in exporters:
        raise HTTPException(status_code=404, detail=f"Unknown export format {fmt!r}")
    task = await get_task(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    _assert_completed(task)
    return exporters[fmt](_task_to_state(task))
