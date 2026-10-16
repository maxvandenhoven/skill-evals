"""Builders for the tests: small projects in a temporary folder, recorded traces."""

import json
import textwrap
from pathlib import Path
from typing import Any

from mlflow.entities import Trace

from skill_evals.config import CONFIG_NAME, use_config

DATA = Path(__file__).resolve().parent / "data"
REPO = Path(__file__).resolve().parent.parent

# The recorded traces in tests/data/, by file name: <harness>-<eval>-<library>.
CLAUDE_SKILL = "claude-pr-matt-pocock-skills"  # Loaded mattpocock-skills:pr
CODEX_SKILL = "codex-pr-matt-pocock-skills"  # Read pr/SKILL.md
CLAUDE_BASELINE = "claude-code-review-none"  # No skill loaded
CODEX_BASELINE = "codex-code-review-none"  # No skill; no eval.trace_reader tag
TRACES = [CLAUDE_SKILL, CODEX_SKILL, CLAUDE_BASELINE, CODEX_BASELINE]

HARNESS_YAML = """\
run: [agent, -p, "{prompt}"]
inventory: [agent, --version]
trace_reader: claude
"""


def trace_dict(name: str) -> dict[str, Any]:
    """Read a recorded trace as a dict, to change it before loading it.

    Args:
        name: The file name in tests/data/, without .json.

    Returns:
        The trace in the shape of `Trace.to_dict`.
    """
    return json.loads((DATA / f"{name}.json").read_text())


def load_trace(name: str) -> Trace:
    """Load a recorded trace.

    Args:
        name: The file name in tests/data/, without .json.

    Returns:
        The trace.
    """
    return Trace.from_json((DATA / f"{name}.json").read_text())


def edited_trace(name: str, span: str, index: int = 0, **attributes: Any) -> Trace:
    """Load a recorded trace with changed span inputs or outputs.

    No recorded trace has, for example, a rejected Skill call, so the tests derive
    such traces from real ones.

    Args:
        name: The file name in tests/data/, without .json.
        span: The name of the span to change, e.g. "tool_Skill".
        index: Which of the spans with that name, from 0.
        **attributes: `inputs` and/or `outputs`, the new values; None removes them.

    Returns:
        The changed trace.
    """
    data = trace_dict(name)
    target = [s for s in data["data"]["spans"] if s["name"] == span][index]
    for key, value in attributes.items():
        attribute = f"mlflow.span{key.capitalize()}"
        if value is None:
            target["attributes"].pop(attribute, None)
        else:
            target["attributes"][attribute] = value
    return Trace.from_dict(data)


def with_skill_call(skill: str, result: str) -> Trace:
    """Load the recorded Claude Code trace with a different Skill call.

    Args:
        skill: The Skill tool's `skill` argument.
        result: The Skill tool's result.

    Returns:
        The trace with that Skill call instead of its own.
    """
    return edited_trace(
        CLAUDE_SKILL, "tool_Skill", inputs={"skill": skill}, outputs={"result": result}
    )


class ProjectBuilder:
    """A skill-evals project in a temporary folder, written file by file.

    The constructor writes .skill-evals.yaml and empty folders, and makes the project
    the current one (see `skill_evals.config.use_config`).

    Attributes:
        root: The project folder.
        config: Its .skill-evals.yaml.
    """

    def __init__(self, root: Path) -> None:
        """Create the project.

        Args:
            root: The project folder; created if missing.
        """
        self.root = root
        self.config = root / CONFIG_NAME
        for folder in ("evals", "harnesses", "libraries", "fixtures"):
            (root / folder).mkdir(parents=True, exist_ok=True)
        self.write(
            CONFIG_NAME,
            """\
            evals: evals
            harnesses: harnesses
            libraries: libraries
            fixtures: fixtures
            runs: runs
            mlflow: mlflow
            """,
        )

    def write(self, relative: str, text: str) -> Path:
        """Write a file, dedented, and make the project current again.

        Args:
            relative: The file's path in the project.
            text: Its content.

        Returns:
            The file.
        """
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text))
        use_config(self.config)  # Clears the cached project
        return path

    def add_eval(self, name: str, text: str) -> Path:
        """Write evals/<name>.yaml.

        Args:
            name: The eval's name.
            text: The eval file.

        Returns:
            The file.
        """
        return self.write(f"evals/{name}.yaml", text)

    def add_harness(self, name: str, harness_yaml: str = HARNESS_YAML) -> Path:
        """Write a harness folder with an sbxenv.yaml and a harness.yaml.

        Args:
            name: The harness's name.
            harness_yaml: The harness.yaml content.

        Returns:
            The harness folder.
        """
        self.write(
            f"harnesses/{name}/sbxenv.yaml", f'schemaVersion: "1"\nagent: {name}\n'
        )
        return self.write(f"harnesses/{name}/harness.yaml", harness_yaml).parent

    def add_library(self, name: str, *harnesses: str) -> None:
        """Write a library with a layer and a kit for each harness.

        Args:
            name: The library's name.
            *harnesses: The harnesses it supports.
        """
        for harness in harnesses:
            folder = f"libraries/{name}/{harness}"
            self.write(f"{folder}/sbxenv.yaml", 'schemaVersion: "1"\nkits: [./kit]\n')
            self.write(f"{folder}/kit/spec.yaml", f"name: {name}-{harness}\n")

    def add_fixture(self, name: str) -> Path:
        """Write a fixture kit.

        Args:
            name: The fixture's name.

        Returns:
            The kit folder.
        """
        return self.write(f"fixtures/{name}/spec.yaml", f"name: fixture-{name}\n").parent

    def add_scorers(self, code: str) -> Path:
        """Write a scorer package and point .skill-evals.yaml at it.

        Args:
            code: The package's __init__.py.

        Returns:
            The package folder.
        """
        config = self.config.read_text()
        if "scorers:" not in config:
            self.write(CONFIG_NAME, config + "scorers: scorers\n")
        return self.write("scorers/__init__.py", code).parent
