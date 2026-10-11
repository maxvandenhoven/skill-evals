"""The example project's own scorers, next to the built-in ones.

.skill-evals.yaml points `scorers:` at this package; its REGISTRY maps the names an
eval file can use to scorer factories. A scorer reads the trace through
skill_evals.traces, so it works for every harness.
"""

import re

from mlflow.entities import Trace
from mlflow.genai.scorers import Scorer, scorer

from skill_evals.traces import reader_for


def command_ran(pattern: str) -> Scorer:
    """Build a scorer that checks whether the agent ran a matching command.

    Unlike answer_matches, it looks at what the agent did, not what it said: every
    tool call's arguments (e.g. Claude Code's Bash command, Codex's exec input).

    Args:
        pattern: Regular expression searched for in each tool call's arguments.

    Returns:
        A scorer named `command_ran:<pattern>` that is True when any call matches.
    """
    compiled = re.compile(pattern)

    @scorer(name=f"command_ran:{pattern}")
    def _command_ran(trace: Trace) -> bool:
        """Check one trace's tool calls.

        Args:
            trace: One eval run's trace.

        Returns:
            Whether any tool call's arguments match the pattern.
        """
        calls = reader_for(trace).tool_calls(trace)
        return any(compiled.search(call.inputs_text) for call in calls)

    return _command_ran


REGISTRY = {"command_ran": command_ran}
