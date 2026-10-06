import re
from backend.literature.schemas import LiteratureItem

# Fields a duplicate may fill when the record kept has them empty: sources differ in what
# they carry (CrossRef has pages and volume, Semantic Scholar the abstract), and the first
# record found used to drop everything the others knew.
_FILLABLE = ("doi", "journal", "year", "abstract", "volume", "issue", "pages", "publisher", "pub_type")


def _normalise_title(title: str) -> str:
    return re.sub(r"\s+", " ", title.lower().strip())


def _fill_blanks(kept: LiteratureItem, dup: LiteratureItem) -> LiteratureItem:
    update = {f: getattr(dup, f) for f in _FILLABLE if not getattr(kept, f) and getattr(dup, f)}
    return kept.model_copy(update=update) if update else kept


def deduplicate(items: list[LiteratureItem]) -> list[LiteratureItem]:
    """
    去重文献列表。

    策略：按 DOI（大小写不敏感）或规范化标题去重，以先匹配到的为准；
    重复记录只用来补齐保留记录中为空的字段。
    有 DOI 的论文同时追踪标题，防止无 DOI 的同名论文漏网。
    """
    by_doi: dict[str, int] = {}
    by_title: dict[str, int] = {}
    result: list[LiteratureItem] = []

    for item in items:
        norm_title = _normalise_title(item.title)
        doi = item.doi.lower().strip() if item.doi else ""

        # 被任意一个键命中即视为重复
        hit = by_doi.get(doi) if doi else None
        if hit is None:
            hit = by_title.get(norm_title)
        if hit is not None:
            result[hit] = _fill_blanks(result[hit], item)
            continue

        # 未重复：同时注册 DOI 和标题
        if doi:
            by_doi[doi] = len(result)
        by_title[norm_title] = len(result)
        result.append(item)

    return result
