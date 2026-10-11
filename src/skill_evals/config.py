"""The project being evaluated: its .skill-evals.yaml and the folders it points to.

A project is any repository with a `.skill-evals.yaml` (see `skill-evals init`). The
file names the folders that hold its evals, harnesses, libraries and fixtures, and
optionally its own scorers; paths are relative to the file:

    evals: tests/skill-evals/evals
    harnesses: tests/skill-evals/harnesses
    libraries: tests/skill-evals/libraries
    fixtures: tests/skill-evals/fixtures
    scorers: tests/skill-evals/scorers  # Optional: extra scorers
    runs: .skill-evals/runs             # Optional: run folders (this default)
    mlflow: .skill-evals/mlflow         # Optional: MLflow store (this default)

The folder layout *is* the configuration: evals are discovered as <evals>/*.yaml,
harnesses, libraries and fixtures as folders. Eval files and harness.yaml are
validated against the schemas shipped with this package.
"""

import importlib.util
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

import jsonschema
import yaml
from mlflow.genai.scorers import Scorer

from skill_evals import scorers as builtin_scorers

CONFIG_NAME = ".skill-evals.yaml"
PACKAGE = Path(__file__).resolve().parent
HARNESSES = PACKAGE / "harnesses"  # The shipped harnesses, which `init` copies
SCHEMAS = PACKAGE / "schemas"
MLFLOW_PORT = 5000  # Fixed: base.sbxenv.yaml points sandboxes at this port
MLFLOW_URI = f"http://127.0.0.1:{MLFLOW_PORT}"  # Host side


@dataclass(frozen=True)
class Project:
    """A project's folders, resolved from its .skill-evals.yaml.

    Attributes:
        root: The folder holding .skill-evals.yaml; relative paths start here.
        evals: Folder of eval files (<name>.yaml).
        harnesses: Folder of harnesses, plus the shared base.sbxenv.yaml.
        libraries: Folder of skill libraries.
        fixtures: Folder of fixture kits.
        scorers: Optional Python package with extra scorers (a REGISTRY dict).
        runs: Where each invocation's run folders and report.md go.
        mlflow: Where the managed MLflow server keeps its database and artifacts.
    """

    root: Path
    evals: Path
    harnesses: Path
    libraries: Path
    fixtures: Path
    scorers: Path | None
    runs: Path
    mlflow: Path

    @property
    def base_env(self) -> Path:
        """The sbxenv layer every sandbox starts from."""
        return self.harnesses / "base.sbxenv.yaml"

    def relative(self, path: Path) -> str:
        """Show a path relative to the project root, for messages.

        Args:
            path: A path inside or outside the project.

        Returns:
            The relative path if it is inside the project, else the path itself.
        """
        return (
            str(path.relative_to(self.root))
            if path.is_relative_to(self.root)
            else str(path)
        )


_config_path: Path | None = None  # Set by `use_config`, e.g. from --config


def use_config(path: Path | None) -> None:
    """Choose the .skill-evals.yaml to use instead of searching for one.

    Args:
        path: The config file, or None to search upwards from the current folder.
    """
    global _config_path
    _config_path = path.resolve() if path else None
    project.cache_clear()


def find_config(start: Path) -> Path:
    """Find .skill-evals.yaml in `start` or the nearest folder above it.

    Args:
        start: Where to start looking.

    Returns:
        The config file's path.

    Raises:
        SystemExit: If there is none; the message points to `skill-evals init`.
    """
    for folder in [start, *start.parents]:
        if (folder / CONFIG_NAME).is_file():
            return folder / CONFIG_NAME
    msg = f"no {CONFIG_NAME} in {start} or above; create one with `skill-evals init`"
    raise SystemExit(msg)


@cache
def project() -> Project:
    """Load the current project, once.

    Returns:
        The project of the chosen config file (see `use_config`), or of the nearest
        .skill-evals.yaml above the current folder.
    """
    path = _config_path or find_config(Path.cwd().resolve())
    data = load_yaml(path, "config.schema.json")
    root = path.parent

    def folder(key: str, default: str | None = None) -> Path:
        """Resolve one configured folder.

        Args:
            key: The config key.
            default: Path to use when the key is absent.

        Returns:
            The absolute folder path.
        """
        return (root / data.get(key, default)).resolve()

    return Project(
        root=root,
        evals=folder("evals"),
        harnesses=folder("harnesses"),
        libraries=folder("libraries"),
        fixtures=folder("fixtures"),
        scorers=folder("scorers") if "scorers" in data else None,
        runs=folder("runs", ".skill-evals/runs"),
        mlflow=folder("mlflow", ".skill-evals/mlflow"),
    )


def discover_evals() -> dict[str, Path]:
    """Find the evals: every <evals>/<name>.yaml.

    Returns:
        Eval name mapped to its file, sorted by name.
    """
    return {p.stem: p for p in sorted(project().evals.glob("*.yaml"))}


def discover_harnesses() -> dict[str, Path]:
    """Find the harnesses: every <harnesses>/<name>/ with sbxenv.yaml and harness.yaml.

    Returns:
        Harness name mapped to its folder, sorted by name.
    """
    return {
        p.parent.name: p.parent
        for p in sorted(project().harnesses.glob("*/harness.yaml"))
        if (p.parent / "sbxenv.yaml").exists()
    }


def discover_libraries() -> list[str]:
    """Find the skill libraries: every folder in <libraries>/.

    Returns:
        "none" (the baseline without a library), then the library names, sorted.
    """
    folders = project().libraries.iterdir() if project().libraries.is_dir() else []
    return ["none"] + sorted(p.name for p in folders if p.is_dir())


def discover_fixtures() -> dict[str, Path]:
    """Find the fixtures: every <fixtures>/<name>/ with a kit spec.yaml.

    Returns:
        Fixture name mapped to its kit folder, sorted by name.
    """
    return {
        p.parent.name: p.parent for p in sorted(project().fixtures.glob("*/spec.yaml"))
    }


def library_layer(library: str, harness: str) -> Path | None:
    """Find a library's sbxenv layer for one harness.

    Args:
        library: Library name, a folder in <libraries>/.
        harness: Harness name, a folder in <harnesses>/.

    Returns:
        The layer's path, or None if the library doesn't support the harness.
    """
    layer = project().libraries / library / harness / "sbxenv.yaml"
    return layer if layer.exists() else None


@cache
def _schema(name: str) -> dict[str, Any]:
    """Read a JSON Schema shipped with the package.

    Args:
        name: The schema's file name, e.g. "eval.schema.json".

    Returns:
        The parsed schema.
    """
    return json.loads((SCHEMAS / name).read_text())


def load_yaml(path: Path, schema: str) -> dict[str, Any]:
    """Read a YAML file and validate it against one of the package's schemas.

    Args:
        path: The YAML file.
        schema: The schema's file name, e.g. "eval.schema.json".

    Returns:
        The parsed, valid content.

    Raises:
        SystemExit: If the file doesn't match the schema; the message names the
            file and the offending field.
    """
    data = yaml.safe_load(path.read_text())
    try:
        jsonschema.validate(data, _schema(schema))
    except jsonschema.ValidationError as e:
        where = "/".join(map(str, e.absolute_path)) or "(top level)"
        msg = f"{path}: {where}: {e.message}"
        raise SystemExit(msg) from e
    return data


@dataclass(frozen=True)
class Fixture:
    """A fixture kit plus the arguments one case passes it.

    Attributes:
        name: The fixture's folder name.
        path: The kit folder.
        args: Kit arguments, as the strings sbx expects.
    """

    name: str
    path: Path
    args: dict[str, str]


@dataclass(frozen=True)
class Case:
    """One prompt of an eval, with the defaults it inherits filled in.

    Attributes:
        id: Unique within the eval; names run folders and the trace tag eval.case.
        prompt: The non-interactive prompt the agent gets.
        fixture: The kit that builds the workspace, or None for an empty workspace.
        scorers: The scorer specs for this case's traces.
    """

    id: str
    prompt: str
    fixture: Fixture | None
    scorers: list[dict[str, Any]]


def load_eval(name: str) -> dict[str, Any]:
    """Read and validate <evals>/<name>.yaml.

    Beyond the schema, checks what JSON Schema can't: unique case ids, every case
    ending up with scorers, that the libraries, fixtures and scorers it names exist,
    and that the scorers can be built with the given arguments.

    Args:
        name: The eval's name.

    Returns:
        The eval's spec, as written.

    Raises:
        SystemExit: If the eval is invalid; the message lists every problem, each
            with the file and field.
    """
    path = discover_evals()[name]
    spec = load_yaml(path, "eval.schema.json")
    where = project().relative(path)

    problems = []
    if not spec["libraries"] and not spec.get("baseline", True):
        problems.append("baseline: false and no libraries, so nothing would run")
    if unknown := sorted(set(spec["libraries"]) - set(discover_libraries())):
        problems.append(f"libraries: no such library: {', '.join(unknown)}")
    ids = [case["id"] for case in spec["cases"]]
    if duplicates := sorted({i for i in ids if ids.count(i) > 1}):
        problems.append(f"cases: duplicate id: {', '.join(duplicates)}")
    fixtures, registry = discover_fixtures(), scorer_registry()
    for i, case in enumerate(spec["cases"]):
        label = f"cases/{i} ({case['id']})"
        fixture = case.get("fixture", spec.get("fixture"))
        fixture_name = (
            fixture if isinstance(fixture, str) else (fixture or {}).get("name")
        )
        if fixture_name and fixture_name not in fixtures:
            problems.append(f"{label}: no such fixture: {fixture_name}")
        specs = case.get("scorers", spec.get("scorers"))
        if specs is None:
            problems.append(f"{label}: no scorers and no default")
        elif unknown := sorted({s["name"] for s in specs} - set(registry)):
            problems.append(f"{label}: no such scorer: {', '.join(unknown)}")
        else:
            # Build the scorers once, so wrong arguments surface before any run.
            try:
                builtin_scorers.build_scorers(specs, registry)
            except Exception as e:  # Any error from a factory means a bad config
                problems.append(f"{label}: scorers: {type(e).__name__}: {e}")
    if problems:
        msg = "\n".join(f"{where}: {problem}" for problem in problems)
        raise SystemExit(msg)
    return spec


def _fixture(value: str | dict[str, Any] | None) -> Fixture | None:
    """Resolve an eval file's `fixture:` value.

    Args:
        value: A fixture name, a mapping with `name` and `args`, or None.

    Returns:
        The fixture, or None for an empty workspace.
    """
    if value is None:
        return None
    spec = {"name": value} if isinstance(value, str) else value
    args = {
        key: str(arg).lower() if isinstance(arg, bool) else str(arg)
        for key, arg in (spec.get("args") or {}).items()
    }
    return Fixture(name=spec["name"], path=discover_fixtures()[spec["name"]], args=args)


def eval_cases(name: str) -> list[Case]:
    """List an eval's cases, with the top-level defaults filled in.

    A case's own `fixture` or `scorers` replaces the default; they aren't merged.

    Args:
        name: The eval's name.

    Returns:
        The cases in file order.
    """
    spec = load_eval(name)
    return [
        Case(
            id=case["id"],
            prompt=case["prompt"],
            fixture=_fixture(case.get("fixture", spec.get("fixture"))),
            scorers=case.get("scorers", spec.get("scorers")),
        )
        for case in spec["cases"]
    ]


def eval_libraries(name: str) -> list[str]:
    """List the libraries an eval runs with.

    Args:
        name: The eval's name.

    Returns:
        "none" (the baseline without a library) unless the eval sets `baseline:
        false`, then the eval's `libraries`.
    """
    spec = load_eval(name)
    baseline = ["none"] if spec.get("baseline", True) else []
    return baseline + spec["libraries"]


def load_harness(name: str) -> dict[str, Any]:
    """Read and validate <harnesses>/<name>/harness.yaml.

    Args:
        name: The harness's name.

    Returns:
        The harness's run settings.
    """
    return load_yaml(discover_harnesses()[name] / "harness.yaml", "harness.schema.json")


def _project_scorers() -> ModuleType | None:
    """Import the project's scorer package, if it configures one.

    It is loaded by path, once, as `skill_evals_project_scorers`, so its modules can
    import each other relatively.

    Returns:
        The package, or None if the project has no `scorers` folder.

    Raises:
        ImportError: If its __init__.py can't be loaded.
    """
    folder = project().scorers
    if folder is None:
        return None
    name = "skill_evals_project_scorers"
    if name in sys.modules:
        return sys.modules[name]
    init = folder / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        name, init, submodule_search_locations=[str(folder)]
    )
    if spec is None or spec.loader is None:
        msg = f"cannot load {init}"
        raise ImportError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def scorer_registry() -> dict[str, Callable[..., Scorer]]:
    """Collect every scorer an eval can name.

    Returns:
        The built-in scorers, plus the project's (its package's REGISTRY), which win
        on a name clash.
    """
    extra = _project_scorers()
    return {**builtin_scorers.REGISTRY, **(getattr(extra, "REGISTRY", None) or {})}


def build_scorers(specs: list[dict[str, Any]]) -> list[Scorer]:
    """Build a case's scorers, plus the always-on diagnostics.

    Args:
        specs: The case's `scorers` list.

    Returns:
        One scorer per spec, in order, followed by the diagnostics.
    """
    return builtin_scorers.build_scorers(specs, scorer_registry())
