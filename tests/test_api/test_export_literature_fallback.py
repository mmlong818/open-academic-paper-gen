"""With no verified citations, the export routes fall back to the literature pool, as the exporters do."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.api.routes.export import export_markdown, export_references
from backend.db.models import TaskStatus
from backend.literature.bibtex import bibtex_key_from_dict

PAPER = {"title": "Dense Passage Retrieval", "authors": ["Vladimir Karpukhin"], "year": 2020,
         "journal": "EMNLP", "pub_type": "proceedings-article", "source": "openalex"}
TASK_ID = "00000000-0000-0000-0000-000000000001"


def _task():
    key = bibtex_key_from_dict(PAPER)
    return SimpleNamespace(topic="t", language="en", status=TaskStatus.completed, state_snapshot={
        "outline": [{"title": "Intro"}], "sections": {"Intro": f"DPR [cite:{key}]."},
        "verified_citations": [], "literature": [PAPER]})


@pytest.mark.asyncio
async def test_markdown_references_come_from_the_literature_pool():
    with patch("backend.api.routes.export.get_task", AsyncMock(return_value=_task())):
        out = await export_markdown(task_id=TASK_ID, style=None, session=None)
    assert "(Karpukhin, 2020)" in out


@pytest.mark.asyncio
async def test_bibtex_export_comes_from_the_literature_pool():
    with patch("backend.api.routes.export.get_task", AsyncMock(return_value=_task())):
        out = await export_references(task_id=TASK_ID, fmt="bibtex", session=None)
    assert "Dense Passage Retrieval" in out
