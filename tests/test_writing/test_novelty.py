"""Novelty diagnosis of the writing angle, with a pseudo-innovation check: shown beside the angle, never rewriting it. The closest prior work must
be a paper of the pool; a key the model invents is dropped."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.literature.bibtex import assign_cite_keys, bibtex_key
from backend.literature.schemas import LiteratureItem
from backend.writing.novelty import LEVELS, NoveltyDiagnoser

ANGLE = {"writing_angle": "Equivariant graph networks for polymer property prediction",
         "contribution": "c", "gap": "polymers are rarely modelled with equivariance"}


def _pool() -> list[LiteratureItem]:
    # keys assigned as cleaning assigns them, so papers sharing author and year stay apart
    return assign_cite_keys([LiteratureItem(title=f"Equivariant graph networks {i}", authors=["Ann Lee"], year=2020 + i % 4,
                           source="arxiv", abstract=f"Polymer property prediction study {i}.") for i in range(40)])


def _llm(reply: str) -> MagicMock:
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content=reply))
    return llm


def _reply(closest_keys: list[str]) -> str:
    closest = ", ".join(f'{{"key": "{k}", "overlap": "same task"}}' for k in closest_keys)
    return ('{"levels": {"problem": {"verdict": "incremental", "reason": "r1"}, '
            '"method": {"verdict": "existing", "reason": "r2"}, "data": {"verdict": "new", "reason": "r3"}, '
            '"perspective": {"verdict": "bogus", "reason": "r4"}}, '
            '"pseudo": [{"pattern": "old_method_new_domain", "reason": "equivariance is not new"}], '
            f'"closest": [{closest}], "objection": "a reviewer would say X"}}')


@pytest.mark.asyncio
async def test_diagnosis_grades_four_levels_and_keeps_pool_keys_only():
    pool = _pool()
    real = bibtex_key(pool[0])
    llm = _llm(_reply([real, "Ghost2099X"]))

    result = await NoveltyDiagnoser(llm).run("polymers", ANGLE, pool, "en")

    assert set(result["levels"]) == set(LEVELS)
    assert result["levels"]["method"]["verdict"] == "existing"
    assert result["levels"]["perspective"]["verdict"] == "unclear", "an unknown verdict is not trusted"
    assert [c["key"] for c in result["closest"]] == [real]
    assert result["closest"][0]["title"] == pool[0].title
    assert result["dropped_keys"] == 1
    assert result["pseudo"][0]["pattern"] == "old_method_new_domain"
    assert result["objection"] == "a reviewer would say X"


@pytest.mark.asyncio
async def test_the_prompt_shows_the_angle_and_keyed_candidates():
    pool = _pool()
    llm = _llm(_reply([]))
    await NoveltyDiagnoser(llm).run("polymers", ANGLE, pool, "en")
    prompt = llm.ainvoke.call_args.args[0]
    assert ANGLE["writing_angle"] in prompt and ANGLE["gap"] in prompt
    assert f"- [{bibtex_key(pool[0])}]" in prompt
    assert prompt.count("\n- [") == 30, "the 30 papers closest to the angle, not the whole pool"


@pytest.mark.asyncio
@pytest.mark.parametrize("reply", ["not json", "[]"])
async def test_an_unusable_reply_gives_no_diagnosis(reply):
    assert await NoveltyDiagnoser(_llm(reply)).run("polymers", ANGLE, _pool(), "en") is None


@pytest.mark.asyncio
async def test_no_angle_means_no_call():
    llm = _llm(_reply([]))
    assert await NoveltyDiagnoser(llm).run("polymers", {}, _pool(), "en") is None
    llm.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_an_unusable_reply_is_logged_with_its_finish_reason(caplog):
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content='{"levels": {"problem"', response_metadata={"finish_reason": "length"}))
    with caplog.at_level("WARNING", logger="backend.writing.novelty"):
        assert await NoveltyDiagnoser(llm).run("polymers", ANGLE, _pool(), "en") is None
    assert "finish_reason=length" in caplog.text
