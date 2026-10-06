import asyncio
import json

import pytest

from backend.services.pubsub import publish_progress


async def test_ws_receives_progress(client):
    resp = await client.post(
        "/api/tasks",
        json={"topic": "ws測試", "language": "zh", "collab_mode": "full_auto"},
    )
    assert resp.status_code == 201
    task_id = resp.json()["id"]

    received: list[dict] = []

    async def listen():
        from backend.services.pubsub import subscribe_task
        pubsub = await subscribe_task(task_id)
        async for message in pubsub.listen():
            if message["type"] == "message":
                received.append(json.loads(message["data"]))
                break
        await pubsub.unsubscribe(f"task:{task_id}")
        await pubsub.aclose()

    listener = asyncio.create_task(listen())
    await asyncio.sleep(0.1)
    await publish_progress(task_id, phase=1, status="running", message="開始文獻檢索")
    await asyncio.wait_for(listener, timeout=3.0)

    assert len(received) == 1
    assert received[0]["phase"] == 1
    assert received[0]["status"] == "running"
    assert received[0]["task_id"] == task_id
