import json
import logging

logger = logging.getLogger(__name__)

_ABLATION_PROMPT_ZH = """你是计算/AI 领域的研究方法专家。根据以下论文信息，设计消融实验方案：

论文主题：{topic}
研究角度与贡献：{contribution}
方法概述：{approach}

提纲章节（含方法和实验部分）：
{outline_summary}

请设计消融实验，包含：
1. 3-5 个消融变体（移除或替换某模块/超参/设计选择）
2. 每个变体的名称、修改内容、预期影响
3. 评估指标建议

返回 JSON：
{{
  "ablation_variants": [
    {{"name": "w/o X", "modification": "移除/替换 X", "expected_impact": "..."}}
  ],
  "metrics": ["指标1", "指标2"],
  "ablation_section_md": "## 消融实验\n\n...完整 markdown 段落..."
}}"""

_ABLATION_PROMPT_EN = """You are a computational/AI research methodology expert. Design an ablation study for the following paper:

Topic: {topic}
Research contribution: {contribution}
Method overview: {approach}

Outline sections (method and experiment parts):
{outline_summary}

Design an ablation study with:
1. 3-5 ablation variants (removing or replacing a module/hyperparameter/design choice)
2. Name, modification, and expected impact for each variant
3. Recommended evaluation metrics

Return JSON:
{{
  "ablation_variants": [
    {{"name": "w/o X", "modification": "Remove/replace X", "expected_impact": "..."}}
  ],
  "metrics": ["metric1", "metric2"],
  "ablation_section_md": "## Ablation Study\n\n...full markdown paragraph..."
}}"""


class AblationAgent:
    def __init__(self, llm):
        self.llm = llm

    async def run(
        self, topic: str, angle: dict, outline: list[dict], language: str = "zh"
    ) -> str:
        """返回 ablation_section_md（markdown 段落）"""
        contribution = angle.get("contribution", "") if angle else ""
        approach = angle.get("approach", "") if angle else ""
        outline_summary = "\n".join(
            f"- {item.get('title', '')}: {(item.get('summary', '') or '')[:80]}"
            for item in outline[:10]
        )
        template = _ABLATION_PROMPT_ZH if language == "zh" else _ABLATION_PROMPT_EN
        prompt = template.format(
            topic=topic,
            contribution=contribution or "未指定",
            approach=approach or "未指定",
            outline_summary=outline_summary or "（暂无提纲）",
        )

        try:
            response = await self.llm.ainvoke(prompt)
            raw = response.content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw)
            return data.get("ablation_section_md", "")
        except Exception as exc:
            logger.warning("AblationAgent failed: %s", exc)
            return ""
