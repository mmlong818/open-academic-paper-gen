"""The cited references as RIS and BibTeX, for Zotero, EndNote and LaTeX users.

Only papers the text cites are exported, as in the reference list; BibTeX keys are the ones
the LaTeX export \\cite{}s, so the two work together.
"""
from backend.export.bib_export import export_bibtex, export_ris
from backend.literature.bibtex import bibtex_key_from_dict

NQ = {"title": "Natural Questions: A Benchmark for Question Answering Research", "year": 2019,
      "authors": ["Kwiatkowski, Tom", "Jennimaria Palomaki"], "journal": "TACL", "volume": "7", "issue": "",
      "pages": "453-466", "doi": "10.1162/tacl_a_00276", "pub_type": "journal-article", "source": "crossref",
      "abstract": "We present the Natural Questions corpus."}
DPR = {"title": "Dense Passage Retrieval & Beyond", "year": 2020, "authors": ["Vladimir Karpukhin"],
       "journal": "Proceedings of EMNLP 2020", "pages": "6769-6781", "pub_type": "proceedings-article",
       "source": "openalex"}
RAG = {"title": "Retrieval-Augmented Generation", "year": 2020, "authors": ["Patrick Lewis"], "pub_type": "preprint",
       "source": "arxiv", "url": "https://arxiv.org/abs/2005.11401"}
UNCITED = {"title": "Never cited", "year": 2021, "authors": ["A B"], "source": "arxiv"}


def _state():
    keys = [bibtex_key_from_dict(c) for c in (NQ, DPR, RAG)]
    return {"outline": [{"title": "Intro"}],
            "sections": {"Intro": f"A [cite:{keys[0]}]. B [cite:{keys[1]}, cite:{keys[2]}]. C [cite:Ghost2099x]."},
            "verified_citations": [NQ, DPR, RAG, UNCITED]}


def test_ris_has_one_record_per_cited_paper_with_its_type_and_fields():
    ris = export_ris(_state())
    records = [r for r in ris.split("ER  - ") if r.strip()]
    assert len(records) == 3 and "Never cited" not in ris
    nq = records[0]
    for line in ("TY  - JOUR", "AU  - Kwiatkowski, Tom", "AU  - Palomaki, Jennimaria", "PY  - 2019", "VL  - 7",
                 "SP  - 453", "EP  - 466", "DO  - 10.1162/tacl_a_00276", "T2  - TACL",
                 "AB  - We present the Natural Questions corpus."):
        assert line in nq, line
    assert "TY  - CONF" in records[1] and "TY  - UNPB" in records[2]
    assert "UR  - https://arxiv.org/abs/2005.11401" in records[2]


def test_bibtex_entries_use_the_latex_export_keys():
    bib = export_bibtex(_state())
    key = bibtex_key_from_dict(NQ)
    assert f"@article{{{key}," in bib
    assert "author = {Kwiatkowski, Tom and Palomaki, Jennimaria}" in bib
    assert "pages = {453--466}" in bib and "doi = {10.1162/tacl_a_00276}" in bib
    assert f"@inproceedings{{{bibtex_key_from_dict(DPR)}," in bib and "booktitle = {Proceedings of EMNLP 2020}" in bib
    assert "title = {Dense Passage Retrieval \\& Beyond}" in bib  # LaTeX specials escaped
    assert f"@misc{{{bibtex_key_from_dict(RAG)}," in bib and "Never cited" not in bib and "Ghost2099x" not in bib


def test_nothing_cited_nothing_exported():
    empty = {"outline": [], "sections": {"Intro": "No citations."}, "verified_citations": [NQ]}
    assert export_ris(empty) == "" and export_bibtex(empty) == ""


def test_a_backslash_and_braces_escape_cleanly():
    from backend.export.bib_export import _bib_escape
    assert _bib_escape(r"a\b {c}") == r"a\textbackslash{}b \{c\}"
