"""Harness-independent access to eval traces: one TraceReader per harness.

    reader = reader_for(trace)  # Picked by the trace's eval.trace_reader tag
    reader.final_answer(trace)
    reader.skill_loads(trace)

A harness names its reader in harness.yaml (`trace_reader: claude`), so several
harnesses can share one, e.g. the same agent with different models. To support a new
kind of agent, add a module with a TraceReader subclass (see base.py, claude.py,
codex.py) and register it in READERS.
"""

from mlflow.entities import Trace

from skill_evals.traces.base import SkillLoad, ToolCall, TraceReader
from skill_evals.traces.claude import ClaudeReader
from skill_evals.traces.codex import CodexReader

__all__ = ["READERS", "SkillLoad", "ToolCall", "TraceReader", "reader_for"]

# Reader name, as harness.yaml's `trace_reader` gives it, mapped to the reader.
READERS: dict[str, TraceReader] = {
    "claude": ClaudeReader(),
    "codex": CodexReader(),
}


def reader_for(trace: Trace) -> TraceReader:
    """Pick the reader for a trace, by the tag `skill-evals run` gave it.

    Args:
        trace: A trace tagged by `skill-evals run`: eval.trace_reader, or for runs
            from before that tag existed, eval.harness.

    Returns:
        The reader for the trace's harness.

    Raises:
        ValueError: If the trace has neither tag or names an unregistered reader.
    """
    tags = trace.info.tags
    name = tags.get("eval.trace_reader") or tags.get("eval.harness")
    if name not in READERS:
        msg = (
            f"trace {trace.info.trace_id}: no trace reader {name!r}; "
            f"registered: {sorted(READERS)}"
        )
        raise ValueError(msg)
    return READERS[name]
