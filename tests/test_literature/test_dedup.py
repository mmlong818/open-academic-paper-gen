import pytest
from backend.literature.schemas import LiteratureItem
from backend.literature.dedup import deduplicate


def _item(title: str, doi: str | None = None, source: str = "arxiv") -> LiteratureItem:
    return LiteratureItem(title=title, doi=doi, source=source)


def test_dedup_by_doi_keeps_first():
    items = [
        _item("Paper A", doi="10.1/abc"),
        _item("Paper A (duplicate)", doi="10.1/abc"),
        _item("Paper B", doi="10.2/xyz"),
    ]
    result = deduplicate(items)
    assert len(result) == 2
    assert result[0].title == "Paper A"


def test_dedup_by_title_normalisation():
    items = [
        _item("attention is all you need"),
        _item("Attention Is All You Need"),
        _item("Transformers Are Great"),
    ]
    result = deduplicate(items)
    assert len(result) == 2


def test_dedup_no_doi_falls_back_to_title():
    items = [
        _item("Unique Paper"),
        _item("Another Paper"),
    ]
    result = deduplicate(items)
    assert len(result) == 2


def test_dedup_empty_list():
    assert deduplicate([]) == []


def test_dedup_doi_with_no_doi_same_title():
    """有 DOI + 无 DOI 但同标题的论文应被去重（只保留第一个）。"""
    items = [
        _item("Attention Is All You Need", doi="10.1/abc"),
        _item("Attention Is All You Need", doi=None),  # 漏网漏洞修复
    ]
    result = deduplicate(items)
    assert len(result) == 1
    assert result[0].doi == "10.1/abc"


def test_dedup_doi_case_insensitive():
    """DOI 去重应大小写不敏感。"""
    items = [
        _item("Paper A", doi="10.1/ABC"),
        _item("Paper A", doi="10.1/abc"),
    ]
    result = deduplicate(items)
    assert len(result) == 1
