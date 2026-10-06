"""Field-level comparison of a record with its CrossRef entry.

A DOI can resolve to another paper than the record describes; the title check alone let such
records through. Critical: no author in common or a different first
author; a year more than one apart (one is allowed for online-first); start pages five or
more apart. Plus sanity flags: a DOI not shaped like one, a future year.
"""
import datetime
import re
import unicodedata

_CJK = re.compile(r"[一-鿿]")
_YEAR_TOLERANCE = 1
_PAGE_TOLERANCE = 4


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return re.sub(r"[^0-9a-z一-鿿]", "", "".join(c for c in text if not unicodedata.combining(c)).lower())


def _surname(name: str) -> str:
    """Family name of a stored author: 'LeCun, Y.' / 'Yann LeCun' / '张艺潆' (kept whole)."""
    name = name.strip()
    if "," in name:
        return _fold(name.split(",")[0])
    if _CJK.search(name):
        return _fold(name)
    parts = name.split()
    return _fold(parts[-1]) if parts else ""


def _tokens(name: str) -> set[str]:
    return {t for t in (_fold(p) for p in re.split(r"[\s,.]+", name)) if t}


def _same_person(local: str, family: str) -> bool:
    if not _fold(family):
        return False
    if _CJK.search(family):
        return _fold(local).startswith(_fold(family))
    # CrossRef often holds a whole pinyin name in "family" ("Wu Runze"), in either order
    # ("Li Hao" for our "Hao Li"): every token of it must appear in our name
    return _fold(family) == _surname(local) or _tokens(family) <= _tokens(local)


def author_issues(local: list[str], crossref: list[dict]) -> list[str]:
    families = [a.get("family") or a.get("name") or "" for a in crossref]
    families = [f for f in families if f.strip()]
    if not local or not families:
        return []
    # pinyin on one side and characters on the other cannot be compared by spelling
    if bool(_CJK.search(" ".join(local))) != bool(_CJK.search(" ".join(families))):
        return []
    if not any(_same_person(name, f) for name in local for f in families):
        return [f"Authors do not match CrossRef ({', '.join(families[:3])}): the DOI may belong to another paper"]
    if not _same_person(local[0], families[0]):
        return [f"First author differs from CrossRef ({local[0]} vs {families[0]})"]
    return []


def year_issue(local: int | None, crossref: int | None) -> list[str]:
    if local and crossref and abs(local - crossref) > _YEAR_TOLERANCE:
        return [f"Year differs from CrossRef ({local} vs {crossref})"]
    return []


def _start_page(pages: str) -> int | None:
    match = re.match(r"\s*(\d+)", pages or "")
    return int(match.group(1)) if match else None


def pages_issue(local: str, crossref: str) -> list[str]:
    a, b = _start_page(local), _start_page(crossref)
    if a is not None and b is not None and abs(a - b) > _PAGE_TOLERANCE:
        return [f"Pages differ from CrossRef ({local} vs {crossref})"]
    return []


def doi_format_issue(doi: str | None) -> list[str]:
    # DOI syntax: "10." + a registrant code of digit groups + "/" + suffix
    if doi and not re.match(r"10\.\d+(\.\d+)*/\S+$", doi.strip()):
        return [f"Invalid DOI format ({doi}): a DOI starts with 10.NNNN/"]
    return []


def future_year_issue(year: int | None) -> list[str]:
    if year and year > datetime.date.today().year:
        return [f"Publication year {year} is in the future"]
    return []


# CrossRef "updated-by" types that make a paper unsafe to cite (Retraction Watch or publisher);
# corrections and errata do not.
_RETRACTION_TYPES = {"retraction": "Retracted", "withdrawal": "Withdrawn", "removal": "Removed",
                     "expression_of_concern": "Expression of concern"}


def retraction_issues(crossref: dict) -> list[str]:
    issues = []
    for update in crossref.get("updated-by") or []:
        label = _RETRACTION_TYPES.get((update.get("type") or "").lower())
        if not label:
            continue
        parts = ((update.get("updated") or {}).get("date-parts") or [[None]])[0]
        when = "-".join(str(p) for p in parts if p) or "date unknown"
        issues.append(f"{label} ({when}, notice {update.get('DOI') or 'without DOI'}): do not cite as valid evidence")
    return issues
