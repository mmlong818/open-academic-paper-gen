import asyncio
import logging
from typing import TYPE_CHECKING

from backend.core.llm import fast_llm
from backend.literature.schemas import LiteratureItem
from backend.writing.prompts import authors_str_for_apa, build_synthesis_prompt

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 20


def _items_to_lit_dicts(items: list[LiteratureItem]) -> list[dict]:
    return [
        {
            "title": item.title or "",
            "authors_str": authors_str_for_apa(item.authors),
            "year": item.year or "n.d.",
            "journal": item.source or "",
            "doi": item.doi or "",
            "abstract": item.abstract or "",
        }
        for item in items
    ]


class SynthesisAgent:
    def __init__(self, llm: "ChatOpenAI | None" = None) -> None:
        self._llm = llm if llm is not None else fast_llm(max_tokens=3000)

    async def _synthesize_chunk(
        self, topic: str, items: list[LiteratureItem], language: str
    ) -> str:
        lit_dicts = _items_to_lit_dicts(items)
        abstracts = [item.abstract for item in items if (item.abstract or "").strip()]
        prompt = build_synthesis_prompt(
            topic=topic,
            abstracts=abstracts,
            language=language,
            lit_items=lit_dicts,
        )
        response = await self._llm.ainvoke(prompt)
        return response.content.strip()

    async def _merge_syntheses(
        self, topic: str, chunk_texts: list[str], language: str
    ) -> str:
        batch_label = "批次" if language == "zh" else "Batch"
        combined = "\n\n---\n\n".join(
            f"[{batch_label} {i+1}]\n{text}" for i, text in enumerate(chunk_texts)
        )
        if language == "zh":
            merge_prompt = f"""你是资深学术研究员。以下是对主题"{topic}"多批次文献的分析摘要，请综合所有批次，输出一份统一的结构化文献综合分析（三部分：主流发现与方法、研究空白与局限、争议与张力），每部分150-250字。直接输出正文，部分之间用空行分隔。

{combined}"""
        else:
            merge_prompt = f"""You are a senior academic researcher. The following are batch literature analysis summaries for the topic "{topic}". Synthesize all batches into one unified structured literature synthesis (three sections: Mainstream Findings & Methods, Research Gaps & Limitations, Tensions & Controversies), 150-250 words each. Output prose sections separated by blank lines.

{combined}"""
        response = await self._llm.ainvoke(merge_prompt)
        return response.content.strip()

    async def run(
        self,
        topic: str,
        literature: list[LiteratureItem],
        language: str,
    ) -> str:
        if not literature:
            return f"[待生成] {topic} 文献综合"

        chunks = [
            literature[i : i + _CHUNK_SIZE]
            for i in range(0, len(literature), _CHUNK_SIZE)
        ]
        logger.info(
            "[synthesis] topic=%r total=%d chunks=%d", topic, len(literature), len(chunks)
        )

        try:
            if len(chunks) == 1:
                return await self._synthesize_chunk(topic, chunks[0], language)

            chunk_texts = await asyncio.gather(
                *[self._synthesize_chunk(topic, chunk, language) for chunk in chunks]
            )
            return await self._merge_syntheses(topic, list(chunk_texts), language)
        except Exception as e:
            err = str(e)
            if "401" in err or "AuthenticationError" in type(e).__name__ or "api_key" in err.lower():
                raise RuntimeError(f"LLM API key 无效，请检查 .env 文件: {e}") from e
            raise RuntimeError(f"文献综合失败，请重试（原因：{type(e).__name__}: {e}）") from e
