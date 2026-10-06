"""Duplicate citations and a preprint cited beside its published version.

The pool is deduplicated by exact DOI and title, but keys are first author + year + first
title word, so the same paper can still be cited twice: a DOI written in another case, a
title differing in punctuation, an arXiv preprint and its proceedings version a year apart.
"""
import difflib
import re

from backend.literature.schemas import LiteratureItem
from backend.verification.metadata_match import _surname

_TITLE_SIMILARITY = 0.9
_PREPRINT_TYPES = {"preprint", "posted-content"}


def _norm_title(title: str) -> str:
    return re.sub(r"[^0-9a-z一-鿿]+", " ", title.lower()).strip()


def is_preprint(item: LiteratureItem) -> bool:
    return item.pub_type in _PREPRINT_TYPES or (item.doi or "").lower().startswith("10.48550/")


def _same_paper(a: LiteratureItem, b: LiteratureItem) -> bool:
    if a.doi and b.doi and a.doi.strip().lower() == b.doi.strip().lower():
        return True
    ta, tb = _norm_title(a.title), _norm_title(b.title)
    if not (ta and tb):
        return False
    # without authors to compare, only the whole title will do: two book chapters named
    # "Retrieval-Augmented Generation" and "Why Retrieval Augmented Generation?" are not one
    if not (a.authors and b.authors):
        return ta == tb
    # a "Review of: <title>" note shares the title but not the first author
    return (_surname(a.authors[0]) == _surname(b.authors[0])
            and difflib.SequenceMatcher(None, ta, tb).ratio() >= _TITLE_SIMILARITY)


def duplicate_issues(cited: dict[str, LiteratureItem]) -> dict[str, str]:
    """Key → reason for each cited paper that repeats another; the preprint side carries it."""
    keys = sorted(cited)
    flagged: dict[str, str] = {}
    for i, first in enumerate(keys):
        for second in keys[i + 1:]:
            if second in flagged or first in flagged or not _same_paper(cited[first], cited[second]):
                continue
            a, b = cited[first], cited[second]
            if is_preprint(a) != is_preprint(b):
                pre, pub = (first, b) if is_preprint(a) else (second, a)
                flagged[pre] = (f"Preprint cited beside its published version ({pub.title[:80]}"
                                f"{', ' + pub.doi if pub.doi else ''}): cite the published version only")
            else:
                flagged[second] = f"Duplicate of [cite:{first}]: the same paper cited under two keys"
    return flagged
