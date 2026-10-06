"""Evidence table: task, method, data, metric, finding and limitation of each paper in the pool.

Cells come from the paper's own text only: with full text, its abstract and its results, discussion, limitations
and conclusion sections; without, its abstract and excerpt. A field the text does not report stays
empty, and a cell naming a number absent from the text is emptied as the model's invention.
Extraction never stops the pipeline: a failed batch just leaves its papers out of the table.
"""
import asyncio
import json
import logging
import re
from typing import TYPE_CHECKING

from backend.literature.bibtex import bibtex_key
from backend.literature.content_fetcher import GAP
from backend.literature.schemas import LiteratureItem
from backend.literature.sections import section_starts
from backend.literature.text_length import weighted_length
from backend.writing.evidence_prompts import build_evidence_prompt

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

FIELDS = ("task", "method", "data", "metric", "finding", "limitation")
FIELD_LABELS = {
    "zh": {"task": "任务", "method": "方法", "data": "数据", "metric": "指标", "finding": "主要发现", "limitation": "局限"},
    "en": {"task": "Task", "method": "Method", "data": "Data", "metric": "Metric", "finding": "Finding",
           "limitation": "Limitation"},
}
EVIDENCE_MAX_TOKENS = 6000
# Five, not ten: a paper with full text sends up to ~5000 chars.
_BATCH = 5
_SOURCE_CHARS = 1500
# On 40 sampled papers the limitation cell was right in 2 and misplaced in 10 when the extractor saw
# the abstract and the first 1500 chars: few papers state their own limitations there.
_ABSTRACT_CHARS = 1000
_SECTION_CHARS = {"results": 800, "discussion": 800, "limitations": 1200, "conclusion": 1200}
_CELL_CHARS = 200
_MIN_TEXT = 200  # the same floor layer 3 needs before judging anything
_NOT_REPORTED = {"not reported", "未报告", "n/a", "na", "none", "-", "无"}
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
# a comma closing an object or array, with the stray quote or empty string the model may leave
_DANGLING = re.compile(r',\s*(?:""|")?\s*([}\]])')


def source_text(item: LiteratureItem) -> str:
    sections = _sections(item.full_text) if item.full_text else []
    abstract = (item.abstract or "").strip()
    if sections:
        return "\n".join([abstract[:_ABSTRACT_CHARS], *sections]).strip()
    body = (item.body_excerpt or "").strip()
    text = f"{abstract}\n{body}" if body and body not in abstract else abstract or body
    return text[:_SOURCE_CHARS]


def _sections(full_text: str) -> list[str]:
    """Each section from its heading to the next one, the gap or its budget, in reading order."""
    starts = section_starts(full_text)
    gap = full_text.find(GAP)
    bounds = sorted([*starts.values(), *([gap] if gap >= 0 else []), len(full_text)])
    out = []
    for name, start in sorted(starts.items(), key=lambda kv: kv[1]):
        end = min(next(b for b in bounds if b > start), start + _SECTION_CHARS[name])
        out.append(full_text[start:end].strip())
    return out


def _cell(value) -> str:
    text = value.strip() if isinstance(value, str) else ""
    return "" if text.lower() in _NOT_REPORTED else text[:_CELL_CHARS]


def _load_json(text: str):
    """json.loads, or failing that, once more without a dangling comma before a closing brace.

    Over 203 batches the fast model broke 5 replies after the last field: `",\\n}`, `","}` or `",""}`.
    """
    try:
        return json.loads(text)
    except ValueError:
        return json.loads(_DANGLING.sub(r"\1", text))


def _parse_rows(raw, n: int) -> dict[int, dict[str, str]]:
    match = re.search(r"\[.*\]", raw if isinstance(raw, str) else "", re.S)
    if not match:
        return {}
    try:
        data = _load_json(match.group(0))
    except ValueError:
        return {}
    rows: dict[int, dict[str, str]] = {}
    for entry in data if isinstance(data, list) else []:
        i = entry.get("i") if isinstance(entry, dict) else None
        if isinstance(i, int) and 1 <= i <= n and i not in rows:
            rows[i] = {f: _cell(entry.get(f)) for f in FIELDS}
    return rows


def _grounded(row: dict[str, str], source: str) -> tuple[dict[str, str], int]:
    """Empty every cell carrying a number the source text does not contain."""
    plain = source.replace(",", "")
    out, dropped = {}, 0
    for field, value in row.items():
        invented = any(n.replace(",", "") not in plain for n in _NUMBER.findall(value))
        out[field] = "" if invented else value
        dropped += invented
    return out, dropped


def evidence_line(row: dict, language: str) -> str:
    """One row as a line for the section writer: the reported fields only."""
    labels = FIELD_LABELS["zh" if language == "zh" else "en"]
    return "; ".join(f"{labels[f]}: {row[f]}" for f in FIELDS if row.get(f))


class EvidenceExtractor:
    def __init__(self, llm: "ChatOpenAI") -> None:
        self._llm = llm
        self._semaphore = asyncio.Semaphore(4)

    async def run(self, items: list[LiteratureItem], language: str) -> list[dict]:
        usable = [item for item in items if weighted_length(source_text(item)) >= _MIN_TEXT]
        batches = [usable[i:i + _BATCH] for i in range(0, len(usable), _BATCH)]
        results = await asyncio.gather(*[self._batch(batch, language) for batch in batches])
        rows = [row for batch_rows in results for row in batch_rows]
        logger.info("[evidence] papers_with_text=%d rows=%d cells_dropped=%d",
                    len(usable), len(rows), sum(r["dropped"] for r in rows))
        return rows

    async def _batch(self, batch: list[LiteratureItem], language: str) -> list[dict]:
        sources = [source_text(item) for item in batch]
        prompt = build_evidence_prompt([(item.title or "", s) for item, s in zip(batch, sources)], language)
        parsed = await self._ask(prompt, len(batch))
        if not parsed:
            return []
        rows = []
        for i, (item, source) in enumerate(zip(batch, sources), 1):
            cells, dropped = _grounded(parsed.get(i, {}), source)
            if any(cells.values()):
                rows.append({"key": bibtex_key(item), "title": item.title, "year": item.year,
                             **cells, "dropped": dropped})
        return rows

    async def _ask(self, prompt: str, n: int) -> dict[int, dict[str, str]]:
        """The parsed rows, asking once more when the call fails or its reply lacks rows."""
        rows: dict[int, dict[str, str]] = {}
        for attempt in (1, 2):
            try:
                async with self._semaphore:
                    response = await self._llm.ainvoke(prompt)
            except Exception as exc:
                logger.warning("[evidence] batch of %d failed (attempt %d): %s", n, attempt, exc)
                continue
            rows = {**_parse_rows(response.content, n), **rows}
            if len(rows) == n:
                break
            logger.warning("[evidence] batch of %d gave %s rows (attempt %d)", n, len(rows) or "no", attempt)
        return rows
