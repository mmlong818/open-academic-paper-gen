from datetime import date

from collections.abc import Callable

from backend.export.citation_styles import (
    apa_in_text,
    apa_reference,
    apa_sort_key,
    gbt_reference,
    resolve_style,
)
from backend.literature.bibtex import bibtex_key_from_dict, iter_cite_keys, sub_cite_markers


def _collect_cited_keys_in_order(sections_in_order: list[str]) -> list[str]:
    """Walk sections in render order, return distinct cite keys in first-occurrence order."""
    seen: dict[str, None] = {}
    for text in sections_in_order:
        for key in iter_cite_keys(text):
            seen.setdefault(key, None)
    return list(seen.keys())


def _build_used_references(
    sections_in_order: list[str],
    pool: list[dict],
) -> tuple[list[dict], dict[str, int]]:
    """Return (ordered list of references actually cited and resolvable, KEY→number map).

    References are limited to keys that (a) appear in the body and (b) resolve to a paper
    in the literature pool. Hallucinated keys are NOT added to references — they remain
    as [?KEY] markers in the body so the user can fix them.
    """
    pool_by_key = {bibtex_key_from_dict(c): c for c in pool}
    ordered_keys = _collect_cited_keys_in_order(sections_in_order)

    refs: list[dict] = []
    key_to_number: dict[str, int] = {}
    for key in ordered_keys:
        item = pool_by_key.get(key)
        if item is None:
            continue
        key_to_number[key] = len(refs) + 1
        refs.append(item)
    return refs, key_to_number


def _numeric_renderer(key_to_number: dict[str, int]) -> Callable[[list[str]], str]:
    """[cite:KEY] -> [N]; unresolved keys become ?KEY. A multi-key marker stays one bracket: [1, 2]."""
    def render(keys: list[str]) -> str:
        return "[" + ", ".join(
            str(key_to_number[k]) if k in key_to_number else f"?{k}" for k in keys
        ) + "]"
    return render


def _author_year_renderer(by_key: dict[str, dict]) -> Callable[[list[str]], str]:
    """[cite:A, cite:B] -> (A et al., 2020; B, 2021); unresolved keys stay visible as [?KEY]."""
    def render(keys: list[str]) -> str:
        known = [by_key[k] for k in keys if k in by_key]
        parts = [apa_in_text(known)] if known else []
        parts += [f"[?{k}]" for k in keys if k not in by_key]
        return " ".join(parts)
    return render


class MarkdownExporter:
    def export(self, state: dict, style: str | None = None) -> str:
        topic = state.get("topic", "Untitled")
        sections: dict[str, str] = state.get("sections", {})
        outline: list[dict] = state.get("outline", [])
        verified_citations: list[dict] = state.get("verified_citations", [])
        literature: list[dict] = state.get("literature", [])
        language = state.get("language", "en")
        style = resolve_style(style, language)

        # 文献池来源：优先用核验后的（已剔除 DOI 404 的），否则回退到原始 literature
        pool = verified_citations if verified_citations else literature

        # 按 outline 顺序收集 sections 文本（用于 cite 按出现顺序编号）
        order = [item["title"] for item in outline] if outline else list(sections.keys())
        sections_in_order = [sections[t] for t in order if t in sections]

        used_refs, key_to_number = _build_used_references(sections_in_order, pool)

        parts: list[str] = [f"# {topic}", f"\n*{date.today().isoformat()}*\n"]

        if style == "apa7":
            render = _author_year_renderer({k: used_refs[n - 1] for k, n in key_to_number.items()})
        else:
            render = _numeric_renderer(key_to_number)
        sections_md = self._build_sections(outline, sections, language, render)
        if sections_md:
            parts.append(sections_md)

        artifact_md = self._build_type_artifact(state)
        if artifact_md:
            parts.append(artifact_md)

        refs_md = self._build_references(used_refs, language, style)
        if refs_md:
            parts.append(refs_md)

        return "\n".join(parts)

    def _is_abstract(self, title: str) -> bool:
        t = title.lower()
        return "abstract" in t or "摘要" in t

    def _build_sections(
        self,
        outline: list[dict],
        sections: dict[str, str],
        language: str,
        render: Callable[[list[str]], str],
    ) -> str:
        if not sections:
            return ""
        order = [item["title"] for item in outline] if outline else list(sections.keys())
        parts: list[str] = []

        body_index = 1
        for title in order:
            if title not in sections:
                continue
            content = sections[title]
            if content.startswith("__SECTION_FAILED__"):
                content = "*[此章节生成失败，请重试]*"
            else:
                content = sub_cite_markers(content, render)

            if self._is_abstract(title):
                abstract_header = "## 摘要" if language == "zh" else "## Abstract"
                parts.append(f"{abstract_header}\n\n{content}")
                parts.append("---")
            else:
                parts.append(f"## {body_index}. {title}\n\n{content}")
                body_index += 1

        return "\n\n".join(parts)

    def _build_type_artifact(self, state: dict) -> str:
        paper_type = state.get("paper_type", "general")
        language = state.get("language", "en")

        if paper_type == "systematic":
            return self._build_prisma_section(state, language)
        elif paper_type == "computational":
            return self._build_ablation_section(state, language)
        elif paper_type in ("empirical", "experimental"):
            return self._build_hypothesis_table(state, language)
        elif paper_type == "review":
            return self._build_research_agenda(state, language)
        return ""

    def _build_prisma_section(self, state: dict, language: str) -> str:
        prisma_flow = state.get("prisma_flow", "")
        if not prisma_flow:
            return ""
        header = "## 附录：PRISMA 文献筛选流程" if language == "zh" else "## Appendix: PRISMA Literature Flow"
        return f"{header}\n\n{prisma_flow}"

    def _build_ablation_section(self, state: dict, language: str) -> str:
        ablation_design = state.get("ablation_design", "")
        if not ablation_design:
            return ""
        return ablation_design

    def _build_hypothesis_table(self, state: dict, language: str) -> str:
        angle = state.get("angle", {}) or {}
        hypotheses: list = angle.get("hypotheses", [])
        if not hypotheses:
            return ""
        if language == "zh":
            header = "## 研究假设汇总"
            table = "| 假设编号 | 假设内容 |\n|---------|--------|\n"
        else:
            header = "## Research Hypotheses Summary"
            table = "| ID | Hypothesis |\n|----|------------|\n"
        for i, h in enumerate(hypotheses, 1):
            table += f"| H{i} | {h} |\n"
        return f"{header}\n\n{table}"

    def _build_research_agenda(self, state: dict, language: str) -> str:
        synthesis = state.get("synthesis", "")
        if not synthesis:
            return ""
        if language == "zh":
            header = "## 未来研究议程"
            body = (
                "**基于现有文献综合，以下方向值得未来研究关注：**\n\n"
                f"{synthesis[:500]}"
            )
        else:
            header = "## Future Research Agenda"
            body = (
                "**Based on the literature synthesis, the following directions merit future investigation:**\n\n"
                f"{synthesis[:500]}"
            )
        return f"{header}\n\n{body}"

    def _build_references(self, citations: list[dict], language: str, style: str = "numeric") -> str:
        if not citations:
            return ""
        header = "## 参考文献" if language == "zh" else "## References"
        if style == "gbt7714":
            return f"{header}\n\n" + "\n\n".join(f"[{i}] {gbt_reference(c)}" for i, c in enumerate(citations, 1))
        if style == "apa7":
            return f"{header}\n\n" + "\n\n".join(apa_reference(c) for c in sorted(citations, key=apa_sort_key))
        items: list[str] = []
        for i, c in enumerate(citations, 1):
            authors = ", ".join(c.get("authors") or ["Unknown"])
            title = c.get("title", "")
            year = c.get("year", "")
            journal = c.get("journal") or ""
            doi = c.get("doi", "")
            line = f"{i}. {authors} ({year}). {title}."
            if journal:
                line += f" *{journal}*."
            if doi:
                line += f" https://doi.org/{doi}"
            items.append(line)
        return f"{header}\n\n" + "\n\n".join(items)
