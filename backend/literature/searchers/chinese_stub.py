# backend/literature/searchers/chinese_stub.py
"""
中文机构数据库存根实现。
Cookie 由用户在 Web 界面粘贴，存入加密会话，任务结束后清除，系统不持久化。
真实爬取逻辑待后续计划实现。
"""
from backend.literature.schemas import LiteratureItem, SearchQuery


class CnkiStubSearcher:
    """知网 CNKI — Cookie 接入框架（存根）。"""

    async def search(self, query: SearchQuery) -> list[LiteratureItem]:
        if not query.cookie:
            return []
        return [
            LiteratureItem(
                title=f"[CNKI 存根] {' '.join(query.keywords)}",
                source="cnki",
                abstract="知网真实检索功能待实现（需机构 Cookie）",
            )
        ]


class WanfangStubSearcher:
    """万方数据 — Cookie 接入框架（存根）。"""

    async def search(self, query: SearchQuery) -> list[LiteratureItem]:
        if not query.cookie:
            return []
        return [
            LiteratureItem(
                title=f"[万方 存根] {' '.join(query.keywords)}",
                source="wanfang",
                abstract="万方真实检索功能待实现（需机构 Cookie）",
            )
        ]


class VipStubSearcher:
    """维普期刊 — Cookie 接入框架（存根）。"""

    async def search(self, query: SearchQuery) -> list[LiteratureItem]:
        if not query.cookie:
            return []
        return [
            LiteratureItem(
                title=f"[维普 存根] {' '.join(query.keywords)}",
                source="vip",
                abstract="维普真实检索功能待实现（需机构 Cookie）",
            )
        ]
