from backend.export.citation_styles import (
    apa_cite_names,
    apa_reference,
    apa_sort_key,
    gbt_reference,
    resolve_style,
)
from backend.export.latex_body import body_to_latex, escape
from backend.export.latex_guard import with_report
from backend.literature.bibtex import bibtex_key_from_dict, iter_cite_keys

# emphasis marks survive escaping, then become \textit{...}
_EM_OPEN, _EM_CLOSE = "\x00", "\x01"


def _collect_cited_keys_in_order(sections_in_order: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for text in sections_in_order:
        for key in iter_cite_keys(text):
            seen.setdefault(key, None)
    return list(seen.keys())


class LatexExporter:
    """将 PaperState 字段序列化为 LaTeX 文档。"""

    def export(self, state: dict, style: str | None = None) -> str:
        topic = state.get("topic", "Untitled")
        sections: dict[str, str] = state.get("sections", {})
        outline: list[dict] = state.get("outline", [])
        verified_citations: list[dict] = state.get("verified_citations", [])
        literature: list[dict] = state.get("literature", [])
        language = state.get("language", "en")
        self._style = resolve_style(style, language)

        doc_lang = "[UTF8]{ctex}" if language == "zh" else ""
        usepackage_lang = f"\\usepackage{doc_lang}\n" if doc_lang else ""

        pool = verified_citations if verified_citations else literature
        pool_by_key = {bibtex_key_from_dict(c): c for c in pool}

        order = [item["title"] for item in outline] if outline else list(sections.keys())
        sections_in_order = [sections[t] for t in order if t in sections]

        ordered_keys = _collect_cited_keys_in_order(sections_in_order)
        used_refs = [pool_by_key[k] for k in ordered_keys if k in pool_by_key]
        resolvable_keys = {k for k in ordered_keys if k in pool_by_key}

        sections_tex = self._build_sections(outline, sections, resolvable_keys)
        bibliography_tex = (self._build_bibliography(used_refs) if self._style == "numeric"
                            else self._build_styled_bibliography(used_refs))

        return with_report(f"""\\documentclass[12pt,a4paper]{{article}}
{usepackage_lang}\\usepackage{{hyperref}}
\\usepackage{{natbib}}
\\usepackage{{tabularx}}

\\title{{{self._escape(topic)}}}
\\date{{\\today}}

\\begin{{document}}
\\maketitle

{sections_tex}
{bibliography_tex}
\\end{{document}}""")

    def _cite(self, keys: list[str], resolvable_keys: set[str]) -> str:
        """One \\cite{A,B} (\\citep for APA) for resolvable keys, then [?KEY] for any unresolved key."""
        known = [k for k in keys if k in resolvable_keys]
        command = "\\citep" if self._style == "apa7" else "\\cite"
        parts = [f"{command}{{{','.join(known)}}}"] if known else []
        parts += [f"[?{self._escape(k)}]" for k in keys if k not in resolvable_keys]
        return " ".join(parts)

    def _build_sections(
        self,
        outline: list[dict],
        sections: dict[str, str],
        resolvable_keys: set[str],
    ) -> str:
        if not sections:
            return ""
        order = [item["title"] for item in outline] if outline else list(sections.keys())
        parts: list[str] = []
        for title in order:
            if title not in sections:
                continue
            text = sections[title]
            if text.startswith("__SECTION_FAILED__"):
                content = "\\textit{[This section failed to generate; retry it]}"
            else:
                # escape the body and convert its Markdown, keeping the citations
                content = body_to_latex(text, lambda keys: self._cite(keys, resolvable_keys))
            parts.append(f"\\section{{{self._escape(title)}}}\n{content}\n")
        return "\n".join(parts)

    def _build_bibliography(self, citations: list[dict]) -> str:
        if not citations:
            return ""
        items: list[str] = []
        for c in citations:
            authors = self._escape(" and ".join(c.get("authors") or ["Unknown"]))
            title = self._escape(c.get("title", ""))
            year = c.get("year", "")
            journal = self._escape(c.get("journal") or "")
            doi = c.get("doi", "")
            key = bibtex_key_from_dict(c)
            entry = f"\\bibitem{{{key}}}\n{authors}.\n\\textit{{{title}}}.\n{journal}, {year}."
            if doi:
                entry += f"\nDOI: {self._escape(doi)}."
            items.append(entry)
        return "\\begin{thebibliography}{99}\n\n" + "\n\n".join(items) + "\n\n\\end{thebibliography}"

    def _build_styled_bibliography(self, citations: list[dict]) -> str:
        """GB/T 7714 numbered in citing order, or APA 7 with natbib author-year labels, sorted."""
        if not citations:
            return ""
        items: list[str] = []
        if self._style == "apa7":
            for c in sorted(citations, key=apa_sort_key):
                text = apa_reference(c, em=lambda s: f"{_EM_OPEN}{s}{_EM_CLOSE}")
                label = f"{apa_cite_names(c.get('authors') or [])}({c.get('year') or 'n.d.'})"
                items.append(f"\\bibitem[{self._escape(label)}]{{{bibtex_key_from_dict(c)}}}\n{self._styled(text)}")
        else:
            items = [f"\\bibitem{{{bibtex_key_from_dict(c)}}}\n{self._styled(gbt_reference(c))}" for c in citations]
        return "\\begin{thebibliography}{99}\n\n" + "\n\n".join(items) + "\n\n\\end{thebibliography}"

    def _styled(self, text: str) -> str:
        return self._escape(text).replace(_EM_OPEN, "\\textit{").replace(_EM_CLOSE, "}")

    def _escape(self, text: str) -> str:
        return escape(text)
