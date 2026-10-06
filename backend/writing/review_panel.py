"""4.3 — three blind reviewers with different focuses, merged into one review (settings.review_panel).

As with independent referees, each reviewer sees the same draft but not the others'
comments. Comments quoting the same text merge and keep the highest severity given; points several
reviewers raise come first. A concession threshold (a point one reviewer raises is minor) was
dropped: on 68 blind-labelled panel comments shared points were valid 30/33, single ones 31/35.
It costs about three single reviews.
"""
import asyncio

from backend.writing.review import ReviewAgent

FOCUSES = {
    "evidence": {
        "zh": "你这次重点审查：论断与证据是否相符、是否过度概括、数字与统计表述是否站得住。",
        "en": "Your focus this time: whether each claim matches its evidence, overgeneralisation, "
              "and whether figures and statistical wording hold up.",
    },
    "coverage": {
        "zh": "你这次重点审查：被忽略的反面证据、替代解释，以及本文讨论中缺失的重要研究方向。",
        "en": "Your focus this time: ignored counter-evidence, alternative explanations, and "
              "important lines of research the paper leaves out.",
    },
    "reasoning": {
        "zh": "你这次重点审查：章节之间的矛盾、推理跳步，以及超出所给证据的结论。",
        "en": "Your focus this time: contradictions between sections, skipped steps in reasoning, "
              "and conclusions that exceed the evidence given.",
    },
}
_MAX_COMMENTS = 15
_MAX_LIMITATIONS = 8


def _same_point(a: dict, b: dict) -> bool:
    return a["section"] == b["section"] and (a["quote"] in b["quote"] or b["quote"] in a["quote"])


def _merge(named: list[tuple[str, dict]]) -> list[dict]:
    groups: list[dict] = []
    for name, review in named:
        for comment in review.get("comments", []):
            group = next((g for g in groups if _same_point(g["comment"], comment)), None)
            if group is None:
                group = {"comment": comment, "reviewers": [], "severities": []}
                groups.append(group)
            if name not in group["reviewers"]:
                group["reviewers"].append(name)
            group["severities"].append(comment["severity"])
    merged = [
        {**g["comment"], "reviewers": g["reviewers"],
         "severity": "major" if "major" in g["severities"] else "minor"}
        for g in groups
    ]
    merged.sort(key=lambda c: len(c["reviewers"]) >= 2, reverse=True)  # stable: shared points first
    return merged


class ReviewPanel:
    def __init__(self, llm, retry_llm=None) -> None:
        self._agent = ReviewAgent(llm=llm, retry_llm=retry_llm)

    async def review(self, sections: dict[str, str], outline: list[dict], topic: str, language: str) -> dict:
        lang = "zh" if language == "zh" else "en"
        reviews = await asyncio.gather(*[
            self._agent.review(sections, outline, topic, language, focus=focus[lang]) for focus in FOCUSES.values()
        ])
        named = list(zip(FOCUSES, reviews))
        limitations = list(dict.fromkeys(item for r in reviews for item in r.get("limitations", [])))
        return {
            "comments": _merge(named)[:_MAX_COMMENTS],
            "limitations": limitations[:_MAX_LIMITATIONS],
            "dropped_unquoted": sum(r.get("dropped_unquoted", 0) for r in reviews),
            "panel": True,
        }
