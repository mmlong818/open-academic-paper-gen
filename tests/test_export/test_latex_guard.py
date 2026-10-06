"""LaTeX export escapes and converts the section bodies, and a guard checks what it wrote.

Real exports did not compile: section text went out unescaped (7-10 bare '%' per paper,
which comment out the rest of the line, plus '&' and '_'), and 46-58 lines of Markdown
tables and '**bold**' came out as literal pipes and stars. Titles were escaped; bodies not.
The guard checks braces, environments, specials, leftovers, unresolved cites.
"""
from backend.export.latex_exporter import LatexExporter
from backend.export.latex_guard import check_latex
from backend.literature.bibtex import bibtex_key_from_dict

PAPER = {"title": "Dense Passage Retrieval", "authors": ["Vladimir Karpukhin"], "year": 2020, "source": "arxiv"}
KEY = bibtex_key_from_dict(PAPER)
BODY = f"""Recall rose by 30% on R&D queries with top_k = 5 [cite:{KEY}]; **dense** retrieval, *not* sparse.

| Study | Gain (%) | Note |
|---|---|---|
| DPR [cite:{KEY}] | 30% | uses **dual** encoders & FAISS |
| BM25 | 0 | baseline_run #1 |

After the table."""


def _tex(style="numeric"):
    state = {"topic": "RAG & QA", "language": "en", "outline": [{"title": "Results"}],
             "sections": {"Results": BODY}, "verified_citations": [PAPER]}
    return LatexExporter().export(state, style=style)


def test_the_body_is_escaped_and_markdown_converted():
    tex = _tex()
    assert r"30\% on R\&D queries with top\_k = 5 \cite{" + KEY + "}" in tex
    assert r"\textbf{dense} retrieval, \textit{not} sparse." in tex
    assert r"\begin{tabularx}{\linewidth}" in tex and r"\end{tabularx}" in tex
    assert r"DPR \cite{" + KEY + r"} & 30\% & uses \textbf{dual} encoders \& FAISS \\" in tex
    assert r"baseline\_run \#1" in tex and "|---|" not in tex and "**" not in tex


def test_the_guard_finds_nothing_in_a_clean_export():
    tex = _tex("apa7")
    assert check_latex(tex) == []
    assert tex.startswith("% latex check: no issues")


def test_the_guard_reports_what_would_break_compilation():
    broken = "\n".join([
        r"\documentclass{article}", r"\begin{document}", r"\section{A}",
        "Recall rose 30% on R&D, top_k", "| a | b |", "**bold**", "cited [?Ghost2099x]",
        r"\begin{itemize}", r"\end{document}",
    ])
    issues = " | ".join(check_latex(broken))
    for expected in ("unescaped %", "unescaped &", "unescaped _", "Markdown table", "Markdown emphasis",
                     "unresolved citation", r"\begin{itemize} is never closed"):
        assert expected in issues, expected


def test_braces_must_balance():
    assert any("braces" in i for i in check_latex(r"\begin{document}\textbf{open\end{document}"))


def test_escaping_a_backslash_keeps_its_braces():
    state = {"topic": r"a\b {c}", "language": "en", "outline": [], "sections": {}, "verified_citations": []}
    assert r"\title{a\textbackslash{}b \{c\}}" in LatexExporter().export(state)
