"""Prompt for the evidence table, kept out of prompts.py, which is already past 800 lines."""


def build_evidence_prompt(papers: list[tuple[str, str]], language: str) -> str:
    """papers: (title, text) pairs, numbered from 1 in the prompt."""
    block = "\n\n".join(f"[{i}] {title}\n{text}" for i, (title, text) in enumerate(papers, 1))
    if language == "zh":
        return f"""请从下面每篇文献的摘要或正文节选中抽取证据表的一行。

{block}

每篇抽取六项，每项不超过 40 字：
- task：研究的问题或任务
- method：采用的方法、模型或研究设计
- data：数据集、样本或研究对象（含规模）
- metric：评价指标或测量方式
- finding：本文得到的结果（有数字就照原文写）；研究目标或贡献声明不是结果
- limitation：作者承认的、本文自身方法或结果的局限。引言里用来说明动机的他人方法缺陷不是本文的局限，不要填

只写原文明确写出的内容，不推测、不补充常识。原文没有写的项填 "未报告"。数字必须与原文一致。

只输出 JSON 数组，每篇一个对象，i 为上面的编号：
[{{"i": 1, "task": "", "method": "", "data": "", "metric": "", "finding": "", "limitation": ""}}]"""
    return f"""Extract one evidence-table row from the abstract or text excerpt of each paper below.

{block}

For each paper give six fields, each at most 25 words:
- task: the research question or task
- method: the method, model or study design
- data: dataset, sample or study population (with its size)
- metric: evaluation metric or measure
- finding: a result this paper obtains (quote figures as the text gives them); an aim or
  claimed contribution is not a result
- limitation: a limitation of this paper's own method or results that the authors state.
  Shortcomings of earlier methods cited as motivation are not this paper's limitations

Write only what the text states; do not infer or add general knowledge. A field the text does not
report is "not reported". Every number must match the text.

Output a JSON array only, one object per paper, i being its number above:
[{{"i": 1, "task": "", "method": "", "data": "", "metric": "", "finding": "", "limitation": ""}}]"""
