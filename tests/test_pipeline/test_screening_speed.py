"""Screening is 92% of the cleaning phase: glm-5.1 spends 88% of its output reasoning.

On task a6f90fcf, 224 screening calls took 708 of 773 seconds at 14 s each, five at a time.
With thinking disabled a call takes about 5 s; at ten concurrent calls the account saw no 429s,
at fifteen it saw 5 of 15. So screening can run without thinking, eight at a time.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core import model_router
from backend.literature.schemas import LiteratureItem
from backend.literature.screener import LiteratureScreener
from backend.pipeline.graph import node_cleaning
from backend.pipeline.states import PaperState


def test_zhipu_without_thinking_asks_for_it_disabled():
    with patch.object(model_router.settings, "zhipu_model_fast", "glm-5.1"):
        assert model_router._zhipu(strong=False, max_tokens=256, thinking=False).extra_body == {
            "thinking": {"type": "disabled"}}


def test_a_model_that_always_thinks_gets_its_lowest_effort_instead():
    """glm-5.3 rejects thinking disabled with a 400, which would send every screening call to OpenAI;
    at reasoning_effort low glm-5.3-flash screened in 1.6 s. glm-5.1 ignores low (9.7 s)."""
    with patch.object(model_router.settings, "zhipu_model_fast", "glm-5.3-flash"):
        assert model_router._zhipu(strong=False, max_tokens=256, thinking=False).extra_body == {
            "reasoning_effort": "low"}


def test_zhipu_keeps_its_default_thinking_otherwise():
    assert model_router._zhipu(strong=False, max_tokens=256).extra_body is None


def test_get_llm_passes_thinking_to_the_fast_model():
    with patch.object(model_router, "_zhipu", wraps=model_router._zhipu) as zhipu:
        model_router.get_llm("synthesis", "t", "en", max_tokens=256, thinking=False)
    assert zhipu.call_args.kwargs["thinking"] is False


@pytest.mark.asyncio
async def test_the_screener_runs_as_many_calls_at_once_as_it_is_given():
    running = peak = 0

    async def call(_prompt):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1
        return MagicMock(content='{"decision": "include", "reason": "r"}')

    llm = MagicMock()
    llm.ainvoke = call
    items = [LiteratureItem(title=f"Paper {i}", abstract="a" * 400, source="arxiv") for i in range(20)]
    await LiteratureScreener(llm, concurrency=8).run(topic="t", items=items, language="en")
    assert peak == 8


@pytest.mark.asyncio
async def test_node_cleaning_screens_with_the_configured_thinking_and_concurrency():
    state = PaperState(task_id="s1", topic="t", language="en", collab_mode="full_auto",
                       literature=[{"title": "A paper", "source": "arxiv", "abstract": "a" * 80}])
    no_op = AsyncMock(return_value=None)
    with (
        patch("backend.pipeline.graph.settings") as cfg,
        patch("backend.pipeline.graph.get_llm") as get_llm,
        patch("backend.pipeline.graph.PaperContentFetcher") as Fetcher,
        patch("backend.pipeline.graph.LiteratureScreener") as Screener,
        patch("backend.pipeline.graph.enrich_abstracts", AsyncMock(side_effect=lambda items: (items, 0))),
        patch("backend.pipeline.graph._save_phase_result", no_op),
        patch("backend.pipeline.graph.publish_progress", no_op),
    ):
        cfg.screening_thinking, cfg.screening_concurrency, cfg.expand_citation_chain = False, 8, False
        Fetcher.return_value.run = AsyncMock(side_effect=lambda items: items)
        Screener.return_value.run = AsyncMock(side_effect=lambda topic, items, language: (items, []))
        await node_cleaning(state)

    assert get_llm.call_args.kwargs["thinking"] is False
    assert Screener.call_args.kwargs["concurrency"] == 8
