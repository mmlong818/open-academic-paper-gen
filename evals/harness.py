"""Run pipeline nodes outside the web app: no database, no progress bus.

The eval scripts call node functions from backend.pipeline.graph directly, so they
see exactly what production runs, minus the persistence side effects.
"""
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from unittest.mock import AsyncMock, patch

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.tracers.context import register_configure_hook

from backend.pipeline.states import PaperState
from backend.verification.evidence import evidence_kind
from backend.verification.layer3_support import SupportChecker
from backend.verification.uncited import UncitedClaimChecker

Node = Callable[[PaperState], Awaitable[dict]]


class UsageCounter(BaseCallbackHandler):
    """Counts LLM calls and tokens per model for every call made while installed."""

    run_inline = True

    def __init__(self) -> None:
        self.calls = 0
        self.by_model: dict[str, dict[str, int]] = {}

    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        self.calls += 1
        model = (response.llm_output or {}).get("model_name") or "unknown"
        tokens = self.by_model.setdefault(model, {"calls": 0, "input": 0, "output": 0})
        tokens["calls"] += 1
        for generations in response.generations:
            for gen in generations:
                usage = getattr(getattr(gen, "message", None), "usage_metadata", None) or {}
                tokens["input"] += usage.get("input_tokens", 0)
                tokens["output"] += usage.get("output_tokens", 0)

    def as_dict(self) -> dict:
        return {"llm_calls": self.calls, "by_model": self.by_model}


_usage_var: ContextVar[UsageCounter | None] = ContextVar("eval_usage_counter", default=None)
register_configure_hook(_usage_var, inheritable=True)


@contextmanager
def count_usage() -> Iterator[UsageCounter]:
    counter = UsageCounter()
    token = _usage_var.set(counter)
    try:
        yield counter
    finally:
        _usage_var.reset(token)


@contextmanager
def offline() -> Iterator[None]:
    """Silence the DB snapshot writes and websocket progress the nodes emit."""
    no_op = AsyncMock(return_value=None)
    with (
        patch("backend.pipeline.graph._save_phase_result", no_op),
        patch("backend.pipeline.graph._save_snapshot_only", no_op),
        patch("backend.pipeline.graph.publish_progress", no_op),
    ):
        yield


@contextmanager
def record_support_verdicts() -> Iterator[list[dict]]:
    """Capture every layer-3 verdict, including supported and unclear ones.

    The orchestrator keeps only unsupported claims in its issue text; the eval needs
    the full set as the denominator and as the pool for hand-labelling.
    """
    records: list[dict] = []
    original = SupportChecker.check
    passes = 0

    async def spy(self, claims_by_key, key_to_item, language="en"):
        # full_auto verifies twice when it applies revisions: before and after
        nonlocal passes
        this_pass, passes = passes, passes + 1
        judged = await original(self, claims_by_key, key_to_item, language)
        for key, verdicts in judged.items():
            evidence = evidence_kind(key_to_item[key])
            records.extend(
                {"key": key, "sentence": v.claim.sentence, "context": v.claim.context,
                 "verdict": v.verdict, "reason": v.reason, "evidence": evidence, "pass": this_pass}
                for v in verdicts
            )
        return judged

    with patch.object(SupportChecker, "check", spy):
        yield records


@contextmanager
def record_uncited() -> Iterator[list[list[dict]]]:
    """Capture the uncited claims each verification pass reported, one list per pass."""
    passes: list[list[dict]] = []
    original = UncitedClaimChecker.check

    async def spy(self, sections, language="en"):
        claims = await original(self, sections, language)
        passes.append([c.as_dict() for c in claims])
        return claims

    with patch.object(UncitedClaimChecker, "check", spy):
        yield passes


async def run_nodes(state: PaperState, nodes: list[Node]) -> PaperState:
    """Apply nodes in order the way LangGraph would, with `errors` appended, not replaced."""
    for node in nodes:
        updates = await node(state)
        errors = state.errors + list(updates.pop("errors", []))
        state = state.model_copy(update={**updates, "errors": errors})
    return state
