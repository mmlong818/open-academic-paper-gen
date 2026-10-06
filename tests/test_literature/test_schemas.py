import pytest
from backend.literature.schemas import LiteratureItem, SearchQuery


def test_literature_item_minimal():
    item = LiteratureItem(title="Test Paper", source="arxiv")
    assert item.title == "Test Paper"
    assert item.doi is None
    assert item.citation_count == 0
    assert item.quality_score == 0.0


def test_literature_item_full():
    item = LiteratureItem(
        title="Deep Learning Survey",
        authors=["LeCun, Y.", "Bengio, Y."],
        year=2015,
        doi="10.1038/nature14539",
        abstract="A survey of deep learning.",
        citation_count=50000,
        journal="Nature",
        source="semantic_scholar",
        source_id="abc123",
        url="https://doi.org/10.1038/nature14539",
    )
    assert item.year == 2015
    assert len(item.authors) == 2
    assert item.citation_count == 50000


def test_search_query_defaults():
    q = SearchQuery(keywords=["deep learning"], language="en")
    assert q.max_results == 10
    assert q.language == "en"


def test_literature_item_bibtex_key():
    from backend.literature.bibtex import bibtex_key
    item = LiteratureItem(
        title="Attention Is All You Need",
        authors=["Ashish Vaswani"],
        year=2017,
        source="semantic_scholar",
    )
    assert bibtex_key(item) == "Vaswani2017Attention"
