import httpx

from backend.core.config import polite_pool_params
from backend.literature.schemas import LiteratureItem, SearchQuery

_BASE = "https://api.crossref.org/works"
_TIMEOUT = 30.0


def _parse_author(author: dict) -> str:
    given = author.get("given", "")
    family = author.get("family", "")
    if family and given:
        return f"{family}, {given}"
    return family or given or "Unknown"


def _parse_year(item: dict) -> int | None:
    for date_field in ("published", "published-print", "published-online", "created"):
        date_obj = item.get(date_field) or {}
        if not isinstance(date_obj, dict):
            continue
        date_parts_list = date_obj.get("date-parts") or [[]]
        parts = date_parts_list[0] if date_parts_list else []
        if parts:
            try:
                return int(parts[0])
            except (ValueError, TypeError):
                pass
    return None


def _extract_abstract(item: dict) -> str:
    raw = item.get("abstract", "")
    if not raw:
        return ""
    # CrossRef 摘要可能包含 JATS XML 标签，简单清除
    import re
    return re.sub(r"<[^>]+>", "", raw).strip()


class CrossRefSearcher:
    """CrossRef 免费 API 搜索器，覆盖有 DOI 的中英文期刊论文。"""

    async def search(self, query: SearchQuery) -> list[LiteratureItem]:
        keyword_str = " ".join(query.keywords)
        params: dict = {
            "query": keyword_str,
            "rows": query.max_results,
            **polite_pool_params(),
            "select": "DOI,title,author,published,published-print,created,abstract,container-title,is-referenced-by-count,URL,"
                      "volume,issue,page,publisher,type",
        }
        # 中文查询：优先筛选中文语言文献（CrossRef 的 language 字段覆盖率约 40%，
        # 不强制过滤，而是搜索后在结果中优先排序中文）
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(_BASE, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return []

        items: list[LiteratureItem] = []
        msg = data.get("message") or {}
        for work in (msg.get("items") or []):
            try:
                titles = work.get("title") or []
                title = titles[0] if titles else ""
                if not title:
                    continue

                authors = [_parse_author(a) for a in (work.get("author") or [])]
                journals = work.get("container-title") or []
                journal = journals[0] if journals else None
                doi = work.get("DOI") or None
                url = work.get("URL") or (f"https://doi.org/{doi}" if doi else "")

                items.append(
                    LiteratureItem(
                        title=title,
                        authors=authors,
                        year=_parse_year(work),
                        doi=doi,
                        abstract=_extract_abstract(work),
                        citation_count=work.get("is-referenced-by-count") or 0,
                        journal=journal,
                        volume=str(work.get("volume") or ""),
                        issue=str(work.get("issue") or ""),
                        pages=str(work.get("page") or ""),
                        publisher=work.get("publisher") or "",
                        pub_type=work.get("type") or "",
                        source="crossref",
                        source_id=doi or "",
                        url=url,
                        raw=work,
                    )
                )
            except Exception:
                continue
        return items
