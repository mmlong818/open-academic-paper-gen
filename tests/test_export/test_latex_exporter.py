import pytest
from backend.export.latex_exporter import LatexExporter
from backend.literature.bibtex import bibtex_key_from_dict

CITED = {
    "title": "Deep learning",
    "authors": ["LeCun, Y.", "Bengio, Y."],
    "year": 2015,
    "doi": "10.1038/nature14539",
    "journal": "Nature",
    "source": "semantic_scholar",
}
# The bibliography lists only papers actually cited in the body, so the fixture must cite one.
CITE_KEY = bibtex_key_from_dict(CITED)


def _make_state():
    return {
        "topic": "深度学习在医学影像中的应用",
        "language": "zh",
        "synthesis": "综合分析表明，深度学习在该领域取得了显著进展。",
        "outline": [
            {"title": "引言", "summary": "介绍背景。"},
            {"title": "相关工作", "summary": "综述方法。"},
            {"title": "结论", "summary": "总结贡献。"},
        ],
        "sections": {
            "引言": f"深度学习近年来在医学影像领域引起广泛关注 [cite:{CITE_KEY}]……",
            "相关工作": "早期工作主要依赖手工特征……",
            "结论": "本文系统综述了深度学习在医学影像中的应用……",
        },
        "verified_citations": [dict(CITED)],
    }


def test_latex_contains_document_class():
    exporter = LatexExporter()
    result = exporter.export(_make_state())
    assert "\\documentclass" in result


def test_latex_contains_topic_as_title():
    exporter = LatexExporter()
    result = exporter.export(_make_state())
    assert "深度学习在医学影像中的应用" in result
    assert "\\title" in result


def test_latex_contains_all_section_titles():
    exporter = LatexExporter()
    result = exporter.export(_make_state())
    assert "\\section{引言}" in result
    assert "\\section{相关工作}" in result
    assert "\\section{结论}" in result


def test_latex_contains_section_content():
    exporter = LatexExporter()
    result = exporter.export(_make_state())
    assert "深度学习近年来在医学影像领域引起广泛关注" in result


def test_latex_contains_bibliography():
    exporter = LatexExporter()
    result = exporter.export(_make_state())
    assert "\\bibitem" in result or "bibliography" in result.lower()


def test_latex_empty_sections_still_valid():
    exporter = LatexExporter()
    state = _make_state()
    state["sections"] = {}
    result = exporter.export(state)
    assert "\\documentclass" in result
    assert "\\end{document}" in result


def test_latex_ends_with_end_document():
    exporter = LatexExporter()
    result = exporter.export(_make_state())
    assert "\\end{document}" in result


def test_latex_multi_key_marker_becomes_one_cite_command():
    other = {"title": "Attention is all you need", "authors": ["Vaswani, A."], "year": 2017,
             "journal": "NeurIPS", "source": "arxiv"}
    other_key = bibtex_key_from_dict(other)
    state = _make_state()
    state["sections"]["引言"] = f"Both hold [cite:{CITE_KEY}, cite:{other_key}, cite:Ghost2099x]."
    state["verified_citations"] = [dict(CITED), other]
    result = LatexExporter().export(state)
    assert f"\\cite{{{CITE_KEY},{other_key}}} [?Ghost2099x]" in result
    assert f"\\bibitem{{{other_key}}}" in result
