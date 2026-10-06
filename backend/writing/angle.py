import json
import re
from typing import TYPE_CHECKING, Any

from backend.writing.prompts import build_angle_prompt

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI

def _extract_json(text: str) -> dict:
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    data = json.loads(cleaned)
    if isinstance(data, dict):
        return data
    raise ValueError("Expected JSON object")


class AngleAgent:
    def __init__(self, llm: "ChatOpenAI") -> None:
        self._llm = llm

    async def run(
        self,
        topic: str,
        synthesis: str,
        research_questions: list[str],
        language: str,
    ) -> dict[str, Any]:
        prompt = build_angle_prompt(
            topic=topic,
            synthesis=synthesis,
            research_questions=research_questions,
            language=language,
        )
        try:
            response = await self._llm.ainvoke(prompt)
            return _extract_json(response.content)
        except Exception as e:
            err = str(e)
            if "401" in err or "AuthenticationError" in type(e).__name__ or "api_key" in err.lower():
                raise RuntimeError(f"LLM API key 无效，请检查 .env 文件: {e}") from e
            raise RuntimeError(f"写作角度生成失败，请重试（原因：{type(e).__name__}: {e}）") from e
