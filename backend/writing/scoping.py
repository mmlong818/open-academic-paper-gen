import re
from typing import TYPE_CHECKING

from backend.core.llm import fast_llm

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI

from backend.writing.prompts import build_scoping_prompt


def _parse_list_items(text: str, section_header_patterns: list[str]) -> list[str]:
    lines = text.split("\n")
    items: list[str] = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        if any(p.lower() in stripped.lower() for p in section_header_patterns):
            in_section = True
            continue
        if stripped.startswith("## ") and in_section:
            break
        if in_section and stripped.startswith("- "):
            items.append(stripped[2:].strip())
    return items


class ScopingAgent:
    def __init__(self, llm: "ChatOpenAI | None" = None) -> None:
        self._llm = llm if llm is not None else fast_llm(max_tokens=1024)

    async def run(self, topic: str, language: str, source_mix: str = "en_major") -> dict:
        prompt = build_scoping_prompt(topic=topic, language=language, source_mix=source_mix)
        try:
            response = await self._llm.ainvoke(prompt)
            text = response.content
        except Exception as e:
            err = str(e)
            if "401" in err or "AuthenticationError" in type(e).__name__ or "api_key" in err.lower():
                raise RuntimeError(f"LLM API key 无效，请检查 .env 文件: {e}") from e
            raise RuntimeError(f"研究问题生成失败，请重试（原因：{type(e).__name__}: {e}）") from e

        if language == "zh":
            rqs = _parse_list_items(text, ["研究问题", "research question"])
            kws = _parse_list_items(text, ["关键词", "keyword"])
        else:
            rqs = _parse_list_items(text, ["research question", "研究问题"])
            kws = _parse_list_items(text, ["keyword", "关键词"])

        return {
            "research_questions": rqs or [f"[待生成] {topic}"],
            "keywords": kws or [topic],
        }
