<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/maxvandenhoven/skill-evals/main/images/logo-dark.svg">
    <img src="https://raw.githubusercontent.com/maxvandenhoven/skill-evals/main/images/logo-light.svg" alt="skill-evals" width="300">
  </picture>
</h1>

`skill-evals` is an agent skill evaluation framework for testing skills across models, harnesses, and installation methods. It helps library maintainers evaluate skills across user setups using their recommended installation method, and helps individuals and organizations evaluate skills for use across agents, including multi-agent setups built with tools such as [Omnigent](https://github.com/omnigent-ai/omnigent).

- **Multiple models and harnesses.** Run the same cases across agent configurations.
- **Isolated environments.** Each run starts in a fresh sandbox without inheriting local agent settings or installed skills.
- **Exact installation method.** Specify the install commands used by you or your users, including harness-specific plugin installers.
- **Composable evaluations.** Define reusable components in YAML and combine built-in checks with custom Python scorers.

<p align="center">
  <img src="https://raw.githubusercontent.com/maxvandenhoven/skill-evals/main/images/architecture.jpeg" alt="Agents run in isolated sandboxes, send traces to MLflow, and have those traces graded by scorers" width="600">
</p>

## Background

Skills are easy to create and distribute, but establishing how well they perform requires testing. Evaluation can show whether an agent discovers a skill, follows its instructions, and completes the intended task. Skill evaluation is not a new concept, but many skill libraries are distributed without it, or with a very narrow set of environments. Library maintainers need broader coverage to understand how their skills perform across the configurations their users rely on.

For individuals and organizations, this is also a question of portability. As models improve, the preferred model or harness for a task can change, while multi-agent workflows may combine several harnesses from the outset. Evaluating the same skills across these configurations helps establish where they work well and where adjustments are needed, without repeating the setup and scoring work by hand.

## Example results

This repository is itself a `skill-evals` project. The [example folder](example/) contains evaluations of Matt Pocock's popular [skill library](https://github.com/mattpocock/skills). The code review case asks an agent to review a feature branch against a spec and coding standards, then checks whether it invoked the library's `code-review` skill and included the expected sections in its answer.

The case was run three times on Claude Code and Codex, both with and without the skills installed. Each harness used the exact plugin installation commands recommended in the library's README. The table below shows how many runs invoked the skill and how many produced the expected format.

| Harness     | Skills installed | Skill invoked | Expected review format |
| ----------- | ---------------- | ------------- | ---------------------- |
| Claude Code | No               | 0 of 3        | 0 of 3                 |
| Claude Code | Yes              | 1 of 3        | 1 of 3                 |
| Codex       | No               | 0 of 3        | 0 of 3                 |
| Codex       | Yes              | 3 of 3        | 3 of 3                 |

Without the library, both harnesses fail these checks, as expected. Adding it produces a consistent improvement across the three Codex runs, while Claude Code loads the skill in only one of three runs. Differences in built-in skills could help explain this behavior, since Claude Code includes its own `code-review` skill. Identifying such differences helps maintainers address inconsistent skill selection and provide a more consistent experience across user setups.

## Quickstart

The framework requires [uv](https://docs.astral.sh/uv/) and [Docker Sandboxes](https://docs.docker.com/ai/sandboxes/install/) to be installed and configured. Once installed, run `sbx login` and configure the agents you want to use through their specific authentication flows. Docker's [agent guides](https://docs.docker.com/ai/sandboxes/agents/) describe the agent-specific steps in more detail.

After authentication, install the framework and initialize a project from your repository's root.

```bash
uv tool install skill-evals
skill-evals init tests/skills
```

This command generates `.skill-evals.yaml`, copies the harness definitions and editor schemas, and creates empty folders for libraries, fixtures, and evals. You can then add your own definitions using the components described below.

To try the evaluation flow before writing your own cases, clone this repository and run its example project. The commands below validate the configuration, run the code review case three times per configuration, and start the MLflow UI for inspecting the traces.

```bash
git clone https://github.com/maxvandenhoven/skill-evals.git
cd skill-evals
uv run skill-evals validate
uv run skill-evals evaluate --evals code-review --harnesses claude,codex -n 3
uv run skill-evals mlflow
```

Along with printing scores, `evaluate` saves a Markdown report under the project's configured run folder. The default is `.skill-evals/runs/<stamp>/report.md`. This repository overrides the `runs` setting in `.skill-evals.yaml` to use `.runs/`, so its reports appear at `.runs/<stamp>/report.md`.

## How it works

A project combines five reusable components, with `.skill-evals.yaml` pointing to the folders that hold their definitions. These live alongside your skills or tests and can be combined to evaluate different tasks and agent setups.

- **Harnesses** declare the agent, model, execution command, and tracing setup for MLflow. They are independent of a particular skill library and can be shared across projects.
- **Libraries** declare how a skill or set of skills is installed for each harness, so the evaluation can use the exact same installation method as your users.
- **Fixtures** optionally prepare the environment a case needs, e.g., by setting up a repository with a feature branch to review.
- **Scorers** evaluate agent traces through MLflow, checking skill invocation, answers, or tool use. Custom scorers can also use an LLM-as-a-judge pattern.
- **Evals** define prompts and connect them to libraries, fixtures, and scorers. Together with the selected harnesses and repeat count, they determine the test plan.

For each case and repetition, the framework creates a fresh sandbox for every harness and library combination, installs the skills, prepares the fixture, and runs the prompt. It also runs the case without a library as a baseline by default. The resulting traces go to MLflow, where scorers attach assessments that are collected into the report.

Although the framework focuses on skills, the same components can be reused for broader agent evaluations. An eval with an empty library list runs without skills while retaining the fixtures, harnesses, and scoring tools.

## Headless mode and CI

Docker Sandboxes supports [running in CI](https://docs.docker.com/ai/sandboxes/workflows/automation/), so evaluations can run automatically when skills change. Authentication requires a Docker personal access token and agent API keys stored as GitHub Actions secrets, since interactive login flows are not suitable for headless applications.

<details>
<summary>Example GitHub Actions workflow for evaluating skill changes</summary>

This example assumes a configured evaluation project and a self-hosted Linux runner with KVM and Docker Sandboxes installed.

```yaml
name: Skill evaluations

on:
  push:
    branches: [main]
    paths: ["skills/**"]
  pull_request:
    paths: ["skills/**"]
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

</details>

## Limitations

Evaluations currently begin with a single, non-interactive prompt. Agents can use tools while responding, but cases cannot include follow-up user messages, which limits testing of skills that depend on clarification or iterative feedback. The framework is therefore best suited to automated evaluation. MLflow traces can be reviewed manually, but a human-in-the-loop workflow that pauses for input or collects human scores would require additional setup.

## Contributing and license

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and checks. Licensed under [MIT](https://github.com/maxvandenhoven/skill-evals/blob/main/LICENSE).
