from langchain_core.language_models.fake_chat_models import FakeListChatModel

from backend.literature.schemas import LiteratureItem
from backend.pipeline.states import PaperState, Phase
from backend.verification.layer3_support import Claim, SupportChecker
from evals.harness import count_usage, offline, record_support_verdicts, run_nodes

EVIDENCE = "Transformers scale predictably with compute and data. " * 10


async def test_count_usage_sees_calls_made_deep_inside_components():
    llm = FakeListChatModel(responses=["hello", "again"])
    with count_usage() as usage:
        await llm.ainvoke("hi")
        await llm.ainvoke("hi")
    assert usage.calls == 2


async def test_record_support_verdicts_captures_every_verdict():
    llm = FakeListChatModel(responses=['[{"verdict": "unsupported", "reason": "off-topic"}]'])
    item = LiteratureItem(title="Scaling laws", source="arxiv", abstract=EVIDENCE)
    claims = {"k1": [Claim(key="k1", sentence="Scaling saturates early [cite:k1].")]}

    with record_support_verdicts() as records:
        await SupportChecker(llm=llm).check(claims, {"k1": item}, "en")

    assert records == [{
        "key": "k1",
        "sentence": "Scaling saturates early [cite:k1].",
        "context": "",
        "verdict": "unsupported",
        "reason": "off-topic",
        "evidence": "abstract",  # no body excerpt, so the judge only saw the abstract
        "pass": 0,
    }]


async def test_record_support_verdicts_numbers_each_verification_pass():
    llm = FakeListChatModel(responses=['[{"verdict": "supported", "reason": ""}]'])
    item = LiteratureItem(title="Scaling laws", source="arxiv", abstract=EVIDENCE)
    claims = {"k1": [Claim(key="k1", sentence="Scaling holds [cite:k1].")]}
    with record_support_verdicts() as records:
        await SupportChecker(llm=llm).check(claims, {"k1": item}, "en")
        await SupportChecker(llm=llm).check(claims, {"k1": item}, "en")
    assert [r["pass"] for r in records] == [0, 1]


async def test_run_nodes_merges_updates_and_accumulates_errors():
    async def first(state):
        return {"keywords": ["a"], "errors": ["e1"], "current_phase": Phase.LITERATURE}

    async def second(state):
        assert state.keywords == ["a"]
        return {"errors": ["e2"]}

    state = PaperState(task_id="t", topic="x", collab_mode="full_auto")
    with offline():
        final = await run_nodes(state, [first, second])
    assert final.keywords == ["a"]
    assert final.errors == ["e1", "e2"]
    assert final.current_phase == Phase.LITERATURE


async def test_offline_turns_db_and_progress_calls_into_no_ops():
    from backend.pipeline import graph

    with offline():
        await graph._save_phase_result("not-a-uuid", Phase.SCOPING, {})
        await graph.publish_progress("t", phase=1, status="running", message="m")
