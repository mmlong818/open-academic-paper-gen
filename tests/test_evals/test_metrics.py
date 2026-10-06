from evals.metrics import (
    aggregate,
    citation_metrics,
    compare,
    support_metrics,
    verification_metrics,
)


def test_citation_metrics_counts_hallucinated_keys_and_uncited_sections():
    sections = {
        "Intro": "A holds [cite:a2020]. B holds [cite:ghost1999].",
        "Method": "C holds [cite:a2020] and [cite:b2021].",
        "Outlook": "No citations here.",
    }
    m = citation_metrics(sections, pool_keys={"a2020", "b2021"})
    assert m["cited_keys"] == 3
    assert m["hallucinated_keys"] == 1
    assert m["sections_total"] == 3
    assert m["sections_without_citation"] == 1
    # distinct keys per section: 2, 2, 0
    assert m["median_citations_per_section"] == 2


def test_citation_metrics_on_empty_draft():
    m = citation_metrics({}, pool_keys=set())
    assert m["cited_keys"] == 0
    assert m["median_citations_per_section"] == 0


def test_support_metrics_rate_is_over_judged_claims():
    records = [
        {"key": "a", "verdict": "supported"},
        {"key": "a", "verdict": "unsupported"},
        {"key": "b", "verdict": "unclear"},
        {"key": "c", "verdict": "unsupported"},
    ]
    m = support_metrics(records)
    assert m["claims_judged"] == 4
    assert m["claims_unsupported"] == 2
    assert m["claims_unclear"] == 1
    assert m["papers_judged"] == 3
    assert m["papers_with_unsupported"] == 2


def test_verification_metrics_counts_actions():
    issues = [
        {"layer": "layer0", "action": "removed"},
        {"layer": "layer1", "action": "removed"},
        {"layer": "layer1+layer3", "action": "warned"},
        {"layer": "layer3", "action": "warned"},
        {"layer": "layer1", "action": "kept"},
    ]
    m = verification_metrics(issues)
    assert m["issues_removed"] == 2
    assert m["issues_warned"] == 2
    assert m["issues_kept"] == 1
    assert m["warned_by_layer3"] == 2


def test_aggregate_sums_counts_and_recomputes_rates_from_sums():
    runs = [
        {"cited_keys": 10, "hallucinated_keys": 1, "claims_judged": 4, "claims_unsupported": 2},
        {"cited_keys": 30, "hallucinated_keys": 0, "claims_judged": 16, "claims_unsupported": 0},
    ]
    agg = aggregate(runs)
    assert agg["cited_keys"] == 40
    # micro-average, not the mean of per-run rates (0.05 and 0.5 would average to 0.275)
    assert agg["hallucinated_key_rate"] == 1 / 40
    assert agg["unsupported_rate"] == 2 / 20


def test_aggregate_rates_are_none_without_denominator():
    agg = aggregate([{"cited_keys": 0, "hallucinated_keys": 0}])
    assert agg["hallucinated_key_rate"] is None


def test_compare_reports_delta_for_shared_numeric_metrics():
    rows = compare({"cited_keys": 40, "unsupported_rate": 0.1, "note": "x"},
                   {"cited_keys": 44, "unsupported_rate": 0.05})
    by_name = {r["metric"]: r for r in rows}
    assert by_name["cited_keys"]["delta"] == 4
    assert abs(by_name["unsupported_rate"]["delta"] - (-0.05)) < 1e-9
    assert "note" not in by_name


def test_support_metrics_split_unclear_by_evidence_type():
    records = [
        {"key": "a", "verdict": "unclear", "evidence": "abstract"},
        {"key": "a", "verdict": "supported", "evidence": "abstract"},
        {"key": "b", "verdict": "unclear", "evidence": "body"},
        {"key": "c", "verdict": "supported", "evidence": "body"},
        {"key": "c", "verdict": "supported", "evidence": "body"},
    ]
    m = support_metrics(records)
    assert m["claims_on_abstract"] == 2
    assert m["claims_unclear_on_abstract"] == 1
    assert m["claims_on_body"] == 3
    assert m["claims_unclear_on_body"] == 1


def test_verification_metrics_count_issue_stages():
    issues = [
        {"layer": "layer0", "action": "removed", "stage": "writing"},
        {"layer": "layer3", "action": "warned", "stage": "writing"},
        {"layer": "layer1+layer3", "action": "warned", "stage": "retrieval+writing"},
        {"layer": "layer1", "action": "kept", "stage": ""},
    ]
    m = verification_metrics(issues)
    assert m["issues_from_writing"] == 3
    assert m["issues_from_retrieval"] == 1


def test_aggregate_recomputes_unclear_rate_per_evidence_type():
    agg = aggregate([
        {"claims_on_abstract": 10, "claims_unclear_on_abstract": 5,
         "claims_on_body": 10, "claims_unclear_on_body": 1},
        {"claims_on_abstract": 10, "claims_unclear_on_abstract": 3,
         "claims_on_body": 30, "claims_unclear_on_body": 3},
    ])
    assert agg["unclear_rate_on_abstract"] == 8 / 20
    assert agg["unclear_rate_on_body"] == 4 / 40


def test_revision_metrics_count_each_outcome():
    from evals.metrics import revision_metrics

    revisions = [
        {"status": "applied", "resolved": True},
        {"status": "applied", "resolved": False},
        {"status": "rejected", "resolved": None},
        {"status": "proposed", "resolved": None},
    ]
    assert revision_metrics(revisions) == {
        "revisions": 4, "revisions_applied": 2, "revisions_rejected": 1, "revisions_resolved": 1,
    }


def test_structure_metrics_measure_theme_coverage_and_section_cohesion():
    from evals.metrics import structure_metrics

    taxonomy = [{"id": 1, "keys": ["a1", "a2", "a3"]}, {"id": 2, "keys": ["b1", "b2"]}, {"id": 3, "keys": ["c1"]}]
    sections = {
        "Group A": "x [cite:a1] y [cite:a2] z [cite:a3] w [cite:b1].",  # 3 of 4 from group 1
        "Group B": "x [cite:b1] y [cite:b2] z [cite:a1].",              # 2 of 3 from group 2
        "Short": "only [cite:c1].",                                     # under 3 citations: not scored
    }
    m = structure_metrics(sections, taxonomy)
    assert m["theme_groups"] == 3
    assert m["themes_cited"] == 3
    assert abs(m["section_cohesion"] - (0.75 + 2 / 3) / 2) < 1e-9


def test_structure_metrics_without_taxonomy_are_empty():
    from evals.metrics import structure_metrics

    assert structure_metrics({"S": "[cite:a]"}, None) == {}


def test_aggregate_averages_cohesion_over_the_runs_that_have_it():
    agg = aggregate([{"section_cohesion": 0.6}, {"section_cohesion": 0.8}, {"cited_keys": 3}])
    assert abs(agg["section_cohesion"] - 0.7) < 1e-9
