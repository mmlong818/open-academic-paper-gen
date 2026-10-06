"""Stage 3 — a simulated peer review of the finished draft, returned as suggestions only.

One call reads the whole draft, so it can catch what no per-sentence check sees: claims
that contradict another section, arguments that skip a step, limitations the paper never
admits. Nothing here edits the text. Automatic rewrites driven by a noisy detector did
harm in T1.2, and AI reviewers are swayed by confident framing (Rhetorical
Reward-Hacking, arXiv 2608.08975), so the prompt asks for substance over tone and every
comment must quote the draft verbatim: a quote not found in the text is dropped as the
reviewer's invention.
"""
import json
import logging
import re

from langchain_openai import ChatOpenAI

from backend.core.config import settings
from backend.writing.prompts import build_review_prompt

logger = logging.getLogger(__name__)

_MAX_COMMENTS = 10
# A normal review is 2,500-3,500 output tokens, reasoning included.
_MAX_TOKENS = 12000
_ATTEMPTS = 2
_MAX_LIMITATIONS = 5
_SEVERITIES = ("major", "minor")


def reviewer_llm(effort: str = "medium"):
    """The strong OpenAI model in JSON mode.

    Without it 4 of 5 eval reviews failed to parse: the model slipped a stray quote into
    the object's structure ('}]," "limitations"'), not into a string. JSON mode rules that
    out; the cost is no zhipu fallback, and a failed call yields an empty review.
    The budget is large because reasoning comes first: at 8192 two English drafts spent
    all of it thinking and returned nothing. Even 32768 ran out once, the same draft that
    had needed 3500 tokens before. With effort capped at medium it still ran away in 1 of 3
    tries, so the budget is kept modest - a runaway fails fast and cheap - and review() retries.
    On one real draft medium ran away on all six attempts, even at 24000; the retry therefore goes
    to low effort, which answered in ~300 reasoning tokens (at 0.85 precision against medium's 0.90).
    """
    llm = ChatOpenAI(
        model=settings.openai_model_strong,
        api_key=settings.openai_api_key,  # type: ignore[arg-type]
        max_tokens=_MAX_TOKENS,
        reasoning_effort=effort,
    )
    return llm.bind(response_format={"type": "json_object"})


class ReviewAgent:
    def __init__(self, llm: "ChatOpenAI", retry_llm: "ChatOpenAI | None" = None) -> None:
        self._llm = llm
        self._retry_llm = retry_llm or llm

    async def review(
        self, sections: dict[str, str], outline: list[dict], topic: str, language: str, focus: str = ""
    ) -> dict:
        shown = {t: s for t, s in sections.items() if not s.startswith("__SECTION_FAILED__")}
        empty = {"comments": [], "limitations": [], "dropped_unquoted": 0}
        if not shown:
            return empty
        order = [o["title"] for o in outline if o.get("title") in shown] or list(shown)
        draft = "\n\n".join(f"## {title}\n{shown[title]}" for title in order)
        data = await self._ask(build_review_prompt(topic, draft, language, focus))
        if data is None:
            return empty
        comments, dropped = _grounded_comments(data.get("comments"), shown)
        limitations = [str(x).strip() for x in data.get("limitations") or [] if str(x).strip()]
        return {
            "comments": comments[:_MAX_COMMENTS],
            "limitations": limitations[:_MAX_LIMITATIONS],
            "dropped_unquoted": dropped,
        }


    async def _ask(self, prompt: str) -> dict | None:
        for attempt in range(1, _ATTEMPTS + 1):
            llm = self._llm if attempt == 1 else self._retry_llm
            try:
                return _parse((await llm.ainvoke(prompt)).content)
            except Exception as exc:  # a failed review must never block the paper
                logger.warning("[review] attempt %d failed: %s", attempt, exc)
        return None


def _parse(raw) -> dict:
    text = (raw if isinstance(raw, str) else "").strip()
    if text.startswith("```"):
        text = text.split("```")[1].removeprefix("json").strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("review reply is not a JSON object")
    return data


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _grounded_comments(raw_comments, sections: dict[str, str]) -> tuple[list[dict], int]:
    """Comments whose quote appears in the draft, attached to the section that holds it."""
    squashed = {title: _squash(text) for title, text in sections.items()}
    kept: list[dict] = []
    dropped = 0
    for c in raw_comments or []:
        if not isinstance(c, dict):
            continue
        quote = _squash(str(c.get("quote", "")))
        claimed = str(c.get("section", ""))
        holder = claimed if quote and quote in squashed.get(claimed, "") else next(
            (title for title, text in squashed.items() if quote and quote in text), None
        )
        if holder is None:
            dropped += 1
            continue
        severity = str(c.get("severity", "minor")).lower()
        kept.append({
            "section": holder,
            "quote": quote,
            "issue": str(c.get("issue", "")).strip(),
            "severity": severity if severity in _SEVERITIES else "minor",
            "suggestion": str(c.get("suggestion", "")).strip(),
        })
    return kept, dropped
