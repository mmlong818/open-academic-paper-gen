import json
import logging
import re
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

from backend.core.config import settings
from backend.core.llm import fast_llm, strong_llm
from backend.literature.bibtex import bibtex_key
from backend.literature.mix import ensure_minimum, required_citations, take_by_mix
from backend.literature.schemas import LiteratureItem
from backend.writing.evidence_table import evidence_line
from backend.writing.prompts import (
    authors_str_for_apa,
    build_paper_selection_prompt,
    build_section_prompt,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI

_TOP_K = 15
_STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or", "is",
    "are", "was", "were", "be", "been", "with", "that", "this", "it", "as",
    "by", "from", "its", "their", "which", "have", "has", "had", "but", "not",
    "一", "的", "了", "在", "是", "和", "与", "对", "为", "中", "等", "也",
    "及", "其", "该", "这", "那", "之", "从", "于", "而", "被", "将",
}


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z一-鿿]+", text.lower())
    return {w for w in words if len(w) > 1 and w not in _STOPWORDS}


def _relevance_score(section_tokens: set[str], item: LiteratureItem) -> int:
    candidate = _tokenize(
        (item.title or "") + " " + (item.abstract or "")
    )
    return len(section_tokens & candidate)


def select_relevant_papers(
    section: dict,
    literature: list[LiteratureItem],
    top_k: int = _TOP_K,
    source_mix: str | None = None,
) -> list[LiteratureItem]:
    if len(literature) <= top_k:
        return literature
    section_text = section.get("title", "") + " " + section.get("summary", "")
    tokens = _tokenize(section_text)
    # A review outline built on the citation graph names the groups a section draws on;
    # their papers come first, then word overlap fills the rest.
    grouped = set(section.get("cluster_keys") or [])
    # Among equally relevant papers, those with an abstract or text come first: a title
    # alone gives the writer nothing to report and layer 3 nothing to check.
    scored = sorted(
        literature,
        key=lambda item: (bibtex_key(item) in grouped, _relevance_score(tokens, item) if tokens else 0,
                          bool((item.abstract or item.body_excerpt or "").strip())),
        reverse=True,
    )
    if source_mix:
        # reserve room for the less represented language before the cut
        return take_by_mix(scored, top_k, source_mix)
    return scored[:top_k]


# Word overlap pre-selects this many; the model then picks up to _TOP_K of them.
_PRESELECT = 40
# Fewer picks than this is a reply not worth trusting over word overlap.
_MIN_PICKS = 3
_CANDIDATE_ABSTRACT_CHARS = 220


async def rerank_papers(
    section: dict,
    literature: list[LiteratureItem],
    llm: "ChatOpenAI",
    language: str,
    top_k: int = _TOP_K,
    source_mix: str | None = None,
) -> list[LiteratureItem]:
    """Word overlap narrows the pool, then the model picks and orders the section's papers.

    Word overlap misses paraphrase and can hand a section fifteen papers making one point.
    Any unusable reply falls back to the overlap ranking.
    """
    pre = select_relevant_papers(section, literature, top_k=_PRESELECT, source_mix=source_mix)
    if len(pre) <= top_k:
        return pre
    block = "\n".join(
        f"[{i}] {p.title} ({p.year or 'n.d.'}) - {(p.abstract or '')[:_CANDIDATE_ABSTRACT_CHARS]}"
        for i, p in enumerate(pre)
    )
    prompt = build_paper_selection_prompt(
        section.get("title", ""), section.get("summary", ""), block, top_k, language
    )
    try:
        response = await llm.ainvoke(prompt)
        picks = _parse_picks(response.content, len(pre))
    except Exception as exc:  # selection must never stop a section from being written
        logger.warning("Paper selection for '%s' failed: %s", section.get("title"), exc)
        picks = []
    chosen = pre[:top_k] if len(picks) < _MIN_PICKS else [pre[i] for i in picks[:top_k]]
    return ensure_minimum(chosen, pre, source_mix) if source_mix else chosen


def _parse_picks(raw, n: int) -> list[int]:
    text = (raw if isinstance(raw, str) else "").strip()
    match = re.search(r"\[[\d,\s]*\]", text)
    if not match:
        return []
    picks: list[int] = []
    for value in json.loads(match.group(0)):
        if isinstance(value, int) and 0 <= value < n and value not in picks:
            picks.append(value)
    return picks

def _to_lit_dict(item: LiteratureItem, row: dict | None = None, language: str = "en") -> dict:
    return {
        "evidence": evidence_line(row, language) if row else "",
        "title": item.title or "",
        "authors_str": authors_str_for_apa(item.authors),
        "year": item.year or "n.d.",
        "journal": item.source or "",
        "doi": item.doi or "",
        "abstract": item.abstract or "",
        "body_excerpt": item.body_excerpt or "",
    }


def section_selector_llm() -> "ChatOpenAI | None":
    """The model that picks each section's papers, or None for word overlap alone."""
    # reasoning models spend part of the budget thinking before they answer
    return fast_llm(max_tokens=4096) if settings.rerank_section_papers else None


class SectionWriter:
    def __init__(self, llm: "ChatOpenAI | None" = None, selector_llm: "ChatOpenAI | None" = None) -> None:
        self._llm = llm if llm is not None else strong_llm(max_tokens=6144)
        # T2.1: with a selector each section's papers are picked by a model reading them;
        # without one, word overlap alone decides, as before.
        self._selector_llm = selector_llm

    def _outline_context(self, outline: list[dict]) -> str:
        return "\n".join(f"- {item['title']}: {item.get('summary', '')}" for item in outline)

    async def _write_section(
        self,
        section: dict,
        outline_context: str,
        synthesis: str,
        literature: list[LiteratureItem],
        language: str,
        angle: dict | None = None,
        review_facts: str = "",
        source_mix: str | None = None,
        evidence: dict[str, dict] | None = None,
    ) -> str:
        if self._selector_llm is not None:
            relevant = await rerank_papers(section, literature, self._selector_llm, language, source_mix=source_mix)
        else:
            pre = select_relevant_papers(section, literature, top_k=_PRESELECT, source_mix=source_mix)
            relevant = ensure_minimum(pre[:_TOP_K], pre, source_mix) if source_mix else pre[:_TOP_K]
        rows = evidence or {}
        lit_dicts = [_to_lit_dict(item, rows.get(bibtex_key(item)), language) for item in relevant]
        cite_keys = [bibtex_key(item) for item in relevant]
        snippets = [
            (item.body_excerpt or item.abstract)
            for item in relevant
            if (item.body_excerpt or item.abstract or "").strip()
        ]

        prompt = build_section_prompt(
            section_title=section["title"],
            outline_context=outline_context,
            synthesis=synthesis,
            literature_snippets=snippets,
            cite_keys=cite_keys,
            language=language,
            angle=angle,
            lit_items=lit_dicts,
            review_facts=review_facts,
            required_citations=required_citations(relevant, source_mix) if source_mix else None,
        )
        try:
            response = await self._llm.ainvoke(prompt)
            return response.content.strip()
        except Exception as e:
            err = str(e)
            if "401" in err or "AuthenticationError" in type(e).__name__ or "api_key" in err.lower():
                raise RuntimeError(f"LLM API key 无效，请检查 .env 文件: {e}") from e
            logger.warning("Section '%s' failed: %s", section["title"], e)
            return f"__SECTION_FAILED__{section['title']}"

    async def run(
        self,
        outline: list[dict],
        synthesis: str,
        literature: list[LiteratureItem],
        language: str,
        angle: dict | None = None,
        on_section_done: Callable[[dict[str, str]], Coroutine[Any, Any, None]] | None = None,
        review_facts: str = "",
        source_mix: str | None = None,
        evidence: dict[str, dict] | None = None,
    ) -> dict[str, str]:
        if not outline:
            return {}

        outline_context = self._outline_context(outline)
        sections: dict[str, str] = {}

        for section in outline:
            content = await self._write_section(
                section=section,
                outline_context=outline_context,
                synthesis=synthesis,
                literature=literature,
                language=language,
                angle=angle,
                review_facts=review_facts,
                source_mix=source_mix,
                evidence=evidence,
            )
            sections[section["title"]] = content
            if on_section_done:
                await on_section_done(dict(sections))

        return sections
