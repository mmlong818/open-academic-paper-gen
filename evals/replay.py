"""Replay fixtures through writing -> verification -> export and score the result.

    python -m evals.replay --label baseline
    python -m evals.replay --label rerank --compare evals/results/baseline.json

Each run writes evals/results/<label>.json: per-topic metrics, aggregate metrics,
every layer-3 verdict (the pool for evals.sample_l3), sections and citation issues.
"""
import argparse
import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from backend.literature.bibtex import bibtex_key
from backend.literature.schemas import LiteratureItem
from backend.pipeline import graph
from backend.pipeline.states import GateStatus, PaperState, Phase
from evals.harness import (
    count_usage,
    offline,
    record_support_verdicts,
    record_uncited,
    run_nodes,
)
from evals.metrics import (
    aggregate,
    citation_metrics,
    compare,
    revision_metrics,
    structure_metrics,
    support_metrics,
    verification_metrics,
    with_rates,
)
from evals.util import git_commit

EVALS_DIR = Path(__file__).parent
RESULTS_DIR = EVALS_DIR / "results"
POST_OUTLINE = [graph.node_writing, graph.node_verification, graph.node_export]
FROM_OUTLINE = [graph.node_outline, graph.node_ablation, *POST_OUTLINE]

# Everything from writing onwards is recomputed; a fixture never carries it forward.
_RESET = {
    "current_phase": Phase.WRITING, "gate_status": GateStatus.SKIPPED,
    "collab_mode": "full_auto", "resume_from_phase": None,
    "sections": {}, "failed_sections": None, "verified_citations": None,
    "citation_issues": None, "uncited_claims": None, "revisions": None, "review": None,
    "quality_results": None, "smart_pause": False,
    "latex_content": "", "markdown_content": "", "errors": [],
}


def load_fixture(path: Path, from_outline: bool = False) -> PaperState:
    data = json.loads(path.read_text(encoding="utf-8"))
    reset = {**_RESET, "current_phase": Phase.OUTLINE, "outline": [], "taxonomy": None} if from_outline else _RESET
    return PaperState(**{**data["state"], **reset})


def _pool_keys(literature: list[dict]) -> set[str]:
    keys = set()
    for lit in literature:
        try:
            keys.add(bibtex_key(LiteratureItem(**lit)))
        except ValidationError:
            continue  # malformed pool entries are skipped the same way graph.py skips them
    return keys


async def _with_evidence_table(state: PaperState, path: Path) -> PaperState:
    """Fixtures predate the evidence table: build it once per fixture and cache it beside them."""
    from backend.core.config import settings
    from backend.core.llm import fast_llm
    from backend.writing.evidence_table import EVIDENCE_MAX_TOKENS, EvidenceExtractor

    if not settings.evidence_table_in_writing or state.evidence_table:
        return state
    cache = EVALS_DIR / "fixtures" / "evidence" / f"{path.stem}.json"
    if cache.exists():
        rows = json.loads(cache.read_text(encoding="utf-8"))
    else:
        items = []
        for lit in state.literature:
            try:
                items.append(LiteratureItem(**lit))
            except ValidationError:
                continue
        rows = await EvidenceExtractor(fast_llm(max_tokens=EVIDENCE_MAX_TOKENS)).run(items, state.language)
        cache.parent.mkdir(exist_ok=True)
        cache.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return state.model_copy(update={"evidence_table": rows})


async def replay_one(path: Path, from_outline: bool = False) -> dict:
    state = await _with_evidence_table(load_fixture(path, from_outline), path)
    # The uncited-claim check ships disabled until measured; the eval is where it gets measured.
    with (
        offline(), count_usage() as usage, record_support_verdicts() as verdicts,
        record_uncited() as uncited_passes,
        patch("backend.verification.uncited.settings.verify_uncited_claims", True),
    ):
        final = await run_nodes(state, FROM_OUTLINE if from_outline else POST_OUTLINE)

    issues = final.citation_issues or []
    uncited = final.uncited_claims or []
    last = max((v["pass"] for v in verdicts), default=0)
    final_verdicts = [v for v in verdicts if v["pass"] == last]
    first_verdicts = [v for v in verdicts if v["pass"] == 0]
    metrics = with_rates({
        **citation_metrics(final.sections, _pool_keys(final.literature)),
        **support_metrics(final_verdicts),
        **verification_metrics(issues),
        **revision_metrics(final.revisions or []),
        **structure_metrics(final.sections, await _structure_taxonomy(final)),
        "claims_unsupported_before_revision": sum(v["verdict"] == "unsupported" for v in first_verdicts),
        "uncited_before_revision": len(uncited_passes[0]) if uncited_passes else 0,
        "review_comments": len((final.review or {}).get("comments", [])),
        "review_limitations": len((final.review or {}).get("limitations", [])),
        "review_dropped_unquoted": (final.review or {}).get("dropped_unquoted", 0),
        "failed_sections": len(final.failed_sections or []),
        "uncited_claims": len(uncited),
        "llm_calls": usage.calls,
    })
    return {
        "slug": path.stem, "fixture": str(path), "metrics": metrics, "usage": usage.as_dict(),
        "verdicts": final_verdicts, "verdicts_before_revision": first_verdicts,
        "citation_issues": issues, "uncited_claims": uncited, "revisions": final.revisions or [],
        "review": final.review,
        "sections": final.sections,
        "errors": final.errors,
    }


async def _structure_taxonomy(final: PaperState) -> list[dict] | None:
    """The groups structure is measured against; the same for runs with and without graph outlines."""
    if final.paper_type != "review":
        return None
    if final.taxonomy:
        return final.taxonomy
    from backend.literature.citation_graph import build_taxonomy

    items = []
    for lit in final.literature:
        try:
            items.append(LiteratureItem(**lit))
        except ValidationError:
            continue
    return await build_taxonomy(items) or None


def _fmt(value) -> str:
    if value is None:
        return "-"
    return f"{value:.3f}" if isinstance(value, float) else str(value)


def print_table(rows: list[dict], columns: list[str]) -> None:
    widths = [max(len(c), *(len(_fmt(r.get(c))) for r in rows)) for c in columns]
    print("  ".join(c.ljust(w) for c, w in zip(columns, widths)))
    for r in rows:
        print("  ".join(_fmt(r.get(c)).ljust(w) for c, w in zip(columns, widths)))


def apply_overrides(pairs: list[str]) -> dict:
    """Set backend settings from KEY=VALUE strings, parsed to the type of the current value."""
    from backend.core.config import settings

    applied = {}
    for pair in pairs:
        key, _, raw = pair.partition("=")
        current = getattr(settings, key)  # an unknown key fails loudly
        value = raw.lower() in ("1", "true", "yes") if isinstance(current, bool) else type(current)(raw)
        setattr(settings, key, value)
        applied[key] = value
    return applied


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("fixtures", nargs="*", help="fixture files (default: evals/fixtures/*.json)")
    parser.add_argument("--label", default=datetime.now().astimezone().strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--compare", help="an earlier results file to diff against")
    parser.add_argument("--from-outline", action="store_true",
                        help="regenerate the outline too, not only writing onwards")
    parser.add_argument("--only", nargs="*", help="fixture slugs to replay")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                        help="override a setting for this run, e.g. --set rerank_section_papers=true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    overrides = apply_overrides(args.set)

    paths = [Path(p) for p in args.fixtures] or sorted((EVALS_DIR / "fixtures").glob("*.json"))
    if args.only:
        paths = [p for p in paths if p.stem in args.only]
    if not paths:
        raise SystemExit("no fixtures; run `python -m evals.capture` first")

    runs = []
    for path in paths:
        try:
            runs.append(await replay_one(path, args.from_outline))
            print(f"[replay] {path.stem}: done")
        except Exception as exc:
            runs.append({"slug": path.stem, "fixture": str(path),
                         "failed": f"{type(exc).__name__}: {exc}"})
            print(f"[replay] {path.stem} FAILED: {type(exc).__name__}: {exc}")

    scored = [r for r in runs if "metrics" in r]
    summary = aggregate([r["metrics"] for r in scored])
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"{args.label}.json"
    out.write_text(json.dumps({
        "meta": {"label": args.label, "git_commit": git_commit(), "overrides": overrides,
                 "from_outline": args.from_outline,
                 "ran_at": datetime.now(timezone.utc).isoformat()},
        "aggregate": summary, "runs": runs,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    columns = ["slug", "cited_keys", "hallucinated_key_rate", "claims_judged",
               "unsupported_rate", "sections_without_citation",
               "median_citations_per_section", "uncited_claims", "revisions_applied",
               "revisions_resolved", "issues_removed", "llm_calls"]
    print_table([{"slug": r["slug"], **r["metrics"]} for r in scored]
                + [{"slug": "ALL", **summary}], columns)
    print(f"-> {out}")

    if args.compare:
        baseline = json.loads(Path(args.compare).read_text(encoding="utf-8"))["aggregate"]
        print(f"\nvs {args.compare}")
        print_table(compare(baseline, summary), ["metric", "baseline", "current", "delta"])


if __name__ == "__main__":
    asyncio.run(main())
