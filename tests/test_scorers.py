"""Tests for the built-in scorers, against real traces recorded in tests/data/."""

from typing import Any

import pytest
import yaml
from mlflow.entities import Trace

from skill_evals.scorers import ALWAYS, REGISTRY, build_scorers
from skill_evals.scorers.answers import answer_matches
from skill_evals.scorers.skills import skill_invoked, skills_used
from tests.helpers import (
    CLAUDE_BASELINE,
    CLAUDE_SKILL,
    CODEX_BASELINE,
    CODEX_SKILL,
    REPO,
    edited_trace,
    load_trace,
    with_skill_call,
)


def example_pattern(eval_name: str) -> str:
    """Read the answer_matches pattern of one of the example's evals.

    Args:
        eval_name: The eval's name in example/evals/.

    Returns:
        The pattern of its first case's answer_matches scorer.
    """
    spec = yaml.safe_load((REPO / "example" / "evals" / f"{eval_name}.yaml").read_text())
    scorers: list[dict[str, Any]] = spec["cases"][0]["scorers"]
    return next(s["args"]["pattern"] for s in scorers if s["name"] == "answer_matches")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (CLAUDE_SKILL, True),
        (CODEX_SKILL, True),
        (CLAUDE_BASELINE, False),
        (CODEX_BASELINE, False),
    ],
)
def test_skill_invoked(name: str, expected: bool) -> None:
    """Check that library runs loaded the pr skill and baselines loaded no skill."""
    assert skill_invoked("pr")(trace=load_trace(name)) is expected


def test_skill_invoked_other_skill() -> None:
    """Check that loading one skill doesn't count as loading another."""
    assert skill_invoked("code-review")(trace=load_trace(CLAUDE_SKILL)) is False


@pytest.mark.parametrize(
    ("trace", "expected"),
    [
        pytest.param(load_trace(CLAUDE_SKILL), True, id="claude-plugin-skill"),
        pytest.param(load_trace(CODEX_SKILL), True, id="codex-skill-file"),
        pytest.param(
            with_skill_call("pr", "Launching skill: pr"), False, id="claude-builtin-skill"
        ),
    ],
)
def test_skill_invoked_namespace_required(trace: Trace, expected: bool) -> None:
    """Check that with namespace_required only plugin skills and SKILL.md reads count."""
    assert skill_invoked("pr", namespace_required=True)(trace=trace) is expected
    assert skill_invoked("pr")(trace=trace) is True


def test_skill_invoked_is_named_after_skill() -> None:
    """Check that each skill_invoked scorer is named after its skill."""
    assert skill_invoked("code-review").name == "skill_invoked:code-review"


@pytest.mark.parametrize(
    ("trace", "expected"),
    [
        pytest.param(load_trace(CLAUDE_SKILL), "mattpocock-skills:pr", id="claude"),
        pytest.param(load_trace(CODEX_SKILL), "pr", id="codex"),
        pytest.param(load_trace(CLAUDE_BASELINE), "(none)", id="claude-baseline"),
        pytest.param(load_trace(CODEX_BASELINE), "(none)", id="codex-baseline"),
        pytest.param(
            edited_trace(
                CLAUDE_SKILL,
                "tool_Bash",
                inputs={"command": "cat x/tdd/SKILL.md x/pr/SKILL.md"},
            ),
            "mattpocock-skills:pr, tdd, pr",
            id="several",
        ),
        pytest.param(
            edited_trace(
                CODEX_SKILL, "tool_exec", index=1, inputs={"input": "cat a/pr/SKILL.md"}
            ),
            "pr",
            id="duplicates",
        ),
    ],
)
def test_skills_used(trace: Trace, expected: str) -> None:
    """Check that skills_used lists each loaded skill once, as the harness named it."""
    assert skills_used(trace=trace) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (CLAUDE_SKILL, True),
        (CODEX_SKILL, True),
        (CLAUDE_BASELINE, False),
        (CODEX_BASELINE, False),
    ],
)
def test_answer_matches_pr_template(name: str, expected: bool) -> None:
    """Check that the pr eval's pattern accepts the PR bodies written with the skill."""
    trace = load_trace(name)
    assert answer_matches(example_pattern("pr"))(trace=trace) is expected


@pytest.mark.parametrize(
    ("trace", "expected"),
    [
        pytest.param(load_trace(CLAUDE_BASELINE), False, id="claude-baseline"),
        pytest.param(load_trace(CODEX_BASELINE), False, id="codex-baseline"),
        pytest.param(
            edited_trace(
                CODEX_BASELINE,
                "codex_conversation",
                outputs="Intro\n\n## Standards\n\n- ok\n\n**Spec**\n\n- ok\n",
            ),
            True,
            id="two-axis-review",
        ),
    ],
)
def test_answer_matches_review_format(trace: Trace, expected: bool) -> None:
    """Check that the code-review pattern needs a Standards and a Spec section."""
    assert answer_matches(example_pattern("code-review"))(trace=trace) is expected


def test_answer_matches_searches_anywhere() -> None:
    """Check that the pattern may match anywhere in the answer, not only at its start."""
    trace = load_trace(CLAUDE_BASELINE)
    assert answer_matches("slugify")(trace=trace) is True
    assert answer_matches("^slugify")(trace=trace) is False


def test_answer_matches_without_answer() -> None:
    """Check that a trace without a final answer doesn't match."""
    trace = edited_trace(CODEX_SKILL, "codex_conversation", outputs=None)
    assert answer_matches(".")(trace=trace) is False


def test_build_scorers_in_spec_order() -> None:
    """Check that scorers are built from their specs in order, then the diagnostics."""
    scorers = build_scorers(
        [
            {"name": "answer_matches", "args": {"pattern": "x"}, "min_pass": 0.5},
            {"name": "skill_invoked", "args": {"skill": "pr"}},
        ]
    )
    assert [s.name for s in scorers] == [
        "answer_matches",
        "skill_invoked:pr",
        "skills_used",
    ]
    assert scorers[-len(ALWAYS) :] == ALWAYS


def test_build_scorers_unknown_name() -> None:
    """Check that an unknown scorer name lists the available ones."""
    with pytest.raises(ValueError, match=r"unknown scorer 'nope'; available: \['answer"):
        build_scorers([{"name": "nope"}])


def test_build_scorers_with_registry() -> None:
    """Check that a registry with project scorers is used instead of the built-in one."""
    registry = {**REGISTRY, "skill_invoked": lambda: skills_used}
    assert [s.name for s in build_scorers([{"name": "skill_invoked"}], registry)] == [
        "skills_used",
        "skills_used",
    ]
