import asyncio
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.services.pubsub import subscribe_task, unregister_mem_queue

router = APIRouter()


@router.websocket("/{task_id}")
async def task_progress(websocket: WebSocket, task_id: uuid.UUID) -> None:
    await websocket.accept()
    try:
        pubsub = await subscribe_task(str(task_id))
    except Exception:
        await websocket.close()
        return

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception:
        pass
    finally:
        try:
            await asyncio.wait_for(
                asyncio.gather(
                    pubsub.unsubscribe(str(task_id)),
                    pubsub.aclose(),
                    return_exceptions=True,
                ),
                timeout=2.0,
            )
        except BaseException:
            pass
        try:
            await unregister_mem_queue(str(task_id), pubsub)
        except BaseException:
            pass
