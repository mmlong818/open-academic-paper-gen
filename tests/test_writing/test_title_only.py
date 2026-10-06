"""Papers known only by their title are cited as examples, never described.

With nothing but titles, a Chinese review still wrote that a customs study "used multimodal
knowledge graphs, community partitioning and incremental indexing" - read off the title.
"""
from backend.literature.schemas import LiteratureItem
from backend.writing.prompts import build_section_prompt
from backend.writing.section_writer import select_relevant_papers

SECTION = {"title": "检索增强生成", "summary": "检索增强生成 问答"}


def test_among_equally_relevant_papers_those_with_text_come_first():
    bare = [LiteratureItem(title=f"检索增强生成 问答 {i}", source="crossref") for i in range(3)]
    read = [LiteratureItem(title=f"检索增强生成 问答 {i}", source="arxiv", abstract="检索增强生成。" * 60) for i in range(3, 6)]
    chosen = select_relevant_papers(SECTION, bare + read, top_k=3)
    assert chosen == read


def _prompt(language: str) -> str:
    items = [{"title": "国产大语言模型检索增强生成技术在海关领域的应用研究", "authors_str": "范", "year": 2025},
             {"title": "RAG", "authors_str": "Lewis", "year": 2020, "abstract": "Retrieval-augmented generation. " * 10}]
    return build_section_prompt(section_title="正文", outline_context="o", synthesis="s", literature_snippets=[],
                                language=language, cite_keys=["k1", "k2"], lit_items=items)


def test_title_only_papers_are_marked_and_may_not_be_described():
    zh = _prompt("zh")
    assert zh.count("仅标题") >= 2  # the marker on the bare paper, and the rule
    assert "不得描述其方法、数据或结论" in zh
    en = _prompt("en")
    assert en.count("Title only") >= 2
    assert "never describe its methods, data or findings" in en
