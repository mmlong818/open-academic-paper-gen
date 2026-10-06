import asyncio
import logging
import uuid

from backend.db.models import TaskStatus
from backend.db.session import AsyncSessionLocal
from backend.pipeline.graph import paper_graph
from backend.pipeline.states import GateStatus, PaperState, Phase
from backend.services.pubsub import publish_progress
from backend.services.task_service import get_task, update_task_snapshot, update_task_status

logger = logging.getLogger(__name__)


async def run_pipeline(
    task_id: str, topic: str, language: str, collab_mode: str, paper_type: str = "general",
    source_mix: str = "balanced",
) -> None:
    state = PaperState(
        task_id=task_id, topic=topic, language=language, collab_mode=collab_mode, paper_type=paper_type,
        source_mix=source_mix,
    )
    async with AsyncSessionLocal() as session:
        await update_task_status(session, uuid.UUID(task_id), TaskStatus.running, phase=1)

    await publish_progress(task_id, phase=1, status="running", message="流水线启动")

    try:
        result = await paper_graph.ainvoke(state)
        gate_status = result.get("gate_status", GateStatus.SKIPPED)
        final_status = (
            TaskStatus.waiting if gate_status == GateStatus.PENDING else TaskStatus.completed
        )
        final_phase = result.get("current_phase", Phase.EXPORT.value)
        async with AsyncSessionLocal() as session:
            await update_task_status(session, uuid.UUID(task_id), final_status, phase=final_phase)
            await update_task_snapshot(session, uuid.UUID(task_id), dict(result))
        await publish_progress(
            task_id, phase=final_phase, status=final_status.value, message="流水线结束"
        )
    except asyncio.CancelledError:
        raise  # 不视为业务失败（通常是 uvicorn 重启导致）
    except Exception as e:
        logger.exception("Pipeline failed for task %s", task_id)
        err_msg = f"{type(e).__name__}: {e}"
        try:
            async with AsyncSessionLocal() as session:
                await update_task_status(
                    session, uuid.UUID(task_id), TaskStatus.failed,
                    error_message=err_msg,
                )
            await publish_progress(task_id, phase=0, status="failed", message=err_msg)
        except Exception:
            pass
        raise


async def resume_pipeline(task_id: str) -> None:
    """从 state_snapshot 重建状态，标记 gate_status=APPROVED，从当前阶段继续执行。"""
    async with AsyncSessionLocal() as session:
        task = await get_task(session, uuid.UUID(task_id))
        if not task:
            return
        snapshot: dict = task.state_snapshot or {}
        collab_mode = (
            task.collab_mode.value
            if hasattr(task.collab_mode, "value")
            else str(task.collab_mode)
        )
        resume_phase = Phase(task.current_phase)
        paper_type_val = (
            task.paper_type.value if hasattr(task.paper_type, "value") else str(task.paper_type)
        )
        state = PaperState(
            task_id=task_id,
            topic=task.topic,
            language=task.language,
            collab_mode=collab_mode,
            current_phase=resume_phase,
            gate_status=GateStatus.APPROVED,
            resume_from_phase=resume_phase,
            paper_type=paper_type_val,
            source_mix=getattr(task.source_mix, "value", task.source_mix) or "balanced",
            **{k: v for k, v in snapshot.items() if k not in {
                "task_id", "topic", "language", "collab_mode",
                "current_phase", "gate_status", "resume_from_phase",
                "paper_type", "source_mix", "errors",  # errors reset intentionally on resume
            }},
        )
        await update_task_status(session, uuid.UUID(task_id), TaskStatus.running)

    await publish_progress(task_id, phase=resume_phase, status="running", message="审批通过，继续执行")

    try:
        result = await paper_graph.ainvoke(state)
        gate_status = result.get("gate_status", GateStatus.SKIPPED)
        final_status = (
            TaskStatus.waiting if gate_status == GateStatus.PENDING else TaskStatus.completed
        )
        final_phase = result.get("current_phase", resume_phase)
        async with AsyncSessionLocal() as session:
            await update_task_status(session, uuid.UUID(task_id), final_status, phase=final_phase)
            merged = {**snapshot, **dict(result)}
            await update_task_snapshot(session, uuid.UUID(task_id), merged)
        await publish_progress(
            task_id, phase=final_phase, status=final_status.value, message="流水线结束"
        )
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.exception("Resume pipeline failed for task %s", task_id)
        err_msg = f"{type(e).__name__}: {e}"
        try:
            async with AsyncSessionLocal() as session:
                await update_task_status(
                    session, uuid.UUID(task_id), TaskStatus.failed,
                    error_message=err_msg,
                )
            await publish_progress(task_id, phase=0, status="failed", message=err_msg)
        except Exception:
            pass
        raise
