"""Duplicate citations, a preprint cited beside its published version, and retracted papers.

Duplicates and preprint-vs-published drift are their own risks, and a
retracted paper must not be cited unflagged. CrossRef carries retractions in "updated-by"
(Retraction Watch or the publisher); the Wakefield 1998 Lancet paper lists its 2010 one there.
"""
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from backend.literature.bibtex import bibtex_key
from backend.literature.schemas import LiteratureItem
from backend.verification.layer1_existence import ExistenceChecker
from backend.verification.orchestrator import VerificationOrchestrator
from backend.verification.schemas import CitationStatus, VerificationResult

ABSTRACT = "Retrieval-augmented generation for knowledge-intensive NLP tasks. " * 10


def _item(title, **kw):
    return LiteratureItem(title=title, authors=["Patrick Lewis"], year=2020, abstract=ABSTRACT, **kw)


async def _verify(items):
    orchestrator = VerificationOrchestrator()
    text = " ".join(f"Claim {i} [cite:{bibtex_key(item)}]." for i, item in enumerate(items))
    with patch.object(orchestrator.support_checker, "check", new=AsyncMock(return_value={})), \
         patch.object(orchestrator.existence_checker, "check", new=AsyncMock(
             side_effect=lambda title, **kw: VerificationResult(title=title, doi=kw.get("doi")))):
        _, issues, summary = await orchestrator.run(items, text)
    return {i.title: i for i in issues}, summary


@pytest.mark.asyncio
async def test_a_preprint_cited_beside_its_published_version_is_flagged_on_the_preprint():
    preprint = _item("Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks", source="arxiv",
                     pub_type="preprint", doi="10.48550/arXiv.2005.11401")
    # the published version a year later: same first author and title, so only the year tells the keys apart
    published = LiteratureItem(title="Retrieval-augmented generation for knowledge-intensive NLP tasks.",
                               authors=["Patrick Lewis"], year=2021, abstract=ABSTRACT, source="openalex",
                               pub_type="proceedings-article", doi="10.5555/3495724.3496517")
    issues, summary = await _verify([preprint, published])
    flagged = issues[preprint.title]
    assert flagged.action == "warned" and "preprint" in flagged.reason.lower()
    assert issues[published.title].action == "kept"
    assert summary.warned == 1 and summary.passed == 1


@pytest.mark.asyncio
async def test_the_same_paper_under_two_keys_is_flagged_as_a_duplicate():
    a = _item("Dense Passage Retrieval for Open-Domain Question Answering", source="openalex",
              doi="10.18653/v1/2020.emnlp-main.550")
    b = LiteratureItem(title="Dense passage retrieval for open-domain question answering", authors=["Vladimir Karpukhin"],
                       year=2020, abstract=ABSTRACT, source="crossref", doi="10.18653/V1/2020.EMNLP-MAIN.550")
    issues, _ = await _verify([a, b])
    reasons = [i.reason for i in issues.values() if i.action == "warned"]
    assert len(reasons) == 1 and "Duplicate" in reasons[0]


@pytest.mark.asyncio
async def test_different_papers_are_left_alone():
    issues, _ = await _verify([_item("Dense Passage Retrieval", source="arxiv"),
                               _item("Leveraging Passage Retrieval with Generative Models", source="arxiv")])
    assert {i.action for i in issues.values()} == {"kept"}


@respx.mock
@pytest.mark.asyncio
async def test_a_retracted_paper_warns_with_the_notice():
    respx.get("https://api.crossref.org/works/10.1016%2FS0140-6736%2897%2911096-0").mock(return_value=httpx.Response(
        200, json={"message": {"title": ["Ileal-lymphoid-nodular hyperplasia"], "updated-by": [
            {"type": "correction", "DOI": "10.1016/s0140-6736(04)15715-2", "updated": {"date-parts": [[2004, 3, 6]]}},
            {"type": "retraction", "DOI": "10.1016/s0140-6736(10)60175-4", "updated": {"date-parts": [[2010, 2, 6]]}},
        ]}}))
    result = await ExistenceChecker().check(title="Ileal-lymphoid-nodular hyperplasia", authors=[],
                                            doi="10.1016/S0140-6736(97)11096-0")
    assert result.status == CitationStatus.WARNED
    assert any("Retracted" in i and "2010" in i and "10.1016/s0140-6736(10)60175-4" in i for i in result.issues)
    assert not any("correction" in i.lower() for i in result.issues)


def test_a_review_of_a_paper_is_not_the_paper():
    # real pool: a Qeios review note repeats the reviewed paper's title inside its own
    from backend.verification.duplicates import duplicate_issues
    paper = LiteratureItem(title="Geometric Analysis of Reasoning Trajectories: A Phase Space Approach", authors=["Marin, Javier"],
                           year=2025, source="crossref", doi="10.32388/7oxug3")
    review = LiteratureItem(title='Review of: "Geometric Analysis of Reasoning Trajectories: A Phase Space Approach"',
                            authors=["Tăbușcă, Alexandru"], year=2025, source="crossref", doi="10.32388/h6iwg5")
    assert duplicate_issues({"a": paper, "b": review}) == {}


def test_authorless_records_must_share_the_whole_title():
    # real pool: two book chapters, 'Retrieval-Augmented Generation' and 'Why Retrieval Augmented Generation?'
    from backend.verification.duplicates import duplicate_issues
    a = LiteratureItem(title="Retrieval‐Augmented Generation", year=2026, source="crossref", doi="10.1002/9781394374717.ch03")
    b = LiteratureItem(title="Why Retrieval Augmented Generation?", year=2024, source="crossref", doi="10.5040/bci-0kgd.ch-1")
    assert duplicate_issues({"a": a, "b": b}) == {}
