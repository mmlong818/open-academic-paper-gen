from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.config import settings
from backend.db.models import Base

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def migrate_columns() -> None:
    """为现有表添加新列（幂等，已存在则忽略）。"""
    stmts = [
        "ALTER TABLE paper_tasks ADD COLUMN IF NOT EXISTS is_starred BOOLEAN DEFAULT FALSE",
        "ALTER TABLE paper_tasks ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE",
        "ALTER TABLE paper_tasks ADD COLUMN IF NOT EXISTS paper_type VARCHAR(30) DEFAULT 'general'",
        "ALTER TABLE paper_tasks ADD COLUMN IF NOT EXISTS source_mix VARCHAR(20) DEFAULT 'balanced'",
    ]
    async with engine.begin() as conn:
        for stmt in stmts:
            await conn.execute(text(stmt))


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
