import logging
import re
from typing import TYPE_CHECKING

from backend.core.config import settings
from backend.literature.bibtex import bibtex_key, iter_cite_keys
from backend.literature.schemas import LiteratureItem
from backend.literature.text_length import weighted_length
from backend.verification.duplicates import duplicate_issues
from backend.verification.evidence import evidence_kind
from backend.verification.layer1_existence import ExistenceChecker
from backend.verification.layer3_support import (
    MIN_EVIDENCE_CHARS,
    MISALIGNED,
    PARTIAL,
    UNCLEAR,
    WARNS,
    Claim,
    SupportChecker,
    SupportVerdict,
)
from backend.verification.schemas import (
    CitationIssue,
    CitationStatus,
    VerificationResult,
    VerificationSummary,
)

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

_SENTENCE_SPLIT = re.compile(r"(?<=[。！？])\s*|(?<=[.!?])\s+")
_TABLE_SEPARATOR = re.compile(r"^\|?\s*:?-{3,}")
# Column headers that mark the writer's own assessment ("Limitation relevant to this review",
# "对机制的支持") rather than a description of the cited work.
_COMMENTARY_HEADER = re.compile(
    r"(?i)limitation|\blimit|gap|remaining|residual|implication|contrary|relative to|motivat"
    r"|proposed|support for|this (study|paper|review|section)|present (question|study|synthesis)"
    r"|convergence|divergence|blind spot|unresolved|integrative conclusion"
    r"|局限|限制|不足|空白|启示|意义|本研究|本文|本综述|本节|的支持|推进"
)
_CLAIM_SNIPPET_CHARS = 160
# Which pipeline stage a failing layer points at: a fabricated key or a claim the source does
# not make is the writer's doing; a dead DOI or mismatched title is a bad retrieved record.
_LAYER_STAGE = {"layer0": "writing", "layer1": "retrieval", "layer3": "writing"}
_MAX_CLAIMS_IN_REASON = 3


def extract_cite_keys(text: str) -> set[str]:
    """Extract all [cite:KEY] markers from section text."""
    return set(iter_cite_keys(text))


def extract_claims(text: str) -> dict[str, list[Claim]]:
    """Group the sentences carrying each [cite:KEY] marker, keyed by citation key.

    The preceding sentence rides along as context: markers often land on a short
    follow-up clause ("This is confirmed [cite:X].") whose claim only reads with
    the sentence before it.

    Markdown tables are taken out first: each cited row becomes its own claim, labelled
    by its column headers, so rows neither merge into one "sentence" nor serve as the
    context of the prose after them.
    """
    prose, rows = _separate_tables(text)
    sentences = _split_sentences(prose)
    units = [(s, sentences[i - 1] if i else "") for i, s in enumerate(sentences)]
    units += [(row, "") for row in rows]

    claims: dict[str, list[Claim]] = {}
    for sentence, context in units:
        for key in sorted(set(iter_cite_keys(sentence))):
            claims.setdefault(key, []).append(
                Claim(key=key, sentence=sentence, context=context)
            )
    return claims


def prose_sentences(text: str) -> list[str]:
    """The sentences of a section with its tables taken out."""
    return _split_sentences(_separate_tables(text)[0])


def _split_sentences(prose: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(prose) if s.strip()]


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _separate_tables(text: str) -> tuple[str, list[str]]:
    """Return the text with tables blanked out, plus one claim sentence per table row."""
    lines = text.splitlines()
    prose: list[str] = []
    rows: list[str] = []
    i = 0
    while i < len(lines):
        starts_table = (
            lines[i].lstrip().startswith("|")
            and i + 1 < len(lines)
            and _TABLE_SEPARATOR.match(lines[i + 1].strip())
        )
        if not starts_table:
            prose.append(lines[i])
            i += 1
            continue
        header = _cells(lines[i])
        i += 2
        while i < len(lines) and lines[i].lstrip().startswith("|"):
            rows.append(_row_claim(header, _cells(lines[i])))
            i += 1
        prose.append("")  # keep a paragraph break where the table stood
    return "\n".join(prose), rows


def _row_claim(header: list[str], cells: list[str]) -> str:
    """The row as "header: cell" pairs, minus the writer's own commentary columns.

    If a marker sits only in a dropped column, the full row is kept: better to judge
    too much than to judge a claim without the citation it hangs on.
    """
    kept = [
        f"{h}: {c}" if h else c
        for h, c in zip(header, cells)
        if c and not _COMMENTARY_HEADER.search(h)
    ]
    claim, full = " | ".join(kept), " | ".join(cells)
    return claim if set(iter_cite_keys(full)) <= set(iter_cite_keys(claim)) else full


class VerificationOrchestrator:
    def __init__(self, llm: "ChatOpenAI | None" = None) -> None:
        self.existence_checker = ExistenceChecker()
        self.support_checker = SupportChecker(llm=llm)

    async def run(
        self,
        items: list[LiteratureItem],
        context: str,
        language: str = "en",
    ) -> tuple[list[LiteratureItem], list[CitationIssue], VerificationSummary]:
        verified, issues, summary, _ = await self.run_with_support(items, context, language)
        return verified, issues, summary

    async def run_with_support(
        self,
        items: list[LiteratureItem],
        context: str,
        language: str = "en",
    ) -> tuple[
        list[LiteratureItem], list[CitationIssue], VerificationSummary,
        dict[str, list[SupportVerdict]],
    ]:
        """Verify citations in the written sections; also return layer 3's verdicts per key.

        Three checks:
        1. Hallucination check: every [cite:KEY] in sections must exist in literature pool.
        2. Existence check (layer 1): if a cited paper has a DOI, CrossRef must confirm it.
        3. Support check (layer 3): the cited paper must actually back the sentence citing it.

        Only checks 1 and 2 can remove a paper. An unsupported claim is a warning — the fix
        belongs in the prose, not in the bibliography.

        verified_citations = full literature pool minus DOI-confirmed-invalid papers.
        The export bibliography is built from verified_citations, not just the cited subset.
        """
        key_to_item: dict[str, LiteratureItem] = {bibtex_key(item): item for item in items}
        cited_keys = extract_cite_keys(context)

        logger.info(
            "[verification] pool_size=%d cited_keys=%d sample_cited=%s sample_pool=%s",
            len(items), len(cited_keys),
            sorted(cited_keys)[:10], sorted(key_to_item.keys())[:10],
        )

        support = await self.support_checker.check(
            extract_claims(context), key_to_item, language
        )

        issues: list[CitationIssue] = []
        invalid_titles: set[str] = set()
        passed = warned = removed = unverified = 0
        row_of: dict[str, int] = {}

        for key in sorted(cited_keys):
            item = key_to_item.get(key)

            if item is None:
                removed += 1
                issues.append(CitationIssue(
                    title=key,
                    doi=None,
                    layer="layer0",
                    reason=f"[cite:{key}] not found in literature pool — hallucinated citation",
                    action="removed",
                    stage=_LAYER_STAGE["layer0"],
                ))
                continue

            row_of[key] = len(issues)
            status, issue = await self._classify(item, support.get(key, []))
            if status == CitationStatus.REMOVED:
                removed += 1
                invalid_titles.add(item.title)
            elif status == CitationStatus.WARNED:
                warned += 1
            elif issue.action == "unverified":
                unverified += 1
            else:
                passed += 1
            issues.append(issue)

        # the same paper under two keys, or a preprint beside its published version
        for was in _flag_duplicates(issues, row_of, key_to_item):
            passed -= was == "kept"
            unverified -= was == "unverified"
            warned += was != "warned"

        # verified = full pool minus papers with confirmed-invalid DOIs
        verified = [it for it in items if it.title not in invalid_titles]

        summary = VerificationSummary(
            total=len(cited_keys),
            passed=passed,
            warned=warned,
            removed=removed,
            unverified=unverified,
        )
        return verified, issues, summary, support

    async def _classify(
        self,
        item: LiteratureItem,
        verdicts: list[SupportVerdict],
    ) -> tuple[str, CitationIssue]:
        """Resolve one cited paper to a single status and a single issue row.

        Exactly one issue per cited paper, however many layers have something to say:
        the UI counts these rows to report how many citations the body actually makes,
        so a paper flagged twice would inflate that count.
        """
        result = await self._check_item(item)

        if result.status == CitationStatus.REMOVED:
            return CitationStatus.REMOVED, self._issue(item, ["layer1"], result.issues, "removed")

        unsupported = [v for v in verdicts if v.verdict in WARNS]
        notes = _support_notes(item, verdicts)
        if result.status == CitationStatus.WARNED or unsupported:
            layers: list[str] = []
            reasons: list[str] = []
            if result.issues:
                layers.append("layer1")
                reasons.extend(result.issues)
            if unsupported:
                layers.append("layer3")
                reasons.append(_unsupported_reason(unsupported))
            return CitationStatus.WARNED, self._issue(item, layers, reasons + notes, "warned")

        layer1_reason = "DOI verified via CrossRef" if item.doi else "No DOI — accepted"
        if settings.verify_citation_support and _no_text_to_check(item):
            # Layer 3 had nothing to judge the claims against: passing it would claim a check never made.
            return CitationStatus.PASSED, CitationIssue(
                title=item.title, doi=item.doi, layer="layer3", action="unverified", stage="retrieval",
                reason=f"{layer1_reason}; no abstract or full text — claims not checked (无摘要或正文，未核对论断)",
            )
        layers = ["layer1", "layer3"] if notes else ["layer1"]
        return CitationStatus.PASSED, self._issue(item, layers, [layer1_reason, *notes], "kept")

    @staticmethod
    def _issue(
        item: LiteratureItem,
        layers: list[str],
        reasons: list[str],
        action: str,
    ) -> CitationIssue:
        return CitationIssue(
            title=item.title,
            doi=item.doi,
            layer="+".join(layers) or "layer1",
            reason="; ".join(r for r in reasons if r) or action,
            action=action,
            stage="" if action == "kept" else "+".join(_LAYER_STAGE[layer] for layer in layers),
        )

    async def _check_item(self, item: LiteratureItem) -> VerificationResult:
        l1 = await self.existence_checker.check(
            title=item.title,
            authors=item.authors,
            doi=item.doi,
            year=item.year,
            pages=item.pages,
            source=item.source,
        )
        return VerificationResult(
            title=item.title,
            doi=item.doi,
            status=l1.status,
            layer1_ok=l1.layer1_ok,
            issues=l1.issues,
        )


def _flag_duplicates(
    issues: list[CitationIssue], row_of: dict[str, int], key_to_item: dict[str, LiteratureItem]
) -> list[str]:
    """Turn the rows of repeated papers into warnings in place; return each row's former action."""
    former = []
    for key, reason in duplicate_issues({k: key_to_item[k] for k in row_of}).items():
        row = issues[row_of[key]]
        if row.action == "removed":
            continue
        former.append(row.action)
        issues[row_of[key]] = row.model_copy(update={
            "action": "warned", "reason": f"{row.reason}; {reason}",
            "layer": row.layer if "layer1" in row.layer else f"{row.layer}+layer1",
            "stage": "+".join(dict.fromkeys(filter(None, [*row.stage.split("+"), "writing"]))),
        })
    return former


def _no_text_to_check(item: LiteratureItem) -> bool:
    text = (item.full_text or item.body_excerpt or item.abstract or "").strip()
    return weighted_length(text) < MIN_EVIDENCE_CHARS


def _snippet(sentence: str) -> str:
    if len(sentence) > _CLAIM_SNIPPET_CHARS:
        return sentence[:_CLAIM_SNIPPET_CHARS] + "..."
    return sentence


def _unsupported_reason(verdicts: list[SupportVerdict]) -> str:
    """One line naming the claims the cited paper does not back."""
    if len(verdicts) == 1:
        verdict = verdicts[0]
        what = "reports the opposite of, or something other than," if verdict.verdict == MISALIGNED else "does not support"
        reason = f'Cited paper {what} the claim: "{_snippet(verdict.claim.sentence)}"'
        reason = f"{reason} — {verdict.reason}" if verdict.reason else reason
        return reason + _page_note(verdict)

    shown = verdicts[:_MAX_CLAIMS_IN_REASON]
    quoted = "; ".join(f'"{_snippet(v.claim.sentence)}"{_page_note(v)}' for v in shown)
    hidden = len(verdicts) - len(shown)
    tail = f" (+{hidden} more)" if hidden else ""
    return f"Cited paper does not support {len(verdicts)} claims: {quoted}{tail}"


def _support_notes(item: LiteratureItem, verdicts: list[SupportVerdict]) -> list[str]:
    """Notes that never warn: partly supported claims, and claims the abstract alone cannot settle."""
    notes = []
    partial = [v for v in verdicts if v.verdict == PARTIAL]
    if len(partial) == 1:
        v = partial[0]
        note = f'claim partly supported (部分支撑): "{_snippet(v.claim.sentence)}"'
        notes.append((f"{note} — {v.reason}" if v.reason else note) + _page_note(v))
    elif partial:
        quoted = "; ".join(f'"{_snippet(v.claim.sentence)}"' for v in partial[:_MAX_CLAIMS_IN_REASON])
        notes.append(f"{len(partial)} claims partly supported (部分支撑): {quoted}")
    unclear = sum(1 for v in verdicts if v.verdict == UNCLEAR)
    if unclear and evidence_kind(item) == "abstract":
        notes.append(f"{unclear} claim(s) cannot be settled on the abstract alone (需全文)")
    return notes


def _page_note(verdict: SupportVerdict) -> str:
    """Where in the source PDF to look (5.1); empty without page data."""
    return f" (PDF p. {', '.join(map(str, verdict.pages))})" if verdict.pages else ""
