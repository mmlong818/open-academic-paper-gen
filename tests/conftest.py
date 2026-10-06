import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.config import settings
from backend.db.models import Base
from backend.db.session import get_session

# Derived from the configured dev database so the port stays in step with
# docker-compose (which publishes 5558, not the postgres default).
TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    settings.database_url.rsplit("/", 1)[0] + "/papergen_test",
)


def pytest_collection_modifyitems(items):
    import pytest
    for item in items:
        if item.get_closest_marker("asyncio") is None:
            item.add_marker(pytest.mark.asyncio)


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(TEST_DB_URL)
    try:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except OSError as exc:
        await eng.dispose()
        pytest.skip(f"test database unreachable at {TEST_DB_URL}: {exc}")
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine):
    async with engine.connect() as conn:
        await conn.begin()
        session_factory = async_sessionmaker(
            bind=conn,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        async with session_factory() as s:
            yield s
        await conn.rollback()


@pytest_asyncio.fixture
async def client(session: AsyncSession):
    from backend.main import app

    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _no_paper_cache(monkeypatch):
    """Tests must not read or write the development database's paper cache."""
    monkeypatch.setattr("backend.core.config.settings.paper_cache", False)


@pytest.fixture(autouse=True)
def _no_real_review(monkeypatch):
    """Node tests with a draft would otherwise send it to the real writing model for review.

    Tests of the review itself build ReviewAgent directly or patch this back.
    """
    from unittest.mock import AsyncMock, MagicMock

    fake = MagicMock()
    fake.return_value.review = AsyncMock(return_value={"comments": [], "limitations": [], "dropped_unquoted": 0})
    monkeypatch.setattr("backend.pipeline.graph.ReviewAgent", fake)
    monkeypatch.setattr("backend.pipeline.graph.ReviewPanel", fake)

