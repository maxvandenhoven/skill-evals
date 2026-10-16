"""Tests for the MLflow server helpers that don't start a server."""

import sys
from pathlib import Path

import pytest

from skill_evals import mlflow_server


def test_server_command_reachable_from_sandboxes() -> None:
    """The server listens locally, accepts the sandbox host and proxies artifacts."""
    store = Path("/store")
    assert mlflow_server.server_command(store) == [
        sys.executable, "-m", "mlflow", "server",
        "--host", "127.0.0.1",
        "--port", "5000",
        "--backend-store-uri", "sqlite:////store/mlflow.db",
        "--artifacts-destination", "/store/artifacts",
        "--allowed-hosts", "localhost:*,127.0.0.1:*,host.docker.internal:*",
    ]  # fmt: skip


def test_running_reuses_a_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """With a server already up, nothing is started and no project is needed."""
    monkeypatch.setattr(mlflow_server, "is_running", lambda: True)
    monkeypatch.setattr(mlflow_server.subprocess, "Popen", None)  # Starting would fail
    with mlflow_server.running():
        pass
