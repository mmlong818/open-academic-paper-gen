"""T1.1 — factual statements that carry no citation at all."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.verification.uncited import UncitedClaimChecker

SECTION = (
    "Remote work rose sharply during 2020 [cite:Smith2021A]. "
    "Productivity fell by 12% in firms that mandated it. "
    "This review argues that duration matters more than location. "
    "Later studies found similar effects [cite:Lee2022B]."
)


def _llm(reply: str):
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content=reply))
    return llm


@pytest.fixture(autouse=True)
def _enabled():
    with patch("backend.verification.uncited.settings.verify_uncited_claims", True):
        yield


async def test_flags_only_the_numbered_uncited_sentences():
    # ids 1 and 2 are the uncited sentences; the model also names a cited one, which is ignored
    llm = _llm('[{"id": 1, "reason": "specific statistic"}, {"id": 0, "reason": "x"}]')
    claims = await UncitedClaimChecker(llm=llm).check({"Findings": SECTION}, "en")
    assert [(c.section, c.sentence, c.reason) for c in claims] == [
        ("Findings", "Productivity fell by 12% in firms that mandated it.", "specific statistic"),
    ]


async def test_prompt_numbers_uncited_sentences_and_shows_cited_ones_as_context():
    llm = _llm("[]")
    await UncitedClaimChecker(llm=llm).check({"Findings": SECTION}, "en")
    prompt = llm.ainvoke.call_args.args[0]
    assert "[1] Productivity fell by 12%" in prompt
    assert "[2] This review argues" in prompt
    assert "Remote work rose sharply during 2020 [cite:Smith2021A]." in prompt
    assert "[0]" not in prompt  # cited sentences are context, not candidates


async def test_abstract_sections_are_not_checked():
    llm = _llm('[{"id": 1, "reason": "r"}]')
    claims = await UncitedClaimChecker(llm=llm).check({"Abstract": SECTION, "摘要": SECTION}, "en")
    assert claims == []
    llm.ainvoke.assert_not_called()


async def test_tables_are_left_out():
    table = "| Study | Finding |\n|---|---|\n| Survey of 500 firms | Output fell 12% |\n"
    llm = _llm("[]")
    await UncitedClaimChecker(llm=llm).check({"Results": table}, "en")
    llm.ainvoke.assert_not_called()  # nothing but a table: no prose sentence to judge


async def test_unparseable_reply_or_llm_error_yields_nothing():
    assert await UncitedClaimChecker(llm=_llm("not json")).check({"S": SECTION}, "en") == []
    broken = MagicMock()
    broken.ainvoke = AsyncMock(side_effect=RuntimeError("boom"))
    assert await UncitedClaimChecker(llm=broken).check({"S": SECTION}, "en") == []


async def test_disabled_by_default_makes_no_call():
    llm = _llm('[{"id": 1, "reason": "r"}]')
    with patch("backend.verification.uncited.settings.verify_uncited_claims", False):
        assert await UncitedClaimChecker(llm=llm).check({"S": SECTION}, "en") == []
    llm.ainvoke.assert_not_called()


def test_off_unless_configured():
    from backend.core.config import Settings

    assert Settings(_env_file=None).verify_uncited_claims is False


async def test_conclusion_and_methodology_sections_are_not_checked():
    """By convention these restate the paper's own findings and procedure, not the literature's."""
    llm = _llm('[{"id": 1, "reason": "r"}]')
    sections = {"Conclusion": SECTION, "5. Conclusions": SECTION, "Methodology": SECTION,
                "研究方法": SECTION, "结论与展望": SECTION}
    assert await UncitedClaimChecker(llm=llm).check(sections, "en") == []
    llm.ainvoke.assert_not_called()


async def test_discussion_is_still_checked():
    llm = _llm('[{"id": 1, "reason": "specific statistic"}]')
    claims = await UncitedClaimChecker(llm=llm).check({"Discussion": SECTION}, "en")
    assert len(claims) == 1
