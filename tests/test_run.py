"""Tests for `skill-evals run`: layers, sbx command lines, cell selection and the report.

Nothing here starts a sandbox: sbx command lines are only built, and the one step
that would run sandboxes (`run_one`) is replaced where the selection is tested.
"""

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from skill_evals import run
from skill_evals.config import HARNESSES, Case, Fixture
from skill_evals.run import Cell, Row, fixture_layer, kit_names, sbx_env
from tests.helpers import REPO, ProjectBuilder

LAYERS = [Path("/p/base.sbxenv.yaml"), Path("/p/claude/sbxenv.yaml")]
ENV_ARGS: dict[str, object] = {"workspace": Path("/runs/w"), "experiment_id": "7"}


@pytest.fixture
def no_sbx_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """Answer the report's `sbx version` call without sbx.

    Args:
        monkeypatch: Replaces the subprocess call that asks for the version.
    """

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        """Pretend to run `sbx version`.

        Args:
            cmd: The command line; only `sbx version` is expected.
            **kwargs: subprocess.run's options, ignored.

        Returns:
            sbx's version output.
        """
        assert cmd == ["sbx", "version"]
        return subprocess.CompletedProcess(cmd, 0, stdout="sbx version: v0.47.0\n")

    monkeypatch.setattr(run.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["skill-evals", "run", "-n", "2"])


def test_cell_names() -> None:
    """Check that a cell's experiment and slug come from eval, harness and library."""
    cell = Cell("pr", "claude", "matt-pocock-skills")
    assert cell.experiment == "skill-evals/pr/claude/matt-pocock-skills"
    assert cell.slug == "pr-claude-matt-pocock-skills"


def test_fixture_layer_with_args(tmp_path: Path) -> None:
    """Check that the fixture layer applies the kit by path, with the case's arguments."""
    fixture = Fixture(name="repo", path=Path("/kits/repo"), args={"with_spec": "true"})
    layer = fixture_layer(fixture, tmp_path)
    assert layer == tmp_path / "fixture.sbxenv.yaml"
    assert layer.read_text().splitlines() == [
        "schemaVersion: '1'",
        "kits:",
        "- source: /kits/repo",
        "  args:",
        "    with_spec: 'true'",
    ]


def test_fixture_layer_without_args(tmp_path: Path) -> None:
    """Check that without arguments the kit has no `args` key, so defaults apply."""
    layer = fixture_layer(
        Fixture(name="repo", path=Path("/kits/repo"), args={}), tmp_path
    )
    assert yaml.safe_load(layer.read_text()) == {
        "schemaVersion": "1",
        "kits": [{"source": "/kits/repo"}],
    }


def test_sbx_env_create() -> None:
    """Check that `create` gives the name and args, then flags, then the layers."""
    assert sbx_env("create", LAYERS, "se-1", ENV_ARGS, "-y", "--kit-arg", "a.v=1") == [
        "sbx", "env", "create", "--name", "se-1",
        "--env-arg", "workspace=/runs/w", "--env-arg", "experiment_id=7",
        "-y", "--kit-arg", "a.v=1",
        "/p/base.sbxenv.yaml", "/p/claude/sbxenv.yaml",
    ]  # fmt: skip


def test_sbx_env_exec_puts_command_after_layers() -> None:
    """Check that for `exec` the flags precede the layers and the command follows `--`."""
    cmd = sbx_env("exec", LAYERS, "se-1", ENV_ARGS, "--", "claude", "-p", "a -- b")
    assert cmd[-6:] == [
        "/p/base.sbxenv.yaml", "/p/claude/sbxenv.yaml", "--", "claude", "-p", "a -- b",
    ]  # fmt: skip


def test_sbx_env_flags_before_command() -> None:
    """Check that flags given before `--` still go before the layers."""
    cmd = sbx_env("exec", LAYERS[:1], "se-1", {}, "-t", "--", "ls")
    assert cmd == ["sbx", "env", "exec", "--name", "se-1", "-t", "/p/base.sbxenv.yaml",
                   "--", "ls"]  # fmt: skip


def test_sbx_env_rm() -> None:
    """Check that `rm` repeats the same names, args and layers as `create`."""
    create = sbx_env("create", LAYERS, "se-1", ENV_ARGS)
    assert sbx_env("rm", LAYERS, "se-1", ENV_ARGS, "-f") == [
        *create[:2], "rm", *create[3:-2], "-f", *create[-2:],
    ]  # fmt: skip


def test_kit_names_of_example_layers(tmp_path: Path) -> None:
    """Check that the kits of base, harness, library and fixture layers are all found."""
    fixture = Fixture(
        name="slugify-repo",
        path=REPO / "example" / "fixtures" / "slugify-repo",
        args={},
    )
    layers = [
        HARNESSES / "base.sbxenv.yaml",
        HARNESSES / "claude" / "sbxenv.yaml",
        REPO / "example" / "libraries" / "matt-pocock-skills" / "claude" / "sbxenv.yaml",
        fixture_layer(fixture, tmp_path),
    ]
    assert kit_names(layers) == {
        "claude-cli-pinned",
        "claude-mlflow-tracing",
        "matt-pocock-skills-claude",
        "fixture-slugify-repo",
    }


def test_kit_names_skips_kits_without_local_spec(tmp_path: Path) -> None:
    """Check that mapping-style kits count and remote kits without a spec are skipped."""
    (tmp_path / "local").mkdir()
    (tmp_path / "local" / "spec.yaml").write_text("name: local-kit\n")
    layer = tmp_path / "sbxenv.yaml"
    layer.write_text(
        "kits:\n  - { source: ./local, args: { x: '1' } }\n  - docker.io/acme/kit:1\n"
    )
    empty = tmp_path / "empty.sbxenv.yaml"
    empty.write_text('schemaVersion: "1"\n')
    assert kit_names([layer, empty]) == {"local-kit"}


@pytest.mark.usefixtures("no_sbx_version")
def test_write_report(project_dir: ProjectBuilder) -> None:
    """Check that the run report lists the command, sbx version and one row per run."""
    rows = [
        Row(cell="pr-claude-none", case="one", repeat=1, trace="tr-1", exit=0, note=""),
        Row(cell="pr-codex-none", case="one", repeat=1, trace=None, exit=None,
            note="sandbox create failed"),
    ]  # fmt: skip
    started = dt.datetime(2026, 10, 16, 21, 50, 19)
    path = run.write_report("20261016-215019", started, rows)
    assert path == project_dir.root / "runs" / "20261016-215019" / "report.md"
    lines = path.read_text().splitlines()
    assert lines[0] == "# skill-evals run 20261016-215019"
    assert "- command: `skill-evals run -n 2`" in lines
    assert "- sbx version: v0.47.0" in lines
    assert lines[-4:] == [
        "| cell | case | # | exit | trace | note |",
        "|---|---|---|---|---|---|",
        "| pr-claude-none | one | 1 | 0 | tr-1 |  |",
        "| pr-codex-none | one | 1 |  |  | sandbox create failed |",
    ]


@pytest.fixture
def planned(
    project_dir: ProjectBuilder, monkeypatch: pytest.MonkeyPatch, no_sbx_version: None
) -> list[tuple[str, str, int]]:
    """Provide a project with two evals, harnesses and libraries; runs are recorded.

    `b` only supports claude, and `e2` skips its baseline.

    Args:
        project_dir: The empty project to fill.
        monkeypatch: Replaces the function that runs one case with a recorder.
        no_sbx_version: Keeps the report from calling sbx.

    Returns:
        The runs `run.main` asked for: (cell slug, case id, repeat), in order.
    """
    for harness in ("claude", "codex"):
        project_dir.add_harness(harness)
    project_dir.add_library("a", "claude", "codex")
    project_dir.add_library("b", "claude")
    scorer = "    scorers: [{ name: answer_matches, args: { pattern: x } }]\n"
    project_dir.add_eval(
        "e1",
        "libraries: [a, b]\ncases:\n"
        f"  - id: one\n    prompt: One.\n{scorer}"
        f"  - id: two\n    prompt: Two.\n{scorer}",
    )
    project_dir.add_eval(
        "e2",
        f"libraries: [a]\nbaseline: false\ncases:\n  - id: one\n    prompt: x\n{scorer}",
    )
    runs: list[tuple[str, str, int]] = []

    def fake_run_one(
        cell: Cell, case: Case, repeat: int, stamp: str, keep: bool, kit_args: list[str]
    ) -> Row:
        """Record a run instead of starting a sandbox.

        Args:
            cell: The run's cell.
            case: The run's case.
            repeat: The repeat number.
            stamp: The invocation's stamp.
            keep: Whether to keep the sandbox.
            kit_args: The --kit-arg overrides.

        Returns:
            A row as if the run worked.
        """
        runs.append((cell.slug, case.id, repeat))
        return Row(
            cell=cell.slug, case=case.id, repeat=repeat, trace="tr", exit=0, note=""
        )

    monkeypatch.setattr(run, "run_one", fake_run_one)
    return runs


def run_args(**options: Any) -> argparse.Namespace:
    """Build `run`'s parsed options.

    Args:
        **options: Options that differ from the defaults.

    Returns:
        The options, as `run.add_arguments` defines them.
    """
    ap = argparse.ArgumentParser()
    run.add_arguments(ap)
    return argparse.Namespace(**{**vars(ap.parse_args(["--parallel", "1"])), **options})


def test_run_plans_every_cell(
    planned: list[tuple[str, str, int]], capsys: pytest.CaptureFixture[str]
) -> None:
    """Check that every eval runs per harness, with its baseline and each library."""
    stamp = run.main(run_args())
    out = capsys.readouterr().out
    assert sorted({slug for slug, _, _ in planned}) == [
        "e1-claude-a", "e1-claude-b", "e1-claude-none", "e1-codex-a", "e1-codex-none",
        "e2-claude-a", "e2-codex-a",
    ]  # fmt: skip
    assert "skip e1/codex/b: library has no layer for this harness" in out
    assert "7 cell(s), 12 run(s)" in out
    report = Path(out.rsplit("Report: ", 1)[1].strip())
    assert report.parent.name == stamp
    assert "| e1-claude-a | two | 1 | 0 | tr |  |" in report.read_text()
    assert "done: 12/12 runs produced a trace." in out


def test_run_cases_in_order_with_repeats(planned: list[tuple[str, str, int]]) -> None:
    """Check that a cell runs its cases and their repeats one after another."""
    run.main(run_args(evals="e1", harnesses="codex", libraries="a", repeats=2))
    assert planned == [
        ("e1-codex-a", "one", 1),
        ("e1-codex-a", "one", 2),
        ("e1-codex-a", "two", 1),
        ("e1-codex-a", "two", 2),
    ]


def test_run_baselines_only(planned: list[tuple[str, str, int]]) -> None:
    """Check that --libraries none runs only baselines and skips evals without one."""
    run.main(run_args(libraries="none", cases="two"))
    assert planned == [("e1-claude-none", "two", 1), ("e1-codex-none", "two", 1)]


@pytest.mark.parametrize(
    ("option", "value", "message"),
    [
        ("libraries", "nope", "no library 'nope'; available: a, b, none"),
        ("cases", "nope", "no case 'nope'; available: one, two"),
        ("libraries", "none,nope", "no library 'nope'"),
    ],
)
def test_run_rejects_unknown_library_or_case(
    planned: list[tuple[str, str, int]], option: str, value: str, message: str
) -> None:
    """Check that a library or case that no selected eval has stops before any run."""
    with pytest.raises(SystemExit, match=message):
        run.main(run_args(**{option: value}))
    assert planned == []


def test_run_rejects_a_selection_without_cells(
    planned: list[tuple[str, str, int]],
) -> None:
    """Check that a library without a layer for the harness leaves nothing to run."""
    with pytest.raises(SystemExit, match="nothing to run"):
        run.main(run_args(evals="e1", harnesses="codex", libraries="b"))
    assert planned == []


def test_run_rejects_baseline_of_eval_without_one(
    planned: list[tuple[str, str, int]],
) -> None:
    """Check that `--libraries none` stops if no selected eval has a baseline."""
    with pytest.raises(SystemExit, match="no library 'none'; available: a"):
        run.main(run_args(evals="e2", libraries="none"))
    assert planned == []
