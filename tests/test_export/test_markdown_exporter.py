import pytest
from backend.export.markdown_exporter import MarkdownExporter
from backend.literature.bibtex import bibtex_key_from_dict

CITED = {
    "title": "Deep learning",
    "authors": ["LeCun, Y."],
    "year": 2015,
    "doi": "10.1038/nature14539",
    "journal": "Nature",
    "source": "semantic_scholar",
}
# References list only papers actually cited in the body, so the fixture must cite one.
CITE_KEY = bibtex_key_from_dict(CITED)


def _make_state():
    return {
        "topic": "深度学习在医学影像中的应用",
        "language": "zh",
        "synthesis": "综合分析表明深度学习在该领域取得了显著进展。",
        "outline": [
            {"title": "引言", "summary": "介绍背景。"},
            {"title": "结论", "summary": "总结贡献。"},
        ],
        "sections": {
            "引言": f"深度学习近年来引起广泛关注 [cite:{CITE_KEY}]……",
            "结论": "本文系统综述了深度学习的应用……",
        },
        "verified_citations": [dict(CITED)],
    }


def test_markdown_starts_with_h1_title():
    exporter = MarkdownExporter()
    result = exporter.export(_make_state())
    assert result.startswith("# 深度学习在医学影像中的应用")


def test_markdown_contains_section_headers():
    exporter = MarkdownExporter()
    result = exporter.export(_make_state())
    assert "## 1. 引言" in result
    assert "## 2. 结论" in result


def test_markdown_contains_section_content():
    exporter = MarkdownExporter()
    result = exporter.export(_make_state())
    assert "深度学习近年来引起广泛关注" in result


def test_markdown_contains_references_section():
    exporter = MarkdownExporter()
    result = exporter.export(_make_state())
    assert "## 参考文献" in result or "## References" in result


def test_markdown_citation_contains_doi_link():
    exporter = MarkdownExporter()
    result = exporter.export(_make_state())
    assert "10.1038/nature14539" in result


def test_markdown_empty_sections_still_valid():
    exporter = MarkdownExporter()
    state = _make_state()
    state["sections"] = {}
    result = exporter.export(state)
    assert result.startswith("# ")
    assert len(result) > 10


def test_markdown_follows_outline_order():
    exporter = MarkdownExporter()
    result = exporter.export(_make_state())
    idx_intro = result.index("## 1. 引言")
    idx_conclusion = result.index("## 2. 结论")
    assert idx_intro < idx_conclusion


OTHER = {"title": "Attention is all you need", "authors": ["Vaswani, A."], "year": 2017,
         "journal": "NeurIPS", "source": "arxiv"}
OTHER_KEY = bibtex_key_from_dict(OTHER)


def _multi_key_state(marker: str) -> dict:
    state = _make_state()
    state["sections"]["引言"] = f"两项工作都成立 {marker}。"
    state["verified_citations"] = [dict(CITED), dict(OTHER)]
    return state


def test_markdown_multi_key_marker_resolves_every_key():
    result = MarkdownExporter().export(_multi_key_state(f"[cite:{CITE_KEY}, cite:{OTHER_KEY}]"))
    assert "两项工作都成立 [1, 2]" in result
    assert "[?" not in result
    assert "Attention is all you need" in result  # both papers reach the reference list


def test_markdown_multi_key_marker_flags_only_the_unresolved_key():
    result = MarkdownExporter().export(_multi_key_state(f"[cite:{CITE_KEY}, cite:Ghost2099x]"))
    assert "两项工作都成立 [1, ?Ghost2099x]" in result
