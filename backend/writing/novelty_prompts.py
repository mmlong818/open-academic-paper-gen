"""Prompt for the novelty diagnosis, kept out of prompts.py, which is already past 800 lines."""


def build_novelty_prompt(topic: str, angle: dict, candidates: str, language: str) -> str:
    angle_block = "\n".join(f"- {k}: {angle[k]}" for k in ("writing_angle", "contribution", "gap") if angle.get(k))
    if language == "zh":
        return f"""你是挑剔的领域审稿人。请诊断下面这个论文写作角度的新颖性，不要改写它。

研究主题：{topic}

写作角度：
{angle_block}

文献池中与该角度最接近的文献（方括号内为 cite key）：
{candidates}

请完成：
1. 分四个层面判断新颖性，每层给 verdict（"new" 新 / "incremental" 增量 / "existing" 已有）和一句理由：
   problem（研究问题）、method（方法）、data（数据或情境）、perspective（视角或理论框架）。
2. 识别伪创新，可多选，没有就给空数组。pattern 取值：
   "a_plus_b"（简单拼接两个已有方向）、"old_method_new_domain"（旧方法换个领域）、
   "dataset_swap"（只换数据集或样本）、"rebranding"（已有概念换新名字）。
3. 压力测试：从上面的文献中选出与该角度重叠最多的 1-3 篇（至少 1 篇），只能用上面出现过的 cite key，说明重叠在哪里；反对意见里点名的文献也要列在这里。
4. 写出审稿人最可能提出的一条反对意见。

只依据上面给出的文献判断；文献池未覆盖的方向，不要断言"已有"。

只输出 JSON：
{{"levels": {{"problem": {{"verdict": "", "reason": ""}}, "method": {{"verdict": "", "reason": ""}}, "data": {{"verdict": "", "reason": ""}}, "perspective": {{"verdict": "", "reason": ""}}}},
 "pseudo": [{{"pattern": "", "reason": ""}}],
 "closest": [{{"key": "", "overlap": ""}}],
 "objection": ""}}"""
    return f"""You are a demanding reviewer in this field. Diagnose the novelty of the writing angle
below; do not rewrite it.

Research topic: {topic}

Writing angle:
{angle_block}

Papers of the pool closest to the angle (cite key in brackets):
{candidates}

Do the following:
1. Judge novelty on four levels, each with a verdict ("new" | "incremental" | "existing") and a
   one-sentence reason: problem, method, data (data or setting), perspective (lens or theory).
2. Name any pseudo-innovation, possibly several, or an empty array. pattern is one of:
   "a_plus_b" (two existing lines simply joined), "old_method_new_domain", "dataset_swap"
   (only the dataset or sample changes), "rebranding" (an existing idea renamed).
3. Pressure test: pick the 1-3 papers above that overlap the angle most (at least one), using
   only cite keys shown above, and say where they overlap; list here any paper the objection names.
4. State the single objection a reviewer is most likely to raise.

Judge only from the papers shown; where the pool is silent, do not assert "existing".

Output JSON only:
{{"levels": {{"problem": {{"verdict": "", "reason": ""}}, "method": {{"verdict": "", "reason": ""}}, "data": {{"verdict": "", "reason": ""}}, "perspective": {{"verdict": "", "reason": ""}}}},
 "pseudo": [{{"pattern": "", "reason": ""}}],
 "closest": [{{"key": "", "overlap": ""}}],
 "objection": ""}}"""
