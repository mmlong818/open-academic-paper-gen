import json
import re
from typing import TYPE_CHECKING

from backend.core.llm import fast_llm
from backend.writing.prompts import build_outline_prompt

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI

_DEFAULT_OUTLINE_ZH = [
    {"title": "引言", "summary": "介绍研究背景、动机与主要贡献。"},
    {"title": "相关工作", "summary": "综述现有方法与研究局限。"},
    {"title": "方法", "summary": "描述提出的方法与技术细节。"},
    {"title": "实验与结果", "summary": "展示实验设置与评估结果。"},
    {"title": "结论", "summary": "总结主要贡献并展望未来工作。"},
]

_DEFAULT_OUTLINE_EN = [
    {"title": "Introduction", "summary": "Introduces background, motivation and contributions."},
    {"title": "Related Work", "summary": "Reviews existing methods and limitations."},
    {"title": "Methodology", "summary": "Describes the proposed method in detail."},
    {"title": "Experiments", "summary": "Presents experimental setup and results."},
    {"title": "Conclusion", "summary": "Summarizes contributions and future work."},
]


def _extract_json(text: str) -> list[dict]:
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    data = json.loads(cleaned)
    if isinstance(data, list):
        return data
    raise ValueError("Expected JSON array")


class OutlineAgent:
    def __init__(self, llm: "ChatOpenAI | None" = None) -> None:
        self._llm = llm if llm is not None else fast_llm(max_tokens=2048)

    async def run(
        self,
        topic: str,
        synthesis: str,
        research_questions: list[str],
        language: str,
        angle: dict | None = None,
        taxonomy_block: str = "",
    ) -> list[dict]:
        prompt = build_outline_prompt(
            topic=topic,
            synthesis=synthesis,
            research_questions=research_questions,
            language=language,
            angle=angle,
            taxonomy_block=taxonomy_block,
        )
        try:
            response = await self._llm.ainvoke(prompt)
            return _extract_json(response.content)
        except Exception as e:
            err = str(e)
            if "401" in err or "AuthenticationError" in type(e).__name__ or "api_key" in err.lower():
                raise RuntimeError(f"LLM API key 无效，请检查 .env 文件: {e}") from e
            raise RuntimeError(f"大纲生成失败，请重试（原因：{type(e).__name__}: {e}）") from e
