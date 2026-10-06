"""Three blind reviewers with different focuses: comments quoting
the same text merge and keep the highest severity given; shared points come first."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core.config import settings
from backend.writing.review_panel import FOCUSES, ReviewPanel

SECTIONS = {"Intro": "Recall doubles with retrieval. Latency is unchanged.",
            "Results": "All baselines lose. The effect holds everywhere."}
OUTLINE = [{"title": "Intro"}, {"title": "Results"}]


def _comment(quote: str, severity: str = "major", section: str = "Intro") -> dict:
    return {"section": section, "quote": quote, "issue": f"issue on {quote}", "severity": severity, "suggestion": "s"}


def _llm(replies: list[dict]) -> MagicMock:
    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=[MagicMock(content=json.dumps(r)) for r in replies])
    return llm


async def _review(replies: list[dict]) -> dict:
    return await ReviewPanel(_llm(replies)).review(SECTIONS, OUTLINE, "rag", "en")


@pytest.mark.asyncio
async def test_each_reviewer_gets_its_own_focus_and_the_same_draft():
    llm = _llm([{"comments": [], "limitations": []}] * 3)
    await ReviewPanel(llm).review(SECTIONS, OUTLINE, "rag", "en")
    prompts = [call.args[0] for call in llm.ainvoke.call_args_list]
    assert len(prompts) == 3
    assert all("Recall doubles with retrieval." in p for p in prompts)
    for focus in FOCUSES.values():
        assert sum(focus["en"] in p for p in prompts) == 1


@pytest.mark.asyncio
async def test_a_point_two_reviewers_raise_merges_and_stays_major():
    review = await _review([
        {"comments": [_comment("Recall doubles with retrieval.")], "limitations": []},
        {"comments": [_comment("Recall doubles", "minor")], "limitations": []},
        {"comments": [], "limitations": []},
    ])
    assert len(review["comments"]) == 1
    merged = review["comments"][0]
    assert merged["severity"] == "major"
    assert merged["reviewers"] == ["evidence", "coverage"]


@pytest.mark.asyncio
async def test_a_major_point_from_one_reviewer_stays_major():
    review = await _review([
        {"comments": [], "limitations": []},
        {"comments": [], "limitations": []},
        {"comments": [_comment("The effect holds everywhere.", section="Results")], "limitations": []},
    ])
    assert review["comments"][0]["severity"] == "major"
    assert review["comments"][0]["reviewers"] == ["reasoning"]


@pytest.mark.asyncio
async def test_shared_points_come_first_and_unquoted_ones_are_dropped():
    review = await _review([
        {"comments": [_comment("Latency is unchanged."), _comment("not in the draft")], "limitations": ["L1"]},
        {"comments": [_comment("All baselines lose.", section="Results")], "limitations": ["L1", "L2"]},
        {"comments": [_comment("All baselines lose.", "minor", section="Results")], "limitations": []},
    ])
    assert [c["quote"] for c in review["comments"]] == ["All baselines lose.", "Latency is unchanged."]
    assert review["dropped_unquoted"] == 1
    assert review["limitations"] == ["L1", "L2"]
    assert review["panel"] is True


@pytest.mark.asyncio
async def test_a_failed_reviewer_leaves_the_other_two():
    ok = MagicMock(content=json.dumps({"comments": [_comment("Latency is unchanged.")], "limitations": []}))

    async def reply(prompt):
        if FOCUSES["coverage"]["en"] in prompt:
            raise RuntimeError("down")
        return ok

    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=reply)
    review = await ReviewPanel(llm).review(SECTIONS, OUTLINE, "rag", "en")
    assert len(review["comments"]) == 1 and review["comments"][0]["reviewers"] == ["evidence", "reasoning"]


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", [False, True])
async def test_the_verification_node_uses_the_panel_only_behind_its_flag(flag):
    from backend.pipeline import graph

    with (
        patch.object(settings, "review_panel", flag),
        patch.object(graph, "ReviewAgent") as single,
        patch.object(graph, "ReviewPanel") as panel,
        patch.object(graph, "reviewer_llm"),
    ):
        single.return_value.review = AsyncMock(return_value={"comments": []})
        panel.return_value.review = AsyncMock(return_value={"comments": [], "panel": True})
        await graph._simulated_review(SECTIONS, OUTLINE, "rag", "en")
    assert panel.called is flag and single.called is not flag


@pytest.mark.asyncio
async def test_the_node_gives_every_reviewer_a_low_effort_retry():
    from backend.pipeline import graph

    with (
        patch.object(settings, "review_panel", True),
        patch.object(graph, "ReviewPanel") as panel,
        patch.object(graph, "reviewer_llm", side_effect=lambda effort="medium": effort),
    ):
        panel.return_value.review = AsyncMock(return_value={"comments": []})
        await graph._simulated_review(SECTIONS, OUTLINE, "rag", "en")
    panel.assert_called_once_with("medium", retry_llm="low")
