"""Hand-label a sample of layer-3 verdicts to measure its precision and recall.

    python -m evals.sample_l3 sample evals/results/baseline.json --name l3_baseline
    # fill in "gold" in evals/labels/l3_baseline.tolabel.jsonl
    python -m evals.sample_l3 score --name l3_baseline
    python -m evals.sample_l3 rejudge --name l3_baseline --label v2   # current prompt vs the same gold
    python -m evals.sample_l3 rejudge --name l3_baseline --label v3 --fine   # with partial / misaligned
    python -m evals.sample_l3 grades --name l3_baseline --label v3   # against <name>.gold5.jsonl

Labelling is blind: the file to label carries no model verdict; predictions sit in a
separate answer file joined by id at scoring time.

Unsupported verdicts are over-sampled (they are rare but the costly kind of error), so
precision is estimated well; recall on this sample is biased upward and is reported
alongside the stratum sizes so it is not over-read.
"""
import argparse
import asyncio
import json
import random
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from backend.literature.bibtex import bibtex_key
from backend.literature.schemas import LiteratureItem
from backend.verification.evidence import select_evidence
from backend.verification.layer3_support import (
    _MAX_EVIDENCE_CHARS,
    SUPPORT_MAX_TOKENS,
    WARNS,
    Claim,
    SupportChecker,
)

VERDICTS = ("supported", "unsupported", "unclear")
LABELS_DIR = Path(__file__).parent / "labels"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def stratified_sample(records: list[dict], n: int = 50, max_unsupported: int = 20,
                      seed: int = 0) -> list[dict]:
    rng = random.Random(seed)
    unsupported = [r for r in records if r["verdict"] == "unsupported"]
    others = [r for r in records if r["verdict"] != "unsupported"]
    picked = rng.sample(unsupported, min(len(unsupported), max_unsupported))
    picked += rng.sample(others, min(len(others), n - len(picked)))
    return picked


def score(predictions: dict[int, str], gold: dict[int, str | None]) -> dict:
    pairs = [(predictions[i], g) for i, g in gold.items() if g and i in predictions]
    confusion = {p: {g: 0 for g in VERDICTS} for p in VERDICTS}
    for pred, g in pairs:
        confusion[pred][g] += 1

    hits = confusion["unsupported"]["unsupported"]
    predicted = sum(confusion["unsupported"].values())
    actual = sum(confusion[p]["unsupported"] for p in VERDICTS)
    return {
        "labelled": len(pairs),
        "agreement": sum(1 for p, g in pairs if p == g) / len(pairs) if pairs else None,
        "unsupported_precision": hits / predicted if predicted else None,
        "unsupported_recall": hits / actual if actual else None,
        "predicted_unsupported": predicted,
        "gold_unsupported": actual,
        "confusion": confusion,
    }


def _share(hits: int, total: int) -> float | None:
    return hits / total if total else None


def score_grades(predictions: dict[int, str], gold5: dict[int, str]) -> dict:
    """Score against five-grade gold: warnings (unsupported or misaligned) and partial, each on its own.

    A three-grade run scores here too, so a baseline and a fine-grade run meet on the same gold.
    """
    pairs = [(predictions[i], g) for i, g in gold5.items() if g and i in predictions]
    warn_hits = sum(1 for p, g in pairs if p in WARNS and g in WARNS)
    partial_hits = sum(1 for p, g in pairs if p == g == "partial")
    return {
        "labelled": len(pairs),
        "agreement": _share(sum(1 for p, g in pairs if p == g), len(pairs)),
        "warn_precision": _share(warn_hits, sum(1 for p, _ in pairs if p in WARNS)),
        "warn_recall": _share(warn_hits, sum(1 for _, g in pairs if g in WARNS)),
        "predicted_warn": sum(1 for p, _ in pairs if p in WARNS),
        "gold_warn": sum(1 for _, g in pairs if g in WARNS),
        "partial_precision": _share(partial_hits, sum(1 for p, _ in pairs if p == "partial")),
        "partial_recall": _share(partial_hits, sum(1 for _, g in pairs if g == "partial")),
    }


def _items_by_key(fixture_path: str) -> dict[str, LiteratureItem]:
    data = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
    out = {}
    for lit in data["state"]["literature"]:
        try:
            item = LiteratureItem(**lit)
        except ValidationError:
            continue  # malformed pool entries are skipped the same way graph.py skips them
        out[bibtex_key(item)] = item
    return out


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _shown_evidence(item: LiteratureItem | None, verdict: dict) -> tuple[str, str]:
    """(title, the evidence layer 3 would show for this one claim) - what the labeller sees."""
    if item is None:
        return "", ""
    claim = Claim(key=verdict["key"], sentence=verdict["sentence"], context=verdict["context"])
    return item.title, select_evidence(item, [claim], budget=_MAX_EVIDENCE_CHARS)


def cmd_sample(results_path: str, name: str, n: int, seed: int, before_revision: bool = False) -> None:
    results = json.loads(Path(results_path).read_text(encoding="utf-8"))
    field = "verdicts_before_revision" if before_revision else "verdicts"
    pool = []
    for run in results["runs"]:
        if field not in run:
            continue
        items = _items_by_key(run["fixture"])
        pool.extend({**v, "slug": run["slug"], "_ev": _shown_evidence(items.get(v["key"]), v)}
                    for v in run[field])

    picked = stratified_sample(pool, n=n, seed=seed)
    random.Random(seed).shuffle(picked)  # do not let file order leak the stratum
    to_label = [
        {"id": i, "slug": r["slug"], "key": r["key"], "title": r["_ev"][0],
         "context": r["context"], "sentence": r["sentence"], "evidence": r["_ev"][1],
         "gold": None, "note": ""}
        for i, r in enumerate(picked, 1)
    ]
    answers = [{"id": i, "verdict": r["verdict"], "reason": r["reason"]}
               for i, r in enumerate(picked, 1)]

    LABELS_DIR.mkdir(exist_ok=True)
    _write_jsonl(LABELS_DIR / f"{name}.tolabel.jsonl", to_label)
    _write_jsonl(LABELS_DIR / f"{name}.answers.jsonl", answers)
    strata = {v: sum(1 for r in picked if r["verdict"] == v) for v in VERDICTS}
    print(f"sampled {len(picked)} of {len(pool)} verdicts; strata={strata}")
    print(f"label: {LABELS_DIR / (name + '.tolabel.jsonl')}  (gold = supported|unsupported|unclear)")


def cmd_score(name: str) -> None:
    labelled = _read_jsonl(LABELS_DIR / f"{name}.tolabel.jsonl")
    answers = _read_jsonl(LABELS_DIR / f"{name}.answers.jsonl")
    result = score({a["id"]: a["verdict"] for a in answers},
                   {r["id"]: r.get("gold") for r in labelled})
    print(json.dumps(result, indent=2, ensure_ascii=False))


async def rejudge(rows: list[dict], llm, language_of: Callable[[str], str]) -> dict[int, str]:
    """Re-run layer 3 on labelled rows through the production SupportChecker.

    Rows citing the same paper are batched together, as production batches claims per key.
    A key that yields no verdict (thin evidence, LLM error) counts as unclear.
    """
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        groups.setdefault((r["slug"], r["key"]), []).append(r)

    checker = SupportChecker(llm=llm)
    predictions: dict[int, str] = {}
    for (slug, key), group in groups.items():
        item = LiteratureItem(title=group[0]["title"] or key, source="upload", abstract=group[0]["evidence"])
        claims = [Claim(key=key, sentence=r["sentence"], context=r["context"]) for r in group]
        verdicts = (await checker.check({key: claims}, {key: item}, language_of(slug))).get(key, [])
        for i, r in enumerate(group):
            predictions[r["id"]] = verdicts[i].verdict if i < len(verdicts) else "unclear"
    return predictions


def _fixture_language(slug: str) -> str:
    data = json.loads((FIXTURES_DIR / f"{slug}.json").read_text(encoding="utf-8"))
    return data["state"]["language"]


def cmd_grades(name: str, label: str) -> None:
    gold5 = {r["id"]: r["gold5"] for r in _read_jsonl(LABELS_DIR / f"{name}.gold5.jsonl")}
    predictions = {r["id"]: r["verdict"] for r in _read_jsonl(LABELS_DIR / f"{name}.rejudge-{label}.jsonl")}
    print(json.dumps(score_grades(predictions, gold5), indent=2, ensure_ascii=False))


def cmd_rejudge(name: str, label: str, fine: bool = False) -> None:
    from backend.core.config import settings
    from backend.core.llm import fast_llm

    settings.l3_fine_grades = fine

    rows = [r for r in _read_jsonl(LABELS_DIR / f"{name}.tolabel.jsonl") if r.get("gold")]
    predictions = asyncio.run(rejudge(rows, fast_llm(max_tokens=SUPPORT_MAX_TOKENS), _fixture_language))
    _write_jsonl(LABELS_DIR / f"{name}.rejudge-{label}.jsonl",
                 [{"id": i, "verdict": v} for i, v in sorted(predictions.items())])
    # the three-grade gold knows no partial or misaligned: fold them into their nearest grade
    folded = {i: {"partial": "supported", "misaligned": "unsupported"}.get(v, v) for i, v in predictions.items()}
    print(json.dumps(score(folded, {r["id"]: r["gold"] for r in rows}), indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("results")
    s.add_argument("--name", required=True)
    s.add_argument("--n", type=int, default=50)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--before-revision", action="store_true",
                   help="sample the first verification pass, whose verdicts drove the revisions")
    c = sub.add_parser("score")
    c.add_argument("--name", required=True)
    j = sub.add_parser("rejudge")
    j.add_argument("--name", required=True)
    j.add_argument("--label", required=True)
    j.add_argument("--fine", action="store_true", help="also grade partial and misaligned support")
    g = sub.add_parser("grades")
    g.add_argument("--name", required=True)
    g.add_argument("--label", required=True)
    args = parser.parse_args()
    if args.cmd == "sample":
        cmd_sample(args.results, args.name, args.n, args.seed, args.before_revision)
    elif args.cmd == "score":
        cmd_score(args.name)
    elif args.cmd == "grades":
        cmd_grades(args.name, args.label)
    else:
        cmd_rejudge(args.name, args.label, args.fine)


if __name__ == "__main__":
    main()
