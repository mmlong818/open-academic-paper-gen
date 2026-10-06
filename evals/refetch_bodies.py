"""Re-run full-text fetching on existing fixtures without re-running retrieval or writing.

    python -m evals.refetch_bodies            # every fixture in evals/fixtures/
    python -m evals.refetch_bodies --only gnn-molecules

A full capture takes hours and redraws the literature pool; when only the fetcher changed,
refreshing the body excerpts of the same pool isolates that change.
"""
import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from backend.literature.content_fetcher import PaperContentFetcher
from backend.literature.schemas import LiteratureItem
from backend.verification.evidence import evidence_kind
from evals.util import git_commit

FIXTURES_DIR = Path(__file__).parent / "fixtures"


async def refetch(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = [LiteratureItem(**lit) for lit in data["state"]["literature"]]
    before = sum(evidence_kind(i) != "abstract" for i in items)
    fresh = await PaperContentFetcher().run([i.model_copy(update={"body_excerpt": ""}) for i in items])
    after = sum(evidence_kind(i) != "abstract" for i in fresh)
    data["state"]["literature"] = [i.model_dump(mode="json", exclude={"raw"}) for i in fresh]
    data["meta"]["bodies_refetched"] = {"at": datetime.now(timezone.utc).isoformat(), "git_commit": git_commit()}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[refetch] {path.stem}: body excerpts {before} -> {after} of {len(items)}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", nargs="*")
    args = parser.parse_args()
    paths = sorted(FIXTURES_DIR.glob("*.json"))
    if args.only:
        paths = [p for p in paths if p.stem in args.only]
    for path in paths:
        await refetch(path)


if __name__ == "__main__":
    asyncio.run(main())
