from evals.sample_uncited import neighbourhood, precision, sample


def test_sample_is_reproducible_and_capped():
    flagged = [{"slug": "s", "section": "A", "sentence": f"s{i}", "reason": ""} for i in range(40)]
    assert sample(flagged, n=30, seed=3) == sample(flagged, n=30, seed=3)
    assert len(sample(flagged, n=30)) == 30
    assert len(sample(flagged[:5], n=30)) == 5


def test_neighbourhood_gives_two_sentences_either_side():
    text = "One is first. Two follows. Three is it. Four comes. Five ends. Six trails."
    before, after = neighbourhood(text, "Three is it.")
    assert before == "One is first. Two follows."
    assert after == "Four comes. Five ends."


def test_precision_counts_only_labelled_rows():
    rows = [{"gold": "needs_citation"}, {"gold": "no"}, {"gold": "needs_citation"}, {"gold": None}]
    assert precision(rows) == {"labelled": 3, "needs_citation": 2, "precision": 2 / 3}


def test_compare_with_labels_tracks_what_a_new_prompt_keeps():
    from evals.sample_uncited import compare_with_labels

    labelled = [
        {"slug": "a", "sentence": "tp1", "gold": "needs_citation"},
        {"slug": "a", "sentence": "tp2", "gold": "needs_citation"},
        {"slug": "a", "sentence": "fp1", "gold": "no"},
        {"slug": "b", "sentence": "fp2", "gold": "no"},
    ]
    new_flags = [
        {"slug": "a", "sentence": "tp1"}, {"slug": "b", "sentence": "fp2"},
        {"slug": "b", "sentence": "fresh"},
    ]
    result, unlabelled = compare_with_labels(labelled, new_flags)
    assert result == {"true_kept": 1, "true_total": 2, "false_kept": 1, "false_total": 2,
                      "new_flags": 3, "unlabelled_flags": 1}
    assert unlabelled == [{"slug": "b", "sentence": "fresh"}]
