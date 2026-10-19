"""Tests for the command line: parsing, exit codes and the glue between commands."""

import argparse
import contextlib
import sys
from collections.abc import Generator
from pathlib import Path

import pytest

from skill_evals import cli, mlflow_server, run, score
from tests.helpers import ProjectBuilder

VALID_EVAL = """\
libraries: []
cases:
  - id: one
    prompt: Do it.
    scorers: [{ name: answer_matches, args: { pattern: done } }]
"""


def run_cli(monkeypatch: pytest.MonkeyPatch, *argv: str) -> int | str | None:
    """Run `skill-evals` with the given arguments, as the console script does.

    Args:
        monkeypatch: Sets sys.argv.
        *argv: The arguments after `skill-evals`.

    Returns:
        The exit code, or the message of a command that stopped with one.

    Raises:
        AssertionError: If the command didn't exit.
    """
    monkeypatch.setattr(sys, "argv", ["skill-evals", *argv])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    code = exc.value.code
    if code is not None and not isinstance(code, int | str):
        msg = f"unexpected exit code {code!r}"
        raise AssertionError(msg)
    return code


@pytest.fixture
def no_server(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace the MLflow server with a context that only records its use.

    Args:
        monkeypatch: Swaps in the recording context.

    Returns:
        One "running" per command that asked for the server.
    """
    entered: list[str] = []

    @contextlib.contextmanager
    def running() -> Generator[None]:
        """Record that a command asked for the server.

        Yields:
            Nothing.
        """
        entered.append("running")
        yield

    monkeypatch.setattr(mlflow_server, "running", running)
    return entered


def test_help_lists_commands(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Check that --help exits 0 and describes every command."""
    assert run_cli(monkeypatch, "--help") == 0
    out = capsys.readouterr().out
    for command in ("init", "evaluate", "run", "score", "validate", "mlflow"):
        assert f"skill-evals {command}" in out


@pytest.mark.parametrize(
    "command", ["init", "evaluate", "run", "score", "validate", "mlflow"]
)
def test_command_help(monkeypatch: pytest.MonkeyPatch, command: str) -> None:
    """Check that every command has --help, which exits 0 without doing anything."""
    assert run_cli(monkeypatch, command, "--help") == 0


@pytest.mark.parametrize(
    ("argv", "error"),
    [
        ((), "the following arguments are required: COMMAND"),
        (("deploy",), "invalid choice: 'deploy'"),
        (("run", "-n", "many"), "argument -n/--repeats: invalid int value: 'many'"),
        (("score", "--min-pass", "high"), "argument --min-pass: invalid float value"),
        (("validate", "--evals", "pr"), "unrecognized arguments: --evals pr"),
    ],
)
def test_usage_errors_exit_2(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: tuple[str, ...],
    error: str,
) -> None:
    """Check that wrong usage exits 2 with argparse's message."""
    assert run_cli(monkeypatch, *argv) == 2
    assert error in capsys.readouterr().err


def test_run_options() -> None:
    """Check that `run` parses its selection and repeat options, with their defaults."""
    parser = cli.build_parser()
    args = parser.parse_args(["run"])
    assert (args.evals, args.harnesses, args.cases, args.libraries) == (None,) * 4
    assert (args.repeats, args.parallel, args.keep, args.kit_arg) == (1, 4, False, [])
    args = parser.parse_args(
        ["run", "--evals", "pr,code-review", "-n", "3", "--keep",
         "--kit-arg", "a.version=1", "--kit-arg", "b.x=2"]
    )  # fmt: skip
    assert (args.evals, args.repeats, args.keep) == ("pr,code-review", 3, True)
    assert args.kit_arg == ["a.version=1", "b.x=2"]


def test_score_and_evaluate_options() -> None:
    """Check that `score` and `evaluate` share the threshold options."""
    parser = cli.build_parser()
    args = parser.parse_args(["score", "--stamp", "latest", "--min-pass", "0.8"])
    assert (args.stamp, args.min_pass, args.summary) == ("latest", 0.8, None)
    args = parser.parse_args(["evaluate", "-n", "2", "--summary", "out.md"])
    assert (args.repeats, args.min_pass, args.summary) == (2, None, Path("out.md"))


def test_init_default_folder() -> None:
    """Check that `init` puts the project folders in ./skill-evals by default."""
    assert cli.build_parser().parse_args(["init"]).dir == "skill-evals"


def test_validate_exits_0(
    project_dir: ProjectBuilder,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Check that `validate` on a valid project prints a summary and exits 0."""
    project_dir.add_eval("one", VALID_EVAL)
    project_dir.add_harness("agent")
    assert run_cli(monkeypatch, "--config", str(project_dir.config), "validate") == 0
    assert capsys.readouterr().out == "valid: 1 eval(s), 1 harness(es)\n"


def test_validate_finds_config_from_current_folder(
    project_dir: ProjectBuilder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check that `validate` without --config uses the config above the current folder."""
    monkeypatch.chdir(project_dir.root / "evals")
    assert run_cli(monkeypatch, "validate") == 0


@pytest.mark.parametrize(
    ("file", "text", "message"),
    [
        (
            "evals/bad.yaml",
            "libraries: []\ncases: []\n",
            "bad.yaml: cases: [] should be non-empty",
        ),
        ("evals/bad.yaml", VALID_EVAL + "baseline: false\n", "so nothing would run"),
        (
            "harnesses/agent/harness.yaml",
            "run: [x]\n",
            "'inventory' is a required property",
        ),
    ],
)
def test_validate_invalid_project_exits_with_message(
    project_dir: ProjectBuilder,
    monkeypatch: pytest.MonkeyPatch,
    file: str,
    text: str,
    message: str,
) -> None:
    """Check that `validate` stops at the first invalid file with exit status 1."""
    project_dir.add_harness("agent")
    project_dir.write(file, text)
    code = run_cli(monkeypatch, "--config", str(project_dir.config), "validate")
    assert isinstance(code, str)
    assert message in code


def test_missing_config_exits_with_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check that commands without a project point to `skill-evals init`."""
    monkeypatch.chdir(tmp_path)
    code = run_cli(monkeypatch, "validate")
    assert isinstance(code, str)
    assert "create one with `skill-evals init`" in code


@pytest.mark.parametrize("command", ["run", "score"])
def test_unknown_eval_exits_with_message(
    project_dir: ProjectBuilder,
    monkeypatch: pytest.MonkeyPatch,
    no_server: list[str],
    command: str,
) -> None:
    """Check that an unknown eval name stops with a message, before any sandbox."""
    project_dir.add_eval("one", VALID_EVAL)
    project_dir.add_harness("agent")
    config = str(project_dir.config)
    code = run_cli(monkeypatch, "--config", config, command, "--evals", "nope")
    assert isinstance(code, str)
    assert "no eval 'nope'; available: one" in code


def test_unknown_harness_exits_with_message(
    project_dir: ProjectBuilder,
    monkeypatch: pytest.MonkeyPatch,
    no_server: list[str],
) -> None:
    """Check that an unknown harness name stops with a message, before any sandbox."""
    project_dir.add_eval("one", VALID_EVAL)
    project_dir.add_harness("agent")
    config = str(project_dir.config)
    code = run_cli(monkeypatch, "--config", config, "run", "--harnesses", "nope")
    assert isinstance(code, str)
    assert "no harness 'nope'; available: agent" in code


@pytest.mark.parametrize(("result", "code"), [(0, 0), (1, 1), ("20261016-215019", 0)])
def test_with_mlflow_runs_server_and_returns_code(
    no_server: list[str], result: object, code: int
) -> None:
    """Check that commands run in the MLflow server; a non-integer result is success."""
    handler = cli._with_mlflow(lambda args: result)
    assert handler(argparse.Namespace()) == code
    assert no_server == ["running"]


@pytest.mark.parametrize("code", [0, 1])
def test_evaluate_scores_exactly_its_run(
    monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    """Check that `evaluate` scores the stamp `run` returns and exits with its code."""
    seen: list[str] = []
    monkeypatch.setattr(run, "main", lambda args: "20261016-215019")
    monkeypatch.setattr(score, "main", lambda args: seen.append(args.stamp) or code)
    assert cli.evaluate(argparse.Namespace(stamp=None)) == code
    assert seen == ["20261016-215019"]


def test_mlflow_command_refuses_second_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """Check that `skill-evals mlflow` stops if a server already answers on the port."""
    monkeypatch.setattr(mlflow_server, "is_running", lambda: True)
    code = run_cli(monkeypatch, "mlflow")
    assert isinstance(code, str)
    assert "already runs on http://127.0.0.1:5000" in code
