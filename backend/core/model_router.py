"""
ModelRouter — 双轨 LLM 路由策略：

  fast 步骤（scoping / synthesis / angle / outline）
      → 智谱 glm 优先，失败自动降级到 OpenAI fast

  strong 步骤（writing）
      → OpenAI 优先，失败自动降级到智谱
      （使用 LangChain with_fallbacks，对上层透明）
"""

from langchain_openai import ChatOpenAI

from backend.core.config import settings

_STEP_TIER: dict[str, str] = {
    "scoping":   settings.model_tier_scoping,
    "synthesis": settings.model_tier_synthesis,
    "angle":     settings.model_tier_synthesis,
    "outline":   settings.model_tier_outline,
    "writing":   settings.model_tier_writing,
}


# 始终思考的模型：关闭思考会 400（随即整批降级到 OpenAI），只能降到最低档。
# glm-5.3-flash 在 low 档筛选一次 1.6 秒；glm-5.1 不认 low（仍推理，9.7 秒），只能关闭。
_ALWAYS_THINKS = ("glm-5.3",)


def _without_thinking(model: str) -> dict:
    return {"reasoning_effort": "low"} if model.startswith(_ALWAYS_THINKS) else {"thinking": {"type": "disabled"}}


def _zhipu(strong: bool, max_tokens: int, thinking: bool = True) -> ChatOpenAI:
    model = settings.zhipu_model_strong if strong else settings.zhipu_model_fast
    return ChatOpenAI(
        model=model,
        api_key=settings.zhipu_api_key,       # type: ignore[arg-type]
        base_url=settings.zhipu_base_url,
        max_tokens=max_tokens,
        extra_body=None if thinking else _without_thinking(model),
    )


def _openai(strong: bool, max_tokens: int) -> ChatOpenAI:
    model = settings.openai_model_strong if strong else settings.openai_model_fast
    return ChatOpenAI(
        model=model,
        api_key=settings.openai_api_key,      # type: ignore[arg-type]
        max_tokens=max_tokens,
    )


def get_llm(
    step: str,
    topic: str,
    language: str,
    max_tokens: int | None = None,
    thinking: bool = True,
):
    """
    返回适合该步骤的 LLM。

    fast tier  → 智谱，失败自动降级到 OpenAI fast
    strong tier → OpenAI，失败自动降级到智谱
    thinking=False 只关闭 fast 档智谱的思考模式（筛选用）；OpenAI 降级不受影响。
    """
    tier = _STEP_TIER.get(step, "fast")
    strong = tier == "strong"
    tokens = max_tokens or (4096 if strong else 2048)

    if not strong:
        # 非关键步骤：智谱优先，省时省钱；限流或欠费时降级到 OpenAI fast。
        # OpenAI fast 是推理模型，预算过小会推理耗尽、返回空回复。
        primary = _zhipu(strong=False, max_tokens=tokens, thinking=thinking)
        fallback = _openai(strong=False, max_tokens=max(tokens, 4096))
        return primary.with_fallbacks([fallback])

    # 关键步骤：OpenAI 优先，智谱兜底
    primary = _openai(strong=True, max_tokens=tokens)
    fallback = _zhipu(strong=True, max_tokens=tokens)
    return primary.with_fallbacks([fallback])


def get_provider_info(topic: str, language: str) -> dict:
    """返回路由决策摘要，用于日志。"""
    return {
        "provider": "openai+zhipu_fallback",
        "strategy": "fast→zhipu+openai_fallback / strong→openai+zhipu_fallback",
        "tiers": {step: _STEP_TIER.get(step, "fast") for step in _STEP_TIER},
        "models": {
            step: (
                f"{settings.openai_model_strong}→{settings.zhipu_model_strong}"
                if _STEP_TIER.get(step) == "strong"
                else f"{settings.zhipu_model_fast}→{settings.openai_model_fast}"
            )
            for step in _STEP_TIER
        },
    }
