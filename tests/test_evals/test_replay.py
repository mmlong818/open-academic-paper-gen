import json
from unittest.mock import patch

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from backend.literature.bibtex import bibtex_key
from backend.literature.schemas import LiteratureItem
from backend.pipeline.states import PaperState, Phase
from evals.replay import replay_one

PAPER = {
    "title": "Scaling laws for neural language models",
    "authors": ["Kaplan, J."],
    "year": 2020,
    "source": "arxiv",
    "abstract": "Language model loss scales as a power law with model size and data. " * 6,
}
KEY = bibtex_key(LiteratureItem(**PAPER))


def _fixture(tmp_path):
    state = PaperState(
        task_id="t1", topic="scaling", language="en", collab_mode="full_auto",
        paper_type="general", current_phase=Phase.WRITING, literature=[PAPER],
        synthesis="s", outline=[{"title": "Introduction", "summary": "scaling laws"}],
        # stale downstream output a fixture must never carry into the replay
        sections={"Old": "stale"},
    )
    path = tmp_path / "scaling.json"
    path.write_text(json.dumps({"meta": {}, "state": state.model_dump(mode="json")}), encoding="utf-8")
    return path


async def test_replay_runs_writing_to_export_and_scores_it(tmp_path):
    writer = FakeListChatModel(responses=[
        f"Loss follows a power law [cite:{KEY}]. Bigger is better [cite:ghost2099]."
    ])
    judge = FakeListChatModel(responses=['[{"verdict": "unsupported", "reason": "r"}]'])

    def fake_get_llm(step, *args, **kwargs):
        assert step == "writing", "verification must not go through the zhipu-first router"
        return writer

    with (
        patch("backend.pipeline.graph.get_llm", side_effect=fake_get_llm),
        patch("backend.pipeline.verify_and_revise.fast_llm", return_value=judge),
        patch("backend.pipeline.verify_and_revise.settings.revise_flagged_claims", False),
    ):
        run = await replay_one(_fixture(tmp_path))

    m = run["metrics"]
    assert "Old" not in run["sections"]
    assert m["cited_keys"] == 2
    assert m["hallucinated_keys"] == 1
    assert m["hallucinated_key_rate"] == 0.5
    assert m["claims_judged"] == 1
    assert m["unsupported_rate"] == 1.0
    assert m["llm_calls"] == 2  # every sentence cites something, so the uncited check makes no call
    assert m["uncited_claims"] == 0
    assert run["uncited_claims"] == []
    assert run["verdicts"][0]["key"] == KEY


async def test_replay_turns_the_uncited_check_on(tmp_path):
    """The uncited check ships disabled; the eval must measure it anyway."""
    writer = FakeListChatModel(responses=["Output fell 12% in mandated firms. Growth resumed later."])
    judge = FakeListChatModel(responses=['[{"id": 0, "reason": "specific statistic"}]'])

    with (
        patch("backend.pipeline.graph.get_llm", return_value=writer),
        patch("backend.pipeline.verify_and_revise.fast_llm", return_value=judge),
        patch("backend.pipeline.verify_and_revise.settings.revise_flagged_claims", False),
    ):
        run = await replay_one(_fixture(tmp_path))

    assert run["metrics"]["uncited_claims"] == 1
    assert run["uncited_claims"][0]["sentence"] == "Output fell 12% in mandated firms."


async def test_replay_measures_problems_before_and_after_revision(tmp_path):
    sentence = f"Loss follows a power law [cite:{KEY}]."
    fixed = f"Loss often follows a power law in reported settings [cite:{KEY}]."
    writer = FakeListChatModel(responses=[sentence])
    reviser = FakeListChatModel(responses=[fixed])
    judge = FakeListChatModel(responses=[
        '[{"verdict": "unsupported", "reason": "overstated"}]',  # first pass
        '[{"verdict": "supported", "reason": "ok"}]',  # after revision
    ])

    def fake_get_llm(step, *args, **kwargs):
        return writer if step == "writing" else reviser

    with (
        patch("backend.pipeline.graph.get_llm", side_effect=fake_get_llm),
        patch("backend.pipeline.verify_and_revise.get_llm", return_value=reviser),
        patch("backend.pipeline.verify_and_revise.fast_llm", return_value=judge),
    ):
        run = await replay_one(_fixture(tmp_path))

    m = run["metrics"]
    assert m["claims_unsupported_before_revision"] == 1
    assert m["claims_unsupported"] == 0
    assert m["revisions_applied"] == 1 and m["revisions_resolved"] == 1
    assert fixed in run["sections"]["Introduction"]
    assert all(v["pass"] == 1 for v in run["verdicts"])  # sampling sees only the final pass


def test_apply_overrides_parses_to_the_setting_type():
    from backend.core.config import settings
    from evals.replay import apply_overrides

    before = settings.rerank_section_papers
    try:
        assert apply_overrides(["rerank_section_papers=true"]) == {"rerank_section_papers": True}
        assert settings.rerank_section_papers is True
    finally:
        settings.rerank_section_papers = before


def test_from_outline_clears_the_outline_and_taxonomy_too(tmp_path):
    from evals.replay import load_fixture

    path = _fixture(tmp_path)
    assert load_fixture(path).outline  # writing-onwards replays keep the frozen outline
    state = load_fixture(path, from_outline=True)
    assert state.outline == [] and state.taxonomy is None and state.current_phase == Phase.OUTLINE
