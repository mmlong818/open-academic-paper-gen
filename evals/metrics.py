"""Metrics over one finished pipeline run. Pure functions: no I/O, no LLM.

Rates are recomputed from summed counts when aggregating (micro-average), so a
topic with 40 citations weighs more than one with 4.
"""
from statistics import median

from backend.verification.orchestrator import extract_cite_keys

# numerator, denominator -> rate name; aggregate() rebuilds these from summed counts
_RATES = {
    "hallucinated_key_rate": ("hallucinated_keys", "cited_keys"),
    "unsupported_rate": ("claims_unsupported", "claims_judged"),
    "unclear_rate_on_abstract": ("claims_unclear_on_abstract", "claims_on_abstract"),
    "unclear_rate_on_body": ("claims_unclear_on_body", "claims_on_body"),
    "unclear_rate_on_full_text": ("claims_unclear_on_full_text", "claims_on_full_text"),
}


def citation_metrics(sections: dict[str, str], pool_keys: set[str]) -> dict:
    per_section = [extract_cite_keys(text) for text in sections.values()]
    cited = set().union(*per_section) if per_section else set()
    return {
        "cited_keys": len(cited),
        "hallucinated_keys": len(cited - pool_keys),
        "sections_total": len(sections),
        "sections_without_citation": sum(1 for keys in per_section if not keys),
        "median_citations_per_section": median(len(k) for k in per_section) if per_section else 0,
    }


def support_metrics(records: list[dict]) -> dict:
    """records: one dict per judged claim, with at least "key" and "verdict"."""
    unsupported_keys = {r["key"] for r in records if r["verdict"] == "unsupported"}
    return {
        "claims_judged": len(records),
        "claims_unsupported": sum(1 for r in records if r["verdict"] == "unsupported"),
        "claims_unclear": sum(1 for r in records if r["verdict"] == "unclear"),
        "papers_judged": len({r["key"] for r in records}),
        "papers_with_unsupported": len(unsupported_keys),
        **_by_evidence(records, "abstract"),
        **_by_evidence(records, "body"),
        **_by_evidence(records, "full_text"),
    }


def _by_evidence(records: list[dict], kind: str) -> dict:
    """Claims judged on this kind of evidence, and how many of them came back unclear.

    A high unclear rate on abstract-only evidence but not on body text says the
    bottleneck is full-text retrieval rather than the judge.
    """
    on_kind = [r for r in records if r.get("evidence") == kind]
    return {
        f"claims_on_{kind}": len(on_kind),
        f"claims_unclear_on_{kind}": sum(1 for r in on_kind if r["verdict"] == "unclear"),
    }


def verification_metrics(issues: list[dict]) -> dict:
    return {
        "issues_removed": sum(1 for i in issues if i["action"] == "removed"),
        "issues_warned": sum(1 for i in issues if i["action"] == "warned"),
        "issues_kept": sum(1 for i in issues if i["action"] == "kept"),
        "issues_unverified": sum(1 for i in issues if i["action"] == "unverified"),
        "warned_by_layer3": sum(
            1 for i in issues if i["action"] == "warned" and "layer3" in i["layer"]
        ),
        "issues_from_writing": sum(1 for i in issues if "writing" in i.get("stage", "")),
        "issues_from_retrieval": sum(1 for i in issues if "retrieval" in i.get("stage", "")),
    }


def structure_metrics(sections: dict[str, str], taxonomy: list[dict] | None) -> dict:
    """How the draft covers the pool's citation-graph groups, and how focused each section is.

    theme coverage: groups with at least one cited paper. Section cohesion: for sections citing
    three or more grouped papers, the share coming from the section's dominant group, averaged.
    """
    if not taxonomy:
        return {}
    group_of = {key: g["id"] for g in taxonomy for key in g["keys"]}
    cited = set().union(*(extract_cite_keys(t) for t in sections.values())) if sections else set()
    shares = []
    for text in sections.values():
        groups = [group_of[k] for k in extract_cite_keys(text) if k in group_of]
        if len(groups) >= 3:
            shares.append(max(groups.count(g) for g in set(groups)) / len(groups))
    return {
        "theme_groups": len(taxonomy),
        "themes_cited": len({group_of[k] for k in cited if k in group_of}),
        "section_cohesion": sum(shares) / len(shares) if shares else None,
    }


def revision_metrics(revisions: list[dict]) -> dict:
    return {
        "revisions": len(revisions),
        "revisions_applied": sum(1 for r in revisions if r["status"] in ("applied", "accepted")),
        "revisions_rejected": sum(1 for r in revisions if r["status"] == "rejected"),
        "revisions_resolved": sum(1 for r in revisions if r.get("resolved") is True),
    }


def with_rates(counts: dict) -> dict:
    out = dict(counts)
    for rate, (num, den) in _RATES.items():
        if num in counts and den in counts:
            out[rate] = counts[num] / counts[den] if counts[den] else None
    return out


# Per-run shares and medians: averaged over the runs that report them, not summed.
_AVERAGED = ("median_citations_per_section", "section_cohesion")


def aggregate(runs: list[dict]) -> dict:
    """Sum every numeric count across runs; shares and medians are averaged instead."""
    totals: dict = {}
    seen: dict = {}
    for run in runs:
        for name, value in run.items():
            if name in _RATES or isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            totals[name] = totals.get(name, 0) + value
            seen[name] = seen.get(name, 0) + 1
    for name in _AVERAGED:
        if name in totals:
            totals[name] /= seen[name]
    return with_rates(totals)


def compare(baseline: dict, current: dict) -> list[dict]:
    rows = []
    for name, base in baseline.items():
        cur = current.get(name)
        numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (base, cur))
        if numeric:
            rows.append({"metric": name, "baseline": base, "current": cur, "delta": cur - base})
    return rows
