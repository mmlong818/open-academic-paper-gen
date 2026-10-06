"""The Methodology and Abstract describe the search the pipeline really ran, never an invented one.

A live review paper's Methodology claimed ACL Anthology, a January 2026 search date, two Boolean
query strings and 15 included studies; the pipeline had searched four other APIs with scoping
keywords and kept 202 papers. The writer had been asked for those details and given none.
"""
from backend.literature.schemas import LiteratureItem
from backend.writing.prisma import review_process_facts
from backend.writing.prompts import build_section_prompt

REPORT = {"total_before": 169, "removed_dup": 0, "excluded_by_llm": 27,
          "chained_candidates": 60, "chained_included": 51}


def _items() -> list[LiteratureItem]:
    return [
        LiteratureItem(title="a", source="semantic_scholar", year=2001),
        LiteratureItem(title="b", source="openalex", year=2026),
        LiteratureItem(title="c", source="arxiv", year=2023),
        LiteratureItem(title="d", source="openalex", year=2020),
    ]


def test_facts_name_the_real_sources_terms_counts_and_years():
    facts = review_process_facts(REPORT, _items(), ["Retrieval-augmented generation", "Dense passage retrieval"], "en")
    assert "Semantic Scholar" in facts and "OpenAlex" in facts and "arXiv" in facts
    assert "CrossRef" not in facts
    assert "Retrieval-augmented generation; Dense passage retrieval" in facts
    assert "Records identified through database searching: 169" in facts
    assert "Additional records identified through citation chaining: 60" in facts
    assert "Studies included: 4" in facts
    assert "2001–2026" in facts


def test_chinese_facts():
    facts = review_process_facts(REPORT, _items(), ["检索增强生成"], "zh")
    assert "检索增强生成" in facts and "最终纳入研究：4" in facts


def test_no_literature_no_facts():
    assert review_process_facts(REPORT, [], ["k"], "en") == ""


def _prompt(title: str, language: str = "en", facts: str = "FACTS-BLOCK") -> str:
    return build_section_prompt(
        section_title=title, outline_context="o", synthesis="s",
        literature_snippets=[], language=language, review_facts=facts,
    )


def test_sections_that_describe_the_method_get_the_facts_and_the_ban_on_inventing_more():
    # the Introduction is asked to outline the method too; left without facts it named ACL Anthology
    for title in ("Methodology", "Abstract", "1. Introduction"):
        prompt = _prompt(title)
        assert "FACTS-BLOCK" in prompt
        assert "Do not invent" in prompt


def test_other_sections_do_not_get_the_facts():
    assert "FACTS-BLOCK" not in _prompt("Discussion")


def test_methodology_without_facts_still_forbids_inventing_them():
    prompt = _prompt("Methodology", facts="")
    assert "Do not invent" in prompt


def test_chinese_methodology_gets_the_facts():
    prompt = _prompt("研究方法", language="zh")
    assert "FACTS-BLOCK" in prompt and "不得编造" in prompt
