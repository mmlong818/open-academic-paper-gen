"""Section bodies to LaTeX: escape the text, convert the Markdown the writer uses, keep citations.

Bodies went out raw: a bare '%' (7-10 per paper) commented out the rest of its line, '&' and
'_' broke compilation, and Markdown tables and '**bold**' printed as pipes and stars.
"""
import re
from collections.abc import Callable

from backend.literature.bibtex import sub_cite_markers

_SPECIALS = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
             "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}")
# private-use marks that survive escaping, swapped for LaTeX once the text is escaped
_BOLD, _BOLD_END, _ITALIC, _ITALIC_END = "", "", "", ""
_CITE = re.compile("(\\d+)")


def escape(text: str) -> str:
    """One pass: escaping '\\' first and '{' after would break the braces of \\textbackslash{}."""
    return re.sub(r"[\\&%$#_{}~^]", lambda m: _SPECIALS[m.group(0)], text)


def inline(text: str, cite: Callable[[list[str]], str]) -> str:
    rendered: list[str] = []

    def keep(keys: list[str]) -> str:
        rendered.append(cite(keys))
        return f"{len(rendered) - 1}"

    text = sub_cite_markers(text, keep)
    text = re.sub(r"\*\*(.+?)\*\*", lambda m: f"{_BOLD}{m.group(1)}{_BOLD_END}", text)
    text = re.sub(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?![*\w])", lambda m: f"{_ITALIC}{m.group(1)}{_ITALIC_END}", text)
    text = escape(text)
    for mark, latex in ((_BOLD, r"\textbf{"), (_BOLD_END, "}"), (_ITALIC, r"\textit{"), (_ITALIC_END, "}")):
        text = text.replace(mark, latex)
    return _CITE.sub(lambda m: rendered[int(m.group(1))], text)


def _cells(row: str) -> list[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def _table(header: list[str], rows: list[list[str]], cite: Callable[[list[str]], str]) -> str:
    width = len(header)

    def line(cells: list[str]) -> str:
        cells = (cells + [""] * width)[:width]
        return " & ".join(inline(c, cite) for c in cells) + r" \\" + "\n\\hline"

    body = "\n".join(line(r) for r in rows)
    return (f"\\begin{{tabularx}}{{\\linewidth}}{{|{'X|' * width}}}\n\\hline\n"
            f"{line(header)}\n{body}\n\\end{{tabularx}}")


def body_to_latex(text: str, cite: Callable[[list[str]], str]) -> str:
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        starts_table = (lines[i].lstrip().startswith("|") and i + 1 < len(lines)
                        and _TABLE_SEPARATOR.match(lines[i + 1]))
        if not starts_table:
            out.append(inline(lines[i], cite))
            i += 1
            continue
        header, i = _cells(lines[i]), i + 2
        rows = []
        while i < len(lines) and lines[i].lstrip().startswith("|"):
            rows.append(_cells(lines[i]))
            i += 1
        out.append(_table(header, rows, cite))
    return "\n".join(out)
