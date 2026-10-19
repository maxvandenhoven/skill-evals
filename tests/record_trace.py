"""Record a real trace from the project's MLflow store as test data.

    make record-trace RUN=.runs/<stamp>/<cell>-<case>-<i>        # By run folder
    make record-trace RUN=tr-50f2b4b57b2b3797f5ff9fbcd19a00be NAME=x  # By trace id

The trace reader and scorer tests run against real traces in tests/data/, so that a
change in how an agent or its MLflow connector shapes traces shows up as a failing
test. After upgrading an agent, run its evals and record one of the new traces with
this script to refresh the data.

The script reads the store of the project's .skill-evals.yaml directly, without an
MLflow server: the trace's info from a copy of its SQLite database, its spans from
the artifact the server stored. It finds the trace by its run folder (the tag
eval.run_dir that `skill-evals run` sets) or takes a trace id.

Before writing tests/data/<name>.json it scrubs the trace: the project and home
folders become /project and /home/user, the user name becomes "user", e-mail
addresses become user@example.com and anything shaped like a credential becomes
<redacted>. The scores of earlier runs (assessments) are dropped. Check the result
before committing it.
"""

import argparse
import getpass
import json
import re
import shutil
import tempfile
from pathlib import Path

from mlflow.entities import Trace, TraceData, TraceInfo
from mlflow.store.tracking.sqlalchemy_store import SqlAlchemyStore

from skill_evals.config import project

DATA = Path(__file__).resolve().parent / "data"

_EMAIL = re.compile(r"[\w.%+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}\b")
_SECRETS = [
    re.compile(pattern)
    for pattern in (
        r"sk-(?:ant-|proj-)?[\w-]{20,}",  # Anthropic and OpenAI keys
        r"gh[pousr]_\w{20,}|github_pat_\w{20,}",  # GitHub tokens
        r"xox[abposr]-[\w-]{10,}",  # Slack tokens
        r"AKIA[0-9A-Z]{16}",  # AWS access key ids
        r"eyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{10,}",  # JWTs, e.g. OAuth tokens
        r"(?i)bearer\s+[\w.~+/-]{16,}=*",
    )
]


def scrub(text: str, root: Path, home: Path, user: str) -> str:
    """Remove host details and credentials from a serialised trace.

    Args:
        text: The trace as JSON.
        root: The project folder, replaced by /project.
        home: The home folder, replaced by /home/user.
        user: The user name, replaced by "user" where it is a whole word.

    Returns:
        The scrubbed JSON.
    """
    text = text.replace(str(root), "/project").replace(str(home), "/home/user")
    text = re.sub(rf"\b{re.escape(user)}\b", "user", text)
    text = _EMAIL.sub("user@example.com", text)
    for secret in _SECRETS:
        text = secret.sub("<redacted>", text)
    return text


def find_trace_id(store: SqlAlchemyStore, run_dir: Path) -> str:
    """Find the trace that `skill-evals run` tagged with a run folder.

    Args:
        store: The project's tracking store.
        run_dir: The run folder, <runs>/<stamp>/<cell>-<case>-<i>.

    Returns:
        The trace id.

    Raises:
        SystemExit: If no trace carries the run folder.
    """
    experiments = [e.experiment_id for e in store.search_experiments()]
    infos, _ = store.search_traces(
        locations=experiments,
        filter_string=f"tag.`eval.run_dir` = '{run_dir}'",
        max_results=1,
    )
    if not infos:
        msg = f"no trace is tagged with the run folder {run_dir}"
        raise SystemExit(msg)
    return infos[0].trace_id


def load_trace(source: str) -> Trace:
    """Load a trace from the project's MLflow store, without a server.

    Args:
        source: A trace id (tr-...) or the run folder of the trace.

    Returns:
        The trace, with its info and spans.

    Raises:
        SystemExit: If the trace's spans aren't in the store's artifacts.
    """
    store_dir = project().mlflow
    with tempfile.TemporaryDirectory() as tmp:
        # A copy, because opening the store can migrate its database.
        db = Path(tmp) / "mlflow.db"
        shutil.copy(store_dir / "mlflow.db", db)
        store = SqlAlchemyStore(f"sqlite:///{db}", str(Path(tmp) / "artifacts"))
        trace_id = (
            source
            if source.startswith("tr-")
            else find_trace_id(store, Path(source).resolve())
        )
        info: TraceInfo = store.get_trace_info(trace_id)
        store.engine.dispose()
    # The server stores mlflow-artifacts:/<path> under its artifacts destination.
    location = info.tags["mlflow.artifactLocation"].removeprefix("mlflow-artifacts:/")
    spans = store_dir / "artifacts" / location / "traces.json"
    if not spans.is_file():
        msg = f"{trace_id}: no spans at {spans}"
        raise SystemExit(msg)
    return Trace(info=info, data=TraceData.from_dict(json.loads(spans.read_text())))


def record(source: str, name: str | None) -> Path:
    """Write a scrubbed copy of a trace to tests/data/.

    Args:
        source: A trace id (tr-...) or the run folder of the trace.
        name: The file name without .json; by default <harness>-<eval>-<library>.

    Returns:
        The written file.
    """
    trace = load_trace(source)
    trace.info.assessments = []
    tags = trace.info.tags
    name = name or "-".join(tags[f"eval.{key}"] for key in ("harness", "eval", "library"))
    home = Path.home()
    # Sorted keys, because the store returns tags and metadata in no fixed order.
    text = json.dumps(json.loads(trace.to_json()), indent=2, sort_keys=True)
    text = scrub(text, project().root, home, getpass.getuser())
    path = DATA / f"{name}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(text + "\n")
    return path


def main() -> None:
    """Parse the command line and record the trace."""
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("source", help="the trace's run folder, or its id (tr-...)")
    ap.add_argument(
        "--name",
        help="file name in tests/data/, without .json (default: "
        "<harness>-<eval>-<library>)",
    )
    args = ap.parse_args()
    path = record(args.source, args.name)
    print(f"wrote {project().relative(path)}; check it before committing")


if __name__ == "__main__":
    main()
