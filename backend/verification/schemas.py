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


class ClaimCoverage(BaseModel):
    """How the claims citing one paper were judged by layer 3."""

    total: int = 0
    judged: int = 0      # supported, unsupported, partial or misaligned
    unclear: int = 0     # the evidence shown could not settle it
    unjudged: int = 0    # no verdict: no text to judge against, or the call failed


class CitationIssue(BaseModel):
    title: str
    doi: str | None = None
    layer: str
    reason: str
    action: str
    # Pipeline stage the problem most likely came from: "writing" (fabricated key or
    # misdescribed source), "retrieval" (bad bibliographic record), joined with "+".
    stage: str = ""
    # What layer 3 judged this paper's claims on ("full_text", "body", "abstract", "none"),
    # and how many of them it settled; empty for keys that are not in the pool.
    evidence: str = ""
    claims: ClaimCoverage | None = None


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
