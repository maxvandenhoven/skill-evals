## v0.1.1 (2026-10-17)

### Fix

- Complete the PyPI page: README, links, keywords; silence the cache warning (#13)

## v0.1.0 (2026-10-17)

First release.

### Feat

- Test whether coding agents load and follow your skills, in Docker Sandboxes, with
  every run traced in MLflow: `skill-evals init`, `run`, `score`, `evaluate`,
  `validate` and `mlflow`.
- Harnesses for Claude Code and Codex, with trace readers for both.
- Libraries installed by their own kits, fixtures that build the workspace, and YAML
  evals that combine libraries, harnesses, fixtures and scorers.
- Built-in scorers `skill_invoked`, `skills_used` and `answer_matches`, and support for
  your own scorers.

### Fix

- Show messages instead of tracebacks for unknown eval and harness names, missing
  files, invalid YAML and scorer folders that are not packages (#11)
