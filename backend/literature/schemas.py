from typing import Any, Literal
from pydantic import BaseModel, Field


class LiteratureItem(BaseModel):
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    abstract: str = ""
    # where the abstract came from when not the searcher's own ("openalex": filled by DOI)
    abstract_via: str = ""
    citation_count: int = 0
    journal: str | None = None
    # bibliographic detail for field-level checks, citation styles and RIS export
    volume: str = ""
    issue: str = ""
    pages: str = ""
    publisher: str = ""
    # kind of work as the source names it: journal-article, proceedings-article, posted-content,
    # article, preprint (arXiv) ...
    pub_type: str = ""
    source: Literal["semantic_scholar", "arxiv", "openalex", "crossref", "cnki", "wanfang", "vip", "upload"]
    source_id: str = ""
    url: str = ""
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)

    # 正文节选（由 content_fetcher 填充，优先于 abstract 用于筛选）
    body_excerpt: str = ""
    # 全文（去掉页眉后，开头 _HEAD_CHARS 字加参考文献前 _TAIL_CHARS 字），供 layer 3 按论断检索相关段落；不进入 API 响应
    full_text: str = ""
    # [offset into full_text, PDF page number] for each page the text spans (5.1 page anchors)
    full_text_pages: list[list[int]] = Field(default_factory=list)

    # 质量评分由 scorer 写入，初始为 0
    quality_score: float = 0.0

    # 文献池建成时分配、池内唯一的引用键（见 bibtex.assign_cite_keys）；旧任务的记录没有，按原算法计算
    cite_key: str = ""


class SearchQuery(BaseModel):
    keywords: list[str]
    language: Literal["en", "zh"] = "en"
    max_results: int = 10
    cookie: str | None = None  # 中文数据库机构 Cookie（运行时注入，不持久化）
    source_mix: str = "balanced"  # zh_major / balanced / en_major
