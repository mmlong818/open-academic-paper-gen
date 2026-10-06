from pydantic import BaseModel, Field, computed_field


class CitationStatus:
    PASSED = "passed"
    WARNED = "warned"
    REMOVED = "removed"


class VerificationResult(BaseModel):
    title: str
    doi: str | None = None
    status: str = CitationStatus.PASSED
    layer1_ok: bool = True
    issues: list[str] = Field(default_factory=list)


class CitationIssue(BaseModel):
    title: str
    doi: str | None = None
    layer: str
    reason: str
    action: str
    # Pipeline stage the problem most likely came from: "writing" (fabricated key or
    # misdescribed source), "retrieval" (bad bibliographic record), joined with "+".
    stage: str = ""


class VerificationSummary(BaseModel):
    total: int
    passed: int
    warned: int
    removed: int
    # cited papers with no text for layer 3 to check against; not counted as passed
    unverified: int = 0

    @computed_field  # type: ignore[misc]
    @property
    def failure_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.warned + self.removed) / self.total

    @computed_field  # type: ignore[misc]
    @property
    def smart_pause_triggered(self) -> bool:
        return self.failure_rate > 0.2
