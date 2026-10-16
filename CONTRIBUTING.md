# Contributing

Thanks for helping out. Bug reports, ideas and pull requests are all welcome.
[README.md](README.md) explains what the project is and how it works.

## Setup

You need [uv](https://docs.astral.sh/uv/). Docker Sandboxes (`sbx`) is only needed to
run evals, not to work on the code.

```bash
uv sync --all-groups
make install-pre-commit
```

## Run everything through uv

All tools are pinned in `uv.lock`. Run commands with `uv run` (the `make` targets
already do), not with a global `python`, `pip` or `ruff`:

```bash
uv run skill-evals validate
uv run ruff check
uv add <package>             # Add a dependency, instead of editing pyproject.toml
```

## Checks

```bash
make check    # Formats, lints (ruff, yamllint, validate) and type checks (ty)
```

Run it before you push. The pre-commit hook runs the same checks on every commit.

If your change affects how runs work, try one cell for real and say so in the PR:

```bash
uv run skill-evals evaluate --evals pr --harnesses claude -n 1
```

This needs `sbx` and uses model credits, so you don't need to run it for docs or small
fixes.

## Pull requests

1. Branch off `main` and open a pull request. The template asks for what, why and how
   you tested it.
2. Give the PR a title in [conventional commit](https://www.conventionalcommits.org/)
   style: `feat: ...`, `fix: ...`, `docs: ...`, `refactor: ...`, `chore: ...`, or
   `feat!: ...` for a breaking change.
3. PRs are squash-merged and the title becomes the commit on `main`, so it is also the
   changelog line. The maintainer can fix a title when merging.

Smaller PRs get reviewed sooner.

## Adding things

These sections of the README describe the format of each piece:

- A [library](README.md#libraries), [fixture](README.md#fixtures) or
  [eval](README.md#evals)
- A [scorer](README.md#scorers)
- A [harness](README.md#harnesses) for another agent, which also needs a tracing kit
  and a trace reader in `src/skill_evals/traces/`

## Other

Please follow the [Code of Conduct](CODE_OF_CONDUCT.md). Report security problems as
described in [SECURITY.md](SECURITY.md).
