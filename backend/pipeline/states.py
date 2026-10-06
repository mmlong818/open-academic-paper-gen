import operator
from enum import IntEnum, StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, Field


class Phase(IntEnum):
    SCOPING = 1
    LITERATURE = 2
    CLEANING = 3   # 文献数据清洗（去重+相关性过滤）
    TRENDS = 4     # 研究趋势/空白发现（原综合）
    ANGLE = 5
    OUTLINE = 6
    WRITING = 7
    VERIFICATION = 8
    EXPORT = 9


class GateStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    SKIPPED = "skipped"


class PaperState(BaseModel):
    task_id: str
    topic: str
    language: str = "zh"
    collab_mode: str = "key_gates"

    current_phase: Phase = Phase.SCOPING
    gate_status: str = GateStatus.SKIPPED

    research_questions: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    chinese_cookie: str | None = None

    literature: list[dict[str, Any]] = Field(default_factory=list)
    cleaning_report: dict[str, Any] | None = None

    synthesis: str = ""  # 保留字段名，前端/导出复用
    # task / method / data / metric / finding / limitation per paper (backend.writing.evidence_table)
    evidence_table: list[dict[str, Any]] | None = None

    angle: dict[str, Any] | None = None
    # novelty diagnosis of the generated angle, shown at its gate (backend.writing.novelty)
    novelty: dict[str, Any] | None = None

    outline: list[dict[str, Any]] = Field(default_factory=list)
    # review papers only: citation-graph groups of the pool that shaped the outline
    taxonomy: list[dict[str, Any]] | None = None

    sections: dict[str, str] = Field(default_factory=dict)

    verified_citations: list[dict[str, Any]] | None = None
    citation_issues: list[dict[str, Any]] | None = None
    uncited_claims: list[dict[str, Any]] | None = None
    revisions: list[dict[str, Any]] | None = None
    review: dict[str, Any] | None = None
    # Style checks on the final text (backend.writing.style_check)
    style_findings: list[dict[str, Any]] | None = None
    smart_pause: bool = False

    latex_content: str = ""
    markdown_content: str = ""

    errors: Annotated[list[str], operator.add] = Field(default_factory=list)

    resume_from_phase: Phase | None = None

    paper_type: str = "general"
    # language mix of the literature: zh_major / balanced / en_major
    source_mix: str = "balanced"
    prisma_flow: str = ""
    ablation_design: str = ""
    quality_results: list[dict[str, Any]] | None = None
    failed_sections: list[str] | None = None

    @property
    def gate_phases(self) -> set[Phase]:
        mode = self.collab_mode.value if hasattr(self.collab_mode, "value") else str(self.collab_mode)
        mapping: dict[str, set[Phase]] = {
            "full_auto": set(),
            "key_gates": {
                Phase.SCOPING, Phase.LITERATURE, Phase.CLEANING, Phase.TRENDS,
                Phase.ANGLE, Phase.OUTLINE, Phase.WRITING, Phase.VERIFICATION, Phase.EXPORT,
            },
        }
        return mapping.get(mode, set())
