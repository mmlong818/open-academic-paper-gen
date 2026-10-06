import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes as _sa_attrs

from backend.api.deps import db
from backend.core.model_router import get_llm
from backend.db.models import CollabMode, PaperTask, PaperType, SourceMix, TaskStatus
from backend.pipeline.runner import resume_pipeline, run_pipeline
from backend.services.task_service import (
    create_task,
    get_task,
    list_tasks,
    soft_delete_task,
    star_task,
    update_task_snapshot,
    update_task_status,
)
from backend.literature.schemas import LiteratureItem
from backend.writing.angle import AngleAgent
from backend.writing.prisma import review_process_facts
from backend.writing.section_writer import SectionWriter, section_selector_llm

logger = logging.getLogger(__name__)
router = APIRouter()


class CreateTaskRequest(BaseModel):
    topic: str
    language: str = "zh"
    collab_mode: CollabMode = CollabMode.key_gates
    paper_type: PaperType = PaperType.general
    source_mix: SourceMix = SourceMix.balanced


def _value(field) -> str | None:
    return field.value if hasattr(field, "value") else field


def _without_full_text(literature: list[dict] | None) -> list[dict] | None:
    """Full text is for layer 3 only; a hundred papers of it would bloat every detail response."""
    if literature is None:
        return None
    return [{k: v for k, v in item.items() if k != "full_text"} for item in literature]


def _count(items: list | None) -> int | None:
    return None if items is None else len(items)


class TaskResponse(BaseModel):
    id: uuid.UUID
    topic: str
    language: str
    collab_mode: CollabMode
    paper_type: str = "general"
    source_mix: str = "balanced"
    status: str
    current_phase: int
    phase: int = 0
    error_message: str | None = None
    citation_issues: list[dict] | None = None
    uncited_claims: list[dict] | None = None
    revisions: list[dict] | None = None
    review: dict | None = None
    style_findings: list[dict] | None = None
    created_at: str | None = None
    updated_at: str | None = None
    is_starred: bool = False
    is_deleted: bool = False
    # 各阶段输出（仅详情接口填充，列表接口为 None）
    research_questions: list[str] | None = None
    keywords: list[str] | None = None
    literature: list[dict] | None = None
    synthesis: str | None = None
    evidence_table: list[dict] | None = None
    angle: dict | None = None
    novelty: dict | None = None
    outline: list[dict] | None = None
    sections: dict[str, str] | None = None
    cleaning_report: dict | None = None
    quality_results: list[dict] | None = None
    failed_sections: list[str] | None = None
    # papers the export may cite after verification; the list itself stays out of the payload
    verified_count: int | None = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm(cls, task: PaperTask, include_snapshot: bool = False) -> "TaskResponse":
        snapshot: dict = task.state_snapshot or {}
        return cls(
            id=task.id,
            topic=task.topic,
            language=task.language,
            collab_mode=task.collab_mode,
            paper_type=task.paper_type.value if hasattr(task.paper_type, "value") else (task.paper_type or "general"),
            source_mix=_value(getattr(task, "source_mix", None)) or "balanced",
            status=task.status.value if hasattr(task.status, "value") else task.status,
            current_phase=task.current_phase,
            phase=task.current_phase,
            error_message=task.error_message,
            citation_issues=snapshot.get("citation_issues") or None,
            uncited_claims=snapshot.get("uncited_claims") if include_snapshot else None,
            revisions=snapshot.get("revisions") if include_snapshot else None,
            review=snapshot.get("review") if include_snapshot else None,
            style_findings=snapshot.get("style_findings") if include_snapshot else None,
            created_at=task.created_at.isoformat() if task.created_at else None,
            updated_at=task.updated_at.isoformat() if task.updated_at else None,
            is_starred=task.is_starred or False,
            is_deleted=task.is_deleted or False,
            research_questions=snapshot.get("research_questions") if include_snapshot else None,
            keywords=snapshot.get("keywords") if include_snapshot else None,
            literature=_without_full_text(snapshot.get("literature")) if include_snapshot else None,
            synthesis=snapshot.get("synthesis") if include_snapshot else None,
            evidence_table=snapshot.get("evidence_table") if include_snapshot else None,
            novelty=snapshot.get("novelty") if include_snapshot else None,
            angle=snapshot.get("angle") if include_snapshot else None,
            outline=snapshot.get("outline") if include_snapshot else None,
            sections=snapshot.get("sections") if include_snapshot else None,
            cleaning_report=snapshot.get("cleaning_report") if include_snapshot else None,
            quality_results=snapshot.get("quality_results") if include_snapshot else None,
            failed_sections=snapshot.get("failed_sections") if include_snapshot else None,
            verified_count=_count(snapshot.get("verified_citations")) if include_snapshot else None,
        )


@router.get("", response_model=list[TaskResponse])
async def get_list(
    starred: bool = False,
    deleted: bool = False,
    session: AsyncSession = Depends(db),
) -> list[TaskResponse]:
    tasks = await list_tasks(session, starred_only=starred, include_deleted=deleted)
    return [TaskResponse.from_orm(t) for t in tasks]


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create(
    req: CreateTaskRequest, session: AsyncSession = Depends(db)
) -> TaskResponse:
    task = await create_task(session, req.topic, req.language, req.collab_mode, paper_type=req.paper_type.value,
                             source_mix=req.source_mix.value)
    return TaskResponse.from_orm(task)


@router.get("/{task_id}", response_model=TaskResponse)
async def get(task_id: uuid.UUID, session: AsyncSession = Depends(db)) -> TaskResponse:
    task = await get_task(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse.from_orm(task, include_snapshot=True)


@router.post("/{task_id}/approve", status_code=status.HTTP_202_ACCEPTED)
async def approve_gate(
    task_id: uuid.UUID, session: AsyncSession = Depends(db)
) -> dict[str, str]:
    task = await get_task(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task_status = task.status.value if hasattr(task.status, "value") else task.status
    if task_status != "waiting":
        raise HTTPException(status_code=409, detail="Task is not waiting for approval")
    asyncio.create_task(resume_pipeline(str(task_id)))
    return {"status": "resumed"}


@router.post("/{task_id}/start", status_code=status.HTTP_202_ACCEPTED)
async def start_task(
    task_id: uuid.UUID, session: AsyncSession = Depends(db)
) -> dict[str, str]:
    task = await get_task(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    logger.info("Starting pipeline for task %s", task_id)
    bg = asyncio.create_task(
        run_pipeline(
            str(task_id), task.topic, task.language, task.collab_mode,
            paper_type=task.paper_type.value if hasattr(task.paper_type, "value") else str(task.paper_type),
            source_mix=_value(task.source_mix) or "balanced",
        )
    )
    def _on_done(fut: asyncio.Future) -> None:
        exc = fut.exception() if not fut.cancelled() else None
        if exc:
            logger.error("Background pipeline task FAILED: %s", exc, exc_info=exc)
        else:
            logger.info("Background pipeline task finished OK")
    bg.add_done_callback(_on_done)
    return {"status": "started"}


@router.post("/{task_id}/star", status_code=status.HTTP_200_OK)
async def toggle_star(
    task_id: uuid.UUID, session: AsyncSession = Depends(db)
) -> TaskResponse:
    task = await get_task(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.is_starred = not (task.is_starred or False)
    await session.commit()
    await session.refresh(task)
    return TaskResponse.from_orm(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task_endpoint(
    task_id: uuid.UUID, session: AsyncSession = Depends(db)
) -> None:
    deleted = await soft_delete_task(session, task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")


class PatchSnapshotRequest(BaseModel):
    research_questions: list[str] | None = None
    keywords: list[str] | None = None
    literature: list[dict] | None = None
    synthesis: str | None = None
    outline: list[dict] | None = None
    sections: dict[str, str] | None = None
    # key_gates: accepting a proposed revision writes the section and the revision's status together
    revisions: list[dict] | None = None


@router.patch("/{task_id}/snapshot", response_model=TaskResponse)
async def patch_snapshot(
    task_id: uuid.UUID,
    req: PatchSnapshotRequest,
    session: AsyncSession = Depends(db),
) -> TaskResponse:
    task = await get_task(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    snapshot = {**(task.state_snapshot or {})}
    for field, value in req.model_dump(exclude_none=True).items():
        snapshot[field] = value
    await update_task_snapshot(session, task_id, snapshot)
    await session.refresh(task)
    return TaskResponse.from_orm(task, include_snapshot=True)


class SaveAngleRequest(BaseModel):
    writing_angle: str
    contribution: str
    gap: str
    hypotheses: list[str]
    approach: str


@router.put("/{task_id}/angle", response_model=TaskResponse)
async def save_angle(
    task_id: uuid.UUID,
    req: SaveAngleRequest,
    session: AsyncSession = Depends(db),
) -> TaskResponse:
    task = await get_task(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    snapshot = {**(task.state_snapshot or {}), "angle": req.model_dump()}
    await update_task_snapshot(session, task_id, snapshot)
    await session.refresh(task)
    return TaskResponse.from_orm(task, include_snapshot=True)


@router.post("/{task_id}/angle", response_model=TaskResponse)
async def generate_angle(
    task_id: uuid.UUID, session: AsyncSession = Depends(db)
) -> TaskResponse:
    task = await get_task(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    snapshot: dict = task.state_snapshot or {}
    synthesis = snapshot.get("synthesis", "")
    research_questions = snapshot.get("research_questions") or []
    if not synthesis:
        raise HTTPException(status_code=422, detail="该任务尚无文献综合内容，无法生成写作角度")
    llm = get_llm("angle", task.topic, task.language, max_tokens=2048)
    agent = AngleAgent(llm=llm)
    angle = await agent.run(
        topic=task.topic,
        synthesis=synthesis,
        research_questions=research_questions,
        language=task.language,
    )
    merged = {**snapshot, "angle": angle}
    await update_task_snapshot(session, task_id, merged)
    await session.refresh(task)
    return TaskResponse.from_orm(task, include_snapshot=True)


# 每个阶段及其下游需清空的快照字段
_PHASE_CLEAR_FIELDS: dict[int, list[str]] = {
    1: ["research_questions", "keywords", "literature", "cleaning_report", "prisma_flow",
        "synthesis", "evidence_table", "angle", "novelty", "outline", "taxonomy", "sections", "failed_sections",
        "verified_citations", "citation_issues", "uncited_claims", "revisions", "review", "style_findings", "quality_results", "smart_pause",
        "markdown_content", "latex_content"],
    2: ["literature", "cleaning_report", "prisma_flow", "synthesis", "evidence_table", "angle", "novelty", "outline", "taxonomy",
        "sections", "failed_sections", "verified_citations", "citation_issues", "uncited_claims", "revisions", "review", "style_findings",
        "quality_results", "smart_pause", "markdown_content", "latex_content"],
    3: ["cleaning_report", "prisma_flow", "synthesis", "evidence_table", "angle", "novelty", "outline", "taxonomy", "sections",
        "failed_sections", "verified_citations", "citation_issues", "uncited_claims", "revisions", "review", "style_findings", "quality_results",
        "smart_pause", "markdown_content", "latex_content"],
    4: ["synthesis", "evidence_table", "angle", "novelty", "outline", "taxonomy", "sections", "failed_sections",
        "verified_citations", "citation_issues", "uncited_claims", "revisions", "review", "style_findings", "quality_results", "smart_pause",
        "markdown_content", "latex_content"],
    5: ["angle", "novelty", "outline", "taxonomy", "sections", "failed_sections", "verified_citations",
        "citation_issues", "uncited_claims", "revisions", "review", "style_findings", "quality_results", "smart_pause", "markdown_content", "latex_content"],
    6: ["outline", "taxonomy", "sections", "failed_sections", "verified_citations", "citation_issues", "uncited_claims", "revisions", "review", "style_findings",
        "quality_results", "smart_pause", "markdown_content", "latex_content"],
    7: ["sections", "failed_sections", "verified_citations", "citation_issues", "uncited_claims", "revisions", "review", "style_findings",
        "quality_results", "smart_pause", "markdown_content", "latex_content"],
    8: ["verified_citations", "citation_issues", "uncited_claims", "revisions", "review", "style_findings", "quality_results", "smart_pause",
        "markdown_content", "latex_content"],
    9: ["markdown_content", "latex_content"],
}


class RedoPhaseRequest(BaseModel):
    phase: int
    # set to redo the search with another language mix of the literature
    source_mix: SourceMix | None = None


@router.post("/{task_id}/redo", status_code=status.HTTP_202_ACCEPTED)
async def redo_phase(
    task_id: uuid.UUID,
    req: RedoPhaseRequest,
    session: AsyncSession = Depends(db),
) -> dict[str, str]:
    """从指定阶段重做：清空该阶段及下游快照，回退 current_phase，重新执行。"""
    task = await get_task(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task_status = task.status.value if hasattr(task.status, "value") else task.status
    if task_status == "running":
        raise HTTPException(status_code=409, detail="Task is currently running")
    if req.phase not in _PHASE_CLEAR_FIELDS:
        raise HTTPException(status_code=422, detail="Invalid phase number")

    snapshot = {**(task.state_snapshot or {})}
    cleared = [f for f in _PHASE_CLEAR_FIELDS[req.phase] if f in snapshot]
    for field in cleared:
        snapshot.pop(field)

    logger.info(
        "[redo] task=%s phase=%s cleared_fields=%s",
        task_id, req.phase, cleared,
    )

    task.state_snapshot = snapshot
    _sa_attrs.flag_modified(task, "state_snapshot")  # 强制告知 SQLAlchemy JSON 列已变更
    if req.source_mix is not None:
        task.source_mix = req.source_mix.value
    task.current_phase = req.phase
    task.status = TaskStatus.waiting
    task.error_message = None
    await session.commit()
    logger.info("[redo] snapshot committed, firing resume_pipeline")

    asyncio.create_task(resume_pipeline(str(task_id)))
    return {"status": "redoing"}


@router.post("/{task_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_task(
    task_id: uuid.UUID, session: AsyncSession = Depends(db)
) -> dict[str, str]:
    """重新执行失败的任务（从当前阶段重试）。"""
    task = await get_task(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task_status = task.status.value if hasattr(task.status, "value") else task.status
    if task_status != "failed":
        raise HTTPException(status_code=409, detail="Task is not in failed state")
    task.error_message = None
    await session.commit()
    asyncio.create_task(resume_pipeline(str(task_id)))
    return {"status": "retrying"}


class RetrySectionRequest(BaseModel):
    section_title: str


@router.post("/{task_id}/retry-section", response_model=TaskResponse)
async def retry_section(
    task_id: uuid.UUID,
    req: RetrySectionRequest,
    session: AsyncSession = Depends(db),
) -> TaskResponse:
    """重新生成单个失败章节。"""
    task = await get_task(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    snapshot: dict = task.state_snapshot or {}
    sections: dict[str, str] = snapshot.get("sections") or {}
    outline: list[dict] = snapshot.get("outline") or []
    literature_raw: list[dict] = snapshot.get("literature") or []
    synthesis: str = snapshot.get("synthesis") or ""

    target = next((s for s in outline if s["title"] == req.section_title), None)
    if not target:
        raise HTTPException(status_code=422, detail="Section not found in outline")

    items: list[LiteratureItem] = []
    for lit in literature_raw:
        try:
            items.append(LiteratureItem(**lit))
        except Exception:
            pass

    llm = get_llm("writing", task.topic, task.language, max_tokens=6144)
    writer = SectionWriter(llm=llm, selector_llm=section_selector_llm())
    new_content = await writer._write_section(
        section=target,
        outline_context="\n".join(f"- {s['title']}: {s.get('summary', '')}" for s in outline),
        synthesis=synthesis,
        literature=items,
        language=task.language,
        angle=snapshot.get("angle"),
        review_facts=review_process_facts(
            snapshot.get("cleaning_report"), items, snapshot.get("keywords") or [], task.language
        ),
        source_mix=_value(task.source_mix) or "balanced",
    )

    sections[req.section_title] = new_content
    failed: list[str] = [
        t for t, c in sections.items() if c.startswith("__SECTION_FAILED__")
    ]
    merged = {**snapshot, "sections": sections, "failed_sections": failed}
    await update_task_snapshot(session, task_id, merged)
    await session.refresh(task)
    return TaskResponse.from_orm(task, include_snapshot=True)
