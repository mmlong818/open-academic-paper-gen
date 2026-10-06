import uuid as uuid_module

import pytest


async def test_create_task_returns_id(client):
    resp = await client.post(
        "/api/tasks",
        json={
            "topic": "大语言模型在医疗诊断中的应用",
            "language": "zh",
            "collab_mode": "key_gates",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert data["status"] == "pending"


async def test_get_task(client):
    create_resp = await client.post(
        "/api/tasks",
        json={"topic": "测试主题", "language": "zh", "collab_mode": "full_auto"},
    )
    task_id = create_resp.json()["id"]
    resp = await client.get(f"/api/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["topic"] == "测试主题"


async def test_get_task_not_found(client):
    resp = await client.get(f"/api/tasks/{uuid_module.uuid4()}")
    assert resp.status_code == 404


async def test_approve_gate_rejects_non_waiting_task(client):
    """approve 只允许 waiting 状态的任务，pending 任务应返回 409。"""
    create_resp = await client.post(
        "/api/tasks",
        json={"topic": "测试", "language": "zh", "collab_mode": "key_gates"},
    )
    task_id = create_resp.json()["id"]
    resp = await client.post(f"/api/tasks/{task_id}/approve")
    assert resp.status_code == 409


async def test_approve_gate_waiting_task(client, session):
    """waiting 状态的任务可以审批，返回 202。"""
    from backend.db.models import TaskStatus
    from backend.services.task_service import create_task, update_task_status

    task = await create_task(session, "审批测试", "zh", "key_gates")
    await update_task_status(session, task.id, TaskStatus.waiting, phase=1)

    from unittest.mock import patch, AsyncMock
    with patch("backend.api.routes.tasks.resume_pipeline", new_callable=AsyncMock):
        resp = await client.post(f"/api/tasks/{task.id}/approve")
    assert resp.status_code == 202
    assert resp.json()["status"] == "resumed"

