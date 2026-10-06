"""Layer 3 evidence: the parts of a cited paper that bear on the claims made about it.

The body excerpt is the first 2000 characters from the Abstract on, so the results a
claim cites - usually in the methods or experiments - were rarely in front of the judge.
When the full text is available, the evidence is its opening plus the passages that best
match the claims, found by keyword overlap weighted by rarity within the paper (no
embedding model, no new dependency). Without full text the old evidence is used as is.
"""
import math
import re
from collections import Counter
from typing import TYPE_CHECKING

from backend.literature.content_fetcher import GAP as FULL_TEXT_GAP
from backend.literature.schemas import LiteratureItem

if TYPE_CHECKING:  # layer3_support imports this module
    from backend.verification.layer3_support import Claim

# Target passage size, and the opening (abstract, start of the introduction) always kept.
_PASSAGE_CHARS = 700
_HEAD_CHARS = 1000
_DEFAULT_BUDGET = 4000
_GAP = "\n[...]\n"

_WORD = re.compile(r"[a-zA-Z][a-zA-Z0-9\-]+|\d+(?:\.\d+)?")
_CJK_RUN = re.compile(r"[一-鿿]+")
_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were", "been", "have",
    "has", "can", "may", "its", "their", "which", "into", "than", "also", "such", "these",
    "those", "cite", "our", "not", "but", "more", "most", "other", "between", "while",
}


def evidence_kind(item: LiteratureItem) -> str:
    """What layer 3 judges against: passages of the full text, a body excerpt, or the abstract."""
    if item.full_text:
        return "full_text"
    body = (item.body_excerpt or "").strip()
    return "body" if body and body != (item.abstract or "").strip() else "abstract"


def _judged_text(item: LiteratureItem) -> str:
    """The full text up to its gap. Judged on the end of a long paper too, layer 3 recognised support
    4% less often (80.3 vs 84.0 of 99 claims, three runs each): end sections sharing a claim's words
    pushed the specific passages out of the budget. The end is kept for the evidence table."""
    return item.full_text.split(FULL_TEXT_GAP, 1)[0]


def select_evidence(item: LiteratureItem, claims: list["Claim"], budget: int = _DEFAULT_BUDGET) -> str:
    if not item.full_text:
        return (item.body_excerpt or item.abstract or "").strip()[:budget]

    text = _judged_text(item)
    head = text[:_HEAD_CHARS].strip()
    passages = [p for p in _passages(text[_HEAD_CHARS:]) if p.strip()]
    picked = _pick(passages, claims, budget - len(head))
    return _GAP.join([head, *(passages[i] for i in sorted(picked))])


def _tokens(text: str) -> list[str]:
    words = [w.lower() for w in _WORD.findall(text) if w.lower() not in _STOPWORDS]
    for run in _CJK_RUN.findall(text):  # Chinese has no spaces: match on character bigrams
        words.extend(run[i:i + 2] for i in range(len(run) - 1))
    return words


_PARAGRAPH_BREAK = re.compile(r"\n\s*\n|\n(?=[A-Z0-9一-鿿])")


def _passages(text: str) -> list[str]:
    """Paragraphs merged or split towards _PASSAGE_CHARS."""
    chunks: list[str] = []
    current = ""
    for para in _PARAGRAPH_BREAK.split(text):
        para = " ".join(para.split())
        while len(para) > _PASSAGE_CHARS * 2:  # one huge paragraph: cut near a sentence end
            cut = para.rfind(". ", 0, _PASSAGE_CHARS * 2)
            cut = cut + 1 if cut > _PASSAGE_CHARS // 2 else _PASSAGE_CHARS
            chunks.append(para[:cut].strip())
            para = para[cut:].strip()
        if current and len(current) + len(para) > _PASSAGE_CHARS:
            chunks.append(current)
            current = ""
        current = f"{current} {para}".strip()
    if current:
        chunks.append(current)
    return chunks


def _paragraphs(text: str) -> list[tuple[str, int]]:
    """Non-empty paragraphs with the offset each starts at."""
    out, pos = [], 0
    for m in [*_PARAGRAPH_BREAK.finditer(text), None]:
        para = text[pos:m.start() if m else len(text)]
        if para.strip():
            out.append((para, pos))
        pos = m.end() if m else pos
    return out


def claim_pages(item: LiteratureItem, claim: "Claim") -> list[int]:
    """The PDF page of the paragraph that best matches the claim; [] without page data.

    Paragraphs, not the merged passages the judge sees, so the offset is exact.
    """
    if not item.full_text or not item.full_text_pages:
        return []
    paragraphs = _paragraphs(_judged_text(item))
    ranking = _rank([para for para, _ in paragraphs], [claim])[0]
    if not ranking:
        return []
    offset = paragraphs[ranking[0]][1]
    return [max((page for start, page in item.full_text_pages if start <= offset), default=item.full_text_pages[0][1])]


def _rank(passages: list[str], claims: list["Claim"]) -> list[list[int]]:
    """For each claim, the passages sharing words with it, best first (rare words weigh more)."""
    passage_tokens = [set(_tokens(p)) for p in passages]
    df = Counter(t for tokens in passage_tokens for t in tokens)
    n = len(passages)

    def score(query: set[str], i: int) -> float:
        return sum(math.log(1 + n / df[t]) for t in query & passage_tokens[i])

    rankings = []
    for claim in claims:
        query = set(_tokens(f"{claim.context} {claim.sentence}"))
        ranked = sorted(range(n), key=lambda i: score(query, i), reverse=True)
        rankings.append([i for i in ranked if score(query, i) > 0])
    return rankings


def _pick(passages: list[str], claims: list["Claim"], budget: int) -> set[int]:
    """Best passages for each claim in turn, until the budget runs out."""
    rankings = _rank(passages, claims)
    picked: set[int] = set()
    used = 0
    for depth in range(max((len(r) for r in rankings), default=0)):
        for ranking in rankings:
            if depth >= len(ranking) or ranking[depth] in picked:
                continue
            cost = len(passages[ranking[depth]]) + len(_GAP)
            if used + cost <= budget:
                picked.add(ranking[depth])
                used += cost
    return picked
