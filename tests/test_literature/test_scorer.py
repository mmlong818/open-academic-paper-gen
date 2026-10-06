import pytest
from backend.literature.schemas import LiteratureItem
from backend.literature.scorer import score_items, JOURNAL_TIERS


def _item(citation_count: int = 0, journal: str | None = None) -> LiteratureItem:
    return LiteratureItem(title="T", source="arxiv", citation_count=citation_count, journal=journal)


def test_high_citation_high_score():
    """Citations top out at 60 of the 100 points; journal and recency carry the rest."""
    item = _item(citation_count=10000)
    results = score_items([item])
    assert results[0].quality_score == 60.0


def test_zero_citation_low_score():
    item = _item(citation_count=0)
    results = score_items([item])
    assert results[0].quality_score < 50.0


def test_top_journal_boosts_score():
    item_plain = _item(citation_count=100)
    item_nature = _item(citation_count=100, journal="Nature")
    scored = score_items([item_plain, item_nature])
    assert scored[1].quality_score > scored[0].quality_score


def test_score_clamped_to_100():
    item = _item(citation_count=9999999, journal="Nature")
    results = score_items([item])
    assert results[0].quality_score <= 100.0


def test_journal_tiers_dict_exists():
    assert isinstance(JOURNAL_TIERS, dict)
    assert "Nature" in JOURNAL_TIERS
