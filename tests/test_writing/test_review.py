"""Stage 3 — a simulated review of the draft, returned as suggestions only."""
import json
from unittest.mock import AsyncMock, MagicMock

from backend.writing.review import ReviewAgent

SECTIONS = {
    "Introduction": "Remote work raises productivity in every setting [cite:A2020x]. We review 40 studies.",
    "Discussion": "The evidence is mixed across sectors [cite:B2021y].",
}
OUTLINE = [{"title": "Introduction", "summary": ""}, {"title": "Discussion", "summary": ""}]


def _llm(payload) -> MagicMock:
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content=json.dumps(payload, ensure_ascii=False)))
    return llm


GOOD = {
    "comments": [
        {"section": "Introduction", "quote": "Remote work raises productivity in every setting",
         "issue": "Overgeneralises; contradicts the Discussion's mixed evidence.", "severity": "major",
         "suggestion": "Qualify the claim by setting."},
        {"section": "Discussion", "quote": "This sentence is not in the draft",
         "issue": "x", "severity": "minor", "suggestion": "y"},
    ],
    "limitations": ["Only English-language studies were screened, which may miss regional evidence."],
}


async def test_comments_must_quote_the_draft_verbatim():
    review = await ReviewAgent(llm=_llm(GOOD)).review(SECTIONS, OUTLINE, "remote work", "en")
    assert [c["quote"] for c in review["comments"]] == ["Remote work raises productivity in every setting"]
    assert review["dropped_unquoted"] == 1  # a quote not found in the text is the reviewer's invention
    assert review["limitations"] == GOOD["limitations"]


async def test_prompt_carries_the_draft_and_the_substance_over_style_rule():
    llm = _llm({"comments": [], "limitations": []})
    await ReviewAgent(llm=llm).review(SECTIONS, OUTLINE, "remote work", "en")
    prompt = llm.ainvoke.call_args.args[0]
    assert "## Introduction" in prompt and "We review 40 studies." in prompt
    assert "tone" in prompt.lower()  # confident framing or claimed novelty is not evidence


async def test_output_is_capped():
    many = {"comments": [{"section": "Introduction", "quote": "We review 40 studies", "issue": f"i{i}",
                          "severity": "minor", "suggestion": "s"} for i in range(30)],
            "limitations": [f"limitation {i} specific enough" for i in range(20)]}
    review = await ReviewAgent(llm=_llm(many)).review(SECTIONS, OUTLINE, "t", "en")
    assert len(review["comments"]) == 10 and len(review["limitations"]) == 5


async def test_failures_yield_an_empty_review_not_an_error():
    broken = MagicMock()
    broken.ainvoke = AsyncMock(side_effect=RuntimeError("down"))
    for llm in (broken, _llm("not an object")):
        review = await ReviewAgent(llm=llm).review(SECTIONS, OUTLINE, "t", "en")
        assert review["comments"] == [] and review["limitations"] == []


async def test_failed_sections_are_left_out_of_the_draft_shown():
    llm = _llm({"comments": [], "limitations": []})
    await ReviewAgent(llm=llm).review({**SECTIONS, "Methods": "__SECTION_FAILED__Methods"}, OUTLINE, "t", "en")
    assert "__SECTION_FAILED__" not in llm.ainvoke.call_args.args[0]


def test_reviewer_runs_in_json_mode():
    from backend.writing.review import reviewer_llm

    llm = reviewer_llm()
    assert llm.kwargs["response_format"] == {"type": "json_object"}
    assert llm.bound.reasoning_effort == "medium"  # an uncapped run once spent all 32768 tokens thinking


async def test_a_failed_attempt_is_retried_once():
    """Reasoning occasionally runs away and exhausts the budget; a second attempt usually lands."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=[
        RuntimeError("length limit was reached"),
        MagicMock(content=json.dumps(GOOD, ensure_ascii=False)),
    ])
    review = await ReviewAgent(llm=llm).review(SECTIONS, OUTLINE, "remote work", "en")
    assert llm.ainvoke.await_count == 2 and len(review["comments"]) == 1


async def test_two_failures_give_up_with_an_empty_review():
    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=RuntimeError("length limit was reached"))
    review = await ReviewAgent(llm=llm).review(SECTIONS, OUTLINE, "t", "en")
    assert llm.ainvoke.await_count == 2 and review["comments"] == []


async def test_the_retry_goes_to_the_low_effort_model_when_given():
    """Medium effort ran away on all six attempts of one real draft; low effort answered in ~300 tokens."""
    first = MagicMock()
    first.ainvoke = AsyncMock(side_effect=RuntimeError("length limit was reached"))
    retry = _llm(GOOD)
    review = await ReviewAgent(llm=first, retry_llm=retry).review(SECTIONS, OUTLINE, "t", "en")
    assert first.ainvoke.await_count == 1 and retry.ainvoke.await_count == 1
    assert len(review["comments"]) == 1


def test_the_retry_model_reasons_at_low_effort():
    from backend.writing.review import reviewer_llm

    assert reviewer_llm("low").bound.reasoning_effort == "low"
