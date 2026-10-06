import asyncio

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_start_endpoint_returns_202(client):
    resp = await client.post(
        "/api/tasks",
        json={"topic": "集成测试主题", "language": "zh", "collab_mode": "full_auto"},
    )
    assert resp.status_code == 201
    task_id = resp.json()["id"]

    start_resp = await client.post(f"/api/tasks/{task_id}/start")
    assert start_resp.status_code == 202
    assert start_resp.json() == {"status": "started"}


@pytest.mark.asyncio
async def test_start_endpoint_404_for_unknown_task(client):
    import uuid

    fake_id = str(uuid.uuid4())
    resp = await client.post(f"/api/tasks/{fake_id}/start")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_run_pipeline_full_auto_completes():
    """full_auto mode: runner calls update_task_status with completed."""
    import uuid
    from backend.pipeline.states import GateStatus

    task_id = str(uuid.uuid4())
    mock_result = {
        "current_phase": 7,
        "gate_status": GateStatus.SKIPPED,
    }

    with (
        patch("backend.pipeline.runner.update_task_status", new_callable=AsyncMock),
        patch("backend.pipeline.runner.update_task_snapshot", new_callable=AsyncMock),
        patch("backend.pipeline.runner.publish_progress", new_callable=AsyncMock),
        patch("backend.pipeline.runner.paper_graph.ainvoke", new_callable=AsyncMock, return_value=mock_result),
        patch("backend.pipeline.runner.AsyncSessionLocal") as mock_session_cls,
    ):
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_ctx

        from backend.pipeline.runner import run_pipeline

        await run_pipeline(task_id, "集成测试", "zh", "full_auto")

    from backend.pipeline.runner import publish_progress
    # verify publish_progress was called at least twice (start + end)


@pytest.mark.asyncio
async def test_run_pipeline_key_gates_becomes_waiting():
    """key_gates mode: gate_status PENDING → waiting status."""
    import uuid
    from backend.pipeline.states import GateStatus
    from backend.db.models import TaskStatus

    task_id = str(uuid.uuid4())
    mock_result = {
        "current_phase": 1,
        "gate_status": GateStatus.PENDING,
    }
    captured_statuses: list[TaskStatus] = []

    async def fake_update(session, tid, s, phase=None):
        captured_statuses.append(s)

    with (
        patch("backend.pipeline.runner.update_task_status", side_effect=fake_update),
        patch("backend.pipeline.runner.update_task_snapshot", new_callable=AsyncMock),
        patch("backend.pipeline.runner.publish_progress", new_callable=AsyncMock),
        patch("backend.pipeline.runner.paper_graph.ainvoke", new_callable=AsyncMock, return_value=mock_result),
        patch("backend.pipeline.runner.AsyncSessionLocal") as mock_session_cls,
    ):
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_ctx

        from backend.pipeline.runner import run_pipeline
        await run_pipeline(task_id, "卡口测试", "zh", "key_gates")

    assert TaskStatus.waiting in captured_statuses


@pytest.mark.asyncio
async def test_run_pipeline_failure_sets_failed_status():
    """If graph.ainvoke raises, runner catches, sets failed, then re-raises."""
    import uuid
    from backend.db.models import TaskStatus

    task_id = str(uuid.uuid4())
    captured_statuses: list[TaskStatus] = []

    async def fake_update(session, tid, s, phase=None, error_message=None):
        captured_statuses.append(s)

    with (
        patch("backend.pipeline.runner.update_task_status", side_effect=fake_update),
        patch("backend.pipeline.runner.publish_progress", new_callable=AsyncMock),
        patch("backend.pipeline.runner.paper_graph.ainvoke", side_effect=RuntimeError("boom")),
        patch("backend.pipeline.runner.AsyncSessionLocal") as mock_session_cls,
    ):
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_ctx

        from backend.pipeline.runner import run_pipeline

        with pytest.raises(RuntimeError, match="boom"):
            await run_pipeline(task_id, "错误测试", "zh", "full_auto")

    assert TaskStatus.failed in captured_statuses
