# Headless evaluations and CI

Evaluations can run automatically when skills change using [Docker Sandboxes automation](https://docs.docker.com/ai/sandboxes/workflows/automation/). A headless runner needs Docker authentication and agent credentials configured without interactive login. The example below uses a Docker personal access token and agent API keys stored as GitHub Actions secrets.

## Runner and trust requirements

Use a configured evaluation project and a dedicated self-hosted Linux runner with KVM, Docker Sandboxes, and uv available. The workflow does not install or provision Docker Sandboxes. Confirm that the runner can create sandboxes and reach the required package registries and model providers before scheduling evaluations.

**Run only trusted code on a runner with credentials.** Sandbox environment files can contain host lifecycle commands, and project scorer packages execute Python on the host, including during validation. Do not run unreviewed pull request code on this runner or expose its credentials to fork workflows. Sandbox isolation does not protect the host from those setup and scoring steps.

The example deliberately uses manual dispatch so a maintainer can review the selected revision before starting a paid evaluation. Once that trust boundary is in place, you can add a push trigger restricted to trusted branches and relevant skill paths. Restrict who can dispatch the workflow and which revisions they may run.

## Example workflow

Store `DOCKER_USERNAME`, `DOCKER_PAT`, `ANTHROPIC_API_KEY`, and `OPENAI_API_KEY` as repository or environment secrets. Include only the agents you intend to test. The configured project determines the libraries, cases, and harnesses selected when no filters are given.

```yaml
name: Skill evaluations

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  evaluate:
    name: Evaluate skills
    runs-on: [self-hosted, linux, kvm]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - name: Authenticate Docker and agents
        env:
          DOCKER_USERNAME: ${{ secrets.DOCKER_USERNAME }}
          DOCKER_PAT: ${{ secrets.DOCKER_PAT }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          printf '%s' "$DOCKER_PAT" | sbx login --username "$DOCKER_USERNAME" --password-stdin
          printf '%s' "$ANTHROPIC_API_KEY" | sbx secret set anthropic
          printf '%s' "$OPENAI_API_KEY" | sbx secret set openai
      - name: Validate evaluations
        run: uvx skill-evals validate
      - name: Run evaluations
        run: uvx skill-evals evaluate -n 5 --min-pass 0.8 --summary "$GITHUB_STEP_SUMMARY"
```

The service-secret commands read keys from standard input instead of exposing them as command-line arguments. On a persistent self-hosted runner, account for stored credentials and evaluation files when deciding how to clean up or replace the runner. Never print keys or commit authentication files.

## Costs and results

`-n 5` repeats each case five times for every selected harness and library combination, including the default no-library baseline. This uses model credits or subscription allowances, and custom LLM-based scorers can add costs. Start with one harness, one eval, and `-n 1` when checking a new setup.

`--min-pass 0.8` supplies the minimum pass rate for scorers that do not declare their own `min_pass`. A missed threshold in a library-installed configuration makes the command exit with status 1. Baselines do not gate, since library-specific checks are expected to fail without the library. This is a scorer threshold, not a general guarantee that the evaluation infrastructure or task outcome is correct.

Scores are appended to the GitHub job summary and the run report. Reports default to `.skill-evals/runs/<stamp>/report.md`, unless the project overrides `runs` in `.skill-evals.yaml`. This repository uses `.runs/`. Keep run folders and the MLflow store out of version control, and review traces, prompts, agent output, and workspaces for sensitive content before publishing artifacts.

Return to the [README](../README.md) for the local workflow and example results.
