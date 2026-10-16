"""Tests for the project config: .skill-evals.yaml and the files it points to."""

from pathlib import Path

import pytest

from skill_evals.config import (
    CONFIG_NAME,
    Fixture,
    build_scorers,
    discover_evals,
    discover_fixtures,
    discover_harnesses,
    discover_libraries,
    eval_cases,
    eval_libraries,
    find_config,
    library_layer,
    load_eval,
    load_harness,
    project,
    scorer_registry,
    use_config,
)
from tests.helpers import ProjectBuilder

# A project scorer package, like example/scorers.
PROJECT_SCORERS = """\
from mlflow.genai.scorers import Scorer, scorer


def always(value: bool) -> Scorer:
    @scorer(name="always")
    def _always(trace) -> bool:
        return value

    return _always


def answer_matches(pattern: str) -> Scorer:
    return always(True)


REGISTRY = {"always": always, "answer_matches": answer_matches}
"""


def eval_text(tail: str, libraries: str = "[]") -> str:
    """Build an eval file with a default scorer and a case `one`.

    Args:
        tail: YAML appended to the file: more keys of case `one`, or more cases.
        libraries: The `libraries` value.

    Returns:
        The eval file.
    """
    return (
        f"libraries: {libraries}\n"
        "scorers: [{ name: answer_matches, args: { pattern: done } }]\n"
        "cases:\n"
        "  - id: one\n"
        "    prompt: Do it.\n"
        f"{tail}"
    )


@pytest.mark.parametrize("depth", [0, 1, 3])
def test_find_config_searches_upwards(tmp_path: Path, depth: int) -> None:
    """The nearest .skill-evals.yaml in the start folder or above is found."""
    (tmp_path / CONFIG_NAME).write_text("")
    start = tmp_path.joinpath(*["sub"] * depth)
    start.mkdir(parents=True, exist_ok=True)
    assert find_config(start) == tmp_path / CONFIG_NAME


def test_find_config_without_one_points_to_init(tmp_path: Path) -> None:
    """Without a config anywhere above, the error suggests `skill-evals init`."""
    with pytest.raises(SystemExit, match="create one with `skill-evals init`"):
        find_config(tmp_path)


def test_project_resolves_folders_relative_to_config(project_dir: ProjectBuilder) -> None:
    """Configured folders resolve against the config file's folder."""
    p = project()
    root = project_dir.root
    assert p.root == root
    assert (p.evals, p.harnesses, p.libraries, p.fixtures) == (
        root / "evals",
        root / "harnesses",
        root / "libraries",
        root / "fixtures",
    )
    assert (p.runs, p.mlflow, p.scorers) == (root / "runs", root / "mlflow", None)
    assert p.base_env == root / "harnesses" / "base.sbxenv.yaml"


def test_project_defaults_for_runs_and_mlflow(tmp_path: Path) -> None:
    """Without `runs` and `mlflow`, both live under .skill-evals/."""
    path = tmp_path / CONFIG_NAME
    path.write_text("evals: e\nharnesses: h\nlibraries: l\nfixtures: f\nscorers: s\n")
    use_config(path)
    p = project()
    assert p.runs == tmp_path / ".skill-evals" / "runs"
    assert p.mlflow == tmp_path / ".skill-evals" / "mlflow"
    assert p.scorers == tmp_path / "s"


def test_project_found_from_current_folder(
    project_dir: ProjectBuilder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without --config, the project is the nearest config above the current folder."""
    use_config(None)
    monkeypatch.chdir(project_dir.root / "evals")
    assert project().root == project_dir.root


def test_relative_paths_for_messages(project_dir: ProjectBuilder, tmp_path: Path) -> None:
    """Paths inside the project are shown relative to it, others in full."""
    assert project().relative(project_dir.root / "evals" / "pr.yaml") == "evals/pr.yaml"
    assert project().relative(tmp_path / "elsewhere") == str(tmp_path / "elsewhere")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (
            "evals: e\nharnesses: h\nlibraries: l\n",
            "(top level): 'fixtures' is a required",
        ),
        (
            "evals: 3\nharnesses: h\nlibraries: l\nfixtures: f\n",
            "evals: 3 is not of type",
        ),
        (
            "evals: e\nharnesses: h\nlibraries: l\nfixtures: f\nrun: r\n",
            "(top level): Additional properties are not allowed ('run'",
        ),
    ],
)
def test_invalid_config_names_file_and_field(
    tmp_path: Path, text: str, message: str
) -> None:
    """A config that breaks the schema stops with the file and offending field."""
    path = tmp_path / CONFIG_NAME
    path.write_text(text)
    use_config(path)
    with pytest.raises(SystemExit) as exc:
        project()
    assert str(exc.value).startswith(f"{path}: ")
    assert message in str(exc.value)


def test_discover_evals_finds_yaml_files_sorted(project_dir: ProjectBuilder) -> None:
    """Evals are the evals folder's *.yaml files, by name; other files are ignored."""
    for name in ("b.yaml", "a.yaml", "notes.md", "c.yml"):
        project_dir.write(f"evals/{name}", "")
    assert list(discover_evals()) == ["a", "b"]
    assert discover_evals()["a"] == project_dir.root / "evals" / "a.yaml"


def test_discover_harnesses_needs_both_files(project_dir: ProjectBuilder) -> None:
    """A harness is a folder with both sbxenv.yaml and harness.yaml."""
    project_dir.add_harness("full")
    project_dir.write("harnesses/no-sbxenv/harness.yaml", "")
    project_dir.write("harnesses/no-harness/sbxenv.yaml", "")
    assert discover_harnesses() == {"full": project_dir.root / "harnesses" / "full"}


def test_discover_libraries_starts_with_baseline(project_dir: ProjectBuilder) -> None:
    """Libraries are the folders in libraries/, sorted, after the "none" baseline."""
    project_dir.add_library("zeta", "claude")
    project_dir.add_library("alpha", "claude")
    project_dir.write("libraries/README.md", "")
    assert discover_libraries() == ["none", "alpha", "zeta"]


def test_discover_libraries_without_folder(project_dir: ProjectBuilder) -> None:
    """A missing libraries folder leaves only the baseline."""
    (project_dir.root / "libraries").rmdir()
    assert discover_libraries() == ["none"]


def test_discover_fixtures_needs_kit_spec(project_dir: ProjectBuilder) -> None:
    """A fixture is a folder with a kit spec.yaml."""
    kit = project_dir.add_fixture("repo")
    (project_dir.root / "fixtures" / "empty").mkdir()
    assert discover_fixtures() == {"repo": kit}


def test_library_layer_per_harness(project_dir: ProjectBuilder) -> None:
    """A library's layer exists only for the harnesses it supports."""
    project_dir.add_library("skills", "claude")
    layer = project_dir.root / "libraries" / "skills" / "claude" / "sbxenv.yaml"
    assert library_layer("skills", "claude") == layer
    assert library_layer("skills", "codex") is None
    assert library_layer("missing", "claude") is None


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        pytest.param(
            "baseline: false\n" + eval_text(""),
            "baseline: false and no libraries, so nothing would run",
            id="nothing-to-run",
        ),
        pytest.param(
            eval_text("", libraries="[missing, skills]"),
            "libraries: no such library: missing",
            id="unknown-library",
        ),
        pytest.param(
            eval_text("  - id: one\n    prompt: Again.\n"),
            "cases: duplicate id: one",
            id="duplicate-case",
        ),
        pytest.param(
            eval_text("    fixture: nope\n"),
            "cases/0 (one): no such fixture: nope",
            id="unknown-fixture",
        ),
        pytest.param(
            "fixture: { name: nope, args: { x: 1 } }\n" + eval_text(""),
            "cases/0 (one): no such fixture: nope",
            id="unknown-default-fixture",
        ),
        pytest.param(
            "libraries: []\ncases:\n  - id: one\n    prompt: Do it.\n",
            "cases/0 (one): no scorers and no default",
            id="no-scorers",
        ),
        pytest.param(
            eval_text("    scorers: [{ name: nope }, { name: also_nope }]\n"),
            "cases/0 (one): no such scorer: also_nope, nope",
            id="unknown-scorer",
        ),
        pytest.param(
            eval_text(
                "    scorers: [{ name: answer_matches, args: { pattern: '(' } }]\n"
            ),
            "cases/0 (one): scorers: ",
            id="scorer-factory-fails",
        ),
    ],
)
def test_load_eval_reports_problem(
    project_dir: ProjectBuilder, text: str, problem: str
) -> None:
    """Problems the schema can't catch stop with the eval file and the field."""
    project_dir.add_library("skills", "claude")
    project_dir.add_eval("bad", text)
    with pytest.raises(SystemExit) as exc:
        load_eval("bad")
    assert f"evals/bad.yaml: {problem}" in str(exc.value)


def test_load_eval_lists_every_problem(project_dir: ProjectBuilder) -> None:
    """All problems of an eval are reported at once, one per line."""
    project_dir.add_eval(
        "bad",
        "libraries: [missing]\ncases:\n"
        "  - { id: one, prompt: a, fixture: nope }\n"
        "  - { id: one, prompt: b }\n",
    )
    with pytest.raises(SystemExit) as exc:
        load_eval("bad")
    assert str(exc.value).splitlines() == [
        "evals/bad.yaml: libraries: no such library: missing",
        "evals/bad.yaml: cases: duplicate id: one",
        "evals/bad.yaml: cases/0 (one): no such fixture: nope",
        "evals/bad.yaml: cases/0 (one): no scorers and no default",
        "evals/bad.yaml: cases/1 (one): no scorers and no default",
    ]


def test_load_eval_schema_error_names_field(project_dir: ProjectBuilder) -> None:
    """An eval that breaks the schema stops with the path to the bad field."""
    path = project_dir.add_eval("bad", eval_text("  - id: Two\n    prompt: x\n"))
    with pytest.raises(SystemExit, match=r"cases/1/id: 'Two' does not match") as exc:
        load_eval("bad")
    assert str(exc.value).startswith(f"{path}: ")


def test_load_eval_checks_scorer_args_against_schema(project_dir: ProjectBuilder) -> None:
    """Built-in scorer arguments are checked by the schema."""
    project_dir.add_eval(
        "bad", eval_text("    scorers: [{ name: skill_invoked, args: { name: pr } }]\n")
    )
    with pytest.raises(SystemExit, match="'skill' is a required property"):
        load_eval("bad")


def test_eval_cases_fill_in_defaults(project_dir: ProjectBuilder) -> None:
    """Cases inherit the top-level fixture and scorers, and their own replace them."""
    kit = project_dir.add_fixture("repo")
    project_dir.add_fixture("other")
    project_dir.add_eval(
        "e",
        "fixture: { name: repo, args: { with_spec: true, depth: 2, mode: fast } }\n"
        + eval_text(
            "  - id: two\n    prompt: Then this.\n    fixture: other\n"
            "    scorers: [{ name: skill_invoked, args: { skill: pr } }]\n"
        ),
    )
    one, two = eval_cases("e")
    assert one.id == "one"
    assert one.prompt == "Do it."
    # Kit arguments become the strings sbx expects, booleans in lower case.
    assert one.fixture == Fixture(
        name="repo", path=kit, args={"with_spec": "true", "depth": "2", "mode": "fast"}
    )
    assert one.scorers == [{"name": "answer_matches", "args": {"pattern": "done"}}]
    assert two.fixture is not None
    assert (two.fixture.name, two.fixture.args) == ("other", {})
    assert two.scorers == [{"name": "skill_invoked", "args": {"skill": "pr"}}]


def test_eval_cases_without_fixture(project_dir: ProjectBuilder) -> None:
    """A case without any fixture starts in an empty workspace."""
    project_dir.add_eval("e", eval_text(""))
    assert [case.fixture for case in eval_cases("e")] == [None]


@pytest.mark.parametrize(
    ("baseline", "expected"),
    [
        ("", ["none", "a", "b"]),
        ("baseline: true\n", ["none", "a", "b"]),
        ("baseline: false\n", ["a", "b"]),
    ],
)
def test_eval_libraries_with_and_without_baseline(
    project_dir: ProjectBuilder, baseline: str, expected: list[str]
) -> None:
    """The baseline runs first unless the eval sets `baseline: false`."""
    project_dir.add_library("a", "claude")
    project_dir.add_library("b", "claude")
    project_dir.add_eval("e", baseline + eval_text("", libraries="[a, b]"))
    assert eval_libraries("e") == expected


def test_load_harness(project_dir: ProjectBuilder) -> None:
    """A valid harness.yaml loads as written."""
    project_dir.add_harness("agent")
    assert load_harness("agent") == {
        "run": ["agent", "-p", "{prompt}"],
        "inventory": ["agent", "--version"],
        "trace_reader": "claude",
    }


@pytest.mark.parametrize(
    ("harness_yaml", "message"),
    [
        ("run: [agent]\ninventory: [v]\ntrace_reader: claude\n", "run: ['agent']"),
        ("run: ['{prompt}']\ninventory: [v]\ntrace_reader: gemini\n", "trace_reader:"),
        ("run: ['{prompt}']\ntrace_reader: claude\n", "'inventory' is a required"),
    ],
)
def test_invalid_harness(
    project_dir: ProjectBuilder, harness_yaml: str, message: str
) -> None:
    """A harness.yaml that breaks the schema stops with the field."""
    project_dir.add_harness("agent", harness_yaml)
    with pytest.raises(SystemExit, match="harness.yaml: ") as exc:
        load_harness("agent")
    assert message in str(exc.value)


def test_scorer_registry_is_builtin_without_project_scorers(
    project_dir: ProjectBuilder,
) -> None:
    """Without a scorers package, evals can use the built-in scorers."""
    assert sorted(scorer_registry()) == ["answer_matches", "skill_invoked"]


def test_project_scorers_extend_and_override(project_dir: ProjectBuilder) -> None:
    """A project's REGISTRY adds scorers and wins on a name clash."""
    project_dir.add_scorers(PROJECT_SCORERS)
    registry = scorer_registry()
    assert sorted(registry) == ["always", "answer_matches", "skill_invoked"]
    assert registry["answer_matches"].__module__ == "skill_evals_project_scorers"


def test_project_scorers_without_registry(project_dir: ProjectBuilder) -> None:
    """A scorers package without REGISTRY adds nothing."""
    project_dir.add_scorers('"""No scorers yet."""\n')
    assert sorted(scorer_registry()) == ["answer_matches", "skill_invoked"]


def test_eval_with_project_scorer(project_dir: ProjectBuilder) -> None:
    """Evals can name project scorers, whose arguments are checked by building them."""
    project_dir.add_scorers(PROJECT_SCORERS)
    project_dir.add_eval(
        "ok", eval_text("    scorers: [{ name: always, args: { value: true } }]\n")
    )
    project_dir.add_eval("bad", eval_text("    scorers: [{ name: always }]\n"))
    assert [case.scorers[0]["name"] for case in eval_cases("ok")] == ["always"]
    with pytest.raises(SystemExit, match=r"cases/0 \(one\): scorers: TypeError: "):
        load_eval("bad")


def test_build_scorers_adds_diagnostics(project_dir: ProjectBuilder) -> None:
    """Built scorers keep the specs' order, followed by skills_used."""
    project_dir.add_scorers(PROJECT_SCORERS)
    scorers = build_scorers(
        [
            {"name": "skill_invoked", "args": {"skill": "pr"}, "min_pass": 0.8},
            {"name": "always", "args": {"value": False}},
        ]
    )
    assert [s.name for s in scorers] == ["skill_invoked:pr", "always", "skills_used"]
