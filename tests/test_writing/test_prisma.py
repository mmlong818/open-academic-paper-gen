"""The PRISMA flow reports what the pipeline actually did; it never removes papers itself."""
from backend.writing.prisma import build_prisma_flow

REPORT = {"total_before": 146, "total_after": 96, "removed_dup": 10, "excluded_by_llm": 38}


def test_flow_counts_come_from_the_cleaning_report():
    flow = build_prisma_flow(REPORT, included=96, language="en")
    assert "Records identified through database searching: 146" in flow
    assert "Duplicates removed: 10" in flow
    assert "Records screened (title/abstract): 136" in flow
    assert "Records excluded at relevance screening: 38" in flow
    assert "Studies included: 96" in flow


def test_records_dropped_by_other_rules_are_reported_not_hidden():
    flow = build_prisma_flow(REPORT, included=96, language="en")
    # 146 - 10 - 38 = 98 screened in, 96 kept: 2 went to other cleaning rules
    assert "Other records removed during cleaning: 2" in flow


def test_chinese_flow():
    flow = build_prisma_flow(REPORT, included=96, language="zh")
    assert "数据库检索识别记录：146" in flow and "最终纳入研究：96" in flow


def test_no_report_no_flow():
    assert build_prisma_flow(None, included=10, language="en") == ""


def test_citation_chaining_is_its_own_identification_source():
    report = {"total_before": 100, "removed_dup": 5, "excluded_by_llm": 30,
              "chained_candidates": 40, "chained_included": 25}
    flow = build_prisma_flow(report, included=105, language="en")
    assert "Additional records identified through citation chaining: 40" in flow
    assert "Records screened (title/abstract): 135" in flow  # 100 - 5 + 40
    assert "Studies included: 105" in flow
    assert "Other records removed" not in flow
