"""Trace reader for Codex, traced by MLflow's notify hook (@mlflow/codex).

    AGENT codex_conversation
      outputs = "<final answer>"
      TOOL tool_exec {"input": "...shell command..."}
      LLM  llm_call

Codex has no skill tool. It reads the skill file with a shell command, so a load is
a tool call whose arguments mention `<skill>/SKILL.md`, e.g.
`cat ~/.codex/plugins/cache/.../skills/engineering/pr/SKILL.md`. Tool spans need the
patched connector (harnesses/codex/tracing).
"""

from mlflow.entities import Trace

from skill_evals.traces.base import SkillLoad, TraceReader, root_span, skill_file_reads


class CodexReader(TraceReader):
    """Reads traces from MLflow's Codex notify hook."""

    def final_answer(self, trace: Trace) -> str:
        """Extract the reply, which the root span records as plain text.

        Args:
            trace: One eval run's trace.

        Returns:
            The final answer as text; empty if there is none.
        """
        outputs = root_span(trace).outputs
        return "" if outputs is None else str(outputs)

    def skill_loads(self, trace: Trace) -> list[SkillLoad]:
        """List the SKILL.md files the agent read.

        Args:
            trace: One eval run's trace.

        Returns:
            The skill loads in the order they happened.
        """
        return [
            load for call in self.tool_calls(trace) for load in skill_file_reads(call)
        ]
