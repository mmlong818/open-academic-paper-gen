# backend/literature/searchers/openalex.py
import httpx

from backend.core.config import polite_pool_params, settings

from backend.literature.schemas import LiteratureItem, SearchQuery

_BASE = "https://api.openalex.org/works"
_TIMEOUT = 30.0
_SELECT = (
    "id,title,authorships,publication_year,doi,abstract_inverted_index,"
    "cited_by_count,primary_location,open_access,language,best_oa_location,biblio,type"
)


def openalex_params(**params) -> dict:
    """Query parameters for any OpenAlex call: the polite-pool mailto and, when set, the API key.

    Since 2026-02-13 OpenAlex bills calls against a daily budget; a free key (openalex.org/settings/api)
    raises it to $1/day. Without one, a day of runs ends in 429s.
    """
    key = settings.openalex_api_key
    return {**params, **polite_pool_params(), **({"api_key": key} if key else {})}


def _reconstruct_abstract(inverted_index: dict | None) -> str:
    if not inverted_index:
        return ""
    positions: list[tuple[int, str]] = []
    for word, pos_list in inverted_index.items():
        for pos in pos_list:
            positions.append((pos, word))
    positions.sort()
    return " ".join(w for _, w in positions)


def _best_url(work: dict) -> str:
    best = work.get("best_oa_location") or {}
    if best.get("pdf_url"):
        return best["pdf_url"]
    if best.get("landing_page_url"):
        return best["landing_page_url"]
    oa = work.get("open_access") or {}
    return oa.get("oa_url") or ""


class OpenAlexSearcher:
    async def search(self, query: SearchQuery) -> list[LiteratureItem]:
        keyword_str = " ".join(query.keywords)
        params: dict = {
            "search": keyword_str,
            "per-page": query.max_results,
            "select": _SELECT,
        }
        # 中文查询：优先中文语言文献
        if query.language == "zh":
            params["filter"] = "language:zh"

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(_BASE, params=openalex_params(**params))
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return []

        results = data.get("results", [])

        # 中文查询且语言过滤结果太少时，补充无过滤搜索
        if query.language == "zh" and len(results) < 3:
            try:
                params_fallback = {**params}
                params_fallback.pop("filter", None)
                async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                    resp2 = await client.get(_BASE, params=openalex_params(**params_fallback))
                    resp2.raise_for_status()
                    extra = resp2.json().get("results", [])
                # 合并，去已有 id
                existing_ids = {w.get("id") for w in results}
                results += [w for w in extra if w.get("id") not in existing_ids]
                results = results[: query.max_results]
            except Exception:
                pass

        items: list[LiteratureItem] = []
        for work in results:
            doi_raw = work.get("doi", "")
            doi = doi_raw.replace("https://doi.org/", "") if doi_raw else None

            authors = [
                a["author"]["display_name"]
                for a in work.get("authorships", [])
                if a.get("author", {}).get("display_name")
            ]

            primary = work.get("primary_location") or {}
            source_meta = primary.get("source") or {}
            journal = source_meta.get("display_name") or None
            biblio = work.get("biblio") or {}
            first, last = biblio.get("first_page") or "", biblio.get("last_page") or ""

            items.append(
                LiteratureItem(
                    title=work.get("title") or "",
                    authors=authors,
                    year=work.get("publication_year"),
                    doi=doi,
                    abstract=_reconstruct_abstract(work.get("abstract_inverted_index")),
                    citation_count=work.get("cited_by_count") or 0,
                    journal=journal,
                    volume=str(biblio.get("volume") or ""),
                    issue=str(biblio.get("issue") or ""),
                    pages=f"{first}-{last}" if first and last and first != last else str(first or last),
                    publisher=source_meta.get("host_organization_name") or "",
                    pub_type=work.get("type") or "",
                    source="openalex",
                    source_id=work.get("id", ""),
                    url=_best_url(work),
                    raw=work,
                )
            )
        return items
