"""Verification phase: verify, propose constrained revisions, and in full_auto apply and re-verify.

Kept out of graph.py so the node there stays a thin adapter between PaperState and this flow.
"""
import logging
from dataclasses import dataclass

from backend.core.config import settings
from backend.core.llm import fast_llm
from backend.core.model_router import get_llm
from backend.literature.schemas import LiteratureItem
from backend.verification.layer3_support import (
    SUPPORT_MAX_TOKENS,
    WARNS,
    SupportVerdict,
)
from backend.verification.orchestrator import VerificationOrchestrator
from backend.verification.schemas import CitationIssue, VerificationSummary
from backend.verification.uncited import UncitedClaim, UncitedClaimChecker
from backend.writing.revision import Problem, Revision, RevisionAgent, apply_revisions

logger = logging.getLogger(__name__)


@dataclass
class VerificationPass:
    verified: list[LiteratureItem]
    issues: list[CitationIssue]
    summary: VerificationSummary
    support: dict[str, list[SupportVerdict]]
    uncited: list[UncitedClaim]


@dataclass
class VerificationOutcome:
    sections: dict[str, str]
    final: VerificationPass
    revisions: list[Revision]


async def verify_sections(
    items: list[LiteratureItem], sections: dict[str, str], language: str
) -> VerificationPass:
    # Blank lines between sections keep a table that opens a section recognisable.
    context = "\n\n".join(sections.values())
    # Layer 3 uses the OpenAI fast model (OPENAI_MODEL_FAST), not the router's zhipu fast tier.
    orchestrator = VerificationOrchestrator(llm=fast_llm(max_tokens=SUPPORT_MAX_TOKENS))
    verified, issues, summary, support = await orchestrator.run_with_support(items, context, language)
    uncited = await UncitedClaimChecker(llm=fast_llm(max_tokens=SUPPORT_MAX_TOKENS)).check(sections, language)
    return VerificationPass(verified, issues, summary, support, uncited)


def collect_problems(sections: dict[str, str], vpass: VerificationPass) -> list[Problem]:
    """Unsupported claims and uncited statements, each tied to the section holding its sentence."""
    problems = [Problem(c.section, c.sentence, "uncited", c.reason) for c in vpass.uncited]
    for key, verdicts in vpass.support.items():
        for v in verdicts:
            if v.verdict not in WARNS:  # partial is a note for the reader, not a fix
                continue
            section = next((t for t, text in sections.items() if v.claim.sentence in text), None)
            if section:  # table-row claims are rebuilt from cells and match no section text
                problems.append(Problem(section, v.claim.sentence, "unsupported", f"[cite:{key}] {v.reason}"))
    return problems


def _still_flagged(revision: Revision, vpass: VerificationPass) -> bool:
    unsupported = (
        v.claim.sentence for vs in vpass.support.values() for v in vs if v.verdict in WARNS
    )
    uncited = (c.sentence for c in vpass.uncited if c.section == revision.section)
    return any(sentence in revision.after for sentence in (*unsupported, *uncited))


async def verify_and_revise(
    items: list[LiteratureItem],
    sections: dict[str, str],
    outline: list[dict],
    language: str,
    topic: str,
    auto_apply: bool,
) -> VerificationOutcome:
    first = await verify_sections(items, sections, language)
    problems = collect_problems(sections, first) if settings.revise_flagged_claims else []
    if not problems:
        return VerificationOutcome(sections, first, [])

    agent = RevisionAgent(llm=get_llm("writing", topic, language, max_tokens=4096))
    # Fixes for unsupported claims may be applied unasked; fixes for uncited statements are only
    # ever proposals. At the uncited check's ~0.4 precision, applying them rewrote sound prose:
    # 4 of 10 hand-checked applied revisions lost or changed the meaning, all uncited-driven.
    auto_fixes = await agent.propose(
        sections, [p for p in problems if p.kind == "unsupported"], items, outline, language
    )
    suggestions = await agent.propose(
        sections, [p for p in problems if p.kind != "unsupported"], items, outline, language
    )
    revisions = auto_fixes + suggestions
    for i, revision in enumerate(revisions, 1):
        revision.id = i
    applicable = [r for r in auto_fixes if r.status == "proposed"] if auto_apply else []
    if not applicable:
        return VerificationOutcome(sections, first, revisions)

    revised = apply_revisions(sections, [r.as_dict() for r in applicable])
    final = await verify_sections(items, revised, language)
    for revision in applicable:
        revision.status = "applied"
        revision.resolved = not _still_flagged(revision, final)
    logger.info(
        "[revision] problems=%d proposed=%d applied=%d resolved=%d",
        len(problems), len(revisions), len(applicable), sum(bool(r.resolved) for r in applicable),
    )
    return VerificationOutcome(revised, final, revisions)
