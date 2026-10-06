"""兼容层：提供 fast_llm / strong_llm 工厂函数，内部使用 model_router。"""
from langchain_openai import ChatOpenAI

from backend.core.config import settings


def fast_llm(max_tokens: int = 2048) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_model_fast,
        api_key=settings.openai_api_key,  # type: ignore[arg-type]
        max_tokens=max_tokens,
    )


def strong_llm(max_tokens: int = 4096) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_model_strong,
        api_key=settings.openai_api_key,  # type: ignore[arg-type]
        max_tokens=max_tokens,
    )
