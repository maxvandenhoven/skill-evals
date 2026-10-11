"""Built-in MLflow scorers for skill evals, referenced by name from eval files.

A case in an eval file (or the eval, as its cases' default) lists scorers like:

    scorers:
      - name: skill_invoked
        args: { skill: pr }
        min_pass: 0.8  # Optional: fail `skill-evals score` below this pass rate
      - name: answer_matches
        args: { pattern: '(?ms)^## Summary' }

`build_scorers` turns that list into MLflow scorer objects via a registry: REGISTRY
below, extended with a project's own scorers (see skill_evals.config). A project
scorer is a factory returning an `@scorer`, like the ones in skills.py and
answers.py. Scorer docs: https://mlflow.org/docs/latest/genai/concepts/scorers/
"""

from collections.abc import Callable, Mapping
from typing import Any

from mlflow.genai.scorers import Scorer

from skill_evals.scorers.answers import answer_matches
from skill_evals.scorers.skills import skill_invoked, skills_used

# Scorer name in an eval file, mapped to a factory that takes the scorer's `args`.
REGISTRY: dict[str, Callable[..., Scorer]] = {
    "skill_invoked": skill_invoked,
    "answer_matches": answer_matches,
}

# Diagnostics added to every case automatically.
ALWAYS: list[Scorer] = [skills_used]


def build_scorers(
    specs: list[dict[str, Any]], registry: Mapping[str, Callable[..., Scorer]] = REGISTRY
) -> list[Scorer]:
    """Build the scorers a case lists, plus the ALWAYS diagnostics.

    Args:
        specs: The case's `scorers` list: mappings with a `name` from the registry,
            optional `args` for its factory and an optional `min_pass` (used when
            scoring, not here).
        registry: Scorer name mapped to factory; REGISTRY plus any project scorers.

    Returns:
        One scorer per spec, in order, followed by the ALWAYS diagnostics.

    Raises:
        ValueError: If a spec names a scorer that isn't in the registry.
    """
    built = []
    for spec in specs:
        name = spec["name"]
        if name not in registry:
            msg = f"unknown scorer {name!r}; available: {sorted(registry)}"
            raise ValueError(msg)
        built.append(registry[name](**spec.get("args", {})))
    return built + ALWAYS
