"""Score the traces `skill-evals run` produced, print a table and check thresholds.

    skill-evals score                          # All evals, every run so far.
    skill-evals score --evals pr
    skill-evals score --stamp 20261011-173917  # Only that run invocation.
    skill-evals score --stamp latest           # Only the newest invocation.
    skill-evals score --stamp latest --min-pass 0.8 --summary "$GITHUB_STEP_SUMMARY"

For every cell's experiment (skill-evals/<eval>/<harness>/<library>) and each of the
eval's cases, it builds the case's scorers, runs `mlflow.genai.evaluate` over the
case's traces and prints pass rates per case, plus a total per cell when the eval has
several cases. Every assessment is also attached to its trace, for the MLflow UI.

Thresholds: a scorer's `min_pass` in the eval file (or --min-pass for scorers without
one) is the lowest acceptable pass rate in each cell WITH a library; baseline cells
are expected to fail and never gate. Any miss makes the command exit with 1.

With --stamp, the scores are appended to that invocation's report.md as Markdown;
--summary appends the same Markdown to another file, e.g. a CI job summary.
"""

import argparse
import re
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import mlflow
import pandas as pd
from mlflow.entities import Experiment

from skill_evals.config import (
    MLFLOW_URI,
    Case,
    build_scorers,
    discover_evals,
    eval_cases,
    load_eval,
    project,
    select_names,
)

Results = dict[str, list[Any]]  # Scorer name -> one value per trace

_STAMP = re.compile(r"\d{8}-\d{6}")  # The run command's <runs>/<stamp>/ folder names


@dataclass
class Row:
    """The scores of one case in one cell (or of all its cases).

    Attributes:
        eval: The eval's name.
        cell: "<harness>/<library>".
        library: The cell's library, "none" for the baseline.
        case: The case's id, or "(all cases)" for a cell's total.
        results: Each scorer's values, one per trace.
        min_pass: Gating threshold per pass/fail scorer, where one applies.
    """

    eval: str
    cell: str
    library: str
    case: str
    results: Results
    min_pass: dict[str, float] = field(default_factory=dict)

    def failed(self) -> list[str]:
        """List the scorers whose pass rate is below their threshold.

        Returns:
            The scorer names; empty for baseline cells, which never gate.
        """
        if self.library == "none":
            return []
        return [
            name
            for name, threshold in self.min_pass.items()
            if _rate(self.results.get(name, [])) < threshold
        ]

    def failures(self) -> list[str]:
        """Describe each threshold miss.

        Returns:
            One message per scorer in `failed`.
        """
        return [
            f"{self.eval} {self.cell} {self.case}: {name} passed "
            f"{format_values(self.results.get(name, []))}, below min_pass "
            f"{self.min_pass[name]:g}"
            for name in self.failed()
        ]


def _rate(values: list[Any]) -> float:
    """Compute a pass/fail scorer's pass rate.

    Args:
        values: One boolean per trace.

    Returns:
        The share of True values; 0 without values.
    """
    return sum(values) / len(values) if values else 0.0


def resolve_stamp(stamp: str) -> str:
    """Turn `latest` into the newest run invocation's stamp.

    Args:
        stamp: A stamp like 20261011-173917, or "latest".

    Returns:
        The stamp itself, or the newest <runs>/<stamp>/ that has a report.md.

    Raises:
        SystemExit: If "latest" was asked for but no run has a report yet.
    """
    if stamp != "latest":
        return stamp
    runs = sorted(
        p.parent.name
        for p in project().runs.glob("*/report.md")
        if _STAMP.fullmatch(p.parent.name)
    )
    if not runs:
        msg = "no run with a report.md yet; use `skill-evals run` first"
        raise SystemExit(msg)
    return runs[-1]


def run_traces(experiment: Experiment, stamp: str | None) -> pd.DataFrame:
    """Load the traces the run command tagged in one cell's experiment.

    Only the trace the run command picked for each run is tagged with its run
    folder (<runs>/<stamp>/<cell>-<case>-<i>). Untagged traces, e.g. Codex subagent
    sessions, would otherwise count as extra runs.

    Args:
        experiment: The cell's MLflow experiment.
        stamp: Keep only traces from this run invocation; None keeps all.

    Returns:
        The selected traces, in the frame shape `mlflow.genai.evaluate` takes.
    """
    traces = mlflow.search_traces(locations=[experiment.experiment_id])
    if traces.empty:
        return traces
    run_dirs = traces["tags"].map(lambda t: (t or {}).get("eval.run_dir", ""))
    keep = run_dirs != ""
    if stamp:
        keep &= run_dirs.map(lambda d: stamp in Path(d).parts)
    return traces[keep]


def score_case(
    experiment: Experiment, traces: pd.DataFrame, case: Case, min_pass: float | None
) -> tuple[Results, dict[str, float]]:
    """Score one case's traces in one cell.

    Logs an evaluation run into the cell's experiment and attaches one assessment
    per scorer to every trace.

    Args:
        experiment: The cell's MLflow experiment.
        traces: The case's traces, from `run_traces`.
        case: The case, whose scorers to run.
        min_pass: Threshold for scorers without their own `min_pass`, or None.

    Returns:
        Each scorer's values (one per trace), and the threshold per scorer name.
    """
    mlflow.set_experiment(experiment_id=experiment.experiment_id)
    scorers = build_scorers(case.scorers)
    # The function build_scorers keeps the specs' order, so spec i built scorer i.
    thresholds = {
        scorer.name: spec.get("min_pass", min_pass)
        for spec, scorer in zip(case.scorers, scorers, strict=False)
        if spec.get("min_pass", min_pass) is not None
    }
    df = mlflow.genai.evaluate(data=traces, scorers=scorers).result_df
    if df is None:
        return {}, thresholds
    # In the case's scorer order, the always-on diagnostics last.
    results = {
        scorer.name: df[f"{scorer.name}/value"].tolist()
        for scorer in scorers
        if f"{scorer.name}/value" in df.columns
    }
    return results, thresholds


def format_values(values: list[Any]) -> str:
    """Format one scorer's values.

    Args:
        values: One value per trace.

    Returns:
        `k/n` for pass/fail scorers, the sorted distinct values for diagnostics.
    """
    if all(isinstance(v, bool) for v in values):
        return f"{sum(values)}/{len(values)}"
    return ", ".join(sorted(set(map(str, values))))


def text_line(row: Row) -> str:
    """Format a row for the terminal.

    Args:
        row: One case in one cell.

    Returns:
        The case id, `n` and every scorer's result on one line.
    """
    if not row.results:
        return f"    {row.case:24} no traces"
    n = max(len(v) for v in row.results.values())
    parts = [f"{name}={format_values(values)}" for name, values in row.results.items()]
    return f"    {row.case:24} n={n}  " + "  ".join(parts)


def markdown(rows: list[Row]) -> str:
    """Render the scores as Markdown: one table per eval, then any threshold misses.

    Args:
        rows: Every row, grouped by eval in order.

    Returns:
        The Markdown text.
    """
    out = []
    for eval_name in dict.fromkeys(r.eval for r in rows):
        group = [r for r in rows if r.eval == eval_name]
        names = list(dict.fromkeys(n for r in group for n in r.results))
        out += [
            f"### {eval_name}",
            "",
            "| cell | case | n | " + " | ".join(f"`{n}`" for n in names) + " |",
            "|---|---|---|" + "---|" * len(names),
        ]
        for r in group:
            failed = set(r.failed())
            cells = [
                (format_values(r.results[n]) + (" ❌" if n in failed else ""))
                if n in r.results
                else ""
                for n in names
            ]
            n = max((len(v) for v in r.results.values()), default=0)
            out.append(f"| {r.cell} | {r.case} | {n} | " + " | ".join(cells) + " |")
        out.append("")
    misses = [m for r in rows for m in r.failures()]
    if misses:
        out += ["**Below threshold:**", "", *(f"- {m}" for m in misses), ""]
    return "\n".join(out)


def add_arguments(ap: argparse.ArgumentParser) -> None:
    """Add the `score` subcommand's options.

    Args:
        ap: The subcommand's parser.
    """
    ap.add_argument("--evals", help="comma-separated eval names (default: all)")
    ap.add_argument(
        "--stamp",
        help="only score traces from that run invocation ('latest' for the newest) "
        "and append the scores to its report.md",
    )
    add_threshold_arguments(ap)


def add_threshold_arguments(ap: argparse.ArgumentParser) -> None:
    """Add the options `score` and `evaluate` share.

    Args:
        ap: The subcommand's parser.
    """
    ap.add_argument(
        "--min-pass",
        type=float,
        metavar="RATE",
        help="minimum pass rate (0-1) for scorers without their own min_pass, in "
        "cells with a library; below it the command exits with 1",
    )
    ap.add_argument(
        "--summary",
        type=Path,
        metavar="FILE",
        help="also append the Markdown scores to FILE, e.g. $GITHUB_STEP_SUMMARY",
    )


def main(args: argparse.Namespace) -> int:
    """Score every cell of the selected evals; print, report and check thresholds.

    Args:
        args: The parsed options from `add_arguments`.

    Returns:
        The exit code: 1 if a threshold was missed, else 0.
    """
    stamp = resolve_stamp(args.stamp) if args.stamp else None
    evals = select_names("eval", args.evals, discover_evals())
    mlflow.set_tracking_uri(MLFLOW_URI)
    rows: list[Row] = []
    for eval_name in evals:
        spec, cases = load_eval(eval_name), eval_cases(eval_name)
        print(f"\n=== {eval_name}: {spec.get('description', '')}")
        # One experiment per cell, named skill-evals/<eval>/<harness>/<library>.
        experiments = mlflow.search_experiments(
            filter_string=f"name LIKE 'skill-evals/{eval_name}/%'"
        )
        for exp in sorted(experiments, key=lambda e: e.name):
            cell = exp.name.removeprefix(f"skill-evals/{eval_name}/")
            library = cell.split("/")[-1]
            traces = run_traces(exp, stamp)
            if stamp and traces.empty:
                continue  # A cell this run invocation didn't include
            print(f"  {cell}")
            case_ids = (
                traces["tags"].map(lambda t: (t or {}).get("eval.case", ""))
                if not traces.empty
                else pd.Series(dtype=str)
            )
            total = Row(eval_name, cell, library, "(all cases)", {})
            for case in cases:
                row = Row(eval_name, cell, library, case.id, {})
                selected = traces[case_ids == case.id] if not traces.empty else traces
                if not selected.empty:
                    row.results, row.min_pass = score_case(
                        exp, selected, case, args.min_pass
                    )
                    for name, values in row.results.items():
                        total.results.setdefault(name, []).extend(values)
                print(text_line(row))
                rows.append(row)
            if len(cases) > 1 and total.results:
                print(text_line(total))
                rows.append(total)
            unknown = int((~case_ids.isin([c.id for c in cases])).sum())
            if unknown:
                print(f"    {unknown} trace(s) of cases not in the eval file, skipped")

    text = markdown(rows)
    misses = [m for r in rows for m in r.failures()]
    command = shlex.join(["skill-evals", *sys.argv[1:]])
    if stamp:
        report = project().runs / stamp / "report.md"
        with report.open("a") as f:
            f.write(f"\n## Scores\n\n- command: `{command}`\n\n{text}")
        print(f"\nappended to {report}")
    if args.summary:
        with args.summary.open("a") as f:
            f.write(f"## skill-evals\n\n{text}")
    for miss in misses:
        print(f"below threshold: {miss}")
    return 1 if misses else 0
