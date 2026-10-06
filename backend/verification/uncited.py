"""T1.1 — uncited claims: factual statements that carry no citation at all.

Layer 3 only sees sentences that cite something, so a figure or finding stated with no
marker slips past every other check. One LLM call per section lists the sentences that
need a source. Like layer 3 this only ever warns, and an unparseable reply or an LLM
error yields nothing rather than a guess.
"""
import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from backend.core.config import settings
from backend.literature.bibtex import iter_cite_keys
from backend.verification.orchestrator import prose_sentences
from backend.writing.prompts import build_uncited_prompt

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

# Fragments shorter than this ("See Table 2.") are not statements worth judging.
_MIN_SENTENCE_CHARS = 20
# Sections that by convention restate the paper's own findings or procedure rather than the
# literature's: on the first labelled sample every flag in them was a false alarm.
_SKIPPED_TITLES = ("abstract", "摘要", "conclusion", "结论", "method", "方法")


@dataclass(frozen=True)
class UncitedClaim:
    section: str
    sentence: str
    reason: str

    def as_dict(self) -> dict:
        return asdict(self)


class UncitedClaimChecker:
    def __init__(self, llm: "ChatOpenAI | None" = None) -> None:
        self._llm = llm
        self._semaphore = asyncio.Semaphore(4)

    async def check(self, sections: dict[str, str], language: str = "en") -> list[UncitedClaim]:
        if not settings.verify_uncited_claims or self._llm is None:
            return []
        results = await asyncio.gather(*[
            self._check_section(title, text, language)
            for title, text in sections.items()
            if not _is_skipped(title) and not text.startswith("__SECTION_FAILED__")
        ])
        return [claim for section_claims in results for claim in section_claims]

    async def _check_section(self, title: str, text: str, language: str) -> list[UncitedClaim]:
        sentences = prose_sentences(text)
        candidates = {
            i: s for i, s in enumerate(sentences)
            if len(s) >= _MIN_SENTENCE_CHARS and not any(iter_cite_keys(s))
        }
        if not candidates:
            return []

        block = "\n".join(f"[{i}] {s}" if i in candidates else f"· {s}" for i, s in enumerate(sentences))
        try:
            async with self._semaphore:
                response = await self._llm.ainvoke(build_uncited_prompt(title, block, language))
            flagged = _parse_flags(response.content)
        except Exception as exc:  # this check must never be the reason verification dies
            logger.warning("[uncited] section %r check failed: %s", title, exc)
            return []
        return [UncitedClaim(title, candidates[i], reason) for i, reason in flagged if i in candidates]


def _is_skipped(title: str) -> bool:
    return any(word in title.lower() for word in _SKIPPED_TITLES)


def _parse_flags(raw) -> list[tuple[int, str]]:
    text = (raw if isinstance(raw, str) else "").strip()
    if text.startswith("```"):
        text = text.split("```")[1].removeprefix("json").strip()
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        logger.warning("[uncited] unparseable reply: %.120s", raw)
        return []
    if not isinstance(data, list):
        return []
    flags = []
    for entry in data:
        if isinstance(entry, dict) and isinstance(entry.get("id"), int):
            flags.append((entry["id"], str(entry.get("reason", "")).strip()))
    return flags
