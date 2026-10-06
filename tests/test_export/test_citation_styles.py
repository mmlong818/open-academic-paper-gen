"""Reference lists in GB/T 7714-2015 (numeric) and APA 7, the formats Chinese and English
journals ask for; the one fixed format before matched neither.
"""
import pytest

from backend.export.citation_styles import (
    apa_in_text,
    apa_reference,
    default_style,
    gbt_reference,
)
from backend.export.latex_exporter import LatexExporter
from backend.export.markdown_exporter import MarkdownExporter
from backend.literature.bibtex import bibtex_key_from_dict

NQ = {"title": "Natural Questions: A Benchmark for Question Answering Research", "year": 2019,
      "authors": ["Kwiatkowski, Tom", "Jennimaria Palomaki", "Olivia Redfield", "Michael Collins"],
      "journal": "Transactions of the Association for Computational Linguistics", "volume": "7", "issue": "",
      "pages": "453-466", "doi": "10.1162/tacl_a_00276", "pub_type": "journal-article", "source": "crossref"}
DPR = {"title": "Dense Passage Retrieval for Open-Domain Question Answering", "year": 2020,
       "authors": ["Vladimir Karpukhin", "Barlas Oğuz"], "journal": "Proceedings of EMNLP 2020",
       "pages": "6769-6781", "doi": "10.18653/v1/2020.emnlp-main.550", "pub_type": "proceedings-article",
       "source": "openalex"}
RAG = {"title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks", "year": 2020,
       "authors": ["Patrick Lewis"], "doi": "10.48550/arXiv.2005.11401", "pub_type": "preprint", "source": "arxiv",
       "url": "https://arxiv.org/abs/2005.11401"}
ZH = {"title": "国产大语言模型检索增强生成技术在海关领域的应用研究", "year": 2025,
      "authors": ["范毅铭", "沈源里", "夏永忠", "林嘉宜"], "journal": "自然科学前沿", "volume": "1", "issue": "9",
      "pages": "1-12", "doi": "10.63887/fns.2025.1.9.1", "pub_type": "journal-article", "source": "crossref"}


def test_gbt_journal_article():
    assert gbt_reference(NQ) == ("KWIATKOWSKI T, PALOMAKI J, REDFIELD O, et al. Natural Questions: A Benchmark for "
                                 "Question Answering Research[J]. Transactions of the Association for Computational "
                                 "Linguistics, 2019, 7: 453-466. DOI:10.1162/tacl_a_00276.")


def test_gbt_chinese_journal_article_uses_deng():
    assert gbt_reference(ZH) == ("范毅铭, 沈源里, 夏永忠, 等. 国产大语言模型检索增强生成技术在海关领域的应用研究[J]. "
                                 "自然科学前沿, 2025, 1(9): 1-12. DOI:10.63887/fns.2025.1.9.1.")


def test_gbt_conference_paper_and_preprint():
    assert gbt_reference(DPR) == ("KARPUKHIN V, OĞUZ B. Dense Passage Retrieval for Open-Domain Question Answering[C]"
                                  "//Proceedings of EMNLP 2020. 2020: 6769-6781. DOI:10.18653/v1/2020.emnlp-main.550.")
    assert gbt_reference(RAG) == ("LEWIS P. Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks[EB/OL]. "
                                  "(2020). DOI:10.48550/arXiv.2005.11401.")


def test_apa_journal_article_conference_and_preprint():
    assert apa_reference(NQ) == ("Kwiatkowski, T., Palomaki, J., Redfield, O., & Collins, M. (2019). Natural Questions: "
                                 "A Benchmark for Question Answering Research. *Transactions of the Association for "
                                 "Computational Linguistics*, *7*, 453–466. https://doi.org/10.1162/tacl_a_00276")
    assert apa_reference(DPR) == ("Karpukhin, V., & Oğuz, B. (2020). Dense Passage Retrieval for Open-Domain Question "
                                  "Answering. In *Proceedings of EMNLP 2020* (pp. 6769–6781). "
                                  "https://doi.org/10.18653/v1/2020.emnlp-main.550")
    assert apa_reference(RAG) == ("Lewis, P. (2020). *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks* "
                                  "[Preprint]. https://doi.org/10.48550/arXiv.2005.11401")


def test_apa_chinese_names_are_written_in_full():
    assert apa_reference(ZH).startswith("范毅铭, 沈源里, 夏永忠, 林嘉宜 (2025). 国产大语言模型")


def test_apa_in_text_citations():
    assert apa_in_text([NQ]) == "(Kwiatkowski et al., 2019)"
    assert apa_in_text([DPR, RAG]) == "(Karpukhin & Oğuz, 2020; Lewis, 2020)"
    assert apa_in_text([ZH]) == "(范毅铭 等, 2025)"


def test_the_default_follows_the_writing_language():
    assert default_style("zh") == "gbt7714" and default_style("en") == "apa7"


def _state(language):
    keys = [bibtex_key_from_dict(c) for c in (NQ, DPR, RAG)]
    return {"topic": "RAG", "language": language, "outline": [{"title": "Intro"}],
            "sections": {"Intro": f"First [cite:{keys[2]}]. Then [cite:{keys[0]}, cite:{keys[1]}]."},
            "verified_citations": [NQ, DPR, RAG]}


def test_markdown_in_apa_cites_author_year_and_sorts_by_author():
    md = MarkdownExporter().export(_state("en"), style="apa7")
    assert "First (Lewis, 2020). Then (Kwiatkowski et al., 2019; Karpukhin & Oğuz, 2020)." in md
    refs = md.split("## References")[1]
    assert refs.index("Karpukhin") < refs.index("Kwiatkowski") < refs.index("Lewis")


def test_markdown_in_gbt_numbers_by_first_appearance():
    md = MarkdownExporter().export(_state("zh"), style="gbt7714")
    assert "First [1]. Then [2, 3]." in md
    assert "[1] LEWIS P." in md and "[2] KWIATKOWSKI T" in md


def test_latex_in_apa_uses_author_year_labels():
    tex = LatexExporter().export(_state("en"), style="apa7")
    assert "\\citep{" in tex and "\\bibitem[Kwiatkowski et al.(2019)]" in tex


def test_an_unknown_style_is_rejected():
    with pytest.raises(ValueError):
        MarkdownExporter().export(_state("en"), style="mla")


def test_a_preprint_without_a_doi_links_its_url():
    # real export: arXiv papers without a DOI ended at "[Preprint]." with no way to find them
    paper = {**RAG, "doi": None}
    assert apa_reference(paper).endswith("[Preprint]. https://arxiv.org/abs/2005.11401")
    assert gbt_reference(paper).endswith("[EB/OL]. (2020). https://arxiv.org/abs/2005.11401.")
