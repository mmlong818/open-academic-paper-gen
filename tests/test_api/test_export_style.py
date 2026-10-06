"""The export endpoints take ?style=gbt7714|apa7|numeric and default by writing language."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from backend.api.routes.export import export_latex, export_markdown
from backend.db.models import TaskStatus
from backend.literature.bibtex import bibtex_key_from_dict

PAPER = {"title": "Dense Passage Retrieval", "authors": ["Vladimir Karpukhin"], "year": 2020,
         "journal": "EMNLP", "pub_type": "proceedings-article", "source": "openalex"}


def _task(language):
    key = bibtex_key_from_dict(PAPER)
    return SimpleNamespace(topic="t", language=language, status=TaskStatus.completed, state_snapshot={
        "outline": [{"title": "Intro"}], "sections": {"Intro": f"DPR [cite:{key}]."},
        "verified_citations": [PAPER]})


async def _export(fn, language, style):
    with patch("backend.api.routes.export.get_task", AsyncMock(return_value=_task(language))):
        return await fn(task_id="00000000-0000-0000-0000-000000000001", style=style, session=None)


@pytest.mark.asyncio
async def test_the_style_parameter_picks_the_format():
    assert "DPR (Karpukhin, 2020)." in await _export(export_markdown, "zh", "apa7")
    assert "DPR [1]." in await _export(export_markdown, "en", "gbt7714")
    assert "\\citep{" in await _export(export_latex, "zh", "apa7")


@pytest.mark.asyncio
async def test_without_a_style_the_writing_language_decides():
    assert "[1] KARPUKHIN V." in await _export(export_markdown, "zh", None)
    assert "(Karpukhin, 2020)" in await _export(export_markdown, "en", None)


@pytest.mark.asyncio
async def test_an_unknown_style_is_a_422():
    with pytest.raises(HTTPException) as err:
        await _export(export_markdown, "en", "mla")
    assert err.value.status_code == 422
