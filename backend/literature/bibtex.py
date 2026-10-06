"""Shared bibtex key generation. Used by section_writer (to render keys into prompts/text),
verification orchestrator (to match [cite:KEY] markers), and exporters (to build bibliographies).

ALL sites MUST use these functions — divergence would cause citations to be mis-classified
as hallucinated, or for cite markers in exports to fail to resolve."""
import re
from collections.abc import Callable, Iterator

from backend.literature.schemas import LiteratureItem

# Writers sometimes pack several keys into one marker: [cite:A, cite:B] or [cite:A; B].
_CITE_MARKER = re.compile(r"\[cite:([^\]]+)\]")
_KEY_SEPARATOR = re.compile(r"[,;]")


def _family_name(author: str) -> str:
    """"Family, Given" -> Family; "Given Family" -> Family."""
    return author.split(",")[0].strip() if "," in author else author.split()[-1]


def _computed_key(authors: list[str], year: int | None, title: str, legacy: bool = False) -> str:
    """legacy=True is the computation records from before stored keys were written with:
    it took the last word even for "Family, Given", and their [cite:...] markers depend on it."""
    if not authors:
        first_author = "Anon"
    else:
        first_author = authors[0].split()[-1] if legacy else _family_name(authors[0])
    slug = re.sub(r"[^a-zA-Z]", "", title.split()[0]) if title else "Untitled"
    return f"{first_author}{year or 'XXXX'}{slug}"


def bibtex_key(item: LiteratureItem) -> str:
    """The key assigned when the pool was built; records from before then compute it."""
    return item.cite_key or _computed_key(item.authors, item.year, item.title, legacy=True)


def bibtex_key_from_dict(c: dict) -> str:
    """Same as bibtex_key, for serialised LiteratureItem dicts (used by exporters)."""
    return c.get("cite_key") or _computed_key(
        c.get("authors") or [], c.get("year"), c.get("title") or "", legacy=True)


def _identity(item: LiteratureItem) -> tuple[str, str]:
    return ((item.doi or "").strip().lower(), re.sub(r"\W+", "", item.title.lower()))


def assign_cite_keys(items: list[LiteratureItem]) -> list[LiteratureItem]:
    """Give every paper its own key: distinct papers behind one computed key get b, c, ... suffixes.

    The computed key (first author + year + first title word, letters only) collides: a Chinese
    title yields an empty slug, so four Chinese papers by one author in 2025 all became
    Xiaoyang2025 and the writer could reach one of them. The same paper twice (one DOI, or one
    title) keeps a single key; the first distinct paper keeps the computed key unchanged.
    """
    seen: dict[str, list[tuple[tuple[str, str], str]]] = {}
    keyed = []
    for item in items:
        base = _computed_key(item.authors, item.year, item.title)
        doi, title = _identity(item)
        papers = seen.setdefault(base, [])
        key = next((k for (d, t), k in papers if (doi and doi == d) or (title and title == t)), None)
        if key is None:
            n = len(papers)
            key = base if n == 0 else base + (chr(ord("a") + n) if n < 26 else str(n))
            papers.append(((doi, title), key))
        keyed.append(item.model_copy(update={"cite_key": key}))
    return keyed


def _marker_keys(inner: str) -> list[str]:
    keys = (part.strip().removeprefix("cite:").strip() for part in _KEY_SEPARATOR.split(inner))
    return [k for k in keys if k]


def iter_cite_keys(text: str) -> Iterator[str]:
    """Every citation key in the text, in order of appearance, one per key (not per marker)."""
    for m in _CITE_MARKER.finditer(text):
        yield from _marker_keys(m.group(1))


def sub_cite_markers(text: str, render: Callable[[list[str]], str]) -> str:
    """Replace each [cite:...] marker with render(its keys)."""
    return _CITE_MARKER.sub(lambda m: render(_marker_keys(m.group(1))), text)
