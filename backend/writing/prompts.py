from __future__ import annotations

from backend.literature.text_length import weighted_length


def authors_str_for_apa(authors: list[str]) -> str:
    """Format author list for APA inline citation."""
    if not authors:
        return "Unknown"
    if len(authors) == 1:
        return authors[0].split()[-1]
    if len(authors) == 2:
        return f"{authors[0].split()[-1]} & {authors[1].split()[-1]}"
    return f"{authors[0].split()[-1]} et al."


def build_scoping_prompt(topic: str, language: str, source_mix: str = "en_major") -> str:
    if language == "zh":
        return f"""你是一位学术研究专家。针对以下研究主题，请生成：
1. 3-5 个核心研究问题（research_questions），每个问题一行，以 "- " 开头
2. 4-6 个中文检索关键词，每个关键词一行，以 "- " 开头
3. 4-6 个英文关键词（该领域在英文文献中的通用术语，用于检索 Semantic Scholar、arXiv 等英文数据库），每个一行，以 "- " 开头

研究主题：{topic}

请按以下格式输出：
## 研究问题
- <研究问题1>
- <研究问题2>

## 中文关键词
- <中文关键词1>
- <中文关键词2>

## 英文关键词
- <English keyword 1>
- <English keyword 2>"""
    if source_mix != "en_major":
        # Chinese sources need Chinese terms; the crew routes them there
        return f"""You are an academic research expert. For the following research topic, generate:
1. 3-5 core research questions, each on a new line starting with "- "
2. 4-6 English search keywords, each on a new line starting with "- "
3. 4-6 Chinese keywords (the field's terms as used in Chinese literature, for searching Chinese sources), each on a new line starting with "- "

Research topic: {topic}

Output format:
## Research Questions
- <question1>
- <question2>

## English Keywords
- <keyword1>
- <keyword2>

## Chinese Keywords
- <中文关键词1>
- <中文关键词2>"""
    return f"""You are an academic research expert. For the following research topic, generate:
1. 3-5 core research questions, each on a new line starting with "- "
2. 5-10 search keywords, each on a new line starting with "- "

Research topic: {topic}

Output format:
## Research Questions
- <question1>
- <question2>

## Keywords
- <keyword1>
- <keyword2>"""


_ABSTRACT_MAX_CHARS = 600
_EXCERPT_MAX_CHARS = 900
_EXCERPT_MIN_CHARS = 300


def _body_excerpt_for_prompt(item: dict) -> str:
    """Return the body excerpt only when it adds something the abstract does not.

    content_fetcher falls back to the abstract when no open-access PDF is available,
    so an excerpt that merely repeats the abstract would double the prompt for nothing.
    """
    excerpt = (item.get("body_excerpt") or "").strip()
    abstract = (item.get("abstract") or "").strip()
    if weighted_length(excerpt) < _EXCERPT_MIN_CHARS or excerpt == abstract or excerpt in abstract:
        return ""
    if len(excerpt) > _EXCERPT_MAX_CHARS:
        return excerpt[:_EXCERPT_MAX_CHARS] + "..."
    return excerpt


_TITLE_ONLY_MARK = {"zh": "    （仅标题：无摘要与正文）", "en": "    (Title only: no abstract or full text)"}


def _format_literature_block(lit_items: list[dict], language: str = "en") -> str:
    """Format literature items as a numbered reference block for prompts."""
    lines: list[str] = []
    for i, item in enumerate(lit_items, 1):
        authors = item.get("authors_str", "Unknown Authors")
        year = item.get("year", "n.d.")
        title = item.get("title", "Untitled")
        journal = item.get("journal", "")
        doi = item.get("doi", "")
        abstract = item.get("abstract", "").strip()

        ref_line = f"[{i}] {authors} ({year}). {title}."
        if journal:
            ref_line += f" {journal}."
        if doi:
            ref_line += f" https://doi.org/{doi}"
        lines.append(ref_line)
        if abstract:
            # Truncate abstract to ~200 chars to keep prompt size manageable
            snippet = (abstract[:_ABSTRACT_MAX_CHARS] + "..."
                   if len(abstract) > _ABSTRACT_MAX_CHARS else abstract)
            lines.append(f"    Abstract: {snippet}")
        excerpt = _body_excerpt_for_prompt(item)
        if excerpt:
            lines.append(f"    Full-text excerpt: {excerpt}")
        if item.get("evidence"):
            lines.append(f"    Evidence row: {item['evidence']}")
        if not abstract and not (item.get("body_excerpt") or "").strip():
            lines.append(_TITLE_ONLY_MARK["zh" if language == "zh" else "en"])
        lines.append("")
    return "\n".join(lines)


def build_synthesis_prompt(
    topic: str,
    abstracts: list[str],
    language: str,
    lit_items: list[dict] | None = None,
) -> str:
    if lit_items:
        refs_block = _format_literature_block(lit_items, language)
    else:
        refs_block = "\n\n".join(f"[{i+1}] {a}" for i, a in enumerate(abstracts))

    if language == "zh":
        return f"""你是一位资深学术研究员，擅长从文献群中发现研究格局和突破口。请根据以下文献，为主题"{topic}"撰写结构化文献综合分析。

要求按以下三部分输出（每部分150-250字），直接输出正文，不要用Markdown标题：

第一部分【主流发现与方法】：归纳现有研究的核心结论、主流方法论和代表性范式，必须引用具体文献（使用"(作者姓, 年份)"格式，如"(Smith et al., 2021)"），指明具体数据和发现（如"X%的研究发现…"、"N项研究表明…"）。

第二部分【研究空白与局限】：明确指出当前研究覆盖不足的维度（哪些群体、情境、变量被忽视？哪些假设尚未被检验？），引用具体文献说明其局限，这些空白是后续原创研究的切入口。

第三部分【争议与张力】：梳理学界内部的分歧、对立观点或尚未解决的理论张力，引用具体持对立观点的文献，这些张力往往是创新论点的生长点。

参考文献列表（只能引用以下文献，不得引用未列出的文献）：
{refs_block}

直接输出三部分正文，每部分之间用空行分隔。所有引用必须来自以上文献列表。"""

    return f"""You are a senior academic researcher skilled at identifying research landscapes and breakthrough opportunities. Based on the following literature, write a structured literature synthesis for the topic "{topic}".

Output three sections (150-250 words each) as flowing prose without markdown headers:

Section 1 [Mainstream Findings & Methods]: Summarize core conclusions, dominant methodologies, and representative paradigms. You MUST cite specific papers using (Author et al., year) format (e.g., "(Smith et al., 2021)"), and include specific data points and quantitative findings where available (e.g., "X% of studies found...", "N studies demonstrated...").

Section 2 [Research Gaps & Limitations]: Explicitly identify underexplored dimensions (which populations, contexts, variables, or assumptions remain untested?). Cite specific papers to illustrate their limitations. These gaps are the entry points for original research.

Section 3 [Tensions & Controversies]: Map the disagreements, competing perspectives, and unresolved theoretical tensions. Cite specific papers holding opposing views. These tensions are where innovative arguments grow.

Reference list (you MUST ONLY cite from the following list — do not invent references):
{refs_block}

Output the three sections as prose, separated by blank lines. All citations must come from the reference list above."""


def build_angle_prompt(
    topic: str,
    synthesis: str,
    research_questions: list[str],
    language: str,
) -> str:
    rqs = "\n".join(f"- {q}" for q in research_questions)
    if language == "zh":
        return f"""你是一位资深学术编辑，擅长发掘论文的创新角度和学术贡献点。

研究主题：{topic}

研究问题：
{rqs}

文献综合（现有研究现状）：
{synthesis}

请根据以上信息，为这篇论文寻找一个能够体现创新性和学术贡献的写作角度。具体需要：

1. **识别研究空白**：在现有文献中，哪些维度、情境、群体或方法论被忽视了？
2. **提出写作角度**：一个能使本文区别于泛化综述的独特切入点（例如：聚焦特定群体、引入新的理论框架、跨学科整合、挑战主流假设等）
3. **明确学术贡献**：本文对学术界的新增价值是什么？能回答什么尚未解决的问题？
4. **可验证假设**：提出2-3个基于此写作角度、可通过实验/案例/模型验证的具体假设
5. **推荐研究方法**：最适合验证上述假设的研究方法

输出格式（JSON，只输出JSON，不要其他文字）：
{{
  "writing_angle": "一句话描述独特的写作角度",
  "contribution": "2-3句话说明对学术界的新增价值",
  "gap": "现有研究中被忽视的具体空白",
  "hypotheses": ["假设1", "假设2", "假设3"],
  "approach": "推荐的研究方法（1-2句）"
}}"""
    return f"""You are a senior academic editor skilled at identifying innovative angles and scholarly contributions.

Research topic: {topic}

Research questions:
{rqs}

Literature synthesis (current state of research):
{synthesis}

Based on the above, identify a writing angle that demonstrates innovation and academic contribution:

1. **Identify research gaps**: Which dimensions, contexts, populations, or methodologies are underexplored?
2. **Propose a writing angle**: A unique entry point that distinguishes this paper from a generic review (e.g., focus on a specific population, introduce a new theoretical framework, cross-disciplinary integration, challenge mainstream assumptions)
3. **Articulate contribution**: What new value does this paper add? What unanswered questions does it address?
4. **Verifiable hypotheses**: 2-3 specific, testable hypotheses grounded in this angle
5. **Recommended approach**: The most suitable research method for validating the hypotheses

Output format (JSON only, no other text):
{{
  "writing_angle": "One sentence describing the unique angle",
  "contribution": "2-3 sentences on new academic value",
  "gap": "Specific gap overlooked in existing research",
  "hypotheses": ["Hypothesis 1", "Hypothesis 2", "Hypothesis 3"],
  "approach": "Recommended research method (1-2 sentences)"
}}"""


def build_outline_prompt(
    topic: str,
    synthesis: str,
    research_questions: list[str],
    language: str,
    angle: dict | None = None,
    taxonomy_block: str = "",
) -> str:
    rqs = "\n".join(f"- {q}" for q in research_questions)
    if language == "zh":
        taxonomy_part = ""
        if taxonomy_block:
            taxonomy_part = f"""
文献主题群（按文献间的引用关系与内容相似度聚类得到）：
{taxonomy_block}

主体分析章节须按这些主题群组织：每节对应一个或多个相近的主题群，而不是逐篇介绍文献或只按研究问题罗列。
每个章节的 JSON 对象增加 "clusters" 字段，列出该节依据的主题群编号（摘要、引言、方法、结论等可为空数组）。
"""
        angle_block = ""
        if angle:
            hyps = "\n".join(f"  - {h}" for h in angle.get("hypotheses", []))
            angle_block = f"""
写作角度与创新贡献：
- 独特视角：{angle.get("writing_angle", "")}
- 研究空白：{angle.get("gap", "")}
- 学术贡献：{angle.get("contribution", "")}
- 可验证假设：
{hyps}
- 研究方法：{angle.get("approach", "")}

大纲必须体现上述写作角度，确保文章有明确的创新贡献和可论证的核心命题。
"""
        return f"""你是一位学术写作专家，负责为系统综述/范围综述类期刊论文生成结构化大纲。

研究主题：{topic}

研究问题：
{rqs}

文献综合：
{synthesis}
{angle_block}{taxonomy_part}
请生成包含 6-8 个章节的大纲，结构必须符合学术期刊规范，包含以下必要部分：
1. 摘要（Abstract）— 说明摘要应包含：研究背景、目的、方法、主要发现、结论
2. 引言（Introduction）— 研究背景、研究空白、研究目的和研究问题
3. 方法（Methodology）— 文献检索策略、纳入/排除标准、分析框架（如PRISMA-ScR）
4. 主体分析章节（2-3节）— 围绕核心研究问题展开，至少一节需要包含比较分析表格
5. 讨论（Discussion）— 综合发现、理论意涵、与现有研究对比
6. 结论（Conclusion）— 主要贡献、局限性、未来研究方向

每个主体分析章节的summary中，如果该章节适合包含表格，请在summary末尾注明"[需要比较分析表]"。

输出格式（每个章节一个 JSON 对象，以 JSON 数组输出）：
[
  {{"title": "摘要", "summary": "结构化摘要，包含背景、目的、方法、发现和结论五个部分"}},
  {{"title": "引言", "summary": "介绍研究背景、动机，明确研究空白，陈述研究目的和三个研究问题..."}}
]

只输出 JSON，不要其他文字。"""

    taxonomy_part = ""
    if taxonomy_block:
        taxonomy_part = f"""
Literature groups (clustered by citation links and content similarity among the papers):
{taxonomy_block}

Organise the main analysis sections around these groups: each covers one or more related groups,
rather than walking through papers one by one or listing research questions.
Give every section object a "clusters" field listing the group numbers it draws on (empty for
Abstract, Introduction, Methodology, Conclusion and the like).
"""
    angle_block = ""
    if angle:
        hyps = "\n".join(f"  - {h}" for h in angle.get("hypotheses", []))
        angle_block = f"""
Writing Angle & Innovation:
- Unique angle: {angle.get("writing_angle", "")}
- Research gap: {angle.get("gap", "")}
- Contribution: {angle.get("contribution", "")}
- Verifiable hypotheses:
{hyps}
- Recommended approach: {angle.get("approach", "")}

The outline MUST reflect the above writing angle and ensure the paper has a clear, arguable thesis and novel contribution.
"""
    return f"""You are an academic writing expert generating a structured outline for a systematic/scoping review journal article.

Topic: {topic}

Research Questions:
{rqs}

Literature Synthesis:
{synthesis}
{angle_block}{taxonomy_part}
Generate an outline with 6-8 sections following academic journal conventions. The structure MUST include:
1. Abstract — Note: should contain background, purpose, methods, findings, and conclusions
2. Introduction — Research background, gap, purpose, and research questions
3. Methodology — Search strategy, inclusion/exclusion criteria, analytical framework (e.g., PRISMA-ScR)
4. Main Analysis Sections (2-3 sections) — Organized around core research questions; at least one section should include a comparative analysis table
5. Discussion — Synthesized findings, theoretical implications, comparison with existing literature
6. Conclusion — Main contributions, limitations, future research directions

For body/analysis sections where a comparative table would be appropriate, add "[TABLE REQUIRED]" at the end of the summary.

Output format (JSON array only, no other text):
[
  {{"title": "Abstract", "summary": "Structured abstract covering background, purpose, methods, findings, and conclusions"}},
  {{"title": "Introduction", "summary": "Introduces background, explicitly states research gap, presents research purpose and three research questions..."}}
]"""


def _detect_section_role(title: str) -> str:
    t = title.lower()
    if any(k in t for k in ["abstract", "摘要"]):
        return "abstract"
    if any(k in t for k in ["introduction", "引言", "背景", "background", "intro"]):
        return "introduction"
    if any(k in t for k in ["conclusion", "结论", "总结", "future"]):
        return "conclusion"
    if any(k in t for k in ["discussion", "讨论"]):
        return "discussion"
    if any(k in t for k in ["method", "方法", "methodology", "prisma"]):
        return "methodology"
    if any(k in t for k in ["related", "相关", "literature", "文献", "review"]):
        return "related_work"
    return "body"


def _review_facts_block(role: str, facts: str, language: str) -> str:
    """The real search behind the pool, for every section asked to describe the method, so none invents one."""
    if role not in ("methodology", "abstract", "introduction"):
        return ""
    if language == "zh":
        rule = ("描述文献检索与筛选过程时，只能使用下列事实。不得编造数据库、检索日期、检索式、时间限定、"
                "筛选人数、一致性系数、质量评价工具，或下文未列出的任何数量；某项常规细节未列出时，省略或说明未记录。")
        return f"\n{rule}\n" + (f"文献检索与筛选事实：\n{facts}\n" if facts else "")
    rule = ("Describe the literature search and screening ONLY with the facts below. Do not invent databases, "
            "search dates, query strings, date limits, numbers of reviewers, agreement statistics, appraisal tools, "
            "or any count not listed; where a usual detail is not listed, omit it or say it was not recorded.")
    return f"\n{rule}\n" + (f"Review-process facts:\n{facts}\n" if facts else "")


def _required_citations_line(required: dict | None, language: str) -> str:
    """The section's minimum citations per language, from the task's literature mix."""
    zh, en = (required or {}).get("zh", 0), (required or {}).get("en", 0)
    if language == "zh":
        parts = []
        if zh:
            parts.append(f"本节须至少引用 {zh} 篇中文文献（列表中标题为中文的文献）；标注「仅标题」的可作为国内已有相关研究或应用的例子引用，不描述其方法与结论")
        if en:
            parts.append(f"本节须至少引用 {en} 篇英文文献")
    else:
        parts = []
        if zh:
            parts.append(f"This section must cite at least {zh} Chinese-language references (those with Chinese titles in the list); "
                         "ones marked \"Title only\" may be cited as examples of existing work in China, without describing their methods or findings")
        if en:
            parts.append(f"This section must cite at least {en} English-language references")
    return "".join(f"\n- {part}" for part in parts)


def build_section_prompt(
    section_title: str,
    outline_context: str,
    synthesis: str,
    literature_snippets: list[str],
    language: str,
    cite_keys: list[str] | None = None,
    angle: dict | None = None,
    lit_items: list[dict] | None = None,
    review_facts: str = "",
    required_citations: dict | None = None,
) -> str:
    keys = cite_keys or []
    role = _detect_section_role(section_title)
    facts_block = _review_facts_block(role, review_facts, language)
    # the abstract is written without citations
    required_line = "" if role == "abstract" else _required_citations_line(required_citations, language)
    needs_table = "[TABLE REQUIRED]" in outline_context or "[需要比较分析表]" in outline_context

    # Build rich reference block from lit_items if available
    if lit_items:
        refs_block = _format_literature_block(lit_items, language)
        # cite:KEY guide — maps each bibtex key to its reference entry
        cite_key_lines = "\n".join(
            f"  {key} → {item.get('authors_str', 'Unknown')} ({item.get('year', 'n.d.')}). {item.get('title', '')[:60]}"
            for key, item in zip(keys, lit_items)
        )
        apa_guide = cite_key_lines
    elif literature_snippets:
        refs_block = "\n\n".join(f"[{i+1}] {s}" for i, s in enumerate(literature_snippets))
        apa_guide = ""
    else:
        refs_block = ""
        apa_guide = ""

    angle_block_zh = ""
    angle_block_en = ""
    if angle:
        hyps = "；".join(angle.get("hypotheses", [])[:2])
        angle_block_zh = f"""
本文核心写作角度（必须在本章节中体现）：
- 独特视角：{angle.get("writing_angle", "")}
- 研究空白：{angle.get("gap", "")}
- 学术贡献：{angle.get("contribution", "")}
- 核心假设：{hyps}
"""
        hyps_en = "; ".join(angle.get("hypotheses", [])[:2])
        angle_block_en = f"""
Core Writing Angle (must be reflected in this section):
- Unique perspective: {angle.get("writing_angle", "")}
- Research gap: {angle.get("gap", "")}
- Contribution: {angle.get("contribution", "")}
- Key hypotheses: {hyps_en}
"""

    if language == "zh":
        role_instruction_zh = {
            "abstract": "本节为结构化摘要。必须按以下五个方面撰写（每方面1-3句）：①背景（研究领域现状和必要性）；②目的（本研究的具体目标）；③方法（文献来源、检索与筛选过程，依据下列事实）；④主要发现（3-5个具体发现，包含数据）；⑤结论（主要贡献和实践启示）。摘要不引用文献，不分段，输出单段连贯文字，200-300字。",
            "introduction": "本章节为引言。必须：①从宏观背景切入，引用2-3篇文献说明该领域的重要性和发展现状；②明确陈述现有研究的空白或不足（引用具体文献）；③明确提出本文的三个研究问题（RQ1、RQ2、RQ3）；④简述本文的研究方法和全文结构。字数要求：800-1200字。",
            "conclusion": "本章节为结论。必须：①逐一回答引言中提出的研究问题（RQ1、RQ2、RQ3），每个RQ给出明确答案；②列举本文对学术界的3-5个新增贡献（与现有研究的不同之处）；③指出本研究的2-3个局限性；④提出3-5个具体可行的未来研究方向。字数要求：800-1200字。",
            "discussion": "本章节为讨论。必须：①综合本文各章节的核心发现；②与现有文献对比（既指出一致之处，也指出矛盾或新发现），引用具体文献；③阐述理论意涵（本文发现对理论框架的贡献）；④阐述实践启示（对教育者、设计者、政策制定者等的具体建议）。字数要求：800-1200字。",
            "methodology": "本章节为研究方法。必须：①说明采用的系统综述/范围综述框架（如PRISMA-ScR）；②依据下列事实说明文献检索与筛选过程（来源、检索词、引用链追溯）；③明确纳入和排除标准（各3-5条，以表格形式呈现）；④说明数据提取和分析过程；⑤依据下列事实报告各环节数量与最终纳入文献数量。必须包含一个纳入/排除标准对比表。字数要求：600-900字。",
            "related_work": "本章节为文献综述。不要只做罗列。必须：①围绕本文的研究问题组织文献，引用至少5篇提供的文献；②评价各研究的方法和发现，指出其贡献和局限（而非仅描述内容）；③明确指出哪些维度被现有研究忽视（本文的切入口）；④如适合，用表格呈现现有研究的对比分析。字数要求：800-1200字。",
            "body": "本章节为正文主体。必须：①明确回应本章节对应的研究问题；②引用至少5篇提供的文献，并提供具体数据和发现（而非泛泛而谈）；③既分析正面发现（支持性证据），也分析负面发现或局限（反驳性证据），做到双向分析；④如适合，用表格汇总文献中的关键数据或研究特征；⑤每段落都要有明确的论点句，避免仅做描述。字数要求：1000-1500字。",
        }.get(role, "字数要求：1000-1500字。")

        table_instruction = "\n- 本章节必须包含至少一个Markdown格式的比较分析表（使用|列1|列2|格式），汇总关键文献数据或研究特征。" if needs_table or role in ("methodology", "body") else ""

        cite_instruction = "引用文献时必须使用标记格式 [cite:KEY]，其中 KEY 来自下方的引用键列表。每个标记只放一个 KEY，同时引用多篇时写成 [cite:KEY1][cite:KEY2]，不要写成 [cite:KEY1, cite:KEY2]。只能引用以下文献，禁止虚构引用键。"

        return f"""你是一位学术写作专家，正在撰写一篇关于"{section_title}"的期刊论文章节。

{role_instruction_zh}
{facts_block}{angle_block_zh}
论文大纲概览：
{outline_context}

文献综合背景：
{synthesis}

可引用文献列表（只能引用以下文献，不得引用未列出的文献）：
{refs_block}

引用键映射（使用 [cite:KEY] 格式在正文中标注引用，KEY 必须来自以下列表）：
{apa_guide}

写作要求：
- {cite_instruction}
- 若某篇文献附有「正文节选」，须优先依据节选中的具体方法、数据与结论展开论述，而非停留在摘要的概括表述
- 标注「仅标题」的文献只能作为某类研究或应用领域的例子引用，不得描述其方法、数据或结论{required_line}
- 避免直接复制摘要内容，需要综合提炼{table_instruction}
- 使用正式学术写作风格
- 使用第三人称
- 只输出章节正文内容，不要添加章节标题行

直接输出章节正文，不要重复章节标题。"""

    role_instruction_en = {
        "abstract": "This is the Structured Abstract. Write exactly five labeled components (1-3 sentences each): ①Background (field context and necessity); ②Purpose (specific research objectives); ③Methods (sources, search and screening, as given in the facts below); ④Findings (3-5 specific findings with data); ⑤Conclusions (contributions and practical implications). No citations in abstract. Output as single continuous paragraph, 200-300 words.",
        "introduction": "This is the Introduction. You MUST: ①Open with macro context, citing 2-3 papers on the field's importance and development; ②Explicitly state gaps or limitations in existing research (cite specific papers); ③Clearly articulate THREE research questions (RQ1, RQ2, RQ3); ④Briefly outline the paper's method and structure. Target: 800-1200 words.",
        "conclusion": "This is the Conclusion. You MUST: ①Answer each research question directly (RQ1, RQ2, RQ3) with explicit answers; ②Enumerate 3-5 specific new contributions of this paper (how it differs from existing literature); ③Acknowledge 2-3 limitations of this study; ④Propose 3-5 concrete future research directions. Target: 800-1200 words.",
        "discussion": "This is the Discussion. You MUST: ①Synthesize core findings from all sections; ②Compare with existing literature (both convergences AND divergences, cite specific papers); ③Articulate theoretical implications (what this paper contributes to theory); ④Articulate practical implications (specific recommendations for educators, designers, policymakers, etc.). Target: 800-1200 words.",
        "methodology": "This is the Methodology section. You MUST: ①State the systematic/scoping review framework used (e.g., PRISMA-ScR); ②Describe the search and screening from the facts below (sources, search terms, citation chaining); ③Present inclusion AND exclusion criteria (3-5 each) in a formatted table; ④Describe data extraction and analysis process; ⑤Report the counts at each stage and the final number of included studies from the facts below. MUST include one inclusion/exclusion criteria table. Target: 600-900 words.",
        "related_work": "This is the Literature Review section. Do NOT merely list studies. You MUST: ①Organize literature thematically around the research questions, citing at least 5 provided papers; ②Critically evaluate methods and findings (contributions AND limitations, not just descriptions); ③Explicitly identify gaps (this paper's entry point); ④Where appropriate, use a table to present comparative analysis of existing studies. Target: 800-1200 words.",
        "body": "This is a main analysis section. You MUST: ①Address the specific research question this section covers; ②Cite at least 5 provided papers, including specific data and quantitative findings; ③Provide BIDIRECTIONAL analysis — both supportive evidence (positive findings) AND contradictory/limiting evidence (negative findings, limitations, unresolved issues); ④Where appropriate, use a table to summarize key data or study characteristics from the literature; ⑤Every paragraph must have a clear topic sentence. Target: 1000-1500 words.",
    }.get(role, "Target: 1000-1500 words.")

    table_instruction = "\n- This section MUST include at least one Markdown-formatted comparative table (using |col1|col2| format) summarizing key literature data or study characteristics." if needs_table or role in ("methodology", "body") else ""

    cite_instruction = "Cite using marker format [cite:KEY] where KEY comes from the key mapping below. One KEY per marker: cite several papers as [cite:KEY1][cite:KEY2], never [cite:KEY1, cite:KEY2]. ONLY use keys from that list — do not invent citation keys."

    return f"""You are an academic writing expert writing the section "{section_title}" for a journal article.

{role_instruction_en}
{facts_block}{angle_block_en}
Paper Outline Overview:
{outline_context}

Literature Synthesis Background:
{synthesis}

Reference list (ONLY cite from these — do not invent references):
{refs_block}

Citation key mapping (use [cite:KEY] format in body text, KEY must come from this list):
{apa_guide}

Requirements:
- {cite_instruction}
- Where a reference carries a "Full-text excerpt", ground your claims in the specific methods, data and conclusions it reports rather than the abstract's generalities
- A reference marked "Title only" may be cited only as an example of a kind of work or application area; never describe its methods, data or findings{required_line}
- Synthesize and analyze — do not copy abstract text directly{table_instruction}
- Formal academic writing style, third person
- Output section body only, no section heading

Output the section body directly, without repeating the section title."""


def _format_claims_block(claims: list[dict], claim_label: str, context_label: str) -> str:
    lines: list[str] = []
    for i, claim in enumerate(claims, 1):
        context = (claim.get("context") or "").strip()
        if context:
            lines.append(f"{i}. [{context_label}] {context}")
            lines.append(f"   [{claim_label}] {claim.get('sentence', '')}")
        else:
            lines.append(f"{i}. [{claim_label}] {claim.get('sentence', '')}")
        lines.append("")
    return "\n".join(lines)


# Finer grades, offered when settings.l3_fine_grades is on.
_FINE_GRADES_ZH = """
- "partial"：归给文献的核心内容有原文依据，但其中某个限定、范围或推广超出了原文（如原文只在某个数据集上成立，句子说成普遍成立）。核心内容没有依据时不用此项。
- "misaligned"：原文结论的方向与该内容相反，或原文说的是另一对象、条件或比较（如原文称不用 3D 输入精度相近，句子却说需要 3D 输入）。此时不判 "unsupported"。"""
_FINE_GRADES_EN = """
- "partial"     — the core of what is attributed is grounded, but a qualifier, scope or generalisation
                  goes beyond the source (it holds on one dataset; the sentence says it holds generally).
                  Not for a core that is itself ungrounded.
- "misaligned"  — the source's finding runs the other way, or concerns a different subject, condition
                  or comparison (the source finds similar accuracy without 3D inputs; the sentence says
                  3D inputs are needed). Use this instead of "unsupported"."""


def build_support_prompt(
    title: str, evidence: str, claims: list[dict], language: str, key: str, passages: bool = False,
    fine: bool = False,
) -> str:
    """Ask whether a cited source supports what the draft attributes to it.

    Only the content the [cite:KEY] marker attaches to is judged; the writer's own
    evaluation around it is not a claim of the source.
    """
    grades_zh = _FINE_GRADES_ZH if fine else ""
    grades_en = _FINE_GRADES_EN if fine else ""
    choices_zh = '"supported"、"partial"、"misaligned"、"unsupported" 或 "unclear"' if fine else '"supported" 或 "unsupported" 或 "unclear"'
    choices_en = '"supported" | "partial" | "misaligned" | "unsupported" | "unclear"' if fine else '"supported" | "unsupported" | "unclear"'
    marker = f"[cite:{key}]"
    # Describe the evidence as it is: calling an abstract "passages picked from the full text"
    # pushed abstract-only verdicts towards unclear (29.7% vs 21.3% on the same pool).
    if passages:
        source_zh = "论文开头，以及按待核句从全文中挑出的若干段落，段落之间以 [...] 分隔"
        source_en = "the paper's opening plus passages picked from the full text for these sentences,\nseparated by [...]"
    else:
        source_zh = "摘要，以及/或正文开头的节选"
        source_en = "the abstract and/or the opening of the paper"
    if language == "zh":
        claims_block = _format_claims_block(claims, claim_label="待核句", context_label="上文")
        return f"""你是引文核验专家。下面每个待核句中都带有标记 {marker}，它指向下面这篇被引文献。请判断：正文借 {marker} 归给这篇文献的内容，原文是否支持。

被引文献标题：{title}

被引文献原文（{source_zh}；这只是论文的一部分，但是你能依据的全部证据）：
{evidence}

先确定要核对的内容——只核对 {marker} 所附着的那部分：
- 句中其他 [cite:...] 标记指向别的文献，与它们相关的内容不在本次核对范围。
- 作者自己的评价、推论、局限性分析、对比或转折（如"但……仍未解决""这意味着……""不能据此推断……"）是作者的观点，不是这篇文献的主张，一律不核对，也不因其与原文不一致而判 unsupported。
- 若句子是表格，只看包含 {marker} 的那一行，并只核对该行中描述这篇文献本身的格子。
- 若文献只是被当作某类研究、方法或主题的例子（如"检索还覆盖了 X 等研究 {marker}"），只核对它是否属于该类。
- 若多篇文献共同支撑一组内容（如"涉及 A、B 与 C [cite:甲]{marker}"），这篇文献只需支撑其中与它相关的部分。

判定标准：
- "supported"：原文陈述了该内容，或可由原文直接推出。概括、转述、换一种说法都算支持，不要求逐字对应。
- "unsupported"：原文与该内容矛盾，或给出了不同的具体数字、研究对象或结论。只因给出的原文里没有提到某个细节，不能判 unsupported。
- "unclear"：该内容涉及的具体细节（数字、实验设置、特定结论）在给出的原文中找不到。给出的只是论文的一部分，没提到不等于论文里没有。{grades_zh}

只依据上面给出的原文判断。证据缺失应判 "unclear"，不是 "unsupported"；但只要归给文献的内容在原文中能找到依据，就应判 "supported"，不要因为句中还有作者自己的评述而降为 "unclear"。

待核句：
{claims_block}
请仅输出 JSON 数组，每条陈述一个对象，顺序与上面一致，不要输出其他文字：
[{{"verdict": {choices_zh}, "reason": "一句话理由"}}]"""

    claims_block = _format_claims_block(claims, claim_label="SENTENCE", context_label="context")
    return f"""You are a citation verification expert. Each sentence below carries the marker
{marker}, which points to the cited source below. Decide whether the source supports what the
manuscript attributes to it through {marker}.

Cited source: {title}

Source text ({source_en}; it is only part of the paper, but it is ALL the evidence you have):
{evidence}

First isolate what to check — only the part of the sentence that {marker} attaches to:
- Other [cite:...] markers in the sentence point to other sources; content tied to them is out of scope.
- The writer's own evaluation, inference, limitation, contrast or caveat ("but X remains
  unresolved", "this suggests...", "does not address...") is the writer's view, not a claim of
  this source. Do not check it, and never mark "unsupported" because it disagrees with the source.
- If the sentence is a table, look only at the row containing {marker}, and only at the cells
  describing this source itself.
- If several sources are cited together for a list ("A, B and C [cite:X]{marker}"), this source
  only needs to support its share of the list.
- If the source is cited as an example of a kind of study, method or topic ("searches also
  covered studies of X {marker}"), only check that it is such an example.

Verdicts:
- "supported"   — the source states it, or it follows directly. Summaries and paraphrases count;
                  wording need not match.
- "unsupported" — the source contradicts it, or gives a different figure, subject or finding.
                  A detail merely missing from the text shown is never "unsupported".
- "unclear"     — the specific details it relies on (numbers, setups, particular findings) are
                  not in the text shown; it is only part of the paper, and silence there is
                  not evidence the paper says otherwise.{grades_en}

Judge ONLY against the source text above. Absence of evidence is "unclear", NOT "unsupported";
but when the attributed content is grounded in the source, answer "supported" — do not downgrade
to "unclear" because the sentence also carries the writer's own commentary.

Sentences to check:
{claims_block}
Output a JSON array only — one object per statement, same order, no other text:
[{{"verdict": {choices_en}, "reason": "one short sentence"}}]"""


def build_uncited_prompt(section_title: str, sentences_block: str, language: str) -> str:
    """Ask which uncited sentences state facts that scholarly convention says need a source.

    sentences_block lists the section in order: uncited candidates as "[n] ...", cited
    sentences as "· ..." for context only.
    """
    if language == "zh":
        return f"""你是学术写作审稿专家。下面是论文章节"{section_title}"的全部句子，按原文顺序排列。
以 [编号] 开头的句子没有引用标记；以 · 开头的句子已有引用，仅作上下文，不需要判断。

{sentences_block}

请找出带编号的句子中，陈述了具体事实、数据或他人研究发现，按学术规范必须注明出处、却没有引用的句子。

以下情况不算：
- 作者自己的论点、推论、评价、研究问题、结论，或对本文结构、方法、范围的说明
- 作者对文献的综合判断：概括整体证据走向（如"现有证据表明……""文献总体显示……"）、指出研究空白（如"现有研究尚未……""仍缺乏……"）、回答本文的研究问题。这些是作者基于全文综述得出的判断，不是需要单独出处的事实
- 常识、术语定义、过渡句
- 紧接着已引用句子、只是延续或概括同一论断的句子（出处已在相邻句给出）

只输出 JSON 数组，每个需要引用的句子一个对象；没有则输出 []，不要输出其他文字：
[{{"id": 编号, "reason": "一句话说明为什么需要引用"}}]"""

    return f"""You are an academic peer reviewer. Below are all sentences of the section "{section_title}",
in their original order. Sentences starting with [n] carry no citation; sentences starting with ·
are already cited and are shown only as context — do not judge them.

{sentences_block}

Identify the numbered sentences that state a specific fact, figure or finding of other research
which scholarly convention requires to be attributed to a source, yet cite nothing.

These do NOT count:
- the author's own argument, inference, evaluation, research question or conclusion, or remarks
  about this paper's structure, method or scope
- the author's synthesis of the literature: statements of the overall direction of the evidence
  ("the evidence indicates...", "across the literature..."), research gaps ("few studies have...",
  "existing work has not yet..."), or answers to this paper's research questions. These are the
  author's judgements drawn from the review as a whole, not facts that need a single source
- common knowledge, definitions of terms, transitions
- a sentence that directly continues or summarises the claim of an adjacent cited sentence
  (its source is already given there)

Output a JSON array only — one object per sentence that needs a citation, or [] if none, no other text:
[{{"id": n, "reason": "one short sentence on why it needs a source"}}]"""

def build_revision_prompt(
    paragraph: str, problems_block: str, candidates_block: str, language: str
) -> str:
    """Ask for a minimal rewrite of the flagged sentences in one paragraph, nothing else."""
    if language == "zh":
        return f"""你是学术写作修订专家。下面这段正文中有若干句子被核验标记为有问题，请只修改这些句子。

原段落：
{paragraph}

被标记的句子及问题：
{problems_block}

可引用的文献（只能使用这里列出的 KEY，或原段落中已经出现的 KEY）：
{candidates_block}

修改方式（每个被标记的句子任选其一）：
- 被引文献不支持该句：把描述改成与该文献一致，或换成下列中确实支持它的文献，或弱化、删去该说法
- 缺少引用：在下列文献确实支持时补上 [cite:KEY]，否则改写为有保留的表述或删去

硬性要求：
- 未被标记的句子必须逐字保留，不改一个字
- 被标记的句子里，作者自己的评价、推论与批评（如"但……仍未……""这说明……"）不是问题所在，须保留其观点；只修改归给被引文献的那部分内容
- 引用格式为 [cite:KEY]，每个标记只放一个 KEY
- 不得编造数据、结论或文献

只输出修改后的完整段落，不要解释，不要输出其他文字。"""

    return f"""You are an academic editor. Some sentences in the paragraph below were flagged by
citation verification. Revise only those sentences.

Paragraph:
{paragraph}

Flagged sentences and problems:
{problems_block}

Sources you may cite (only these KEYs, or KEYs already in the paragraph):
{candidates_block}

For each flagged sentence, do one of:
- The cited source does not support it: make the description match the source, cite a listed
  source that does support it, or soften or drop the claim
- It needs a citation: add [cite:KEY] where a listed source genuinely supports it, otherwise
  hedge or drop the claim

Hard rules:
- Keep every unflagged sentence exactly as it is, word for word
- Within a flagged sentence, the writer's own evaluation, inference or critique ("but X has
  not yet...", "this suggests...") is not the problem: keep its point, and change only what
  the sentence attributes to the cited source
- Cite as [cite:KEY], one KEY per marker
- Do not invent data, findings or sources

Output the full revised paragraph only — no explanation, no other text."""

def build_paper_selection_prompt(
    section_title: str, section_summary: str, candidates_block: str, top_k: int, language: str
) -> str:
    """Ask which candidate papers this section should draw on, best first."""
    if language == "zh":
        return f"""你是学术写作助手。下面是论文中一个章节的标题与要点，以及按词语匹配初选出的候选文献。
请挑选最多 {top_k} 篇最适合支撑本章节论述的文献。

章节标题：{section_title}
章节要点：{section_summary}

候选文献：
{candidates_block}

挑选要求：
- 与本章节要论证的内容直接相关，而不只是用了相同的词
- 覆盖本章节的不同子观点，避免挑出多篇讲同一件事的文献
- 兼顾奠基性工作与近期进展

只输出按重要性排序的编号 JSON 数组，例如 [3, 0, 12]，不要输出其他文字。"""

    return f"""You are an academic writing assistant. Below are the title and brief of one section of a
paper, and candidate papers pre-selected by word overlap. Pick at most {top_k} papers that best
support what this section argues.

Section title: {section_title}
Section brief: {section_summary}

Candidates:
{candidates_block}

Pick papers that:
- bear directly on what the section argues, not merely share its words
- cover the section's different sub-points; avoid several papers making the same point
- balance foundational work with recent advances

Output a JSON array of candidate numbers, most important first, e.g. [3, 0, 12] — no other text."""

def build_review_prompt(topic: str, draft: str, language: str, focus: str = "") -> str:
    """Ask for a substantive peer review of the whole draft: comments that quote it, and limitations.

    focus: one reviewer's emphasis on the review panel (backend.writing.review_panel).
    """
    focus = f"\n{focus}\n" if focus else ""
    if language == "zh":
        return f"""你是严格而公正的学术审稿人。请审阅下面这篇关于"{topic}"的论文草稿。

{draft}

请只就论证的实质提出意见：
- 论断是否有正文中的证据支撑，是否过度概括
- 不同章节之间是否相互矛盾
- 推理是否跳步，结论是否超出所给证据
- 重要的反面证据或替代解释是否被忽略
{focus}
评判时不要受行文语气影响：自信的措辞、对"新颖""首次"的强调、流畅的表达都不是证据。只看论断与其依据之间的关系。
不要评论文风、格式或引用格式。

每条意见必须逐字引用草稿中的一段原文（quote），且只引用一句或一个短语；无法逐字引用的意见不要提出。

另外，列出本文应当承认但没有承认的局限：必须具体到本文的研究范围、方法或证据，不要写"数据集可能存在偏差""需要更多研究"这类放之四海皆准的话。

只输出 JSON 对象，不要其他文字：
{{"comments": [{{"section": "章节标题", "quote": "逐字原文", "issue": "问题是什么", "severity": "major 或 minor", "suggestion": "如何修改"}}],
  "limitations": ["具体局限1", "具体局限2"]}}
意见最多 10 条，按重要性排序；局限最多 5 条。"""

    return f"""You are a rigorous, fair academic peer reviewer. Review the draft below on "{topic}".

{draft}

Comment only on the substance of the argument:
- whether claims are supported by evidence in the text, or overgeneralise
- whether sections contradict one another
- whether reasoning skips steps or conclusions exceed the evidence given
- whether important counter-evidence or alternative explanations are ignored
{focus}
Do not let tone sway you: confident wording, claims of novelty or "first", and fluent prose are
not evidence. Judge only the link between each claim and what backs it.
Do not comment on style, formatting or citation format.

Every comment must quote one sentence or phrase of the draft verbatim ("quote"); raise no
comment you cannot quote.

Also list limitations the paper should admit but does not: specific to this paper's scope,
method or evidence - not boilerplate such as "the data may be biased" or "more research is needed".

Output a JSON object only, no other text:
{{"comments": [{{"section": "section title", "quote": "verbatim text", "issue": "what is wrong", "severity": "major or minor", "suggestion": "how to fix it"}}],
  "limitations": ["specific limitation 1", "specific limitation 2"]}}
At most 10 comments, most important first; at most 5 limitations."""

def _title_screening_prompt(topic: str, title: str, abstract: str, language: str) -> str:
    """Screening a record with no usable abstract: its title decides, still leaning to include."""
    extra = abstract.strip()
    if language == "zh":
        abstract_line = f"\n摘要片段：{extra}\n" if extra else ""
        return f"""你是系统综述筛选专家。这条记录只有标题（没有可用的摘要），请仅凭标题判断是否纳入文献库。

筛选原则：信息有限，默认纳入；只有当标题明确表明论文属于与研究主题无关的领域（例如文学评论、金融定价、与主题无交集的工程或医学研究），或标题根本不是论文题目（如图注、目录）时才排除。拿不准就纳入。

研究主题：{topic}

论文标题：{title}
{abstract_line}
请仅输出 JSON，不要其他文字：
{{"decision": "include" 或 "exclude", "reason": "一句话说明理由"}}"""
    abstract_line = f"\nAbstract fragment: {extra}\n" if extra else ""
    return f"""You are a systematic review screening expert. Title only: this record has no usable abstract, so decide from the title alone whether to include it.

Screening rule: with this little to go on, default to include. Exclude only when the title plainly places the paper in a field unrelated to the topic (e.g. literary criticism, option pricing, engineering or medicine with no overlap), or is not a paper title at all (a figure caption, a table of contents). When in doubt, include.

Research topic: {topic}

Title: {title}
{abstract_line}
Output JSON only, no other text:
{{"decision": "include" or "exclude", "reason": "One sentence rationale"}}"""


def build_screening_prompt(topic: str, title: str, abstract: str, language: str, title_only: bool = False) -> str:
    if title_only:
        return _title_screening_prompt(topic, title, abstract, language)
    if language == "zh":
        return f"""你是系统综述筛选专家。请阅读以下论文摘要，判断该论文是否应纳入文献库。

筛选原则：默认纳入，只有在论文与研究主题明显无关时才排除（例如：主题完全不同的领域、纯技术手册、与研究问题毫无交集）。如有疑问，选择纳入。

研究主题：{topic}

论文标题：{title}

摘要（正文节选）：{abstract}

请仅输出 JSON，不要其他文字：
{{"decision": "include" 或 "exclude", "reason": "一句话说明理由"}}"""
    return f"""You are a systematic review screening expert. Read the following paper abstract and decide whether to include it.

Screening rule: Default to include. Only exclude when the paper is clearly and obviously unrelated to the research topic (e.g., completely different domain, pure technical manual, no overlap whatsoever with the research questions). When in doubt, include.

Research topic: {topic}

Title: {title}

Abstract (body excerpt): {abstract}

Output JSON only, no other text:
{{"decision": "include" or "exclude", "reason": "One sentence rationale"}}"""
