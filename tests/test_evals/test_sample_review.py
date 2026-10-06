from evals.sample_review import context_of, precision, sample


def test_sample_is_reproducible_and_capped():
    comments = [{"slug": "s", "section": "A", "quote": f"q{i}"} for i in range(30)]
    assert sample(comments, n=20, seed=1) == sample(comments, n=20, seed=1)
    assert len(sample(comments, n=20)) == 20


def test_context_shows_text_around_the_quote():
    text = "x" * 500 + "THE QUOTE" + "y" * 500
    before, after = context_of(text, "THE QUOTE", width=100)
    assert before == "x" * 100 and after == "y" * 100


def test_precision_counts_valid_labels():
    rows = [{"gold": "valid"}, {"gold": "invalid"}, {"gold": "valid"}, {"gold": None}]
    assert precision(rows) == {"labelled": 3, "valid": 2, "precision": 2 / 3}
