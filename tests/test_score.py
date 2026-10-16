"""Tests for `skill-evals score`: pass rates, thresholds, the tables and the reports.

The end-to-end tests score recorded traces with `score.main`, against a temporary
SQLite store instead of the MLflow server.
"""

import argparse
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import mlflow
import pytest
from mlflow.tracing.utils.copy import copy_trace_to_experiment

from skill_evals import score
from skill_evals.config import use_config
from skill_evals.score import Row, format_values, markdown, resolve_stamp, text_line
from tests.helpers import (
    CLAUDE_BASELINE,
    CLAUDE_SKILL,
    CODEX_BASELINE,
    CODEX_SKILL,
    ProjectBuilder,
    trace_dict,
)

STAMP = "20261016-215019"
OLD_STAMP = "20261011-205026"


@pytest.mark.parametrize(
    ("values", "text"),
    [
        ([True, False, True], "2/3"),
        ([], "0/0"),
        (["pr", "(none)", "pr"], "(none), pr"),
        (["a, b", "c"], "a, b, c"),
    ],
)
def test_format_values(values: list[Any], text: str) -> None:
    """Check that pass/fail values show as k/n and diagnostics as distinct values."""
    assert format_values(values) == text


@pytest.mark.parametrize(
    ("library", "values", "threshold", "failed"),
    [
        ("lib", [True, True, False], 0.8, ["skill_invoked:pr"]),
        ("lib", [True, True, False, False], 0.5, []),  # Exactly at the threshold
        ("lib", [True], 1.0, []),
        ("none", [False, False], 0.8, []),  # Baselines never gate
    ],
)
def test_row_failed(
    library: str, values: list[bool], threshold: float, failed: list[str]
) -> None:
    """Check that a scorer fails below its threshold pass rate, in library cells."""
    row = Row(
        "pr", f"claude/{library}", library, "one",
        {"skill_invoked:pr": values, "answer_matches": [False] * len(values)},
        {"skill_invoked:pr": threshold},
    )  # fmt: skip
    assert row.failed() == failed


def test_row_without_results_fails_its_thresholds() -> None:
    """Check that a threshold without any values counts as a pass rate of 0."""
    row = Row("pr", "claude/lib", "lib", "one", {}, {"answer_matches": 0.1})
    assert row.failures() == [
        "pr claude/lib one: answer_matches passed 0/0, below min_pass 0.1"
    ]


def test_row_failures_describe_misses() -> None:
    """Check that each miss names the eval, cell, case, scorer, result and threshold."""
    row = Row(
        "pr", "codex/lib", "lib", "one",
        {"a": [True, False], "b": [False, False]}, {"a": 0.75, "b": 0.5},
    )  # fmt: skip
    assert row.failures() == [
        "pr codex/lib one: a passed 1/2, below min_pass 0.75",
        "pr codex/lib one: b passed 0/2, below min_pass 0.5",
    ]


def test_text_line() -> None:
    """Check that a terminal line shows the case, n and every scorer's result."""
    row = Row(
        "pr", "claude/lib", "lib", "feature-branch",
        {"skill_invoked:pr": [True, False], "skills_used": ["pr", "(none)"]},
    )  # fmt: skip
    assert text_line(row) == (
        "    feature-branch           n=2  skill_invoked:pr=1/2  skills_used=(none), pr"
    )
    assert text_line(Row("pr", "claude/lib", "lib", "one", {})) == (
        "    one                      no traces"
    )


def test_markdown_tables_per_eval() -> None:
    """Check that the Markdown has one table per eval, with misses marked and listed."""
    rows = [
        Row("pr", "claude/lib", "lib", "one", {"a": [True, False], "skills_used": ["pr"]},
            {"a": 1.0}),
        Row("pr", "claude/none", "none", "one", {"a": [False]}, {"a": 1.0}),
        Row("pr", "codex/lib", "lib", "one", {}),
        Row("review", "codex/lib", "lib", "two", {"b": [True]}),
    ]  # fmt: skip
    assert markdown(rows).splitlines() == [
        "### pr",
        "",
        "| cell | case | n | `a` | `skills_used` |",
        "|---|---|---|---|---|",
        "| claude/lib | one | 2 | 1/2 ❌ | pr |",
        "| claude/none | one | 1 | 0/1 |  |",
        "| codex/lib | one | 0 |  |  |",
        "",
        "### review",
        "",
        "| cell | case | n | `b` |",
        "|---|---|---|---|",
        "| codex/lib | two | 1 | 1/1 |",
        "",
        "**Below threshold:**",
        "",
        "- pr claude/lib one: a passed 1/2, below min_pass 1",
    ]


def test_markdown_without_misses() -> None:
    """Check that there is no threshold section without misses."""
    text = markdown([Row("pr", "claude/lib", "lib", "one", {"a": [True]}, {"a": 1.0})])
    assert "Below threshold" not in text


def test_resolve_stamp_keeps_explicit_stamp(project_dir: ProjectBuilder) -> None:
    """Check that a given stamp is used as is, without looking at the run folders."""
    assert resolve_stamp(OLD_STAMP) == OLD_STAMP


def test_resolve_latest_stamp(project_dir: ProjectBuilder) -> None:
    """Check that `latest` is the newest run folder with a report, by its stamp name."""
    for folder in (OLD_STAMP, STAMP, "claude-login", "20991231-235959"):
        (project_dir.root / "runs" / folder).mkdir(parents=True)
    for folder in (OLD_STAMP, STAMP, "claude-login"):
        (project_dir.root / "runs" / folder / "report.md").write_text("")
    assert resolve_stamp("latest") == STAMP


def test_resolve_latest_stamp_without_runs(project_dir: ProjectBuilder) -> None:
    """Check that `latest` without any run report stops with a message."""
    with pytest.raises(SystemExit, match="no run with a report.md yet"):
        resolve_stamp("latest")


def log_trace(
    name: str, cell: str, case: str, run_dir: str | None, artifacts: Path
) -> None:
    """Copy a recorded trace into a cell's experiment, tagged as a run of a case.

    Args:
        name: The recorded trace's file name in tests/data/, without .json.
        cell: "<harness>/<library>"; the pr eval's experiment is created if missing.
        case: The eval.case tag.
        run_dir: The eval.run_dir tag, or None for an untagged trace.
        artifacts: Where new experiments keep their artifacts.
    """
    data = trace_dict(name)
    tags = data["info"]["tags"]
    tags["eval.case"] = case
    if run_dir is None:
        del tags["eval.run_dir"]
    else:
        tags["eval.run_dir"] = run_dir
    experiment = f"skill-evals/pr/{cell}"
    found = mlflow.get_experiment_by_name(experiment)
    experiment_id = (
        found.experiment_id
        if found
        else mlflow.create_experiment(experiment, artifact_location=str(artifacts))
    )
    copy_trace_to_experiment(data, experiment_id)


@pytest.fixture(scope="module")
def scored_store(tmp_path_factory: pytest.TempPathFactory) -> Iterator[ProjectBuilder]:
    """Provide a project with a pr eval and recorded traces in a temporary SQLite store.

    claude/matt-pocock-skills has a run that loaded the skill and one that didn't;
    codex/matt-pocock-skills one that did, plus an untagged trace and a run of a case
    no longer in the eval. claude/none has a baseline run from an older invocation.

    Args:
        tmp_path_factory: Makes the project's folder.

    Yields:
        The project; MLflow and `score` use the store meanwhile.
    """
    builder = ProjectBuilder(tmp_path_factory.mktemp("scored"))
    builder.add_library("matt-pocock-skills", "claude", "codex")
    builder.add_eval(
        "pr",
        """\
        description: Write a PR body.
        libraries: [matt-pocock-skills]
        cases:
          - id: feature-branch
            prompt: Write the PR body.
            scorers:
              - name: skill_invoked
                args: { skill: pr }
                min_pass: 0.5
              - name: answer_matches
                args: { pattern: '(?m)^## Summary' }
        """,
    )
    runs = builder.root / "runs"
    for stamp in (OLD_STAMP, STAMP):
        (runs / stamp).mkdir(parents=True)
        (runs / stamp / "report.md").write_text(f"# skill-evals run {stamp}\n")
    store = builder.root / "mlflow"
    uri = f"sqlite:///{store / 'mlflow.db'}"
    store.mkdir()
    latest, old = f"{runs}/{STAMP}/run", f"{runs}/{OLD_STAMP}/run"
    traces = [
        (CLAUDE_SKILL, "claude/matt-pocock-skills", "feature-branch", latest),
        (CLAUDE_BASELINE, "claude/matt-pocock-skills", "feature-branch", latest),
        (CODEX_SKILL, "codex/matt-pocock-skills", "feature-branch", latest),
        (CODEX_SKILL, "codex/matt-pocock-skills", "feature-branch", None),
        (CODEX_BASELINE, "codex/matt-pocock-skills", "old-case", latest),
        (CLAUDE_BASELINE, "claude/none", "feature-branch", old),
    ]
    previous = mlflow.get_tracking_uri()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(score, "MLFLOW_URI", uri)
        mlflow.set_tracking_uri(uri)
        for name, cell, case, run_dir in traces:
            log_trace(name, cell, case, run_dir, store / "artifacts")
        mlflow.flush_trace_async_logging()
        yield builder
    mlflow.set_tracking_uri(previous)


@pytest.fixture
def scored(scored_store: ProjectBuilder) -> ProjectBuilder:
    """Make the scored project current for one test.

    Args:
        scored_store: The project shared by all tests of the module.

    Returns:
        The scored project.
    """
    use_config(scored_store.config)
    return scored_store


def score_args(**options: Any) -> argparse.Namespace:
    """Build `score`'s parsed options.

    Args:
        **options: Options that differ from the defaults.

    Returns:
        The options, as `score.add_arguments` defines them.
    """
    ap = argparse.ArgumentParser()
    score.add_arguments(ap)
    return argparse.Namespace(**{**vars(ap.parse_args([])), **options})


def test_score_latest_run_with_threshold(
    scored: ProjectBuilder, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Check that scoring appends the table and exits 1 on a missed threshold.

    --min-pass applies to answer_matches only; skill_invoked keeps its own 0.5.
    """
    summary = tmp_path / "summary.md"
    assert score.main(score_args(stamp="latest", min_pass=1.0, summary=summary)) == 1
    table = [
        "| cell | case | n | `skill_invoked:pr` | `answer_matches` | `skills_used` |",
        "|---|---|---|---|---|---|",
        "| claude/matt-pocock-skills | feature-branch | 2 | 1/2 | 1/2 ❌ "
        "| (none), mattpocock-skills:pr |",
        "| codex/matt-pocock-skills | feature-branch | 1 | 1/1 | 1/1 | pr |",
    ]
    miss = (
        "pr claude/matt-pocock-skills feature-branch: answer_matches passed 1/2, "
        "below min_pass 1"
    )
    report = (scored.root / "runs" / STAMP / "report.md").read_text()
    assert report.startswith(f"# skill-evals run {STAMP}\n\n## Scores\n")
    assert "\n".join(["### pr", "", *table]) in report
    assert f"**Below threshold:**\n\n- {miss}\n" in report
    assert summary.read_text().startswith("## skill-evals\n\n### pr\n")
    out = capsys.readouterr().out
    assert "1 trace(s) of cases not in the eval file, skipped" in out
    assert f"below threshold: {miss}" in out
    assert "claude/none" not in out  # Not part of the latest run


def test_score_all_runs_without_threshold(
    scored: ProjectBuilder, capsys: pytest.CaptureFixture[str]
) -> None:
    """Check that without --stamp every tagged run counts; baselines don't gate."""
    report = scored.root / "runs" / OLD_STAMP / "report.md"
    assert score.main(score_args(evals="pr")) == 0
    out = capsys.readouterr().out
    assert "=== pr: Write a PR body." in out
    # MLflow prints its own lines between the cell and its scores.
    section = out.split("  claude/none\n", 1)[1].splitlines()
    baseline = next(line for line in section if line.startswith("    feature-branch"))
    assert baseline.split() == [
        "feature-branch", "n=1", "skill_invoked:pr=0/1", "answer_matches=0/1",
        "skills_used=(none)",
    ]  # fmt: skip
    assert report.read_text() == f"# skill-evals run {OLD_STAMP}\n"  # No --stamp
