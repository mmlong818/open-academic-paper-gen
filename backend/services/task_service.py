import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import PaperTask, TaskStatus


async def create_task(
    session: AsyncSession, topic: str, language: str, collab_mode: str, paper_type: str = "general",
    source_mix: str = "balanced",
) -> PaperTask:
    task = PaperTask(topic=topic, language=language, collab_mode=collab_mode, paper_type=paper_type,
                     source_mix=source_mix)
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def get_task(session: AsyncSession, task_id: uuid.UUID) -> PaperTask | None:
    result = await session.execute(select(PaperTask).where(PaperTask.id == task_id))
    return result.scalar_one_or_none()


async def update_task_status(
    session: AsyncSession,
    task_id: uuid.UUID,
    status: TaskStatus,
    phase: int | None = None,
    error_message: str | None = None,
) -> PaperTask | None:
    task = await get_task(session, task_id)
    if not task:
        return None
    task.status = status
    if phase is not None:
        task.current_phase = phase
    if error_message is not None:
        task.error_message = error_message
    await session.commit()
    await session.refresh(task)
    return task


async def update_task_snapshot(
    session: AsyncSession,
    task_id: uuid.UUID,
    snapshot: dict,
) -> PaperTask | None:
    task = await get_task(session, task_id)
    if not task:
        return None
    task.state_snapshot = snapshot
    await session.commit()
    await session.refresh(task)
    return task


async def list_tasks(
    session: AsyncSession,
    starred_only: bool = False,
    include_deleted: bool = False,
) -> list[PaperTask]:
    stmt = select(PaperTask)
    if not include_deleted:
        stmt = stmt.where(PaperTask.is_deleted.is_(False) | PaperTask.is_deleted.is_(None))
    if starred_only:
        stmt = stmt.where(PaperTask.is_starred == True)
    stmt = stmt.order_by(PaperTask.created_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def star_task(
    session: AsyncSession, task_id: uuid.UUID, starred: bool
) -> PaperTask | None:
    task = await get_task(session, task_id)
    if not task:
        return None
    task.is_starred = starred
    await session.commit()
    await session.refresh(task)
    return task




async def soft_delete_task(
    session: AsyncSession, task_id: uuid.UUID
) -> bool:
    task = await get_task(session, task_id)
    if not task:
        return False
    task.is_deleted = True
    await session.commit()
    return True
