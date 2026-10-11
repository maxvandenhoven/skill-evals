"""`skill-evals init`: set up a project to evaluate skills in.

    skill-evals init                 # Folders in ./skill-evals/
    skill-evals init tests/skills    # Folders in ./tests/skills/

Copies the shipped harnesses (Claude Code, Codex) and the JSON Schemas (for editor
completion) into the folder, creates empty evals/, libraries/ and fixtures/ folders
for your own, and writes .skill-evals.yaml in the current folder, pointing at them.
Everything it creates is yours to edit; the package only reads it. For a worked
example, see example/ in the skill-evals repository.
"""

import argparse
import os
import shutil
from pathlib import Path

from skill_evals.config import CONFIG_NAME, HARNESSES, SCHEMAS

COPIED = {"harnesses": HARNESSES, "schemas": SCHEMAS}
CREATED = ("evals", "libraries", "fixtures")


def init(target: Path, config_dir: Path) -> Path:
    """Set up the project folders in `target` and write the project config.

    Args:
        target: Folder for the harnesses, schemas, evals, libraries and fixtures.
        config_dir: Folder for .skill-evals.yaml, usually the repository root.

    Returns:
        The written config file.

    Raises:
        SystemExit: If the config already exists or `target` isn't empty.
    """
    config = config_dir / CONFIG_NAME
    if config.exists():
        msg = f"{config} already exists"
        raise SystemExit(msg)
    if target.exists() and any(target.iterdir()):
        msg = f"{target} is not empty"
        raise SystemExit(msg)
    for name, source in COPIED.items():
        shutil.copytree(
            source, target / name, ignore=shutil.ignore_patterns("__pycache__")
        )
    for name in CREATED:
        (target / name).mkdir(parents=True)
        (target / name / ".gitkeep").touch()  # So git keeps the empty folder
    rel = Path(os.path.relpath(target.resolve(), config_dir.resolve())).as_posix()
    config.write_text(
        f"# yaml-language-server: $schema={rel}/schemas/config.schema.json\n"
        "# Where skill-evals finds this project's evals, harnesses, libraries and\n"
        "# fixtures. Paths are relative to this file.\n"
        f"evals: {rel}/evals\n"
        f"harnesses: {rel}/harnesses\n"
        f"libraries: {rel}/libraries\n"
        f"fixtures: {rel}/fixtures\n"
        f"# scorers: {rel}/scorers  # Optional: a package with your own scorers\n"
    )
    return config


def main(args: argparse.Namespace) -> int:
    """Run `init` and print the next steps.

    Args:
        args: The parsed options: `dir`.

    Returns:
        The exit code, 0.
    """
    config = init(Path(args.dir), Path.cwd())
    print(f"created {config.name} and {args.dir}/: harnesses and schemas (copied),")
    print("  evals, libraries and fixtures (empty, for yours)")
    print("next:")
    print("  echo .skill-evals/ >> .gitignore   # Run folders and the MLflow store")
    print("  sbx login && sbx secret ls          # Sandbox login, agent credentials")
    print(
        "  add a library, a fixture and an eval (see example/ in the skill-evals repo),"
    )
    print("  then: skill-evals evaluate")
    return 0
