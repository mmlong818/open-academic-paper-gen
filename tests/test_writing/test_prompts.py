from backend.writing.prompts import (
    build_scoping_prompt,
    build_synthesis_prompt,
    build_outline_prompt,
    build_section_prompt,
)


def test_scoping_prompt_contains_topic():
    prompt = build_scoping_prompt(topic="深度学习在医学影像中的应用", language="zh")
    assert "深度学习在医学影像中的应用" in prompt
    assert "research_questions" in prompt or "研究问题" in prompt


def test_synthesis_prompt_contains_abstracts():
    abstracts = ["摘要1：深度学习", "摘要2：卷积网络"]
    prompt = build_synthesis_prompt(topic="深度学习", abstracts=abstracts, language="zh")
    assert "摘要1" in prompt
    assert "摘要2" in prompt


def test_outline_prompt_contains_synthesis():
    prompt = build_outline_prompt(
        topic="深度学习",
        synthesis="综合分析表明...",
        research_questions=["RQ1", "RQ2"],
        language="zh",
    )
    assert "综合分析表明" in prompt
    assert "RQ1" in prompt


def test_section_prompt_contains_section_title():
    prompt = build_section_prompt(
        section_title="相关工作",
        outline_context="本文包含以下章节...",
        synthesis="综合分析...",
        literature_snippets=["文献1摘要", "文献2摘要"],
        language="zh",
    )
    assert "相关工作" in prompt
    assert "文献1摘要" in prompt


def test_prompts_support_english():
    prompt = build_scoping_prompt(topic="deep learning in medical imaging", language="en")
    assert "deep learning in medical imaging" in prompt
