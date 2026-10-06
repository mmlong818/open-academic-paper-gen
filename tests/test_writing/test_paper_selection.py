"""T2.1 — pick each section's papers by reading them, not by word overlap alone."""
from unittest.mock import AsyncMock, MagicMock

from backend.literature.schemas import LiteratureItem
from backend.writing.section_writer import SectionWriter, rerank_papers

SECTION = {"title": "Equivariant models", "summary": "E(3) equivariance for molecular property prediction"}


def _lit(n: int) -> list[LiteratureItem]:
    return [LiteratureItem(title=f"Paper {i} equivariant molecular", source="arxiv",
                           abstract=f"Abstract {i} about equivariant molecular models.") for i in range(n)]


def _llm(reply: str):
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content=reply))
    return llm


async def test_the_model_picks_and_orders_the_papers():
    lit = _lit(30)
    chosen = await rerank_papers(SECTION, lit, _llm("[7, 3, 12, 3, 99]"), "en", top_k=15)
    # duplicates and out-of-range indices are ignored
    assert [p.title for p in chosen] == ["Paper 7 equivariant molecular", "Paper 3 equivariant molecular",
                                         "Paper 12 equivariant molecular"]


async def test_prompt_lists_numbered_candidates_with_the_section_brief():
    llm = _llm("[0, 1, 2]")
    await rerank_papers(SECTION, _lit(30), llm, "en", top_k=15)
    prompt = llm.ainvoke.call_args.args[0]
    assert "Equivariant models" in prompt and "E(3) equivariance" in prompt
    assert "[0] Paper" in prompt and "15" in prompt


async def test_unusable_reply_falls_back_to_word_overlap():
    lit = _lit(30)
    for reply in ("not json", "[]", "[1]"):  # a single pick is too few to trust
        chosen = await rerank_papers(SECTION, lit, _llm(reply), "en", top_k=15)
        assert len(chosen) == 15


async def test_small_pools_skip_the_call():
    llm = _llm("[0]")
    chosen = await rerank_papers(SECTION, _lit(10), llm, "en", top_k=15)
    assert len(chosen) == 10
    llm.ainvoke.assert_not_called()


async def test_writer_uses_the_selector_only_when_given_one():
    writer_llm = _llm("Section text.")
    selector = _llm("[0, 1, 2, 3]")
    await SectionWriter(llm=writer_llm, selector_llm=selector).run(
        outline=[SECTION], synthesis="s", literature=_lit(30), language="en")
    assert selector.ainvoke.await_count == 1
    prompt = writer_llm.ainvoke.call_args.args[0]
    assert "Paper 3 equivariant" in prompt and "Paper 20 equivariant" not in prompt

    plain = _llm("Section text.")
    await SectionWriter(llm=plain).run(outline=[SECTION], synthesis="s", literature=_lit(30), language="en")
    assert plain.ainvoke.await_count == 1  # no selector call without a selector


def test_reranking_is_on_by_default():
    from backend.core.config import Settings

    assert Settings(_env_file=None).rerank_section_papers is True
