"""Tests for `skill-evals init`, which sets up a project."""

import argparse
from pathlib import Path

import pytest

from skill_evals import cli, init
from skill_evals.config import (
    CONFIG_NAME,
    HARNESSES,
    discover_harnesses,
    discover_libraries,
    project,
    use_config,
)


def test_init_writes_project(tmp_path: Path) -> None:
    """Check that `init` copies harnesses and schemas and creates folders and config."""
    config = init.init(tmp_path / "tests" / "skills", tmp_path)
    target = tmp_path / "tests" / "skills"
    assert config == tmp_path / CONFIG_NAME
    assert sorted(p.name for p in target.iterdir()) == [
        "evals",
        "fixtures",
        "harnesses",
        "libraries",
        "schemas",
    ]
    for name in init.CREATED:
        assert [p.name for p in (target / name).iterdir()] == [".gitkeep"]
    shipped = sorted(p.relative_to(HARNESSES) for p in HARNESSES.rglob("*.yaml"))
    harnesses = target / "harnesses"
    copied = sorted(p.relative_to(harnesses) for p in harnesses.rglob("*.yaml"))
    assert copied == shipped
    assert not list(target.rglob("__pycache__"))
    assert config.read_text().splitlines()[0] == (
        "# yaml-language-server: $schema=tests/skills/schemas/config.schema.json"
    )


def test_init_result_validates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Check that a fresh project is valid: no evals yet, the two shipped harnesses."""
    config = init.init(tmp_path / "skill-evals", tmp_path)
    use_config(config)
    assert project().evals == tmp_path / "skill-evals" / "evals"
    assert project().scorers is None  # The scorers line is a comment
    assert list(discover_harnesses()) == ["claude", "codex"]
    assert discover_libraries() == ["none"]
    assert cli.validate(argparse.Namespace()) == 0
    assert capsys.readouterr().out == "valid: 0 eval(s), 2 harness(es)\n"


def test_init_target_outside_config_folder(tmp_path: Path) -> None:
    """Check that the config's paths are relative to it, even to a folder beside it."""
    (tmp_path / "repo").mkdir()
    config = init.init(tmp_path / "shared" / "skills", tmp_path / "repo")
    use_config(config)
    assert "evals: ../shared/skills/evals\n" in config.read_text()
    assert project().evals == tmp_path / "shared" / "skills" / "evals"


def test_init_into_existing_empty_folder(tmp_path: Path) -> None:
    """Check that an existing but empty target folder is accepted."""
    (tmp_path / "skills").mkdir()
    assert init.init(tmp_path / "skills", tmp_path).exists()


def test_init_refuses_existing_config(tmp_path: Path) -> None:
    """Check that `init` never overwrites a .skill-evals.yaml."""
    (tmp_path / CONFIG_NAME).write_text("evals: mine\n")
    with pytest.raises(SystemExit, match=f"{CONFIG_NAME} already exists"):
        init.init(tmp_path / "skills", tmp_path)
    assert (tmp_path / CONFIG_NAME).read_text() == "evals: mine\n"
    assert not (tmp_path / "skills").exists()


def test_init_refuses_non_empty_target(tmp_path: Path) -> None:
    """Check that `init` never writes into a folder that has files."""
    (tmp_path / "skills").mkdir()
    (tmp_path / "skills" / "notes.md").write_text("")
    with pytest.raises(SystemExit, match="skills is not empty"):
        init.init(tmp_path / "skills", tmp_path)
    assert not (tmp_path / CONFIG_NAME).exists()


def test_init_command_uses_current_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Check that `skill-evals init DIR` writes the config to the current folder."""
    monkeypatch.chdir(tmp_path)
    assert init.main(argparse.Namespace(dir="tests/skills")) == 0
    assert (tmp_path / CONFIG_NAME).is_file()
    assert (tmp_path / "tests" / "skills" / "harnesses" / "base.sbxenv.yaml").is_file()
    assert "created .skill-evals.yaml and tests/skills/" in capsys.readouterr().out
