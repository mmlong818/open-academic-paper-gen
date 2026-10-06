import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import Boolean, DateTime, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TaskStatus(str, Enum):
    pending = "pending"
    running = "running"
    waiting = "waiting"
    completed = "completed"
    failed = "failed"


class CollabMode(str, Enum):
    full_auto = "full_auto"
    key_gates = "key_gates"


class SourceMix(str, Enum):
    """Language mix of the literature, set apart from the language the paper is written in."""
    zh_major = "zh_major"
    balanced = "balanced"
    en_major = "en_major"


class PaperType(str, Enum):
    general = "general"
    review = "review"
    empirical = "empirical"
    experimental = "experimental"
    systematic = "systematic"
    computational = "computational"


class PaperCache(Base):
    """Fetched paper content reused across tasks (backend.literature.paper_cache); no task data."""

    __tablename__ = "paper_cache"

    key: Mapped[str] = mapped_column(String(300), primary_key=True)  # doi:... or arxiv:...
    abstract: Mapped[str] = mapped_column(Text, default="")
    body_excerpt: Mapped[str] = mapped_column(Text, default="")
    full_text: Mapped[str] = mapped_column(Text, default="")
    full_text_pages: Mapped[list[Any]] = mapped_column(JSON, default=list)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class PaperTask(Base):
    __tablename__ = "paper_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    topic: Mapped[str] = mapped_column(String(500), nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="zh")
    collab_mode: Mapped[CollabMode] = mapped_column(String(20), default=CollabMode.key_gates)
    paper_type: Mapped[PaperType] = mapped_column(String(30), default=PaperType.general)
    source_mix: Mapped[SourceMix | None] = mapped_column(String(20), default=SourceMix.balanced, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(String(20), default=TaskStatus.pending)
    current_phase: Mapped[int] = mapped_column(default=0)
    state_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_starred: Mapped[bool | None] = mapped_column(Boolean, default=False, nullable=True)
    is_deleted: Mapped[bool | None] = mapped_column(Boolean, default=False, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
