"""Reference entries and in-text citations in GB/T 7714-2015 (numeric) and APA 7.

Chinese journals and theses ask for GB/T 7714; English journals mostly for APA. The one fixed
format before ("Authors (year). Title. Journal. DOI") matched neither.

GB/T 7714-2015 顺序编码制: surname in capitals and initials without points for Latin names,
the full name for Chinese ones; three authors, then ", 等" (Chinese entry) or ", et al";
type marks [J] [C] [M] [EB/OL]; "刊名, 年, 卷(期): 页码. DOI:…".
APA 7: "Surname, I." for Latin names, full names for Chinese ones; up to 20 authors with "&";
"(Year). Title. *Journal*, *vol*(issue), pages. https://doi.org/…"; author-year in the text.
"""
import re
from collections.abc import Callable

STYLES = ("gbt7714", "apa7", "numeric")
_CJK = re.compile(r"[一-鿿]")
_PREPRINT = {"preprint", "posted-content"}
_CONFERENCE = {"proceedings-article", "conference-paper", "proceedings"}
_BOOK = {"book-chapter", "book", "monograph", "edited-book", "reference-entry"}


def default_style(language: str) -> str:
    return "gbt7714" if language == "zh" else "apa7"


def resolve_style(style: str | None, language: str) -> str:
    if style is None:
        return default_style(language)
    if style not in STYLES:
        raise ValueError(f"unknown citation style {style!r}; choose one of {', '.join(STYLES)}")
    return style


def split_name(name: str) -> tuple[str, str, bool]:
    """(family, given, is_chinese) of a stored author: 'LeCun, Y.' / 'Yann LeCun' / '张艺潆'."""
    name = name.strip()
    if _CJK.search(name):
        return name, "", True
    if "," in name:
        family, given = name.split(",", 1)
        return family.strip(), given.strip(), False
    parts = name.split()
    return (parts[-1], " ".join(parts[:-1]), False) if parts else ("", "", False)


def _initials(given: str, points: bool) -> str:
    groups = []
    for part in given.replace(".", " ").split():
        letters = [p[0].upper() for p in part.split("-") if p]
        groups.append(("-".join(f"{l}." for l in letters)) if points else " ".join(letters))
    return " ".join(groups)


def reference_kind(c: dict) -> str:
    pub_type = (c.get("pub_type") or "").lower()
    if pub_type in _PREPRINT or (c.get("doi") or "").lower().startswith("10.48550/") or c.get("source") == "arxiv":
        return "preprint"
    if pub_type in _CONFERENCE:
        return "conference"
    if pub_type in _BOOK:
        return "book"
    return "journal"


def _ends(text: str) -> str:
    """The text closed with a full stop, unless it already ends in one."""
    return text if text.endswith((".", "?", "!", "。", "？", "！")) else f"{text}."


# ---------------------------------------------------------------- GB/T 7714-2015

def _gbt_author(name: str) -> str:
    family, given, chinese = split_name(name)
    if chinese:
        return family
    initials = _initials(given, points=False)
    return f"{family.upper()} {initials}".strip()


def _gbt_authors(authors: list[str], chinese_entry: bool) -> str:
    shown = ", ".join(_gbt_author(a) for a in authors[:3])
    if len(authors) > 3:
        shown += ", 等" if chinese_entry else ", et al"
    return shown


def gbt_reference(c: dict) -> str:
    title = c.get("title") or ""
    authors = _gbt_authors(c.get("authors") or [], bool(_CJK.search(title)))
    year, journal, pages = str(c.get("year") or ""), c.get("journal") or "", c.get("pages") or ""
    volume, issue, doi = c.get("volume") or "", c.get("issue") or "", c.get("doi") or ""
    kind = reference_kind(c)
    head = f"{authors}. {title}" if authors else title
    if kind == "preprint":
        where = f"[EB/OL]. ({year})" if year else "[EB/OL]"
    elif kind == "conference":
        where = f"[C]//{journal}. {year}" if journal else f"[C]. {year}"
        where += f": {pages}" if pages else ""
    elif kind == "book":
        publisher = f"{c['publisher']}, " if c.get("publisher") else ""
        where = f"[M]//{journal}. {publisher}{year}" if journal else f"[M]. {publisher}{year}"
        where += f": {pages}" if pages else ""
    else:
        where = f"[J]. {journal}, {year}" if journal else f"[J]. {year}"
        where += f", {volume}({issue})" if volume and issue else f", {volume}" if volume else ""
        where += f": {pages}" if pages else ""
    link = f" DOI:{doi}." if doi else (f" {c['url']}." if kind == "preprint" and c.get("url") else "")
    return f"{head}{where}.{link}"


# ---------------------------------------------------------------- APA 7

def _apa_author(name: str) -> str:
    family, given, chinese = split_name(name)
    if chinese:
        return family
    initials = _initials(given, points=True)
    return f"{family}, {initials}" if initials else family


def _apa_authors(authors: list[str]) -> str:
    names = [_apa_author(a) for a in authors]
    if all(_CJK.search(a) for a in authors):
        return ", ".join(names)
    if len(names) > 20:
        return ", ".join(names[:19]) + ", . . . " + names[-1]
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + ", & " + names[-1]


def apa_reference(c: dict, em: Callable[[str], str] = lambda s: f"*{s}*") -> str:
    authors = _apa_authors(c.get("authors") or [])
    year = str(c.get("year") or "n.d.")
    title, journal = c.get("title") or "", c.get("journal") or ""
    pages = (c.get("pages") or "").replace("-", "–")
    volume, issue, doi = c.get("volume") or "", c.get("issue") or "", c.get("doi") or ""
    kind = reference_kind(c)
    # a preprint without a DOI is still findable by its URL (arXiv abs page)
    link = f" https://doi.org/{doi}" if doi else (f" {c['url']}" if kind == "preprint" and c.get("url") else "")
    lead = f"{authors} ({year})." if authors else f"{_ends(title)} ({year})."
    if kind == "preprint":
        body = f"{em(title)} [Preprint]." + (f" {journal}." if journal else "")
        return f"{lead} {body}{link}" if authors else f"{lead}{link}"
    body = _ends(title) if authors else ""
    if kind in ("conference", "book") and journal:
        body += f" In {em(journal)}" + (f" (pp. {pages})." if pages else ".")
        if kind == "book" and c.get("publisher"):
            body += f" {_ends(c['publisher'])}"
    elif journal:
        body += f" {em(journal)}" + (f", {em(volume)}" if volume else "") + (f"({issue})" if issue else "")
        body += f", {pages}." if pages else "."
    return f"{lead} {body.strip()}{link}".replace("  ", " ")


def apa_cite_names(authors: list[str]) -> str:
    families = [split_name(a)[0] for a in authors]
    chinese = bool(families) and all(_CJK.search(f) for f in families)
    if not families:
        return "Anon."
    if len(families) == 1:
        return families[0]
    if len(families) == 2:
        return f"{families[0]}, {families[1]}" if chinese else f"{families[0]} & {families[1]}"
    return f"{families[0]} 等" if chinese else f"{families[0]} et al."


def apa_in_text(cited: list[dict]) -> str:
    return "(" + "; ".join(f"{apa_cite_names(c.get('authors') or [])}, {c.get('year') or 'n.d.'}"
                           for c in cited) + ")"


def apa_sort_key(c: dict) -> tuple[str, str]:
    authors = c.get("authors") or []
    first = split_name(authors[0])[0] if authors else (c.get("title") or "")
    return first.casefold(), str(c.get("year") or "")
