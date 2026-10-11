"""Trace reader for Claude Code, traced by MLflow's Claude Code plugin.

    AGENT claude_code_conversation
      outputs = {"status": ..., "response": "<final answer>"}
      TOOL tool_Skill {"skill": "mattpocock-skills:pr"}
      TOOL tool_Bash  {"command": "..."}
      LLM  llm

Claude Code loads skills with its dedicated `Skill` tool. Skills from a plugin are
namespaced `<plugin>:<skill>`; Claude Code's built-in skills (e.g. its own
`code-review`) and project skills are not.
"""

from mlflow.entities import Trace

from skill_evals.traces.base import SkillLoad, TraceReader, root_span, skill_file_reads


class ClaudeReader(TraceReader):
    """Reads traces from MLflow's Claude Code plugin."""

    def final_answer(self, trace: Trace) -> str:
        """Extract the reply from the root span's `response` output.

        Args:
            trace: One eval run's trace.

        Returns:
            The final answer as text; empty if there is none.
        """
        outputs = root_span(trace).outputs
        if isinstance(outputs, dict):
            return str(outputs.get("response") or "")
        return "" if outputs is None else str(outputs)

    def skill_loads(self, trace: Trace) -> list[SkillLoad]:
        """List the Skill tool's loads, plus any SKILL.md files read directly.

        Args:
            trace: One eval run's trace.

        Returns:
            The skill loads in the order they happened.
        """
        loads = []
        for call in self.tool_calls(trace):
            if call.name != "Skill":
                loads += skill_file_reads(call)
                continue
            # A rejected call (e.g. unknown skill) still has a span; skip it.
            if "tool_use_error" in call.output or "Unknown skill" in call.output:
                continue
            plugin, _, skill = str(call.inputs.get("skill")).rpartition(":")
            loads.append(SkillLoad(skill=skill, plugin=plugin or None, source="tool"))
        return loads
