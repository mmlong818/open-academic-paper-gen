"""T1.2 — constrained revision of sentences that verification flagged.

Each paragraph holding a flagged sentence (a claim its source does not support, or a
factual statement with no citation) goes to the writer once. The reply is kept only if
it passes deterministic checks: no citation keys beyond the section's candidates, and
the unflagged sentences left as they were. Whether a revision actually fixed anything
is decided afterwards by running verification again, not by trusting the writer.
"""
import asyncio
import logging
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

from backend.literature.bibtex import bibtex_key, iter_cite_keys
from backend.literature.schemas import LiteratureItem
from backend.verification.orchestrator import prose_sentences
from backend.writing.prompts import build_revision_prompt
from backend.writing.section_writer import select_relevant_papers

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

# Share of unflagged sentences a revision must keep verbatim; below this it rewrote the paragraph.
_MIN_KEPT_SHARE = 0.8
_CANDIDATE_ABSTRACT_CHARS = 500


@dataclass(frozen=True)
class Problem:
    section: str
    sentence: str
    kind: str  # "unsupported" | "uncited"
    reason: str


@dataclass
class Revision:
    id: int
    section: str
    before: str
    after: str
    problems: list[dict] = field(default_factory=list)
    # proposed -> applied (full_auto) or accepted (user, key_gates); rejected if a check failed
    status: str = "proposed"
    note: str = ""
    # set after re-verification: did the flagged problems go away?
    resolved: bool | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _paragraphs(text: str) -> list[str]:
    return text.split("\n\n")


def group_by_paragraph(
    sections: dict[str, str], problems: list[Problem]
) -> dict[tuple[str, int], list[Problem]]:
    """Problems keyed by (section, paragraph index); ones whose sentence cannot be found are dropped."""
    groups: dict[tuple[str, int], list[Problem]] = {}
    for problem in problems:
        paragraphs = _paragraphs(sections.get(problem.section, ""))
        index = next((i for i, p in enumerate(paragraphs) if problem.sentence in p), None)
        if index is not None:
            groups.setdefault((problem.section, index), []).append(problem)
    return groups


def check_revision(
    before: str, after: str, problems: list[Problem], allowed_keys: set[str]
) -> tuple[bool, str]:
    """Deterministic gate on a writer reply: (ok, why-not)."""
    if not after.strip() or after.strip() == before.strip():
        return False, "no change"
    invented = set(iter_cite_keys(after)) - set(iter_cite_keys(before)) - allowed_keys
    if invented:
        return False, f"cites keys outside the candidates: {', '.join(sorted(invented))}"
    flagged = {p.sentence for p in problems}
    unflagged = [s for s in prose_sentences(before) if s not in flagged]
    kept = sum(1 for s in unflagged if s in after)
    if unflagged and kept / len(unflagged) < _MIN_KEPT_SHARE:
        return False, f"rewrote unflagged sentences ({kept}/{len(unflagged)} kept)"
    return True, ""


def apply_revisions(sections: dict[str, str], revisions: list[dict]) -> dict[str, str]:
    """Sections with each revision's paragraph swapped in (first occurrence only)."""
    revised = dict(sections)
    for r in revisions:
        text = revised.get(r["section"], "")
        if r["before"] in text:
            revised[r["section"]] = text.replace(r["before"], r["after"], 1)
    return revised


class RevisionAgent:
    def __init__(self, llm: "ChatOpenAI") -> None:
        self._llm = llm
        self._semaphore = asyncio.Semaphore(3)

    async def propose(
        self,
        sections: dict[str, str],
        problems: list[Problem],
        literature: list[LiteratureItem],
        outline: list[dict],
        language: str,
    ) -> list[Revision]:
        groups = group_by_paragraph(sections, problems)
        outline_by_title = {item.get("title"): item for item in outline}
        results = await asyncio.gather(*[
            self._revise(
                section, _paragraphs(sections[section])[index], group,
                select_relevant_papers(outline_by_title.get(section, {"title": section}), literature),
                language,
            )
            for (section, index), group in groups.items()
        ])
        revisions = [r for r in results if r is not None]
        for i, revision in enumerate(revisions, 1):
            revision.id = i
        return revisions

    async def _revise(
        self,
        section: str,
        paragraph: str,
        problems: list[Problem],
        candidates: list[LiteratureItem],
        language: str,
    ) -> Revision | None:
        allowed = {bibtex_key(item) for item in candidates}
        try:
            prompt = build_revision_prompt(
                paragraph, _problems_block(problems), _candidates_block(candidates), language
            )
            async with self._semaphore:
                response = await self._llm.ainvoke(prompt)
            after = _strip_fences(response.content)
        except Exception as exc:  # a failed revision must never sink verification
            logger.warning("[revision] section %r paragraph failed: %s", section, exc)
            return None
        ok, why = check_revision(paragraph, after, problems, allowed)
        return Revision(
            id=0, section=section, before=paragraph, after=after,
            problems=[{"sentence": p.sentence, "kind": p.kind, "reason": p.reason} for p in problems],
            status="proposed" if ok else "rejected", note=why,
        )


def _problems_block(problems: list[Problem]) -> str:
    return "\n".join(f"- [{p.kind}] {p.sentence}\n  {p.reason}" for p in problems)


def _candidates_block(candidates: list[LiteratureItem]) -> str:
    lines = []
    for item in candidates:
        abstract = (item.abstract or "").strip()[:_CANDIDATE_ABSTRACT_CHARS]
        lines.append(f"- {bibtex_key(item)}: {item.title}\n  {abstract}")
    return "\n".join(lines) or "(none)"


def _strip_fences(raw) -> str:
    text = (raw if isinstance(raw, str) else "").strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text.split("\n", 1)[1] if "\n" in text else text
    return text.strip()
