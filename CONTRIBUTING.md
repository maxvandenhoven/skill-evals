# Contributing

Thanks for helping out. Bug reports, ideas and pull requests are all welcome.
[README.md](README.md) explains what the project is and how it works.

## Setup

You need [uv](https://docs.astral.sh/uv/) to work on the code. Docker Sandboxes (`sbx`)
is only needed to run evals. Install the dependencies and the git hooks with these two
commands:

```bash
uv sync --all-groups
make install-pre-commit
```

## Run everything through uv

All tools are pinned in `uv.lock`, so run commands with `uv run` instead of a global
`python`, `pip` or `ruff`. The `make` targets already do this. The examples below run
the validator and the linter, and add a dependency with `uv add` rather than by
editing `pyproject.toml`:

```bash
uv run skill-evals validate
uv run ruff check
uv add <package>
```

## Checks

Before you push, run `make check`. It formats the code, lints it with ruff and
yamllint, validates the example project and type checks with ty. The pre-commit hook
runs the same checks on every commit.

```bash
make check
```

## Tests

The unit tests take seconds and need no `sbx`, network or model credentials. Run all of
them, with a coverage report, using `make test`. To run one file, or only the tests
whose name matches a word, call `pytest` through uv:

```bash
make test
uv run pytest tests/test_config.py -k discover
```

Keep the tests up to date with your change. A new feature or changed behavior comes
with new or updated tests in the same pull request, and a bug fix starts with a test
that fails before the fix. If you fix a bug that a test marks with `xfail`, remove the
mark.

A test function gets a one-line docstring that starts with a verb, such as "Check that
a missing config suggests `skill-evals init`." Fixtures and helpers get the full Google
docstring that the source code uses, with `Args` and `Returns`.

Some tests read real agent traces from `tests/data/`. When an agent upgrade changes
how its traces look, record a new one from a run folder with the command below. The
script scrubs paths, e-mail addresses and credentials, but check the file before you
commit it, and update the tests that depend on it.

```bash
make record-trace RUN=.runs/<stamp>/<cell>-<case>-<i>
```

## Real runs

If your change affects how runs work, also try one cell for real, for example with the
command below, and mention it in the pull request. This needs `sbx` and uses model
credits, so you can skip it for docs or small fixes.

```bash
uv run skill-evals evaluate --evals pr --harnesses claude -n 1
```

## Pull requests

Branch off `main` and open a pull request. The template asks what changed, why, and
how you tested it. Give the PR a title in
[conventional commit](https://www.conventionalcommits.org/) style, such as
`feat: ...`, `fix: ...`, `docs: ...`, `refactor: ...` or `chore: ...`, and add a `!`
(`feat!: ...`) for a breaking change.

PRs are squash-merged, so the title becomes the commit on `main` and the changelog
line. The maintainer can fix a title when merging. Smaller PRs get reviewed sooner.

## Adding things

The README describes the format of each piece: a [library](README.md#libraries), a
[fixture](README.md#fixtures), an [eval](README.md#evals), a
[scorer](README.md#scorers) and a [harness](README.md#harnesses). A harness for
another agent also needs a tracing kit and a trace reader in `src/skill_evals/traces/`.
