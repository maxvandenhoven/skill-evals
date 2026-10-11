"""skill-evals: test whether coding agents load and follow your skills.

    skill-evals init [DIR]        Set up a project (.skill-evals.yaml + folders)
    skill-evals evaluate          Run the evals, then score them (run + score)
    skill-evals run               Run evals in sandboxes
    skill-evals score             Score runs' traces; check thresholds
    skill-evals validate          Check the project's eval and harness files
    skill-evals mlflow            Open the MLflow server (UI) on the project's store

run, score and evaluate start an MLflow server for their duration if none is up.
"""

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from skill_evals import init, mlflow_server, run, score
from skill_evals.config import (
    discover_evals,
    discover_harnesses,
    eval_cases,
    load_harness,
    use_config,
)

# A subcommand's function: takes the parsed options, returns an exit code (or, like
# `run`, something else that counts as success).
Handler = Callable[[argparse.Namespace], object]


def validate(args: argparse.Namespace) -> int:
    """Validate every eval file and harness.yaml.

    Args:
        args: The parsed options; `validate` has none of its own.

    Returns:
        The exit code, 0 (invalid files stop with a message instead).
    """
    del args  # Every subcommand takes the parsed options; this one has none
    evals, harnesses = discover_evals(), discover_harnesses()
    for name in evals:
        eval_cases(name)  # Validates the file and resolves fixtures and scorers
    for name in harnesses:
        load_harness(name)
    print(f"valid: {len(evals)} eval(s), {len(harnesses)} harness(es)")
    return 0


def evaluate(args: argparse.Namespace) -> int:
    """Run the selected evals, then score exactly that run.

    Args:
        args: The parsed options of `run` plus the threshold options of `score`.

    Returns:
        The exit code of the scoring: 1 if a threshold was missed, else 0.
    """
    args.stamp = run.main(args)
    return score.main(args)


def serve(args: argparse.Namespace) -> int:
    """Run the MLflow server in the foreground.

    Args:
        args: The parsed options; `mlflow` has none of its own.

    Returns:
        The exit code, 0.
    """
    del args  # Every subcommand takes the parsed options; this one has none
    mlflow_server.serve()
    return 0


def _with_mlflow(handler: Handler) -> Handler:
    """Wrap a subcommand so an MLflow server runs while it does.

    Args:
        handler: The subcommand's function, taking the parsed options.

    Returns:
        A function with the same signature.
    """

    def wrapped(args: argparse.Namespace) -> int:
        """Run the wrapped subcommand inside `mlflow_server.running`.

        Args:
            args: The parsed options.

        Returns:
            The subcommand's exit code; a non-integer result counts as 0.
        """
        with mlflow_server.running():
            result = handler(args)
        return result if isinstance(result, int) else 0

    return wrapped


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser with every subcommand.

    Returns:
        The parser; each subcommand sets `handler`.
    """
    fmt = argparse.RawDescriptionHelpFormatter
    ap = argparse.ArgumentParser(
        prog="skill-evals", description=__doc__, formatter_class=fmt
    )
    ap.add_argument(
        "--config",
        type=Path,
        help="the project's .skill-evals.yaml (default: the nearest one above the "
        "current folder)",
    )
    sub = ap.add_subparsers(required=True, metavar="COMMAND")

    p = sub.add_parser(
        "init", help="set up a project", description=init.__doc__, formatter_class=fmt
    )
    p.add_argument(
        "dir", nargs="?", default="skill-evals", help="folder (default: skill-evals)"
    )
    p.set_defaults(handler=init.main)

    p = sub.add_parser(
        "evaluate", help="run, then score that run", description=evaluate.__doc__
    )
    run.add_arguments(p)
    score.add_threshold_arguments(p)
    p.set_defaults(handler=_with_mlflow(evaluate))

    p = sub.add_parser(
        "run", help="run evals in sandboxes", description=run.__doc__, formatter_class=fmt
    )
    run.add_arguments(p)
    p.set_defaults(handler=_with_mlflow(run.main))

    p = sub.add_parser(
        "score", help="score runs' traces", description=score.__doc__, formatter_class=fmt
    )
    score.add_arguments(p)
    p.set_defaults(handler=_with_mlflow(score.main))

    p = sub.add_parser("validate", help="check eval and harness files")
    p.set_defaults(handler=validate)

    p = sub.add_parser("mlflow", help="open the MLflow server (UI) in the foreground")
    p.set_defaults(handler=serve)
    return ap


def main() -> None:
    """Parse the command line and run the chosen subcommand."""
    args = build_parser().parse_args()
    use_config(args.config)
    code = args.handler(args)
    sys.exit(code if isinstance(code, int) else 0)
