"""Novelty diagnosis of the writing angle, shown beside it at the angle gate; it never rewrites the angle.

Novelty is graded on four levels (problem / method / data / perspective), with a pseudo-innovation
diagnosis and a pressure test. The pressure test names the pool papers closest to
the angle; a key outside the papers shown is the model's invention and is dropped.
"""
import json
import logging
import re
from typing import TYPE_CHECKING

from backend.literature.bibtex import bibtex_key
from backend.literature.schemas import LiteratureItem
from backend.writing.novelty_prompts import build_novelty_prompt
from backend.writing.section_writer import select_relevant_papers

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

LEVELS = ("problem", "method", "data", "perspective")
_VERDICTS = ("new", "incremental", "existing")
_PATTERNS = ("a_plus_b", "old_method_new_domain", "dataset_swap", "rebranding")
_CANDIDATES = 30
_ABSTRACT_CHARS = 300
_MAX_CLOSEST = 3
# Reasoning comes first: at 4096 replies ran to 3,210 tokens and one real run came back unusable.
NOVELTY_MAX_TOKENS = 8192


def _candidates(angle: dict, literature: list[LiteratureItem]) -> list[LiteratureItem]:
    brief = {"title": angle.get("writing_angle", ""), "summary": f"{angle.get('gap', '')} {angle.get('contribution', '')}"}
    return select_relevant_papers(brief, literature, top_k=_CANDIDATES)


def _candidate_block(items: list[LiteratureItem]) -> str:
    return "\n".join(
        f"- [{bibtex_key(it)}] {it.title} ({it.year or 'n.d.'}): {(it.abstract or '')[:_ABSTRACT_CHARS]}"
        for it in items
    )


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _parse(raw, shown: dict[str, LiteratureItem]) -> dict | None:
    match = re.search(r"\{.*\}", raw if isinstance(raw, str) else "", re.S)
    try:
        data = json.loads(match.group(0)) if match else None
    except ValueError:
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("levels"), dict):
        return None
    levels = {}
    for level in LEVELS:
        entry = data["levels"].get(level) if isinstance(data["levels"].get(level), dict) else {}
        verdict = _text(entry.get("verdict")).lower()
        levels[level] = {"verdict": verdict if verdict in _VERDICTS else "unclear", "reason": _text(entry.get("reason"))}
    pseudo = [{"pattern": _text(p.get("pattern")), "reason": _text(p.get("reason"))}
              for p in data.get("pseudo") or [] if isinstance(p, dict) and _text(p.get("pattern")) in _PATTERNS]
    closest, dropped = [], 0
    for entry in data.get("closest") or []:
        key = _text(entry.get("key")) if isinstance(entry, dict) else ""
        if key not in shown:
            dropped += 1
            continue
        if len(closest) < _MAX_CLOSEST and key not in {c["key"] for c in closest}:
            closest.append({"key": key, "title": shown[key].title, "year": shown[key].year,
                            "overlap": _text(entry.get("overlap"))})
    return {"levels": levels, "pseudo": pseudo, "closest": closest, "dropped_keys": dropped,
            "objection": _text(data.get("objection"))}


class NoveltyDiagnoser:
    def __init__(self, llm: "ChatOpenAI") -> None:
        self._llm = llm

    async def run(self, topic: str, angle: dict | None, literature: list[LiteratureItem], language: str) -> dict | None:
        """The diagnosis, or None when there is no angle or no usable reply; never raises."""
        if not angle or not angle.get("writing_angle"):
            return None
        shown = _candidates(angle, literature)
        try:
            prompt = build_novelty_prompt(topic, angle, _candidate_block(shown), language)
            response = await self._llm.ainvoke(prompt)
            result = _parse(response.content, {bibtex_key(it): it for it in shown})
        except Exception as exc:
            logger.warning("[novelty] diagnosis failed: %s", exc)
            return None
        if result is None:
            finish = (getattr(response, "response_metadata", None) or {}).get("finish_reason")
            logger.warning("[novelty] unusable reply (finish_reason=%s): %.120s", finish, response.content)
        else:
            logger.info("[novelty] closest=%d dropped_keys=%d pseudo=%d",
                        len(result["closest"]), result["dropped_keys"], len(result["pseudo"]))
        return result
