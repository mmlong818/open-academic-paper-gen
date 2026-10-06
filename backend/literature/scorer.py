import math
from datetime import date

from backend.literature.schemas import LiteratureItem

JOURNAL_TIERS: dict[str, float] = {
    "Nature": 30.0,
    "Science": 30.0,
    "Cell": 28.0,
    "Nature Communications": 22.0,
    "PNAS": 20.0,
    "NeurIPS": 25.0,
    "ICML": 24.0,
    "ICLR": 24.0,
    "CVPR": 22.0,
    "ACL": 22.0,
    "IEEE Transactions on Pattern Analysis and Machine Intelligence": 20.0,
    "Journal of Machine Learning Research": 20.0,
    "Computers & Education": 18.0,
    "British Journal of Educational Technology": 16.0,
    "Educational Technology & Society": 14.0,
    "中国科学": 20.0,
    "计算机学报": 18.0,
    "软件学报": 18.0,
    "自动化学报": 16.0,
}

_JOURNAL_LOOKUP: dict[str, float] = {k.lower(): v for k, v in JOURNAL_TIERS.items()}

_CURRENT_YEAR = date.today().year


def _citation_score(count: int) -> float:
    """引用量映射到 0-60 分（log 曲线）。"""
    if count <= 0:
        return 0.0
    return min(60.0, 60.0 * math.log1p(count) / math.log1p(1000))


def _journal_score(journal: str | None) -> float:
    if not journal:
        return 0.0
    return _JOURNAL_LOOKUP.get(journal.lower(), 0.0)


def _recency_score(year: int | None) -> float:
    """近年文献奖励分（最高 20 分），鼓励纳入最新研究。"""
    if year is None:
        return 0.0
    age = _CURRENT_YEAR - year
    if age <= 1:
        return 20.0
    if age <= 2:
        return 16.0
    if age <= 3:
        return 12.0
    if age <= 5:
        return 8.0
    if age <= 8:
        return 4.0
    return 0.0


def _abstract_bonus(abstract: str) -> float:
    """有摘要的论文给小幅奖励，鼓励优先保留可供 LLM 分析的文献。"""
    return 5.0 if abstract and len(abstract.strip()) > 50 else 0.0


def score_items(items: list[LiteratureItem]) -> list[LiteratureItem]:
    """计算每篇文献的 quality_score（0-100）。"""
    result = []
    for item in items:
        raw_score = (
            _citation_score(item.citation_count)
            + _journal_score(item.journal)
            + _recency_score(item.year)
            + _abstract_bonus(item.abstract)
        )
        scored = item.model_copy(update={"quality_score": min(100.0, raw_score)})
        result.append(scored)
    return result
