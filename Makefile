# Common commands. The eval pipeline itself is described in README.md.

.PHONY: sync install-pre-commit pre-commit format lint type check \
	mlflow claude-login evals score

# Eval selection for `make evals`, overridable: `make evals EVALS=pr N=10`.
EVALS ?= pr,code-review
HARNESSES ?= claude,codex
N ?= 3
PARALLEL ?= 1

sync:
	@uv sync --all-groups

# Install the git hook that runs the checks below on every commit.
install-pre-commit:
	@uv run pre-commit install

pre-commit:
	@uv run pre-commit run --all-files

format:
	@uv run ruff format

# Lint Python and YAML, and validate the example's eval and harness files.
lint:
	@uv run ruff check --fix --output-format concise
	@uv run yamllint --strict .
	@uv run skill-evals validate

type:
	@uv run ty check

check: format lint type

# Open the MLflow UI on this project's store. Not needed for runs: run, score and
# evaluate start a server for their duration if none is up.
mlflow:
	@uv run skill-evals mlflow

# Log Claude Code in with your Claude subscription: opens Claude in a throwaway
# sandbox; run /login there, then exit. Requires no `anthropic` API-key secret
# (`sbx secret rm anthropic`), since /login is only offered without one. Mounts an
# empty folder, not this repo.
claude-login:
	mkdir -p .runs/claude-login
	-sbx rm -f se-claude-login
	sbx run --name se-claude-login claude .runs/claude-login
	sbx rm -f se-claude-login
	sbx secret ls

# Reference run: every library, sequentially, then score exactly that run. Writes
# .runs/<stamp>/report.md with the commands, per-run results and scores.
evals:
	uv run skill-evals evaluate --evals $(EVALS) --harnesses $(HARNESSES) -n $(N) \
		--parallel $(PARALLEL)

# Score the latest run again, e.g. after changing a scorer.
score:
	uv run skill-evals score --evals $(EVALS) --stamp latest
