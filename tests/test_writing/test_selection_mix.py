"""Each section's papers keep at least half the mix's share of either language.

A Chinese review with 18 Chinese papers in its pool cited 24 papers, none Chinese.
"""
from unittest.mock import AsyncMock, MagicMock

from backend.literature.mix import ensure_minimum, is_chinese
from backend.literature.schemas import LiteratureItem
from backend.writing.section_writer import rerank_papers

SECTION = {"title": "检索增强生成 retrieval", "summary": "检索增强生成 retrieval augmented generation"}


def _en(n: int) -> list[LiteratureItem]:
    return [LiteratureItem(title=f"Retrieval augmented generation {i}", source="arxiv",
                           abstract="retrieval augmented generation " * 20) for i in range(n)]


def _zh(n: int) -> list[LiteratureItem]:
    return [LiteratureItem(title=f"检索增强生成研究{i}", source="crossref", abstract="检索增强生成。" * 60)
            for i in range(n)]


def test_a_short_language_replaces_the_lowest_ranked_picks():
    picks, extra_zh = _en(15), _zh(5)
    fixed = ensure_minimum(picks, picks + extra_zh, "balanced")
    assert len(fixed) == 15
    assert sum(is_chinese(p) for p in fixed) == 4  # half of 7.5, rounded
    assert fixed[:11] == picks[:11]  # the best-ranked picks stay
    assert fixed[11:] == extra_zh[:4]


def test_minimums_follow_the_mix():
    picks = _en(15)
    assert sum(is_chinese(p) for p in ensure_minimum(picks, picks + _zh(10), "zh_major")) == 5
    assert sum(is_chinese(p) for p in ensure_minimum(picks, picks + _zh(10), "en_major")) == 2
    zh_picks = _zh(15)
    assert sum(not is_chinese(p) for p in ensure_minimum(zh_picks, zh_picks + _en(10), "zh_major")) == 2


def test_no_candidates_no_change():
    picks = _en(15)
    assert ensure_minimum(picks, picks, "balanced") == picks


async def test_the_model_s_picks_are_topped_up_to_the_minimum():
    literature = _en(40) + _zh(10)
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content=str(list(range(15)))))
    chosen = await rerank_papers(SECTION, literature, llm, "zh", top_k=15, source_mix="balanced")
    assert len(chosen) == 15 and sum(is_chinese(p) for p in chosen) >= 4
    # the candidates the model saw reserved room for Chinese papers
    prompt = llm.ainvoke.call_args.args[0]
    assert "检索增强生成研究" in prompt


# D1: the candidates' Chinese papers were there, yet a Chinese review cited none of them.

from backend.literature.mix import required_citations
from backend.writing.prompts import build_section_prompt


def test_required_citations_follow_the_mix_and_the_candidates():
    picks = _en(11) + _zh(4)
    assert required_citations(picks, "balanced") == {"zh": 4, "en": 4}
    assert required_citations(_en(13) + _zh(2), "balanced") == {"zh": 2, "en": 4}  # only two to cite
    assert required_citations(_en(15), "balanced") == {"zh": 0, "en": 4}


def _section_prompt(language: str, required: dict | None) -> str:
    return build_section_prompt(section_title="正文", outline_context="o", synthesis="s", literature_snippets=[],
                                language=language, required_citations=required)


def test_the_prompt_demands_the_required_chinese_citations():
    zh = _section_prompt("zh", {"zh": 4, "en": 4})
    assert "至少引用 4 篇中文文献" in zh and "至少引用 4 篇英文文献" in zh
    en = _section_prompt("en", {"zh": 2, "en": 0})
    assert "cite at least 2 Chinese-language" in en and "English-language" not in en


def test_no_requirement_no_line():
    assert "至少引用" not in _section_prompt("zh", {"zh": 0, "en": 0})
    assert "至少引用" not in _section_prompt("zh", None)


def test_the_abstract_stays_free_of_citations():
    # the abstract is written without citations; the requirement once gave it fifteen
    prompt = build_section_prompt(section_title="摘要", outline_context="o", synthesis="s", literature_snippets=[],
                                  language="zh", required_citations={"zh": 4, "en": 4})
    assert "至少引用" not in prompt
