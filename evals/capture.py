"""Capture eval fixtures: run the live pipeline from scoping up to, not including, writing.

    python -m evals.capture                 # every topic in evals/topics.json
    python -m evals.capture --only gnn-molecules

Retrieval results drift from day to day; freezing everything before writing lets replays
compare writing and verification changes against the same literature pool.
"""
import argparse
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.pipeline import graph
from backend.pipeline.states import PaperState
from evals.harness import count_usage, offline, run_nodes
from evals.util import git_commit

EVALS_DIR = Path(__file__).parent
FIXTURES_DIR = EVALS_DIR / "fixtures"

PRE_WRITING = [
    graph.node_scoping, graph.node_literature, graph.node_cleaning, graph.node_prisma,
    graph.node_trends, graph.node_angle, graph.node_outline, graph.node_ablation,
]


async def capture(topic: dict) -> Path:
    state = PaperState(
        task_id=str(uuid.uuid4()), topic=topic["topic"], language=topic["language"],
        collab_mode="full_auto", paper_type=topic["paper_type"],
    )
    with offline(), count_usage() as usage:
        state = await run_nodes(state, PRE_WRITING)

    FIXTURES_DIR.mkdir(exist_ok=True)
    path = FIXTURES_DIR / f"{topic['slug']}.json"
    payload = {
        "meta": {**topic, "captured_at": datetime.now(timezone.utc).isoformat(),
                 "git_commit": git_commit(), "usage": usage.as_dict()},
        "state": state.model_dump(mode="json"),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[capture] {topic['slug']}: literature={len(state.literature)} "
          f"outline={len(state.outline)} errors={len(state.errors)} llm_calls={usage.calls} -> {path}")
    return path


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", nargs="*", help="topic slugs to capture")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    topics = json.loads((EVALS_DIR / "topics.json").read_text(encoding="utf-8"))
    if args.only:
        topics = [t for t in topics if t["slug"] in args.only]
    for topic in topics:
        try:
            await capture(topic)
        except Exception as exc:  # one bad topic must not sink the rest of the batch
            print(f"[capture] {topic['slug']} FAILED: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
