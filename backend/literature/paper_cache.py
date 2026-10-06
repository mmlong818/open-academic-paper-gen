"""Cross-task paper cache, keyed by DOI or arXiv id.

Keeps what is costly to fetch again - abstract, body excerpt, full text with its page offsets, and
bibliographic metadata - and nothing of any task. A paper counts as cached only with full text: one
cached with an abstract alone is fetched again, so a PDF that failed once gets another try. The
cache is a convenience: any database error leaves the fetcher working as if it were empty.
"""
import re

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from backend.db.models import PaperCache
from backend.db.session import AsyncSessionLocal
from backend.literature.schemas import LiteratureItem
from backend.literature.text_length import weighted_length

META_FIELDS = ("volume", "issue", "pages", "publisher", "pub_type")
_CONTENT_FIELDS = ("abstract", "body_excerpt", "full_text", "full_text_pages")
_MIN_ABSTRACT = 200  # below this an abstract is not worth a row
_ARXIV_VERSION = re.compile(r"v\d+$")
# 2: the body's start and its end before the references. Rows cut by an older rule count as
# having no full text, so the paper is fetched again.
FULL_TEXT_VERSION = 2


def cache_key(item: LiteratureItem) -> str | None:
    doi = (item.doi or "").strip().lower().removeprefix("https://doi.org/").removeprefix("http://doi.org/")
    if doi:
        return f"doi:{doi}"
    if item.source == "arxiv" and item.source_id:
        return f"arxiv:{_ARXIV_VERSION.sub('', item.source_id.strip())}"
    return None


def to_row(item: LiteratureItem) -> dict | None:
    key = cache_key(item)
    if key is None:
        return None
    text = {f: getattr(item, f).replace("\x00", "") for f in ("abstract", "body_excerpt", "full_text")}
    meta = {f: getattr(item, f) for f in META_FIELDS if getattr(item, f)}
    if item.full_text:
        meta["full_text_version"] = FULL_TEXT_VERSION
    return {"key": key, **text, "full_text_pages": item.full_text_pages, "meta": meta}


def current(row: dict) -> dict:
    """The row, without its full text if an older rule cut it."""
    if not row.get("full_text") or (row.get("meta") or {}).get("full_text_version") == FULL_TEXT_VERSION:
        return row
    return {**row, "full_text": "", "full_text_pages": []}


def worth_storing(item: LiteratureItem) -> bool:
    return bool(item.full_text) or weighted_length(item.abstract) >= _MIN_ABSTRACT


def merge_cached(item: LiteratureItem, row: dict) -> LiteratureItem:
    """Fill what the item lacks from its cached row; the item's own values win."""
    update: dict = {}
    if row.get("full_text") and not item.full_text:
        update.update(full_text=row["full_text"], full_text_pages=row.get("full_text_pages") or [],
                      body_excerpt=row.get("body_excerpt") or item.body_excerpt)
    if weighted_length(row.get("abstract") or "") > weighted_length(item.abstract):
        update["abstract"] = row["abstract"]
    update.update({f: v for f, v in (row.get("meta") or {}).items() if f in META_FIELDS and not getattr(item, f)})
    return item.model_copy(update=update) if update else item


async def load_cached(keys: list[str]) -> dict[str, dict]:
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(PaperCache).where(PaperCache.key.in_(keys)))).scalars()
        return {r.key: {"key": r.key, "abstract": r.abstract, "body_excerpt": r.body_excerpt,
                        "full_text": r.full_text, "full_text_pages": r.full_text_pages, "meta": r.meta}
                for r in rows}


async def store_cached(items: list[LiteratureItem]) -> int:
    rows = list({row["key"]: row for item in items if worth_storing(item) and (row := to_row(item))}.values())
    if not rows:
        return 0
    stmt = insert(PaperCache).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[PaperCache.key],
        set_={f: stmt.excluded[f] for f in (*_CONTENT_FIELDS, "meta")},
    )
    async with AsyncSessionLocal() as session:
        await session.execute(stmt)
        await session.commit()
    return len(rows)
