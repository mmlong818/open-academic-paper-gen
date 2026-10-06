"""
Pub/Sub 服务：优先使用 Redis，Redis 不可用时自动降级到进程内内存队列。
WebSocket 和 pipeline 均通过此模块通信，无需关心底层实现。
"""
import asyncio
import json
import logging
from collections import defaultdict
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# ---------- 内存 pub/sub ----------

_mem_subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
_mem_lock = asyncio.Lock()


async def _mem_publish(channel: str, payload: str) -> None:
    async with _mem_lock:
        queues = list(_mem_subscribers.get(channel, []))
    for q in queues:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass


@asynccontextmanager
async def _mem_subscribe(channel: str):
    """上下文管理器：进入时注册队列，退出时注销。"""
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    async with _mem_lock:
        _mem_subscribers[channel].append(q)
    try:
        yield q
    finally:
        async with _mem_lock:
            try:
                _mem_subscribers[channel].remove(q)
            except ValueError:
                pass


# ---------- Redis pub/sub ----------

try:
    import redis.asyncio as aioredis
    _HAS_REDIS = True
except ImportError:
    _HAS_REDIS = False

from backend.core.config import settings

_redis: "aioredis.Redis | None" = None
_redis_lock = asyncio.Lock()
_redis_ok = True  # optimistic; flips to False on first failure


async def _get_redis():
    global _redis, _redis_ok
    if not _HAS_REDIS or not _redis_ok:
        return None
    async with _redis_lock:
        if _redis is None:
            try:
                _redis = await aioredis.from_url(settings.redis_url, decode_responses=True)
            except Exception:
                _redis_ok = False
                logger.warning("[pubsub] Redis 连接失败，降级到内存队列")
                return None
    return _redis


async def _redis_publish(task_id: str, payload: str) -> bool:
    redis = await _get_redis()
    if redis is None:
        return False
    try:
        await redis.publish(f"task:{task_id}", payload)
        return True
    except Exception:
        global _redis_ok, _redis
        async with _redis_lock:
            _redis_ok = False
            _redis = None
        logger.warning("[pubsub] Redis publish 失败，降级到内存队列")
        return False


# ---------- 公共接口 ----------

async def publish_progress(task_id: str, phase: int, status: str, message: str) -> None:
    payload = json.dumps(
        {"task_id": task_id, "phase": int(phase), "status": status, "message": message}
    )
    sent = await _redis_publish(task_id, payload)
    if not sent:
        await _mem_publish(f"task:{task_id}", payload)


class _MemPubSubAdapter:
    """模仿 redis PubSub 接口的内存适配器，供 ws.py 使用。"""

    def __init__(self, channel: str, queue: asyncio.Queue):
        self._channel = channel
        self._queue = queue
        self._closed = False

    async def listen(self):
        while not self._closed:
            try:
                data = await asyncio.wait_for(self._queue.get(), timeout=30)
                yield {"type": "message", "data": data}
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def unsubscribe(self, channel: str) -> None:
        self._closed = True

    async def aclose(self) -> None:
        self._closed = True


async def subscribe_task(task_id: str):
    """
    返回一个 pubsub 对象（Redis PubSub 或内存适配器）。
    调用方使用 async for message in pubsub.listen() 接收消息。
    """
    redis = await _get_redis()
    if redis is not None:
        try:
            pubsub = redis.pubsub()
            await pubsub.subscribe(f"task:{task_id}")
            return pubsub
        except Exception:
            pass  # fall through to memory

    # 内存模式：通过上下文管理器注册，ws.py 需要手动管理生命周期
    # 返回一个需要调用方自行关闭的适配器
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    channel = f"task:{task_id}"
    async with _mem_lock:
        _mem_subscribers[channel].append(q)
    return _MemPubSubAdapter(channel, q)


async def unregister_mem_queue(task_id: str, adapter) -> None:
    """WebSocket 关闭时，注销内存队列中对应的 adapter。"""
    if not isinstance(adapter, _MemPubSubAdapter):
        return
    channel = f"task:{task_id}"
    async with _mem_lock:
        try:
            _mem_subscribers[channel].remove(adapter._queue)
        except ValueError:
            pass
