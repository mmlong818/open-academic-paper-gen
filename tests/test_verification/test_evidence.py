"""Layer 3 evidence: passages of the full text that match the claims, not the first 2000 chars."""
from backend.literature.schemas import LiteratureItem
from backend.verification.evidence import evidence_kind, select_evidence
from backend.verification.layer3_support import Claim

FILLER = "Background material on unrelated architectures and datasets. " * 12
DEEP = "In the ablation, removing layer normalisation cost 3.1 BLEU on the translation benchmark."
FULL = "Abstract: We study transformers.\n\n" + "\n\n".join([FILLER] * 30 + [DEEP] + [FILLER] * 10)


def _item(**kw) -> LiteratureItem:
    return LiteratureItem(**{"title": "T", "source": "arxiv", "abstract": "We study transformers.", **kw})


def _claim(sentence: str) -> Claim:
    return Claim(key="K", sentence=sentence)


def test_without_full_text_the_excerpt_is_used_as_before():
    item = _item(body_excerpt="Excerpt text.")
    assert select_evidence(item, [_claim("x")]) == "Excerpt text."
    assert evidence_kind(item) == "body"
    assert evidence_kind(_item()) == "abstract"


def test_a_matching_passage_deep_in_the_text_is_included():
    item = _item(full_text=FULL, body_excerpt=FULL[:2000])
    evidence = select_evidence(item, [_claim("Removing layer normalisation cost 3.1 BLEU [cite:K].")])
    assert DEEP in evidence
    assert evidence.startswith("Abstract: We study transformers.")  # the opening always rides along
    assert evidence_kind(item) == "full_text"


def test_evidence_stays_within_budget():
    item = _item(full_text=FULL)
    evidence = select_evidence(item, [_claim("unrelated architectures and datasets")], budget=2500)
    assert len(evidence) <= 2500


def test_each_claim_gets_its_own_passage():
    other = "Pretraining on 40GB of web text improved perplexity by 12 points."
    full = FULL + "\n\n" + FILLER + "\n\n" + other
    item = _item(full_text=full)
    evidence = select_evidence(item, [
        _claim("Removing layer normalisation cost 3.1 BLEU."),
        _claim("Pretraining on 40GB of web text improved perplexity."),
    ])
    assert DEEP in evidence and other in evidence


def test_chinese_claims_match_chinese_passages():
    target = "干预组焦虑评分较对照组下降12分，差异具有统计学意义。"
    filler = "本研究介绍了研究背景与相关理论框架。" * 20
    full = "摘要：本研究探讨正念干预。\n\n" + "\n\n".join([filler] * 20 + [target] + [filler] * 5)
    item = _item(full_text=full)
    evidence = select_evidence(item, [_claim("正念干预使焦虑评分下降12分[cite:K]。")])
    assert target in evidence
