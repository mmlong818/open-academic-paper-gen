"""The writing language and the language mix of the literature are set apart.

One "language" setting used to pick the prose language and the sources alike, so a Chinese
paper that should cite the international literature, or an English paper on a Chinese topic,
could not be asked for.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.api.routes.tasks import TaskResponse


async def test_a_task_keeps_the_mix_it_was_created_with(client):
    resp = await client.post("/api/tasks", json={"topic": "t", "language": "en", "source_mix": "zh_major"})
    assert resp.status_code == 201
    assert resp.json()["source_mix"] == "zh_major"


async def test_the_mix_defaults_to_balanced(client):
    resp = await client.post("/api/tasks", json={"topic": "t", "language": "zh"})
    assert resp.json()["source_mix"] == "balanced"


async def test_an_unknown_mix_is_rejected(client):
    resp = await client.post("/api/tasks", json={"topic": "t", "source_mix": "mostly_french"})
    assert resp.status_code == 422


async def test_redoing_the_search_can_change_the_mix(client):
    task_id = (await client.post("/api/tasks", json={"topic": "t", "source_mix": "balanced"})).json()["id"]
    with patch("backend.api.routes.tasks.resume_pipeline", new=AsyncMock()):
        resp = await client.post(f"/api/tasks/{task_id}/redo", json={"phase": 2, "source_mix": "en_major"})
    assert resp.status_code == 202
    assert (await client.get(f"/api/tasks/{task_id}")).json()["source_mix"] == "en_major"


async def test_a_redo_without_a_mix_leaves_it_alone(client):
    task_id = (await client.post("/api/tasks", json={"topic": "t", "source_mix": "zh_major"})).json()["id"]
    with patch("backend.api.routes.tasks.resume_pipeline", new=AsyncMock()):
        await client.post(f"/api/tasks/{task_id}/redo", json={"phase": 2})
    assert (await client.get(f"/api/tasks/{task_id}")).json()["source_mix"] == "zh_major"


def test_tasks_from_before_the_column_read_as_balanced():
    task = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001", topic="t", language="zh", collab_mode="full_auto",
        paper_type="general", status="completed", current_phase=9, error_message=None, source_mix=None,
        created_at=None, updated_at=None, is_starred=False, is_deleted=False, state_snapshot={},
    )
    assert TaskResponse.from_orm(task).source_mix == "balanced"
