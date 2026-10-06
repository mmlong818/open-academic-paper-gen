"""Hand-label a sample of simulated-review comments: is each a real, specific problem?

    python -m evals.sample_review sample evals/results/<label>.json --name review_v1
    # set "gold" to valid | invalid in evals/labels/review_v1.tolabel.jsonl
    python -m evals.sample_review score --name review_v1
"""
import argparse
import json
import random
import re
from pathlib import Path

LABELS_DIR = Path(__file__).parent / "labels"


def sample(comments: list[dict], n: int = 20, seed: int = 0) -> list[dict]:
    return random.Random(seed).sample(comments, min(n, len(comments)))


def context_of(text: str, quote: str, width: int = 400) -> tuple[str, str]:
    squashed = re.sub(r"\s+", " ", text)
    i = squashed.find(quote)
    if i < 0:
        return "", ""
    return squashed[max(0, i - width):i], squashed[i + len(quote):i + len(quote) + width]


def precision(rows: list[dict]) -> dict:
    labelled = [r for r in rows if r.get("gold")]
    valid = sum(1 for r in labelled if r["gold"] == "valid")
    return {"labelled": len(labelled), "valid": valid,
            "precision": valid / len(labelled) if labelled else None}


def cmd_sample(results_path: str, name: str, n: int, seed: int) -> None:
    runs = json.loads(Path(results_path).read_text(encoding="utf-8"))["runs"]
    comments = []
    for run in runs:
        for c in (run.get("review") or {}).get("comments", []):
            before, after = context_of(run["sections"].get(c["section"], ""), c["quote"])
            comments.append({"slug": run["slug"], **c, "before": before, "after": after})
    rows = [{"id": i, **c, "gold": None, "note": ""} for i, c in enumerate(sample(comments, n, seed), 1)]
    LABELS_DIR.mkdir(exist_ok=True)
    out = LABELS_DIR / f"{name}.tolabel.jsonl"
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"sampled {len(rows)} of {len(comments)} comments -> {out}  (gold = valid | invalid)")


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
    s.add_argument("--n", type=int, default=20)
    s.add_argument("--seed", type=int, default=0)
    c = sub.add_parser("score")
    c.add_argument("--name", required=True)
    args = parser.parse_args()
    if args.cmd == "sample":
        cmd_sample(args.results, args.name, args.n, args.seed)
    else:
        cmd_score(args.name)


if __name__ == "__main__":
    main()
