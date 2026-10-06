"""T1.2 — constrained revision of flagged sentences."""
from unittest.mock import AsyncMock, MagicMock

from backend.literature.schemas import LiteratureItem
from backend.writing.revision import (
    Problem,
    RevisionAgent,
    apply_revisions,
    check_revision,
    group_by_paragraph,
)

PARA_1 = "Remote work rose in 2020 [cite:Smith2021A]. Output fell 12% in mandated firms."
PARA_2 = "A second paragraph stays untouched. It has two sentences."
SECTION = f"{PARA_1}\n\n{PARA_2}"
SECTIONS = {"Findings": SECTION}
OUTLINE = [{"title": "Findings", "summary": "remote work output"}]
LIT = [LiteratureItem(title="Remote work and output", authors=["Lee K"], year=2022, source="arxiv",
                      abstract="Mandated remote work reduced output by 12% in a panel of firms. " * 3)]
LEE = "K2022Remote"  # bibtex_key of LIT[0]
UNCITED = Problem("Findings", "Output fell 12% in mandated firms.", "uncited", "specific statistic")


def test_problems_are_grouped_by_the_paragraph_that_holds_them():
    groups = group_by_paragraph(SECTIONS, [UNCITED])
    assert list(groups) == [("Findings", 0)]
    assert groups[("Findings", 0)] == [UNCITED]


def test_problem_whose_sentence_is_not_found_is_dropped():
    lost = Problem("Findings", "Study: X | Finding: Y", "unsupported", "table row")
    assert group_by_paragraph(SECTIONS, [lost]) == {}


def test_check_rejects_keys_outside_the_candidate_list():
    after = PARA_1.replace("mandated firms.", "mandated firms [cite:Invented2099X].")
    ok, why = check_revision(PARA_1, after, [UNCITED], allowed_keys={LEE, "Smith2021A"})
    assert not ok and "Invented2099X" in why


def test_check_rejects_rewriting_unflagged_sentences():
    after = "Remote work collapsed entirely [cite:Smith2021A]. Output fell 12% [cite:K2022Remote]."
    ok, why = check_revision(PARA_1, after, [UNCITED], allowed_keys={LEE, "Smith2021A"})
    assert not ok and "unflagged" in why


def test_check_accepts_a_fix_that_only_touches_the_flagged_sentence():
    after = f"Remote work rose in 2020 [cite:Smith2021A]. Output fell 12% in mandated firms [cite:{LEE}]."
    assert check_revision(PARA_1, after, [UNCITED], allowed_keys={LEE, "Smith2021A"}) == (True, "")


def test_apply_replaces_only_the_revised_paragraph():
    after = f"Remote work rose in 2020 [cite:Smith2021A]. Output fell 12% [cite:{LEE}]."
    revised = apply_revisions(SECTIONS, [{"section": "Findings", "before": PARA_1, "after": after}])
    assert revised["Findings"] == f"{after}\n\n{PARA_2}"


async def test_propose_asks_once_per_paragraph_and_checks_the_reply():
    after = f"Remote work rose in 2020 [cite:Smith2021A]. Output fell 12% in mandated firms [cite:{LEE}]."
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content=after))
    revisions = await RevisionAgent(llm=llm).propose(SECTIONS, [UNCITED], LIT, OUTLINE, "en")

    assert llm.ainvoke.await_count == 1
    prompt = llm.ainvoke.call_args.args[0]
    assert "Output fell 12% in mandated firms." in prompt and LEE in prompt
    assert [(r.section, r.before, r.after, r.status) for r in revisions] == [
        ("Findings", PARA_1, after, "proposed"),
    ]


async def test_reply_breaking_the_constraints_is_kept_as_rejected_not_applied():
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content="Everything is rewritten [cite:Nope1999Z]."))
    revisions = await RevisionAgent(llm=llm).propose(SECTIONS, [UNCITED], LIT, OUTLINE, "en")
    assert revisions[0].status == "rejected"
    assert revisions[0].note


async def test_llm_failure_proposes_nothing():
    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=RuntimeError("down"))
    assert await RevisionAgent(llm=llm).propose(SECTIONS, [UNCITED], LIT, OUTLINE, "en") == []
