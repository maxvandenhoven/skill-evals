"""Scorers about skill loading.

How a skill load shows up in a trace depends on the harness (Claude Code: its Skill
tool; Codex: reading SKILL.md); the trace readers in skill_evals.traces turn both
into SkillLoad records, which these scorers check.
"""

from mlflow.entities import Trace
from mlflow.genai.scorers import Scorer, scorer

from skill_evals.traces import reader_for


def skill_invoked(skill: str, namespace_required: bool = False) -> Scorer:
    """Build a scorer that checks whether the agent loaded a given skill.

    Args:
        skill: Skill name, e.g. "pr" or "code-review".
        namespace_required: Only count skill-tool loads that carry a plugin
            namespace ("<plugin>:<skill>"), so a built-in skill with the same name
            (Claude Code's own `code-review`) doesn't count. SKILL.md reads carry no
            namespace and always count.

    Returns:
        A scorer named `skill_invoked:<skill>` that is True when the skill was loaded.
    """

    # Name it after the skill so several can coexist; MLflow metric names allow
    # letters, digits, _ - . space : and / (no brackets).
    @scorer(name=f"skill_invoked:{skill}")
    def _skill_invoked(trace: Trace) -> bool:
        """Check one trace for the skill.

        Args:
            trace: One eval run's trace.

        Returns:
            Whether the skill was loaded, honouring `namespace_required`.
        """
        return any(
            load.skill == skill
            and (not namespace_required or load.plugin or load.source == "file")
            for load in reader_for(trace).skill_loads(trace)
        )

    return _skill_invoked


@scorer
def skills_used(trace: Trace) -> str:
    """List every skill loaded in the trace, as a diagnostic next to pass/fail scorers.

    Args:
        trace: One eval run's trace.

    Returns:
        The loaded skill names (namespaced where the harness namespaces them),
        comma-separated and without duplicates, or "(none)".
    """
    names = dict.fromkeys(str(load) for load in reader_for(trace).skill_loads(trace))
    return ", ".join(names) or "(none)"
