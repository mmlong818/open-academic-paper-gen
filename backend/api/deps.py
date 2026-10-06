from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_session


async def db(session: AsyncSession = Depends(get_session)) -> AsyncSession:
    yield session
