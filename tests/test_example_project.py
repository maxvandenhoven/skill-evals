"""Golden tests: this repository's own example/ project, as .skill-evals.yaml sets it up.

They only read the example's files; nothing runs and nothing is written.
"""

import sys

import pytest

from skill_evals import cli
from skill_evals.config import (
    CONFIG_NAME,
    HARNESSES,
    discover_evals,
    discover_harnesses,
    eval_cases,
    eval_libraries,
    library_layer,
    project,
    scorer_registry,
    use_config,
)
from tests.helpers import REPO, TRACES, load_trace


@pytest.fixture
def example() -> None:
    """Make the repository's .skill-evals.yaml the current project."""
    use_config(REPO / CONFIG_NAME)


def test_example_validates(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`skill-evals validate` passes on the example project."""
    monkeypatch.chdir(REPO)
    monkeypatch.setattr(sys, "argv", ["skill-evals", "validate"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 0
    assert capsys.readouterr().out == "valid: 2 eval(s), 2 harness(es)\n"


@pytest.mark.usefixtures("example")
def test_example_uses_shipped_harnesses() -> None:
    """The example runs the package's own harnesses, the ones `init` copies."""
    assert project().harnesses == HARNESSES
    assert list(discover_harnesses()) == ["claude", "codex"]
    assert list(discover_evals()) == ["code-review", "pr"]


@pytest.mark.usefixtures("example")
@pytest.mark.parametrize("eval_name", ["code-review", "pr"])
def test_example_library_supports_every_harness(eval_name: str) -> None:
    """Every library of the example's evals has a layer for both harnesses."""
    assert eval_libraries(eval_name) == ["none", "matt-pocock-skills"]
    for harness in discover_harnesses():
        assert library_layer("matt-pocock-skills", harness) is not None


@pytest.mark.usefixtures("example")
def test_example_fixture_args() -> None:
    """The code-review case passes with_spec to the fixture, as sbx's string."""
    (case,) = eval_cases("code-review")
    assert case.fixture is not None
    assert (case.fixture.name, case.fixture.args) == (
        "slugify-repo",
        {"with_spec": "true"},
    )
    (case,) = eval_cases("pr")
    assert case.fixture is not None
    assert (case.fixture.name, case.fixture.args) == ("slugify-repo", {})


@pytest.mark.usefixtures("example")
@pytest.mark.parametrize("name", TRACES)
def test_example_command_ran_scorer(name: str) -> None:
    """The example's own scorer finds the git commands in every recorded run."""
    scorer = scorer_registry()["command_ran"]("git (diff|log)")
    assert scorer.name == "command_ran:git (diff|log)"
    assert scorer(trace=load_trace(name)) is True
    assert scorer_registry()["command_ran"]("rm -rf /$")(trace=load_trace(name)) is False
