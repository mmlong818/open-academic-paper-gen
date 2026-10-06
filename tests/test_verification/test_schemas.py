import pytest
from backend.verification.schemas import (
    CitationStatus,
    VerificationResult,
    CitationIssue,
    VerificationSummary,
)


def test_citation_status_values():
    assert CitationStatus.PASSED == "passed"
    assert CitationStatus.WARNED == "warned"
    assert CitationStatus.REMOVED == "removed"


def test_verification_result_defaults():
    result = VerificationResult(title="Test Paper")
    assert result.status == CitationStatus.PASSED
    assert result.layer1_ok is True
    assert result.issues == []


def test_verification_result_with_issues():
    result = VerificationResult(
        title="Test Paper",
        doi="10.1/test",
        status=CitationStatus.WARNED,
        layer1_ok=False,
        issues=["DOI not found in CrossRef"],
    )
    assert result.status == CitationStatus.WARNED
    assert len(result.issues) == 1


def test_citation_issue_fields():
    issue = CitationIssue(
        title="Unknown Paper",
        layer="layer1",
        reason="DOI not found",
        action="removed",
    )
    assert issue.layer == "layer1"
    assert issue.action == "removed"


def test_verification_summary_failure_rate():
    summary = VerificationSummary(
        total=10,
        passed=8,
        warned=1,
        removed=1,
    )
    assert summary.failure_rate == pytest.approx(0.2)
    assert summary.smart_pause_triggered is False


def test_verification_summary_smart_pause_trigger():
    summary = VerificationSummary(
        total=10,
        passed=6,
        warned=1,
        removed=3,
    )
    # failure_rate = 4/10 = 0.4 > 0.2
    assert summary.smart_pause_triggered is True
