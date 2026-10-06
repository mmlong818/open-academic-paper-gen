"""The task detail payload must not carry every paper's full text (tens of KB each)."""
from types import SimpleNamespace

from backend.api.routes.tasks import TaskResponse


def _task(literature):
    return SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001", topic="t", language="en", collab_mode="full_auto",
        paper_type="general", status="completed", current_phase=9, error_message=None,
        created_at=None, updated_at=None, is_starred=False, is_deleted=False,
        state_snapshot={"literature": literature},
    )


def test_full_text_is_left_out_of_the_literature_payload():
    literature = [{"title": "A", "source": "arxiv", "body_excerpt": "short", "full_text": "x" * 40000}]
    response = TaskResponse.from_orm(_task(literature), include_snapshot=True)
    assert response.literature == [{"title": "A", "source": "arxiv", "body_excerpt": "short"}]
    assert "full_text" in literature[0], "the stored snapshot itself is untouched"


def test_verified_count_reports_the_exportable_pool_without_sending_it():
    # the verification panel read a verified_citations field the payload never had, and showed 0
    task = _task([])
    task.state_snapshot["verified_citations"] = [{"title": "A", "full_text": "x" * 40000}, {"title": "B"}]
    response = TaskResponse.from_orm(task, include_snapshot=True)
    assert response.verified_count == 2
    assert "verified_citations" not in response.model_dump()


def test_verified_count_is_none_before_verification():
    assert TaskResponse.from_orm(_task([]), include_snapshot=True).verified_count is None
