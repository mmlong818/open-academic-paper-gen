"""Layer 3 asks whether the cited paper backs the sentence — the failure a DOI check misses."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.literature.schemas import LiteratureItem
from backend.verification.layer3_support import (
    SUPPORTED,
    UNCLEAR,
    UNSUPPORTED,
    Claim,
    SupportChecker,
    _parse_verdicts,
)
from backend.verification.orchestrator import extract_claims

EVIDENCE = "We evaluate retrieval augmentation on open-domain QA. " * 10  # > 200 chars


def _item(title: str = "RAG for QA", abstract: str = EVIDENCE) -> LiteratureItem:
    return LiteratureItem(title=title, abstract=abstract, source="arxiv")


def _llm(reply: str) -> MagicMock:
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content=reply))
    return llm


# ---------------------------------------------------------------- claim extraction

def test_extract_claims_groups_sentences_by_key():
    text = (
        "Retrieval helps recall [cite:Smith2024]. "
        "Scaling laws hold across modalities [cite:Lee2023]. "
        "Recall improves further under distillation [cite:Smith2024]."
    )
    claims = extract_claims(text)
    assert set(claims) == {"Smith2024", "Lee2023"}
    assert len(claims["Smith2024"]) == 2
    assert "distillation" in claims["Smith2024"][1].sentence


def test_extract_claims_carries_previous_sentence_as_context():
    text = "Transformers dominate translation benchmarks. This is confirmed [cite:Lee2023]."
    claims = extract_claims(text)
    assert claims["Lee2023"][0].context == "Transformers dominate translation benchmarks."


def test_extract_claims_splits_chinese_sentences():
    text = "检索增强显著提升召回率[cite:Zhang2024]。规模定律在多模态下依然成立[cite:Lee2023]。"
    claims = extract_claims(text)
    assert set(claims) == {"Zhang2024", "Lee2023"}
    assert "召回率" in claims["Zhang2024"][0].sentence
    assert "规模定律" not in claims["Zhang2024"][0].sentence


def test_extract_claims_empty_for_text_without_markers():
    assert extract_claims("A paragraph with no citations at all.") == {}


# ---------------------------------------------------------------- reply parsing

def test_parse_verdicts_reads_json_array():
    raw = '[{"verdict": "supported", "reason": "stated"}, {"verdict": "unsupported", "reason": "off topic"}]'
    assert _parse_verdicts(raw, 2) == [(SUPPORTED, "stated"), (UNSUPPORTED, "off topic")]


def test_parse_verdicts_strips_markdown_fence():
    raw = '```json\n[{"verdict": "unsupported", "reason": "r"}]\n```'
    assert _parse_verdicts(raw, 1) == [(UNSUPPORTED, "r")]


def test_parse_verdicts_falls_back_to_unclear_on_garbage():
    assert _parse_verdicts("not json at all", 3) == [(UNCLEAR, "")] * 3


def test_parse_verdicts_rejects_invented_verdict_labels():
    raw = '[{"verdict": "definitely false", "reason": "r"}]'
    assert _parse_verdicts(raw, 1) == [(UNCLEAR, "r")]


def test_parse_verdicts_pads_a_short_reply():
    raw = '[{"verdict": "supported", "reason": "ok"}]'
    assert _parse_verdicts(raw, 3) == [(SUPPORTED, "ok"), (UNCLEAR, ""), (UNCLEAR, "")]


# ---------------------------------------------------------------- checker behaviour

@pytest.mark.asyncio
async def test_check_reports_unsupported_claim():
    checker = SupportChecker(llm=_llm('[{"verdict": "unsupported", "reason": "paper is about QA"}]'))
    claims = {"Smith2024": [Claim(key="Smith2024", sentence="Recall triples [cite:Smith2024].")]}

    result = await checker.check(claims, {"Smith2024": _item()})

    assert result["Smith2024"][0].verdict == UNSUPPORTED
    assert result["Smith2024"][0].reason == "paper is about QA"


@pytest.mark.asyncio
async def test_check_skips_papers_with_too_little_evidence():
    checker = SupportChecker(llm=_llm('[{"verdict": "unsupported", "reason": "r"}]'))
    claims = {"Thin2024": [Claim(key="Thin2024", sentence="A claim [cite:Thin2024].")]}

    result = await checker.check(claims, {"Thin2024": _item(abstract="too short")})

    assert result == {}
    checker._llm.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_check_skips_keys_absent_from_the_pool():
    checker = SupportChecker(llm=_llm("[]"))
    claims = {"Ghost2024": [Claim(key="Ghost2024", sentence="A claim [cite:Ghost2024].")]}

    assert await checker.check(claims, {}) == {}
    checker._llm.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_llm_failure_yields_no_verdict_rather_than_a_warning():
    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=RuntimeError("rate limited"))
    checker = SupportChecker(llm=llm)
    claims = {"Smith2024": [Claim(key="Smith2024", sentence="A claim [cite:Smith2024].")]}

    assert await checker.check(claims, {"Smith2024": _item()}) == {}


@pytest.mark.asyncio
async def test_check_is_disabled_by_settings_flag():
    from backend.core.config import settings

    checker = SupportChecker(llm=_llm('[{"verdict": "unsupported", "reason": "r"}]'))
    claims = {"Smith2024": [Claim(key="Smith2024", sentence="A claim [cite:Smith2024].")]}

    settings.verify_citation_support = False
    try:
        assert await checker.check(claims, {"Smith2024": _item()}) == {}
    finally:
        settings.verify_citation_support = True


@pytest.mark.asyncio
async def test_body_excerpt_is_preferred_over_abstract_as_evidence():
    captured: list[str] = []

    async def capture(prompt):
        captured.append(prompt)
        return MagicMock(content='[{"verdict": "supported", "reason": ""}]')

    llm = MagicMock()
    llm.ainvoke = capture
    item = LiteratureItem(
        title="RAG", abstract=EVIDENCE,
        body_excerpt="UNIQUE BODY MARKER. " + EVIDENCE, source="arxiv",
    )
    claims = {"K": [Claim(key="K", sentence="A claim [cite:K].")]}

    await SupportChecker(llm=llm).check(claims, {"K": item})

    assert "UNIQUE BODY MARKER" in captured[0]


# ---------------------------------------------------------------- prompt contract

def test_support_prompt_carries_evidence_claim_and_context():
    from backend.writing.prompts import build_support_prompt

    prompt = build_support_prompt(
        title="RAG for QA",
        evidence="UNIQUE EVIDENCE TEXT",
        claims=[{"sentence": "Recall triples [cite:K].", "context": "Earlier setup sentence."}],
        language="en",
        key="K",
    )
    assert "UNIQUE EVIDENCE TEXT" in prompt
    assert "Recall triples [cite:K]." in prompt
    assert "Earlier setup sentence." in prompt
    # the f-string must emit a literal JSON example, not a formatted placeholder
    assert '[{"verdict":' in prompt
    assert "{{" not in prompt


def test_support_prompt_has_a_chinese_form():
    from backend.writing.prompts import build_support_prompt

    prompt = build_support_prompt(
        title="检索增强",
        evidence="唯一证据文本",
        claims=[{"sentence": "召回率提升三倍[cite:K]。", "context": ""}],
        language="zh",
        key="K",
    )
    assert "唯一证据文本" in prompt
    assert "召回率提升三倍" in prompt
    assert '[{"verdict":' in prompt
    assert "{{" not in prompt


@pytest.mark.asyncio
async def test_non_string_llm_content_is_swallowed_not_raised():
    """LangChain can hand back a list of content blocks; that must not kill verification."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content=[{"type": "text", "text": "[]"}]))
    claims = {"K": [Claim(key="K", sentence="A claim [cite:K].")]}

    assert await SupportChecker(llm=llm).check(claims, {"K": _item()}) == {}


def test_support_prompt_names_the_marker_under_review_in_both_languages():
    """A sentence often cites several papers; the judge must know which marker it is checking."""
    from backend.writing.prompts import build_support_prompt

    for language in ("en", "zh"):
        prompt = build_support_prompt(
            title="T", evidence="E",
            claims=[{"sentence": "A [cite:OTHER] and B [cite:TARGET].", "context": ""}],
            language=language, key="TARGET",
        )
        # once in the sentence, at least once more where the task names it
        assert prompt.count("[cite:TARGET]") >= 2, language



def test_support_prompt_describes_the_evidence_it_actually_carries():
    """Calling an abstract "passages picked from the full text" made abstract-only verdicts
    drift to unclear; each kind of evidence gets its own, truthful description."""
    from backend.writing.prompts import build_support_prompt

    claims = [{"sentence": "A [cite:K].", "context": ""}]
    for language in ("en", "zh"):
        with_passages = build_support_prompt("T", "E", claims, language, key="K", passages=True)
        abstract_only = build_support_prompt("T", "E", claims, language, key="K", passages=False)
        assert "[...]" in with_passages, language
        assert "[...]" not in abstract_only, language


async def test_checker_flags_full_text_evidence_to_the_prompt():
    from unittest.mock import patch as _patch

    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content='[{"verdict": "supported", "reason": ""}]'))
    item = LiteratureItem(title="T", source="arxiv", abstract="a " * 150,
                          full_text="Opening. " * 200 + "\n\nThe result is 3.1 BLEU. " * 5)
    claims = {"K": [Claim(key="K", sentence="The result is 3.1 BLEU [cite:K].")]}
    with _patch("backend.verification.layer3_support.build_support_prompt", return_value="p") as build:
        await SupportChecker(llm=llm).check(claims, {"K": item})
    assert build.call_args.kwargs["passages"] is True
