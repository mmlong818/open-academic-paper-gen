"""Hand-label a sample of T1.1 uncited-claim flags to measure their precision.

    python -m evals.sample_uncited sample evals/results/<label>.json --name uncited_v1
    # set "gold" to needs_citation | no in evals/labels/uncited_v1.tolabel.jsonl
    python -m evals.sample_uncited score --name uncited_v1
    python -m evals.sample_uncited rejudge evals/results/<label>.json --name uncited_v1 --label v2
        # re-runs the current checker on the same drafts, compares with the labels, and writes
        # a held-out sample of flags nobody has labelled yet

Every row is something the checker flagged, so the sample measures precision only;
recall would need every uncited sentence labelled, flagged or not.
"""
import argparse
import asyncio
import json
import random
from pathlib import Path
from unittest.mock import patch

from backend.verification.orchestrator import prose_sentences

LABELS_DIR = Path(__file__).parent / "labels"


def sample(flagged: list[dict], n: int = 30, seed: int = 0) -> list[dict]:
    return random.Random(seed).sample(flagged, min(n, len(flagged)))


def neighbourhood(section_text: str, sentence: str, width: int = 2) -> tuple[str, str]:
    """The sentences just before and after one sentence, for the labeller's context."""
    sentences = prose_sentences(section_text)
    if sentence not in sentences:
        return "", ""
    i = sentences.index(sentence)
    return " ".join(sentences[max(0, i - width):i]), " ".join(sentences[i + 1:i + 1 + width])


def precision(rows: list[dict]) -> dict:
    labelled = [r for r in rows if r.get("gold")]
    hits = sum(1 for r in labelled if r["gold"] == "needs_citation")
    return {"labelled": len(labelled), "needs_citation": hits,
            "precision": hits / len(labelled) if labelled else None}


def compare_with_labels(labelled: list[dict], new_flags: list[dict]) -> tuple[dict, list[dict]]:
    """How many labelled true / false flags the new run still raises, plus the unlabelled rest."""
    flagged = {(f["slug"], f["sentence"]) for f in new_flags}
    labelled_keys = {(r["slug"], r["sentence"]) for r in labelled}
    true = [r for r in labelled if r.get("gold") == "needs_citation"]
    false = [r for r in labelled if r.get("gold") == "no"]
    unlabelled = [f for f in new_flags if (f["slug"], f["sentence"]) not in labelled_keys]
    return {
        "true_kept": sum((r["slug"], r["sentence"]) in flagged for r in true),
        "true_total": len(true),
        "false_kept": sum((r["slug"], r["sentence"]) in flagged for r in false),
        "false_total": len(false),
        "new_flags": len(new_flags),
        "unlabelled_flags": len(unlabelled),
    }, unlabelled


async def _recheck(runs: list[dict]) -> list[dict]:
    from backend.core.llm import fast_llm
    from backend.verification.layer3_support import SUPPORT_MAX_TOKENS
    from backend.verification.uncited import UncitedClaimChecker
    from evals.sample_l3 import _fixture_language

    checker = UncitedClaimChecker(llm=fast_llm(max_tokens=SUPPORT_MAX_TOKENS))
    flags = []
    with patch("backend.verification.uncited.settings.verify_uncited_claims", True):
        for run in runs:
            for claim in await checker.check(run["sections"], _fixture_language(run["slug"])):
                before, after = neighbourhood(run["sections"][claim.section], claim.sentence)
                flags.append({"slug": run["slug"], **claim.as_dict(), "before": before, "after": after})
    return flags


def cmd_rejudge(results_path: str, name: str, label: str, n: int, seed: int) -> None:
    from backend.verification.uncited import _is_skipped

    runs = json.loads(Path(results_path).read_text(encoding="utf-8"))["runs"]
    flags = asyncio.run(_recheck(runs))
    labelled_path = LABELS_DIR / f"{name}.tolabel.jsonl"
    labelled = [json.loads(line) for line in labelled_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    # rows in sections the checker now skips cannot be flagged again; leave them out of the comparison
    labelled = [r for r in labelled if not _is_skipped(r["section"])]
    result, unlabelled = compare_with_labels(labelled, flags)
    print(json.dumps(result, indent=2))

    holdout = [{"id": i, **r, "gold": None, "note": ""} for i, r in enumerate(sample(unlabelled, n, seed), 1)]
    out = LABELS_DIR / f"{name}-{label}-holdout.tolabel.jsonl"
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in holdout), encoding="utf-8")
    print(f"held-out sample of {len(holdout)} unlabelled flags -> {out}")


def cmd_sample(results_path: str, name: str, n: int, seed: int) -> None:
    results = json.loads(Path(results_path).read_text(encoding="utf-8"))
    flagged = []
    for run in results["runs"]:
        for claim in run.get("uncited_claims", []):
            before, after = neighbourhood(run["sections"].get(claim["section"], ""), claim["sentence"])
            flagged.append({"slug": run["slug"], **claim, "before": before, "after": after})
    rows = [{"id": i, **r, "gold": None, "note": ""} for i, r in enumerate(sample(flagged, n, seed), 1)]
    LABELS_DIR.mkdir(exist_ok=True)
    out = LABELS_DIR / f"{name}.tolabel.jsonl"
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"sampled {len(rows)} of {len(flagged)} flags -> {out}  (gold = needs_citation | no)")


def cmd_score(name: str) -> None:
    path = LABELS_DIR / f"{name}.tolabel.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(json.dumps(precision(rows), indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("results")
    s.add_argument("--name", required=True)
    s.add_argument("--n", type=int, default=30)
    s.add_argument("--seed", type=int, default=0)
    c = sub.add_parser("score")
    c.add_argument("--name", required=True)
    j = sub.add_parser("rejudge")
    j.add_argument("results")
    j.add_argument("--name", required=True)
    j.add_argument("--label", required=True)
    j.add_argument("--n", type=int, default=20)
    j.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    if args.cmd == "sample":
        cmd_sample(args.results, args.name, args.n, args.seed)
    elif args.cmd == "score":
        cmd_score(args.name)
    else:
        cmd_rejudge(args.results, args.name, args.label, args.n, args.seed)


if __name__ == "__main__":
    main()
