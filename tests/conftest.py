"""Shared fixtures: isolation from the repository's project and MLflow store."""

import sys
from collections.abc import Iterator
from pathlib import Path

import mlflow
import pytest

from skill_evals.config import use_config
from tests.helpers import ProjectBuilder


@pytest.fixture(autouse=True, scope="session")
def _mlflow_in_tmp(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Run in a temporary folder with a temporary MLflow store, never the repo's."""
    folder = tmp_path_factory.mktemp("cwd")
    with pytest.MonkeyPatch.context() as mp:
        # MLflow defaults to ./mlflow.db and ./mlruns, relative to the current folder.
        mp.chdir(folder)
        mp.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{folder / 'mlflow.db'}")
        yield


@pytest.fixture(autouse=True)
def _fresh_state() -> Iterator[None]:
    """Forget the project, its scorers and any MLflow URI a test set, after each test."""
    uri = mlflow.get_tracking_uri()
    yield
    use_config(None)
    sys.modules.pop("skill_evals_project_scorers", None)
    # score.main points MLflow at the real server's address; never keep that.
    if mlflow.get_tracking_uri() != uri:
        mlflow.set_tracking_uri(uri)


@pytest.fixture
def project_dir(tmp_path: Path) -> ProjectBuilder:
    """Provide an empty project in a temporary folder, made the current project.

    Returns:
        The builder for the project's files.
    """
    return ProjectBuilder(tmp_path / "project")
