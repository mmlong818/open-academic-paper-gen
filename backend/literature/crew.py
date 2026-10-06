# backend/literature/crew.py
import asyncio

from backend.literature.dedup import deduplicate
from backend.literature.mix import take_by_mix
from backend.literature.schemas import LiteratureItem, SearchQuery
from backend.literature.scorer import score_items
from backend.literature.searchers.arxiv import ArxivSearcher
from backend.literature.searchers.base import Searcher
from backend.literature.searchers.chinese_stub import (
    CnkiStubSearcher,
    VipStubSearcher,
    WanfangStubSearcher,
)
from backend.literature.searchers.crossref import CrossRefSearcher
from backend.literature.searchers.openalex import OpenAlexSearcher
from backend.literature.searchers.semantic_scholar import SemanticScholarSearcher

# 单关键词搜索时每来源取的条数（多路并行，总量仍受控）
_PER_KEYWORD_LIMIT = 10
# 合并查询时每来源取的条数
_COMBINED_LIMIT = 15
# 每个关键词最多并发搜索的来源数
_MAX_CONCURRENT = 8


def _has_cjk(text: str) -> bool:
    return any("一" <= c <= "鿿" for c in text)


def _kw_useful(kw: str) -> bool:
    """跳过单字/单字母等过于通用的词，避免拉入海量不相关结果。"""
    stripped = kw.strip()
    if _has_cjk(stripped):
        return len(stripped) >= 2   # 中文：≥2个字即有效（通常 2-6 字，如"机器学习"）
    return len(stripped) >= 4 or " " in stripped  # 英文：≥4字符或多词


class LiteratureCrew:
    def __init__(self) -> None:
        self._en_searchers: list[Searcher] = [
            SemanticScholarSearcher(),
            ArxivSearcher(),
            OpenAlexSearcher(),
            CrossRefSearcher(),
        ]
        self._zh_searchers: list[Searcher] = [
            CrossRefSearcher(),
            OpenAlexSearcher(),
            SemanticScholarSearcher(),
            CnkiStubSearcher(),
            WanfangStubSearcher(),
            VipStubSearcher(),
        ]

    async def _safe_search(
        self, searcher: Searcher, query: SearchQuery
    ) -> list[LiteratureItem]:
        import logging
        try:
            return await searcher.search(query)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Searcher %s failed: %s", type(searcher).__name__, exc
            )
            return []

    async def _search_one_keyword(
        self,
        keyword: str,
        base_query: SearchQuery,
        searchers: list[Searcher],
        limit: int,
    ) -> list[LiteratureItem]:
        """用单个关键词并行搜索所有来源。"""
        kw_query = base_query.model_copy(
            update={"keywords": [keyword], "max_results": limit}
        )
        tasks = [self._safe_search(s, kw_query) for s in searchers]
        batches = await asyncio.gather(*tasks)
        items: list[LiteratureItem] = []
        for batch in batches:
            items.extend(batch)
        return items

    async def _search_group(
        self, query: SearchQuery, keywords: list[str], searchers: list[Searcher], language: str
    ) -> list[LiteratureItem]:
        """One language's keywords against the sources that can read them."""
        # language 决定来源的语种过滤（OpenAlex 在 zh 下只返回中文文献）
        group = query.model_copy(update={"keywords": keywords, "language": language})
        items: list[LiteratureItem] = []

        # 1. 合并关键词联合查询（捕获需要多词共现的论文）
        combined_query = group.model_copy(update={"max_results": _COMBINED_LIMIT})
        combined_tasks = [self._safe_search(s, combined_query) for s in searchers]
        for batch in await asyncio.gather(*combined_tasks):
            items.extend(batch)

        # 2. 逐关键词搜索（捕获只匹配单个术语的论文）
        top_keywords = [kw for kw in keywords[:5] if _kw_useful(kw)]
        kw_search_tasks = [
            self._search_one_keyword(kw, group, searchers, _PER_KEYWORD_LIMIT)
            for kw in top_keywords
        ]
        for kw_items in await asyncio.gather(*kw_search_tasks):
            items.extend(kw_items)
        return items

    async def run(self, query: SearchQuery) -> list[LiteratureItem]:
        # 中文关键词送中文可检索的来源，英文关键词送英文来源：
        # Semantic Scholar 与 arXiv 用中文检索几乎一无所获，中文题目因此漏掉整个英文主干文献
        zh_keywords = [kw for kw in query.keywords if _has_cjk(kw)]
        en_keywords = [kw for kw in query.keywords if not _has_cjk(kw)]
        groups = [(zh_keywords, self._zh_searchers, "zh"), (en_keywords, self._en_searchers, "en")]

        all_items: list[LiteratureItem] = []
        for batch in await asyncio.gather(*[
            self._search_group(query, keywords, searchers, language)
            for keywords, searchers, language in groups if keywords
        ]):
            all_items.extend(batch)

        deduped = deduplicate(all_items)
        scored = score_items(deduped)
        # 按质量排序，最终返回 max_results * 3 上限，保证足够文献量供 LLM 综合；
        # 上限按文献侧重在中英文之间分配，否则英文高被引文献会挤掉中文文献
        cap = max(query.max_results * 3, 50)
        ranked = sorted(scored, key=lambda x: x.quality_score, reverse=True)
        return take_by_mix(ranked, cap, query.source_mix)
