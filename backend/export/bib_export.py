"""The cited references as RIS and BibTeX, for reference managers.

Only papers the text cites and the pool resolves are exported, in citing order, as in the
reference list. BibTeX keys are the keys the LaTeX export \\cite{}s.
"""
import re

from backend.export.citation_styles import reference_kind, split_name
from backend.export.markdown_exporter import _build_used_references
from backend.literature.bibtex import bibtex_key_from_dict

_RIS_TYPE = {"journal": "JOUR", "conference": "CONF", "book": "CHAP", "preprint": "UNPB"}
_BIB_TYPE = {"journal": "article", "conference": "inproceedings", "book": "incollection", "preprint": "misc"}
_BIB_VENUE = {"journal": "journal", "conference": "booktitle", "book": "booktitle", "preprint": "howpublished"}


def _cited(state: dict) -> list[dict]:
    outline, sections = state.get("outline") or [], state.get("sections") or {}
    order = [item["title"] for item in outline] if outline else list(sections)
    pool = state.get("verified_citations") or state.get("literature") or []
    refs, _ = _build_used_references([sections[t] for t in order if t in sections], pool)
    return refs


def _person(name: str) -> str:
    family, given, chinese = split_name(name)
    return family if chinese or not given else f"{family}, {given}"


def _page_range(pages: str) -> tuple[str, str]:
    start, _, end = (pages or "").partition("-")
    return start.strip(), end.strip()


def _ris_record(c: dict) -> str:
    kind = reference_kind(c)
    start, end = _page_range(c.get("pages") or "")
    lines = [f"TY  - {_RIS_TYPE[kind]}"]
    lines += [f"AU  - {_person(a)}" for a in c.get("authors") or []]
    fields = [("TI", c.get("title")), ("T2", c.get("journal")), ("PY", c.get("year")), ("VL", c.get("volume")),
              ("IS", c.get("issue")), ("SP", start), ("EP", end), ("PB", c.get("publisher")),
              ("DO", c.get("doi")), ("UR", c.get("url")), ("AB", c.get("abstract"))]
    lines += [f"{tag}  - {' '.join(str(value).split())}" for tag, value in fields if value]
    return "\n".join(lines) + "\nER  - \n"


def export_ris(state: dict) -> str:
    return "\n".join(_ris_record(c) for c in _cited(state))


_BIB_SPECIALS = {"\\": "\\textbackslash{}", "&": "\\&", "%": "\\%", "$": "\\$", "#": "\\#",
                 "_": "\\_", "{": "\\{", "}": "\\}"}


def _bib_escape(text: str) -> str:
    # one pass: escaping "\" first and "{" after would break the braces of \textbackslash{}
    return re.sub(r"[\\&%$#_{}]", lambda m: _BIB_SPECIALS[m.group(0)], text)


def _bib_entry(c: dict) -> str:
    kind = reference_kind(c)
    start, end = _page_range(c.get("pages") or "")
    fields = [("author", " and ".join(_person(a) for a in c.get("authors") or [])),
              ("title", c.get("title")), (_BIB_VENUE[kind], c.get("journal")), ("year", c.get("year")),
              ("volume", c.get("volume")), ("number", c.get("issue")),
              ("pages", f"{start}--{end}" if start and end else start), ("publisher", c.get("publisher")),
              ("doi", c.get("doi")), ("url", c.get("url"))]
    body = ",\n".join(f"  {name} = {{{value if name in ('doi', 'url') else _bib_escape(str(value))}}}"
                      for name, value in fields if value)
    return f"@{_BIB_TYPE[kind]}{{{bibtex_key_from_dict(c)},\n{body}\n}}\n"


def export_bibtex(state: dict) -> str:
    return "\n".join(_bib_entry(c) for c in _cited(state))
