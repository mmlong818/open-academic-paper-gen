from evals.sample_l3 import score, stratified_sample


def _records(n_unsupported: int, n_other: int) -> list[dict]:
    rows = [{"key": f"u{i}", "verdict": "unsupported"} for i in range(n_unsupported)]
    rows += [{"key": f"s{i}", "verdict": "supported" if i % 2 else "unclear"} for i in range(n_other)]
    return rows


def test_sample_takes_all_unsupported_under_cap_then_fills_with_others():
    picked = stratified_sample(_records(5, 100), n=50, max_unsupported=20, seed=0)
    assert len(picked) == 50
    assert sum(1 for r in picked if r["verdict"] == "unsupported") == 5


def test_sample_caps_unsupported_share():
    picked = stratified_sample(_records(80, 100), n=50, max_unsupported=20, seed=0)
    assert sum(1 for r in picked if r["verdict"] == "unsupported") == 20
    assert len(picked) == 50


def test_sample_is_reproducible_for_a_seed():
    rows = _records(30, 100)
    assert stratified_sample(rows, n=50, seed=7) == stratified_sample(rows, n=50, seed=7)


def test_sample_returns_everything_when_pool_is_small():
    assert len(stratified_sample(_records(2, 3), n=50)) == 5


def test_score_precision_and_recall_for_unsupported():
    predictions = {1: "unsupported", 2: "unsupported", 3: "supported", 4: "unclear", 5: "supported"}
    gold = {1: "unsupported", 2: "supported", 3: "unsupported", 4: "unclear", 5: "supported"}
    result = score(predictions, gold)
    assert result["labelled"] == 5
    assert result["unsupported_precision"] == 1 / 2
    assert result["unsupported_recall"] == 1 / 2
    assert result["agreement"] == 3 / 5
    assert result["confusion"]["unsupported"]["supported"] == 1  # predicted unsupported, gold supported


def test_score_ignores_unlabelled_rows():
    result = score({1: "supported", 2: "unsupported"}, {1: "supported", 2: None})
    assert result["labelled"] == 1
    assert result["unsupported_precision"] is None


async def test_rejudge_maps_batched_verdicts_back_to_row_ids():
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    from evals.sample_l3 import rejudge

    evidence = "Graph neural networks predict molecular properties from bonds and atoms. " * 5
    rows = [
        {"id": 7, "slug": "s", "key": "k1", "title": "T1", "context": "", "sentence": "A [cite:k1].",
         "evidence": evidence},
        {"id": 3, "slug": "s", "key": "k1", "title": "T1", "context": "", "sentence": "B [cite:k1].",
         "evidence": evidence},
        {"id": 5, "slug": "s", "key": "k2", "title": "T2", "context": "", "sentence": "C [cite:k2].",
         "evidence": "too short"},
    ]
    llm = FakeListChatModel(responses=[
        '[{"verdict": "supported", "reason": "a"}, {"verdict": "unsupported", "reason": "b"}]'
    ])
    predictions = await rejudge(rows, llm, language_of=lambda slug: "en")
    # k2 has too little evidence for a verdict, which counts as unclear, as in production
    assert predictions == {7: "supported", 3: "unsupported", 5: "unclear"}


def test_grade_scoring_counts_misaligned_as_a_warning_and_partial_on_its_own():
    from evals.sample_l3 import score_grades

    predictions = {1: "misaligned", 2: "unsupported", 3: "partial", 4: "supported", 5: "unsupported"}
    gold5 = {1: "unsupported", 2: "misaligned", 3: "partial", 4: "partial", 5: "partial"}
    result = score_grades(predictions, gold5)

    assert result["warn_precision"] == 2 / 3      # row 5 warned on a partly supported claim
    assert result["warn_recall"] == 1.0
    assert result["partial_precision"] == 1.0
    assert result["partial_recall"] == 1 / 3
    assert result["labelled"] == 5
