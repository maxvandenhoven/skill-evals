"""The MLflow tracking server every sandbox sends its traces to.

`running()` wraps a command that needs the server: it reuses one that is already up
(for example `skill-evals mlflow`, kept open for the UI) or starts one for the
duration of the command. `serve()` runs it in the foreground.

Why these server flags (all three matter for sandboxes):

    --host 127.0.0.1          Only reachable from this machine. Sandboxes still reach
                              it: inside a sandbox, http://host.docker.internal:5000
                              goes through the sbx host proxy to localhost:5000.
    --allowed-hosts ...       MLflow rejects requests whose Host header it doesn't
                              know (DNS-rebinding protection). Requests from a sandbox
                              carry "Host: host.docker.internal:5000", so allow it.
    --artifacts-destination   Trace payloads are uploaded as artifacts over HTTP (the
                              proxied artifact store). A plain artifact root path
                              would make clients write to a host path they can't see
                              from inside the sandbox VM.
"""

import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from skill_evals.config import MLFLOW_PORT, MLFLOW_URI, project

STARTUP_SECONDS = 60


def is_running() -> bool:
    """Check whether an MLflow server answers on MLFLOW_URI.

    Returns:
        True if its health endpoint responds with OK.
    """
    try:
        with urllib.request.urlopen(f"{MLFLOW_URI}/health", timeout=2) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False


def server_command(store: Path) -> list[str]:
    """Build the command line for an MLflow server that sandboxes can reach.

    Args:
        store: Folder for the server's SQLite database and trace artifacts.

    Returns:
        The command as an argv list, run with this Python's MLflow.
    """
    return [
        sys.executable, "-m", "mlflow", "server",
        "--host", "127.0.0.1",
        "--port", str(MLFLOW_PORT),
        "--backend-store-uri", f"sqlite:///{store / 'mlflow.db'}",
        "--artifacts-destination", str(store / "artifacts"),
        "--allowed-hosts", "localhost:*,127.0.0.1:*,host.docker.internal:*",
    ]  # fmt: skip


@contextmanager
def running() -> Generator[None]:
    """Make sure an MLflow server runs while the block executes.

    Yields:
        Nothing; the server is up inside the block.

    Raises:
        SystemExit: If a started server doesn't become healthy in time; the message
            points to its log.
    """
    if is_running():
        yield
        return
    store = project().mlflow
    store.mkdir(parents=True, exist_ok=True)
    log_path = store / "server.log"
    print(f"starting MLflow on {MLFLOW_URI} (store: {project().relative(store)})")
    with log_path.open("a") as log:
        # Its own session, so stopping it also stops the server's worker processes.
        server = subprocess.Popen(
            server_command(store),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + STARTUP_SECONDS
            while not is_running():
                if server.poll() is not None or time.monotonic() > deadline:
                    msg = f"MLflow server didn't start; see {log_path}"
                    raise SystemExit(msg)
                time.sleep(0.5)
            yield
        finally:
            _stop(server)


def _stop(server: subprocess.Popen[bytes]) -> None:
    """Stop a server started by `running`, with its worker processes.

    Args:
        server: The server process (a session leader).
    """
    if server.poll() is not None:
        return
    os.killpg(server.pid, signal.SIGTERM)
    try:
        server.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(server.pid, signal.SIGKILL)
        server.wait()


def serve() -> None:
    """Run the MLflow server in the foreground until interrupted, e.g. for its UI.

    Raises:
        SystemExit: If a server already runs on the port.
    """
    if is_running():
        msg = f"an MLflow server already runs on {MLFLOW_URI}"
        raise SystemExit(msg)
    store = project().mlflow
    store.mkdir(parents=True, exist_ok=True)
    print(
        f"MLflow UI: {MLFLOW_URI} (store: {project().relative(store)}); Ctrl+C stops it"
    )
    try:
        subprocess.run(server_command(store), check=False)
    except KeyboardInterrupt:
        pass
