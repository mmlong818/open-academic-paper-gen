import logging
import sys
from contextlib import asynccontextmanager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import update

from backend.api.routes import tasks
from backend.api.routes import ws
from backend.api.routes.export import router as export_router
from backend.api.routes.tools import router as tools_router
from backend.core.config import settings
from backend.db.models import PaperTask, TaskStatus
from backend.db.session import AsyncSessionLocal, create_tables, migrate_columns

logger = logging.getLogger(__name__)


async def _cleanup_stale_running_tasks() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(PaperTask)
            .where(PaperTask.status == TaskStatus.running)
            .values(status=TaskStatus.failed, error_message="服务器重启，任务被中断")
        )
        await session.commit()


def _llm_endpoint() -> tuple[str, str, str]:
    """返回 (provider_label, api_key, check_url)。"""
    if settings.llm_provider == "zhipu":
        return "智谱", settings.zhipu_api_key, f"{settings.zhipu_base_url.rstrip('/')}/models"
    return "OpenAI", settings.openai_api_key, "https://api.openai.com/v1/models"


async def _check_llm_connectivity(timeout: int = 5) -> str:
    _, key, url = _llm_endpoint()
    if not key:
        return "not_configured"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {key}"})
        return "ok" if resp.status_code == 200 else f"error_{resp.status_code}"
    except Exception:
        return "unreachable"


async def _verify_llm_key() -> None:
    label, key, _ = _llm_endpoint()
    if not key:
        logger.error("[LLM] %s API key 未配置，pipeline 将无法生成内容", label)
        return
    result = await _check_llm_connectivity(timeout=10)
    if result == "ok":
        logger.info("[LLM] %s API key 验证通过 (provider=%s)", label, settings.llm_provider)
    elif result == "unreachable":
        logger.warning("[LLM] 无法验证 %s API key（网络问题？）", label)
    else:
        logger.error("[LLM] %s API key 无效（%s）。请在 .env 中更新 key。", label, result)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    await migrate_columns()
    await _cleanup_stale_running_tasks()
    await _verify_llm_key()
    yield


app = FastAPI(title="Academic Paper Generator", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3600", "http://localhost:4000", "http://127.0.0.1:4000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(ws.router, prefix="/ws", tags=["websocket"])
app.include_router(export_router)
app.include_router(tools_router, prefix="/api/tools", tags=["tools"])


@app.get("/health/routing")
async def health_routing(topic: str = "测试", language: str = "zh") -> dict:
    from backend.core.model_router import get_provider_info
    return get_provider_info(topic, language)


@app.get("/health")
async def health() -> dict:
    llm_status = await _check_llm_connectivity()
    return {"status": "ok", "llm_provider": settings.llm_provider, "llm": llm_status}
