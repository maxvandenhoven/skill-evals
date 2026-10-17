"""Run evals in sandboxes: every eval x harness x library, then case x repeat.

    skill-evals run                              # Everything, 1 repeat.
    skill-evals run --evals pr --harnesses codex -n 3
    skill-evals run --libraries none             # Baselines only.

Each eval lists the libraries it tests (`libraries:` in its file); the baseline
library "none" runs too, unless the eval sets `baseline: false`. --libraries only
narrows that list.

For each run it:

  1. creates an empty workspace under <runs>/<stamp>/<cell>-<case>-<i>/
  2. creates a sandbox from layered sbxenv files:
         base.sbxenv.yaml + <harness> [+ <library>/<harness>] [+ fixture layer]
     (kits inside install the CLI, tracing, the skill library and the fixture)
  3. runs the harness's one-shot command (harness.yaml `run`) with the prompt
  4. waits for the tracing hook, finds the new trace in MLflow and tags it
  5. removes the sandbox

Traces go to one MLflow experiment per cell: skill-evals/<eval>/<harness>/<library>.
Every invocation writes <runs>/<stamp>/report.md; `skill-evals score --stamp <stamp>`
scores exactly those runs, and `skill-evals evaluate` does both.

Library "none" means no library layer: the baseline (only the agent's built-ins).
"""

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

import mlflow
import yaml

from skill_evals.config import (
    MLFLOW_URI,
    Case,
    Fixture,
    discover_evals,
    discover_harnesses,
    eval_cases,
    eval_libraries,
    library_layer,
    load_harness,
    project,
    select_names,
)


@dataclass
class Cell:
    """One combination of eval, harness and library (repeated N times).

    Attributes:
        eval: Eval name, a file in the project's evals folder.
        harness: Harness name, a folder in the project's harnesses folder.
        library: Library name, a folder in the project's libraries folder, or "none".
    """

    eval: str
    harness: str
    library: str

    @property
    def experiment(self) -> str:
        """The MLflow experiment that holds this cell's traces."""
        return f"skill-evals/{self.eval}/{self.harness}/{self.library}"

    @property
    def slug(self) -> str:
        """A file- and sandbox-name-friendly id, e.g. `pr-claude-none`."""
        return f"{self.eval}-{self.harness}-{self.library}"


class Row(TypedDict):
    """How one run went, as printed and written to report.md.

    Attributes:
        cell: The cell's slug.
        case: The case's id.
        repeat: Repeat number within the case, from 1.
        trace: The tagged MLflow trace id, or None if none was found.
        exit: The agent command's exit code, or None if it never ran.
        note: What went wrong, empty when nothing did.
    """

    cell: str
    case: str
    repeat: int
    trace: str | None
    exit: int | None
    note: str


def fixture_layer(fixture: Fixture, run_dir: Path) -> Path:
    """Write the sbxenv layer that applies a case's fixture kit.

    The kit builds the workspace inside the sandbox while it is created. The layer
    is written to the run folder, so each run records exactly what it applied.

    Args:
        fixture: The case's fixture and its arguments.
        run_dir: The run's folder.

    Returns:
        The layer's path.
    """
    layer = run_dir / "fixture.sbxenv.yaml"
    kit: dict[str, object] = {"source": str(fixture.path)}
    if fixture.args:
        kit["args"] = fixture.args
    layer.write_text(
        yaml.safe_dump({"schemaVersion": "1", "kits": [kit]}, sort_keys=False)
    )
    return layer


def sbx_env(
    verb: str, layers: list[Path], name: str, env_args: dict[str, object], *extra: str
) -> list[str]:
    """Build an `sbx env <verb>` command line for this run's layered environment.

    Every `sbx env` command must name the same files, args and sandbox name, because
    sbx re-reads the environment each time. Flags go BEFORE the file paths: for
    `exec`, everything between the files and `--` is read as a path.

    Args:
        verb: The `sbx env` subcommand: "create", "exec" or "rm".
        layers: The sbxenv files, in merge order.
        name: The sandbox name.
        env_args: Values for the `args:` the layers declare, passed as --env-arg.
        *extra: sbx flags, optionally followed by "--" and the command to run.

    Returns:
        The command line as an argv list.
    """
    cmd = ["sbx", "env", verb, "--name", name]
    for key, value in env_args.items():
        cmd += ["--env-arg", f"{key}={value}"]
    split = extra.index("--") if "--" in extra else len(extra)
    flags, command = list(extra[:split]), list(extra[split:])
    return cmd + flags + list(map(str, layers)) + command


def kit_names(layers: list[Path]) -> set[str]:
    """Collect the names of all kits the given sbxenv layers apply.

    Args:
        layers: The sbxenv files of one run.

    Returns:
        The `name:` of each local kit's spec.yaml; kits without one are skipped.
    """
    names = set()
    for layer in layers:
        for kit in yaml.safe_load(layer.read_text()).get("kits") or []:
            source = kit if isinstance(kit, str) else kit.get("source", "")
            spec = layer.parent / source / "spec.yaml"
            if spec.exists():
                names.add(yaml.safe_load(spec.read_text())["name"])
    return names


def run_one(
    cell: Cell, case: Case, repeat: int, stamp: str, keep: bool, kit_args: list[str]
) -> Row:
    """Execute one eval run end to end: workspace, sandbox, agent turn, trace.

    Args:
        cell: The eval, harness and library to run.
        case: The eval's case (prompt, fixture) to run.
        repeat: Repeat number within the case, from 1.
        stamp: The invocation's timestamp, naming <runs>/<stamp>/.
        keep: Leave the sandbox running afterwards, for debugging.
        kit_args: --kit-arg overrides (`<kit>.<arg>=<value>`), passed to sbx only for
            kits this run's sandbox has.

    Returns:
        How the run went.

    Raises:
        ValueError: If the cell's library has no layer for its harness.
    """
    harness_dir, harness = discover_harnesses()[cell.harness], load_harness(cell.harness)

    # 1. MLflow experiment for this cell (created on first use).
    mlflow.set_tracking_uri(MLFLOW_URI)
    exp = mlflow.get_experiment_by_name(cell.experiment)
    if exp and exp.lifecycle_stage == "deleted":
        # MLflow keeps a deleted experiment's name reserved (creating it again
        # fails), so restore it instead, e.g. after deleting a cell to start over.
        mlflow.MlflowClient().restore_experiment(exp.experiment_id)
    exp_id = (
        exp.experiment_id
        if exp
        else mlflow.create_experiment(
            cell.experiment,
            tags={"eval": cell.eval, "harness": cell.harness, "library": cell.library},
        )
    )

    # 2. Run folder with an empty workspace; the fixture kit fills it in the sandbox.
    run_id = f"{cell.slug}-{case.id}-{repeat}"
    run_dir = project().runs / stamp / run_id
    workspace = run_dir / "workspace"
    workspace.mkdir(parents=True)

    # 3. Layered environment: base + harness (+ library) (+ fixture).
    layers = [project().base_env, harness_dir / "sbxenv.yaml"]
    if cell.library != "none":
        layer = library_layer(cell.library, cell.harness)
        if layer is None:
            msg = f"library {cell.library!r} has no layer for harness {cell.harness!r}"
            raise ValueError(msg)
        layers.append(layer)
    if case.fixture:
        layers.append(fixture_layer(case.fixture, run_dir))
    log = (run_dir / "sbx.log").open("w")
    # Sandbox names: letters, digits, hyphens, periods, at most 60 characters. A
    # hash of the full run id keeps truncated names unique.
    digest = hashlib.sha1(f"{stamp}/{run_id}".encode()).hexdigest()[:6]
    name = re.sub(r"[^a-zA-Z0-9-]", "-", f"se-{digest}-{run_id}")[:60]
    env_args: dict[str, object] = {"workspace": workspace, "experiment_id": exp_id}

    row = Row(cell=cell.slug, case=case.id, repeat=repeat, trace=None, exit=None, note="")
    try:
        # Create the sandbox: lifecycle `initialize` (host), image, kits (in sandbox).
        # --kit-arg overrides a kit's args for this run, e.g. a CLI version to try
        # before bumping the pin: claude-cli-pinned.version=2.1.297. sbx rejects an
        # override for a kit the sandbox doesn't have, so pass "<kit>.<arg>=..." only
        # to runs that include that kit.
        present = kit_names(layers)
        kit_args = [
            a
            for a in kit_args
            if "." not in a.split("=")[0] or a.split(".")[0] in present
        ]
        kit_flags = [f for arg in kit_args for f in ("--kit-arg", arg)]
        created = subprocess.run(
            sbx_env("create", layers, name, env_args, "-y", *kit_flags),
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        if created.returncode != 0:
            row["note"] = f"sandbox create failed, see {run_dir / 'sbx.log'}"
            return row

        # What did the installs actually produce? (E.g. which library version.)
        # stdin=DEVNULL on every exec: newer Codex reads a piped stdin as extra
        # prompt input and would wait forever for it to close.
        inventory = subprocess.run(
            sbx_env("exec", layers, name, env_args, "--", *harness["inventory"]),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
        ).stdout
        (run_dir / "inventory.txt").write_text(inventory)

        # 4. The eval turn itself. "{prompt}" becomes one argv element.
        command = [part.replace("{prompt}", case.prompt) for part in harness["run"]]
        started_ms = int(time.time() * 1000)
        result = subprocess.run(
            sbx_env("exec", layers, name, env_args, "--", *command),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
        )
        (run_dir / "answer.txt").write_text(result.stdout)
        (run_dir / "stderr.txt").write_text(result.stderr)
        row["exit"] = result.returncode

        # 5. Let the tracing hook finish, then find and tag this run's trace.
        time.sleep(harness.get("settle_seconds", 5))
        trace_id = find_trace(exp_id, started_ms)
        if trace_id:
            tags = {
                "eval.eval": cell.eval,
                "eval.harness": cell.harness,
                "eval.library": cell.library,
                "eval.case": case.id,
                "eval.trace_reader": harness["trace_reader"],
                "eval.repeat": str(repeat),
                "eval.exit_code": str(result.returncode),
                "eval.kit_args": " ".join(kit_args),
                "eval.run_dir": str(run_dir),
                "eval.inventory": inventory[-4000:],
            }
            for key, value in tags.items():
                mlflow.MlflowClient().set_trace_tag(trace_id, key, value)
            row["trace"] = trace_id
        else:
            row["note"] = f"no trace found; see {run_dir}/stderr.txt"
        return row
    finally:
        if not keep:
            subprocess.run(
                sbx_env("rm", layers, name, env_args, "-f"),
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        log.close()


def find_trace(exp_id: str, started_ms: int) -> str | None:
    """Find the trace of the run that started at `started_ms`.

    The runs of one cell run sequentially (see main), so within an experiment every
    trace after the start time belongs to this run. There can be more than one:
    Codex uploads a separate trace per subagent session (e.g. matt-pocock-skills'
    code-review spawns Standards and Spec reviewers), with the same request and no
    parent link. The main session starts first, so take the oldest. A small margin
    covers clock skew between the sandbox VM and the host.

    Args:
        exp_id: The cell's MLflow experiment id.
        started_ms: When the agent command started, in Unix milliseconds.

    Returns:
        The trace id, or None if no trace arrived.
    """
    traces = mlflow.search_traces(
        locations=[exp_id],
        filter_string=f"timestamp_ms > {started_ms - 5000}",
        order_by=["timestamp_ms ASC"],
        max_results=1,
        return_type="list",
    )
    return traces[0].info.trace_id if traces else None


def write_report(stamp: str, started: dt.datetime, rows: list[Row]) -> Path:
    """Write <runs>/<stamp>/report.md: what ran and how each run went.

    `skill-evals score --stamp <stamp>` appends the scores for exactly these runs.

    Args:
        stamp: The invocation's timestamp.
        started: When the invocation started.
        rows: One row per run.

    Returns:
        The report's path.
    """
    sbx = subprocess.run(["sbx", "version"], capture_output=True, text=True).stdout
    finished = dt.datetime.now()
    lines = [
        f"# skill-evals run {stamp}",
        "",
        f"- command: `{shlex.join(['skill-evals', *sys.argv[1:]])}`",
        f"- started: {started:%Y-%m-%d %H:%M:%S}, finished: {finished:%Y-%m-%d %H:%M:%S}",
        f"- {sbx.strip()}",
        f"- MLflow: {MLFLOW_URI} (experiments skill-evals/<eval>/<harness>/<library>)",
        "",
        "## Runs",
        "",
        "| cell | case | # | exit | trace | note |",
        "|---|---|---|---|---|---|",
        *(
            f"| {r['cell']} | {r['case']} | {r['repeat']} "
            f"| {'' if r['exit'] is None else r['exit']} "
            f"| {r['trace'] or ''} | {r['note']} |"
            for r in rows
        ),
        "",
    ]
    path = project().runs / stamp / "report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))
    return path


def add_arguments(ap: argparse.ArgumentParser) -> None:
    """Add the `run` subcommand's options.

    Args:
        ap: The subcommand's parser.
    """
    ap.add_argument("--evals", help="comma-separated eval names (default: all)")
    ap.add_argument("--harnesses", help="comma-separated harness names (default: all)")
    ap.add_argument(
        "--cases", help="comma-separated case ids to run (default: every case)"
    )
    ap.add_argument(
        "--libraries",
        help="comma-separated; only run these of each eval's libraries, e.g. 'none' "
        "for baselines only (default: each eval's own list, plus its baseline)",
    )
    ap.add_argument(
        "-n", "--repeats", type=int, default=1, help="runs per case (default 1)"
    )
    ap.add_argument(
        "--parallel", type=int, default=4, help="cells run concurrently (default 4)"
    )
    ap.add_argument(
        "--keep",
        action="store_true",
        help="keep sandboxes for debugging (sbx ls / sbx exec)",
    )
    ap.add_argument(
        "--kit-arg",
        action="append",
        default=[],
        metavar="KIT.ARG=VALUE",
        help="override a kit argument, e.g. claude-cli-pinned.version=2.1.297 "
        "(repeatable)",
    )


def main(args: argparse.Namespace) -> str:
    """Run every selected cell and write the report.

    Args:
        args: The parsed options from `add_arguments`.

    Returns:
        The invocation's stamp, naming its run folder.

    Raises:
        SystemExit: If a name in an option doesn't exist, or the selection leaves
            nothing to run.
    """
    evals = select_names("eval", args.evals, discover_evals())
    harnesses = select_names("harness", args.harnesses, discover_harnesses())
    known_libraries = {lib for e in evals for lib in eval_libraries(e)}
    only = set(select_names("library", args.libraries, sorted(known_libraries)))
    known_cases = {c.id for e in evals for c in eval_cases(e)}
    wanted = set(select_names("case", args.cases, sorted(known_cases)))
    cells = []
    for e in evals:
        libraries = [lib for lib in eval_libraries(e) if lib in only]
        for h in harnesses:
            for lib in libraries:
                if lib != "none" and not library_layer(lib, h):
                    print(f"skip {e}/{h}/{lib}: library has no layer for this harness")
                    continue
                cells.append(Cell(e, h, lib))
    if not cells:
        msg = "nothing to run: no selected eval, harness and library make a cell"
        raise SystemExit(msg)

    started = dt.datetime.now()
    stamp = started.strftime("%Y%m%d-%H%M%S")
    cases = {
        e: [c for c in eval_cases(e) if c.id in wanted]
        for e in {cell.eval for cell in cells}
    }
    total = sum(len(cases[cell.eval]) for cell in cells) * args.repeats
    runs = project().relative(project().runs / stamp)
    print(f"{len(cells)} cell(s), {total} run(s); run files in {runs}/")

    def run_cell(cell: Cell) -> list[Row]:
        """Run every case of one cell, each repeated, one run after another.

        Sequential runs keep find_trace from mixing them up; different cells run
        in parallel.

        Args:
            cell: The cell to run.

        Returns:
            One row per run.
        """
        rows = []
        for case in cases[cell.eval]:
            for i in range(1, args.repeats + 1):
                row = run_one(cell, case, i, stamp, args.keep, args.kit_arg)
                print(
                    f"  {row['cell']:32} {case.id:20} #{i}  exit={row['exit']}  "
                    f"trace={row['trace']}  {row['note']}",
                    flush=True,
                )
                rows.append(row)
        return rows

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as pool:
        rows = [r for rs in pool.map(run_cell, cells) for r in rs]

    found = sum(1 for r in rows if r["trace"])
    report = write_report(stamp, started, rows)
    print(f"\ndone: {found}/{len(rows)} runs produced a trace. Report: {report}")
    return stamp
