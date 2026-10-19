<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/maxvandenhoven/skill-evals/main/images/logo-dark.svg">
    <img src="https://raw.githubusercontent.com/maxvandenhoven/skill-evals/main/images/logo-light.svg" alt="skill-evals" width="300">
  </picture>
</h1>

`skill-evals` is an agent skill evaluation framework for testing skills across
models, harnesses and installation methods. It helps library maintainers evaluate
skills across user setups using their recommended installation method, and helps
individuals and organizations evaluate skills for use across agents, including
multi-agent setups built with tools such as [Omnigent](https://github.com/omnigent-ai/omnigent).

- **Multiple models and harnesses.** Run the same cases across agent configurations.
- **Isolated environments.** Each run starts in a fresh sandbox without inheriting
  local agent settings or installed skills.
- **Exact installation method.** Specify the install commands used by you or your
  users, including harness-specific plugin installers.
- **Composable evaluations.** Define reusable components in YAML and combine
  built-in checks with custom Python scorers.

<p align="center">
  <img src="https://raw.githubusercontent.com/maxvandenhoven/skill-evals/main/images/architecture.jpeg" alt="Agents run in isolated sandboxes, send traces to MLflow, and have those traces graded by scorers" width="600">
</p>

## Background

Skills are easy to create and distribute, but establishing how well they perform
requires testing. Evaluation can show whether an agent discovers a skill, follows
its instructions and completes the intended task. Skill evaluation is not new,
but testing in one setup, such as Claude Code on a maintainer's machine, leaves
questions about other setups unanswered. For a library with a varied user base,
those differences are part of the library's quality.

Portability also matters for individuals and organizations. As models improve,
the preferred model or harness for a task can change. Multi-agent workflows can
also combine agents that use different harnesses. Evaluating the same skills
across these configurations helps users decide where they work well and where
adjustments are needed, without repeating the setup and scoring work by hand.

## Example results

This repository is itself a `skill-evals` project. Its [example folder](example/)
contains evaluations of [Matt Pocock's skill library](https://github.com/mattpocock/skills).
The code review case asks an agent to review a feature branch against a spec and
coding standards. It checks whether the library's `code-review` skill was invoked
and whether the answer contains the expected Standards and Spec sections.

The case was run three times on Claude Code and Codex, both with and without the
library. Each harness used the exact plugin installation commands recommended in
the library's README, captured in the [library definition](example/libraries/matt-pocock-skills/).

| Harness | Skills installed | Skill invoked | Expected review format |
|---|---|---|---|
| Claude Code | No | 0 of 3 | 0 of 3 |
| Claude Code | Yes | 1 of 3 | 1 of 3 |
| Codex | No | 0 of 3 | 0 of 3 |
| Codex | Yes | 3 of 3 | 3 of 3 |

Installing the library improved format adherence in both harnesses in this sample,
with a larger improvement in Codex. One possible explanation is that the Claude
Code setup includes another `code-review` skill with the same name, which could
influence skill selection. Three runs cannot establish the cause, and differences
in models and installed library versions may also contribute. This is the kind of
difference maintainers need to investigate when distributing skills to users with
varied setups.

## Quickstart

Install [uv](https://docs.astral.sh/uv/) and
[Docker Sandboxes](https://docs.docker.com/ai/sandboxes/install/), then run `sbx login`.
The package requires Python 3.12 or later. It was tested with sbx v0.47.0 and uses
the experimental `sbx env` commands.

Agent authentication follows Docker Sandboxes' agent-specific flow. For a ChatGPT
subscription, run `sbx secret set openai --oauth`. For a Claude subscription, start
a Claude Code sandbox and run `/login` inside it, with no Anthropic API key stored.
Both agents also accept API keys through `sbx secret set openai` or
`sbx secret set anthropic`, which is useful for headless environments. See Docker's
[agent guides](https://docs.docker.com/ai/sandboxes/agents/) for authentication details.

Install the framework and initialize a project from your repository's root.

```bash
uv tool install skill-evals
skill-evals init tests/skills
```

This generates `.skill-evals.yaml`, copies the harness definitions and editor
schemas, and creates folders for libraries, fixtures and evals. Add `.skill-evals/`
to `.gitignore`, then define the components described below. Initialization does
not create runnable evals.

To start with a populated project, clone this repository instead. The following
commands run the code review case three times per configuration and open MLflow
for inspecting the traces.

```bash
git clone https://github.com/maxvandenhoven/skill-evals.git
cd skill-evals
uv run skill-evals validate
uv run skill-evals evaluate --evals code-review --harnesses claude,codex -n 3
uv run skill-evals mlflow
```

`evaluate` prints scores and saves a Markdown report. New projects use
`.skill-evals/runs/<stamp>/report.md`, while this repository uses `.runs/<stamp>/report.md`.
An excerpt of the score report for the results above looks like this, with other
scorers omitted.

| Configuration | Case | Runs | `skill_invoked:code-review` | `answer_matches` |
|---|---|---|---|---|
| claude/none | branch-review | 3 | 0/3 | 0/3 |
| claude/matt-pocock-skills | branch-review | 3 | 1/3 | 1/3 |
| codex/none | branch-review | 3 | 0/3 | 0/3 |
| codex/matt-pocock-skills | branch-review | 3 | 3/3 | 3/3 |

## How it works

A project combines five components. Their definitions are kept alongside your
skills or tests, with `.skill-evals.yaml` pointing to their folders.

| Component | Role |
|---|---|
| [Harness](src/skill_evals/harnesses/) | Declares the agent, model, execution command and tracing setup for MLflow. Harnesses are independent of a particular skill library and can be shared across projects. |
| [Library](example/libraries/matt-pocock-skills/) | Declares how a skill or set of skills is installed for each harness. |
| [Fixture](example/fixtures/slugify-repo/) | Optionally prepares the environment and files needed by a case, such as a repository with a feature branch to review. |
| [Scorer](example/scorers/__init__.py) | Evaluates an agent trace through MLflow. Checks can cover skill invocation, answers and tool use, or use an LLM as a judge. |
| [Eval](example/evals/code-review.yaml) | Defines prompts and connects them to libraries, fixtures and scorers. Together with the selected harnesses and repeat count, it determines the test plan. |

For each case, the framework creates a fresh sandbox for every harness and library
combination, installs the skills, prepares the fixture and runs the prompt. By
default, it also runs the case without a library as a baseline. Traces are sent to
MLflow, where scorers attach assessments that are collected into the report.


The framework focuses on skills, but these components can be reused for broader
agent evaluations. An eval with an empty library list runs without skills, using
the same fixtures, harnesses and scoring tools.

## Headless mode and CI

Docker Sandboxes supports [running in CI](https://docs.docker.com/ai/sandboxes/workflows/automation/).
Use a runner with `sbx` installed and local sandbox virtualization available. The
workflow below assumes a self-hosted Linux runner with KVM and a configured
`skill-evals` project. Docker authentication uses a personal access token, and
agent authentication uses API keys stored as GitHub Actions secrets. Claude's
subscription login requires an interactive flow, so it is less suitable for
setting up an unattended runner.

Save this as `.github/workflows/skill-evals.yaml`. It runs when files in a
fictional `skills/` folder or the evaluation configuration change. The library
definition must install the skills from the revision being tested so that the
check evaluates the proposed changes.

```yaml
name: Skill evaluations

on:
  push:
    branches: [main]
    paths: ['skills/**', 'tests/skills/**', '.skill-evals.yaml', '.github/workflows/skill-evals.yaml']
  pull_request:
    paths: ['skills/**', 'tests/skills/**', '.skill-evals.yaml', '.github/workflows/skill-evals.yaml']
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
          sbx secret set anthropic --force --token "$ANTHROPIC_API_KEY"
          sbx secret set openai --force --token "$OPENAI_API_KEY"
      - name: Validate evaluations
        run: uvx skill-evals validate
      - name: Run evaluations
        run: uvx skill-evals evaluate -n 5 --min-pass 0.8 --summary "$GITHUB_STEP_SUMMARY"
```

A library score below its threshold makes the job fail. Here the default is 80%,
with any per-scorer `min_pass` taking precedence. Baselines do not determine whether
the job passes. Make `Evaluate skills` a required status check in your repository
rules to block merges on failure. GitHub withholds repository secrets from fork
pull requests, so those need a separate trusted execution process. See the
[GitHub workflow documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushpull_requestpull_request_targetpathspaths-ignore)
for the effect of path filters on required checks.

## Limitations

Each case supplies a single, non-interactive prompt. Agents can use tools while
responding, but the framework does not support a conversation with follow-up user
messages. This limits evaluation of skills that depend on clarification or
iterative feedback.

Human-in-the-loop evaluation is not a built-in workflow. Traces can be inspected
manually in MLflow, but pausing a run for human input or collecting human scores
would require additional support.

## Contributing and license

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and checks.
Licensed under [MIT](LICENSE).
