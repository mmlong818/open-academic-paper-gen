"""PRISMA flow for systematic and English-language reviews, built from what the pipeline did.

The flow used to come from an LLM asked to screen the pool a second time. Its exclusions
were applied only when its titles matched the pool verbatim, so the same topic lost 0 or
90% of its papers depending on the run, including plainly relevant ones. Relevance
screening already happens once in the cleaning phase; this module now only reports the
counts of that screening and never removes a paper.
"""

_LABELS = {
    "en": {
        "identified": "Records identified through database searching",
        "chained": "Additional records identified through citation chaining",
        "duplicates": "Duplicates removed",
        "screened": "Records screened (title/abstract)",
        "excluded": "Records excluded at relevance screening",
        "other": "Other records removed during cleaning",
        "included": "Studies included",
    },
    "zh": {
        "identified": "数据库检索识别记录",
        "chained": "通过引用链追溯识别的其他记录",
        "duplicates": "去除重复记录",
        "screened": "标题/摘要筛选记录",
        "excluded": "相关性筛选排除记录",
        "other": "清洗阶段因其他规则移除记录",
        "included": "最终纳入研究",
    },
}


def build_prisma_flow(cleaning_report: dict | None, included: int, language: str) -> str:
    if not cleaning_report:
        return ""
    labels = _LABELS["zh" if language == "zh" else "en"]
    sep = "：" if language == "zh" else ": "
    identified = cleaning_report.get("total_before", 0)
    duplicates = cleaning_report.get("removed_dup", 0)
    excluded = cleaning_report.get("excluded_by_llm", 0)
    chained = cleaning_report.get("chained_candidates", 0)
    screened = identified - duplicates + chained
    other = screened - excluded - included

    rows = [(labels["identified"], identified)]
    if chained:
        rows.append((labels["chained"], chained))
    rows += [
        (labels["duplicates"], duplicates),
        (labels["screened"], screened),
        (labels["excluded"], excluded),
    ]
    if other > 0:
        rows.append((labels["other"], other))
    rows.append((labels["included"], included))
    return "\n".join(f"- {label}{sep}{count}" for label, count in rows)


_SOURCE_NAMES = {
    "semantic_scholar": "Semantic Scholar", "openalex": "OpenAlex", "crossref": "CrossRef",
    "arxiv": "arXiv", "cnki": "CNKI", "wanfang": "Wanfang", "vip": "VIP",
}

_FACT_LABELS = {
    "en": {"sources": "Sources of the included records", "terms": "Search terms",
           "chaining": "Citation chaining: references and citing papers of the highest-scoring included papers (Semantic Scholar)",
           "screening": "Screening: automated relevance screening of titles and abstracts against the topic",
           "title_only": "{n} of them without an abstract, screened on the title alone",
           "years": "Publication years of the included records"},
    "zh": {"sources": "纳入记录的来源数据库", "terms": "检索词",
           "chaining": "引用链追溯：从质量分最高的已纳入论文出发，追溯其参考文献与施引文献（Semantic Scholar）",
           "screening": "筛选：按主题对标题与摘要做自动相关性筛选",
           "title_only": "其中 {n} 条无摘要，仅按标题筛选",
           "years": "纳入记录的发表年份"},
}


def review_process_facts(
    cleaning_report: dict | None, literature: list, keywords: list[str], language: str
) -> str:
    """What the pipeline really did to gather the pool, for the Methodology and Abstract to report."""
    if not literature:
        return ""
    labels = _FACT_LABELS["zh" if language == "zh" else "en"]
    sep = "：" if language == "zh" else ": "
    sources = dict.fromkeys(_SOURCE_NAMES.get(item.source, item.source) for item in literature
                            if item.source != "upload")
    years = [item.year for item in literature if item.year]
    lines = []
    if sources:
        lines.append(f"- {labels['sources']}{sep}{', '.join(sources)}")
    if keywords:
        lines.append(f"- {labels['terms']}{sep}{'; '.join(keywords)}")
    if cleaning_report and cleaning_report.get("chained_candidates"):
        lines.append(f"- {labels['chaining']}")
    title_only = sum(1 for row in (cleaning_report or {}).get("screening_rows") or [] if row.get("basis") == "title")
    screening = labels["screening"] + (("；" if language == "zh" else "; ") + labels["title_only"].format(n=title_only)
                                       if title_only else "")
    lines.append(f"- {screening}")
    if years:
        lines.append(f"- {labels['years']}{sep}{min(years)}–{max(years)}")
    flow = build_prisma_flow(cleaning_report, len(literature), language)
    return "\n".join(lines + ([flow] if flow else []))
