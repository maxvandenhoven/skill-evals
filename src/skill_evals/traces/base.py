"""The interface every harness's trace reader implements, and shared helpers.

Each harness's MLflow connector shapes its traces differently: span names, where the
final answer sits, how loading a skill shows up. A TraceReader hides that, so scorers
ask harness-independent questions (what was the answer, which skills were loaded)
instead of poking at spans. To support a new harness, subclass TraceReader in a
module next to this one and register it in traces/__init__.py under the harness's
folder name.
"""

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

from mlflow.entities import Span, SpanType, Trace

# Matches the folder name in ".../<skill-name>/SKILL.md".
_SKILL_FILE = re.compile(r"([\w.-]+)/SKILL\.md")


@dataclass(frozen=True)
class ToolCall:
    """One tool call from a trace, in a harness-independent shape.

    Attributes:
        name: Span name minus the "tool_" prefix, e.g. "Skill" or "exec".
        inputs: The tool arguments as recorded on the span.
        output: The tool result, serialised to text.
    """

    name: str
    inputs: dict[str, Any]
    output: str

    @property
    def inputs_text(self) -> str:
        """All arguments as one JSON string, for substring checks."""
        return json.dumps(self.inputs, ensure_ascii=False)


@dataclass(frozen=True)
class SkillLoad:
    """One time the agent loaded a skill.

    Attributes:
        skill: The skill's name without namespace, e.g. "code-review".
        plugin: The plugin namespace, for skills loaded as "<plugin>:<skill>";
            None for built-in, project and file-read skills.
        source: How it was loaded: through a dedicated skill tool, or by reading
            the skill's SKILL.md file.
    """

    skill: str
    plugin: str | None
    source: Literal["tool", "file"]

    def __str__(self) -> str:
        """Format the load the way the harness named it.

        Returns:
            "<plugin>:<skill>", or the bare skill name without a plugin.
        """
        return f"{self.plugin}:{self.skill}" if self.plugin else self.skill


class TraceReader(ABC):
    """Reads one harness's traces. Subclass per harness."""

    @abstractmethod
    def final_answer(self, trace: Trace) -> str:
        """Extract the agent's final reply.

        Args:
            trace: One eval run's trace.

        Returns:
            The final answer as text; empty if there is none.
        """

    @abstractmethod
    def skill_loads(self, trace: Trace) -> list[SkillLoad]:
        """List every skill load in the trace, in order, duplicates included.

        Args:
            trace: One eval run's trace.

        Returns:
            The skill loads in the order they happened.
        """

    def tool_calls(self, trace: Trace) -> list[ToolCall]:
        """List every tool call in the trace.

        The default reads TOOL spans named "tool_<name>", the convention of the
        MLflow connectors so far. Override it for a connector that differs.

        Args:
            trace: One eval run's trace.

        Returns:
            The tool calls in the order they started.
        """
        spans = sorted(
            (s for s in trace.data.spans if s.span_type == SpanType.TOOL),
            key=lambda s: s.start_time_ns,
        )
        return [
            ToolCall(
                name=s.name.removeprefix("tool_"),
                inputs=s.inputs if isinstance(s.inputs, dict) else {"input": s.inputs},
                output=json.dumps(s.outputs, ensure_ascii=False, default=str),
            )
            for s in spans
        ]


def root_span(trace: Trace) -> Span:
    """Find the trace's root span, which holds the conversation's inputs and outputs.

    Args:
        trace: One eval run's trace.

    Returns:
        The span without a parent.

    Raises:
        ValueError: If the trace has no root span.
    """
    for span in trace.data.spans:
        if span.parent_id is None:
            return span
    msg = f"trace {trace.info.trace_id} has no root span"
    raise ValueError(msg)


def skill_file_reads(call: ToolCall) -> list[SkillLoad]:
    """Find skill loads in a tool call that reads `<skill>/SKILL.md` files.

    Args:
        call: Any tool call; its arguments are searched for SKILL.md paths.

    Returns:
        One file load per SKILL.md path in the arguments, in order.
    """
    return [
        SkillLoad(skill=name, plugin=None, source="file")
        for name in _SKILL_FILE.findall(call.inputs_text)
    ]
