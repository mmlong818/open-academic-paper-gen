import asyncio
import json
import logging
from typing import TYPE_CHECKING

from backend.literature.schemas import LiteratureItem
from backend.literature.text_length import weighted_length
from backend.writing.prompts import build_screening_prompt

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


class LiteratureScreener:
    def __init__(self, llm: "ChatOpenAI", concurrency: int = 5) -> None:
        self._llm = llm
        self._semaphore = asyncio.Semaphore(concurrency)

    async def _screen_one(
        self, item: LiteratureItem, topic: str, language: str
    ) -> tuple[LiteratureItem, str, str, str]:
        """Returns (item, decision, reason, basis). Decision is 'include' or 'exclude'."""
        # 优先使用抓取到的正文节选，不足时退回摘要
        content = (item.body_excerpt or "").strip() or (item.abstract or "").strip()
        title = (item.title or "").strip()
        # 不足 300 字时按标题筛选：中文记录大多没有摘要，直接放行会让无关论文占满文献池
        basis = "abstract" if weighted_length(content) >= 300 else "title" if title else "none"
        if basis == "none":
            return item, "include", "no title or abstract to screen — defaulting to include", basis

        prompt = build_screening_prompt(
            topic=topic,
            title=title,
            abstract=content,
            language=language,
            title_only=basis == "title",
        )
        async with self._semaphore:
            try:
                response = await self._llm.ainvoke(prompt)
                raw = response.content.strip()
                # strip markdown fences if present
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                        raw = raw.strip()
                data = json.loads(raw)
                decision = "include" if data.get("decision", "include").lower().strip() != "exclude" else "exclude"
                reason = data.get("reason", "")
            except Exception as exc:
                logger.warning("Screening LLM call failed for '%s': %s", item.title, exc)
                decision = "include"
                reason = "screening error — defaulting to include"
        return item, decision, reason, basis

    async def run(
        self,
        topic: str,
        items: list[LiteratureItem],
        language: str,
    ) -> tuple[list[LiteratureItem], list[dict]]:
        """Screen all items concurrently.

        Returns:
            retained: papers with decision == 'include'
            report: list of {title, decision, reason} for all papers
        """
        tasks = [self._screen_one(item, topic, language) for item in items]
        results = await asyncio.gather(*tasks)

        retained: list[LiteratureItem] = []
        report: list[dict] = []
        for item, decision, reason, basis in results:
            report.append({"title": item.title or "", "decision": decision, "reason": reason, "basis": basis})
            if decision == "include":
                retained.append(item)

        logger.info(
            "[screener] topic=%r total=%d retained=%d excluded=%d",
            topic, len(items), len(retained), len(items) - len(retained),
        )
        return retained, report
