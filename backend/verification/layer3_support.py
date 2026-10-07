"""Layer 3 — citation support: does the cited paper actually say what the sentence claims?

Layer 1 asks whether a cited work exists. This layer asks whether it supports the claim
attached to it — a real paper hung on a sentence it never argues passes a clean DOI check,
and a reader cannot catch it without opening the source.

Verdicts degrade towards silence: too little evidence text, an unparseable reply or an LLM
error all yield no verdict at all, matching layer 1's "cannot verify != invalid" policy.
Nothing here ever removes a citation; unsupported claims are warnings for a human to settle.
"""
import asyncio
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from backend.core.config import settings
from backend.core.llm import fast_llm
from backend.literature.schemas import LiteratureItem
from backend.literature.text_length import weighted_length
from backend.verification.evidence import claim_pages, select_evidence
from backend.writing.prompts import build_support_prompt

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

SUPPORTED = "supported"
UNSUPPORTED = "unsupported"
UNCLEAR = "unclear"
# finer grades, asked for only when settings.l3_fine_grades is on
PARTIAL = "partial"          # the core holds, a part is overstated: a note, not a warning
MISALIGNED = "misaligned"    # the source's finding runs the other way: warns like unsupported
_VERDICTS = (SUPPORTED, UNSUPPORTED, UNCLEAR, PARTIAL, MISALIGNED)
WARNS = (UNSUPPORTED, MISALIGNED)

# Below this much source text there is nothing worth judging against.
MIN_EVIDENCE_CHARS = 200
_MAX_EVIDENCE_CHARS = 4000
# Claims judged per call. A paper cited more often is judged in several calls, each with its own
# evidence: capped at six, 10 of 92 citations of a real review went unjudged.
_CLAIMS_PER_CALL = 6
# Reasoning models spend output tokens thinking first: at 1024 a six-claim batch came
# back empty (finish_reason=length, all 1024 tokens spent on reasoning).
SUPPORT_MAX_TOKENS = 4096


@dataclass(frozen=True)
class Claim:
    """A sentence carrying a [cite:KEY] marker, with the sentence before it as context."""

    key: str
    sentence: str
    context: str = ""


@dataclass(frozen=True)
class SupportVerdict:
    claim: Claim
    verdict: str
    reason: str
    # PDF page of the passage best matching the claim (5.1); shown in the verification panel only
    pages: tuple[int, ...] = ()


def _parse_verdicts(raw: str, expected: int) -> list[tuple[str, str]]:
    """Parse the model's JSON array. Anything unrecognised becomes UNCLEAR, which warns nobody."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text.removeprefix("json")
        text = text.strip()

    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        logger.warning("[layer3] unparseable support reply: %.120s", raw)
        return [(UNCLEAR, "")] * expected

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return [(UNCLEAR, "")] * expected

    parsed: list[tuple[str, str]] = []
    for i in range(expected):
        entry = data[i] if i < len(data) and isinstance(data[i], dict) else {}
        verdict = str(entry.get("verdict", UNCLEAR)).strip().lower()
        if verdict not in _VERDICTS:
            verdict = UNCLEAR
        parsed.append((verdict, str(entry.get("reason", "")).strip()))
    return parsed


class SupportChecker:
    """Judges each cited claim against the text of the paper it cites."""

    def __init__(self, llm: "ChatOpenAI | None" = None) -> None:
        self._llm = llm
        self._semaphore = asyncio.Semaphore(4)

    def _resolve_llm(self) -> "ChatOpenAI":
        if self._llm is None:
            self._llm = fast_llm(max_tokens=SUPPORT_MAX_TOKENS)
        return self._llm

    async def check(
        self,
        claims_by_key: dict[str, list[Claim]],
        key_to_item: dict[str, LiteratureItem],
        language: str = "en",
    ) -> dict[str, list[SupportVerdict]]:
        """Return verdicts per citation key. Keys with nothing to say are omitted."""
        if not settings.verify_citation_support:
            return {}

        pending = {
            key: claims for key, claims in claims_by_key.items()
            if key in key_to_item and claims
        }
        if not pending:
            return {}

        try:
            llm = self._resolve_llm()
        except Exception as exc:  # no provider configured — same policy as a network failure
            logger.warning("[layer3] no usable LLM, skipping support check: %s", exc)
            return {}

        results = await asyncio.gather(*[
            self._check_key(llm, key, claims, key_to_item[key], language)
            for key, claims in pending.items()
        ])
        judged = {key: verdicts for key, verdicts in results if verdicts}
        logger.info(
            "[layer3] keys_checked=%d keys_judged=%d unsupported=%d",
            len(pending), len(judged),
            sum(1 for vs in judged.values() for v in vs if v.verdict in WARNS),
        )
        return judged

    async def _check_key(
        self,
        llm: "ChatOpenAI",
        key: str,
        claims: list[Claim],
        item: LiteratureItem,
        language: str,
    ) -> tuple[str, list[SupportVerdict]]:
        batches = [claims[i:i + _CLAIMS_PER_CALL] for i in range(0, len(claims), _CLAIMS_PER_CALL)]
        results = await asyncio.gather(*[self._check_batch(llm, key, batch, item, language) for batch in batches])
        return key, [verdict for verdicts in results for verdict in verdicts]

    async def _check_batch(
        self,
        llm: "ChatOpenAI",
        key: str,
        claims: list[Claim],
        item: LiteratureItem,
        language: str,
    ) -> list[SupportVerdict]:
        # full text when there is one: its opening plus the passages matching these claims
        evidence = select_evidence(item, claims, budget=_MAX_EVIDENCE_CHARS)
        if weighted_length(evidence) < MIN_EVIDENCE_CHARS:
            return []

        # Prompt building, the call and parsing all sit inside one guard: this layer must
        # never be the reason verification dies, and gather() would propagate anything raised.
        try:
            prompt = build_support_prompt(
                title=item.title or "",
                evidence=evidence,
                claims=[{"sentence": c.sentence, "context": c.context} for c in claims],
                language=language,
                key=key,
                passages=bool(item.full_text),
                fine=settings.l3_fine_grades,
            )
            async with self._semaphore:
                response = await llm.ainvoke(prompt)
            verdicts = _parse_verdicts(response.content, len(claims))
        except Exception as exc:
            logger.warning("[layer3] support check failed for %s: %s", key, exc)
            return []

        return [
            SupportVerdict(claim=claim, verdict=verdict, reason=reason, pages=tuple(claim_pages(item, claim)))
            for claim, (verdict, reason) in zip(claims, verdicts)
        ]
