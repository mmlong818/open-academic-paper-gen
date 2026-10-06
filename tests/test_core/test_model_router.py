import pytest
from unittest.mock import patch

from langchain_core.runnables import RunnableLambda

from backend.core import model_router


def _raise(_):
    raise RuntimeError("429 rate limit")


@pytest.mark.asyncio
async def test_fast_step_falls_back_to_openai_when_zhipu_fails():
    calls = {}

    def fake_openai(strong, max_tokens):
        calls["openai"] = (strong, max_tokens)
        return RunnableLambda(lambda _: "from openai")

    with patch.object(model_router, "_zhipu", return_value=RunnableLambda(_raise)), \
         patch.object(model_router, "_openai", side_effect=fake_openai):
        llm = model_router.get_llm("synthesis", "t", "en", max_tokens=256)
        assert await llm.ainvoke("x") == "from openai"

    strong, max_tokens = calls["openai"]
    assert strong is False
    # the OpenAI fast model reasons before replying; a small budget comes back empty
    assert max_tokens >= 4096
