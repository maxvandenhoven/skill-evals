<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/maxvandenhoven/skill-evals/main/images/logo-dark.svg">
    <img src="https://raw.githubusercontent.com/maxvandenhoven/skill-evals/main/images/logo-light.svg" alt="skill-evals" width="300">
  </picture>
</h1>

`skill-evals` tests whether coding agents load your skills and follow them.

Suppose you wrote a skill: a `SKILL.md` that teaches Claude Code or Codex how to write
a PR body, review a branch, or follow your team's conventions. You then want to know
whether the agent ever loads the skill, and whether it follows the skill once it has
loaded it. Neither is guaranteed. The skill's description decides whether it
triggers, agents ship built-in skills that can have the same name, and every agent
release can change the behaviour.

`skill-evals` measures this. It runs your prompts in fresh, isolated
[Docker Sandboxes](https://docs.docker.com/ai/sandboxes/), once with your skills
installed and once without them, for each agent you configure. It traces every run
with [MLflow](https://mlflow.org) and scores the traces. This is the result of three
runs of the example's code review eval:

```
=== code-review: Review a feature branch against a spec and standards
  claude/matt-pocock-skills
    branch-review   n=3  skill_invoked:code-review=1/3  answer_matches=1/3
  claude/none
    branch-review   n=3  skill_invoked:code-review=0/3  answer_matches=0/3
  codex/matt-pocock-skills
    branch-review   n=3  skill_invoked:code-review=3/3  answer_matches=3/3
  codex/none
    branch-review   n=3  skill_invoked:code-review=0/3  answer_matches=0/3
```

Without the skill library (`none`), neither agent produced a review in the skill's
format. With the library installed, Codex loaded the skill and followed its format
in all three runs, while Claude Code did so in one of three. The skill improves
both agents, but the improvement is much larger for Codex (from 0 to 3 out of 3)
than for Claude Code (from 0 to 1 out of 3). The same skill can therefore work well
in one harness and poorly in another, which is why `skill-evals` tests every skill
in every harness. Part of such a difference can come from the model or from the
library version that each agent installs; see [Limitations](#limitations).

## Quickstart

You need the [sbx CLI](https://docs.docker.com/ai/sandboxes/install/) and
[uv](https://docs.astral.sh/uv/), and the agents must be logged in (see below). This
repository is itself a `skill-evals` project: [`example/`](https://github.com/maxvandenhoven/skill-evals/tree/main/example/) tests Matt
Pocock's skills with two evals. You can run it as follows:

```bash
git clone https://github.com/maxvandenhoven/skill-evals.git && cd skill-evals
uv run skill-evals evaluate -n 3    # Run every eval 3 times, then score the runs
```

The `evaluate` command runs every eval in every harness (agent), once without a
library and once with each library that the eval lists. It then prints the scores
and writes them to `.skill-evals/runs/<stamp>/report.md`. If no MLflow server is
running, it starts one for the duration of the command. These are the options you
will use most often:

```bash
skill-evals evaluate --evals code-review           # Only some evals
skill-evals evaluate --harnesses claude            # Only some agents
skill-evals evaluate --cases branch-review         # Only some prompts of an eval
skill-evals evaluate --libraries none              # Only the baselines
skill-evals evaluate -n 10 --parallel 4            # 10 runs per case, 4 sandboxes at once
skill-evals evaluate --min-pass 0.8                # Exit 1 if a library cell passes < 80%
skill-evals evaluate --kit-arg claude-cli-pinned.version=2.1.300  # Try another CLI version

skill-evals run ... / skill-evals score --stamp latest   # The two halves separately
skill-evals mlflow                                       # Browse traces in the MLflow UI
skill-evals validate                                     # Check your eval files
```

### Logging the agents in

Sandboxes never see your `~/.claude` or `~/.codex`. The credentials live in the
secret store of sbx on your machine, and the sandbox proxy adds them to the agent's
requests, so they never enter a sandbox. First sign in to sbx itself with
`sbx login`, which you only need to do once. Then choose one of the following
options for each agent:

| Agent | Subscription | API key |
|---|---|---|
| Claude Code | Run `sbx run claude` in an empty folder, type `/login`, and exit. | `sbx secret set anthropic` |
| Codex | `sbx secret set openai --oauth` (ChatGPT plan) | `sbx secret set openai` |

To log in with a Claude subscription, use a throwaway sandbox and remove it
afterwards:

```bash
mkdir -p /tmp/claude-login && sbx run --name claude-login claude /tmp/claude-login
# In Claude Code: run /login, finish in the browser, then /exit
sbx rm -f claude-login
sbx secret ls   # Both anthropic and openai should be listed
```

Claude Code only offers `/login` while no Anthropic API key is stored, so remove an
existing key first with `sbx secret rm anthropic`. Storing a token from
`claude setup-token` as the API key does not work.

## Install

```bash
uv tool install skill-evals      # Or pipx install skill-evals, or add it as a dev dependency
```

To set up your project, run `skill-evals init <folder>` from the root of your
repository. The command writes `.skill-evals.yaml` to the root, copies the
ready-to-use harnesses and the JSON Schemas into the folder, and creates empty
folders for your own libraries, fixtures and evals:

```
.skill-evals.yaml          Where the folders below are (paths relative to this file)
tests/skills/
  harnesses/               The agents: Claude Code and Codex, ready to use
  schemas/                 JSON Schemas, for completion and validation in your editor
  libraries/               Your skills, as installable libraries   (empty)
  fixtures/                Workspaces the agent starts in          (empty)
  evals/                   Prompts and how to score them           (empty)
```

All of these files are yours to edit, and `skill-evals` only reads them. Add
`.skill-evals/`, which holds the run folders and the MLflow store, to your
`.gitignore`. Then add a library with your skills, a fixture and an eval, as
described in [Concepts](#concepts). The [`example/`](https://github.com/maxvandenhoven/skill-evals/tree/main/example/) folder in this
repository contains one of each, as well as a custom scorer.

### Writing files with the schemas

`skill-evals` defines three file formats of its own, and `init` copies a JSON Schema
for each of them into the `schemas/` folder of your project:

| Schema | Describes |
|---|---|
| `config.schema.json` | `.skill-evals.yaml` |
| `eval.schema.json` | `evals/<name>.yaml` |
| `harness.schema.json` | `harnesses/<name>/harness.yaml` |

The other files, such as `sbxenv.yaml` and the kits' `spec.yaml`, use the formats of
sbx, which its [documentation](https://docs.docker.com/ai/sandboxes/) describes.

To use a schema in your editor, start the file with a comment that points to the
schema, relative to the file itself. The `.skill-evals.yaml` that `init` writes and
the copied harnesses already start with such a comment. For a new eval, add this line
at the top of the file:

```yaml
# yaml-language-server: $schema=../schemas/eval.schema.json
```

Editors that use the YAML language server read this comment, such as VS Code with the
[YAML extension by Red Hat](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml),
or Neovim and Zed with the YAML language server configured. In JetBrains IDEs, map
the schema to the files instead, under *Settings > Languages & Frameworks > Schemas
and DTDs > JSON Schema Mappings*. The editor then completes the keys, shows a
description of each key when you hover over it, and marks unknown keys, missing keys
and values of the wrong type.

`skill-evals validate` checks every eval and harness file against the same schemas.
It also checks what a schema cannot express: that the libraries, fixtures and
scorers an eval names exist, that its case ids are unique, and that every scorer can
be built with its arguments. Every `run` and `evaluate` performs the same checks
before it starts any sandbox. The schema accepts any scorer name, because your
project can add its own scorers, and it only describes the arguments of the built-in
scorers. Your editor therefore cannot check the arguments of your own scorers, but
`skill-evals validate` does.

### Running in CI

The `evaluate` command exits with code 1 when a score is below its threshold, and
the `--summary` option writes the scores as Markdown to a file, such as the job
summary of GitHub Actions:

```yaml
jobs:
  skills:
    runs-on: [self-hosted, linux, kvm]   # See the requirements below
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - name: Agent credentials (API keys; subscriptions need a browser)
        run: |
          echo "$ANTHROPIC_API_KEY" | sbx secret set anthropic
          echo "$OPENAI_API_KEY" | sbx secret set openai
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
      - run: uvx skill-evals evaluate -n 5 --min-pass 0.8 --summary "$GITHUB_STEP_SUMMARY"
```

You can set a threshold per scorer in the eval file (`min_pass: 0.8`) or one for all
scorers with `--min-pass`. Thresholds only apply to cells with a library, because
the baseline without a library is expected to fail.

The CI runner has the same requirements as sbx. Local sandboxes run as microVMs, so
a Linux runner must run Ubuntu 24.04 or later with KVM enabled, and the virtual
machine needs nested virtualization if the runner is itself a virtual machine. The
runner also needs `sbx` installed and signed in. Because `sbx login` opens a
browser, sign in once by hand on a self-hosted runner. Every run costs model tokens,
so run the evals on demand or when a skill changes, rather than on every push.

## Features

**Declarative and composable.** `skill-evals` is built around the
[kits](https://docs.docker.com/ai/sandboxes/customize/kits-v2/) of Docker Sandboxes.
Everything that a sandbox needs, from the agent CLI and its tracing to your skills and
the workspace, is described in small YAML files that stack on top of each other.
Adding an agent, a skill library or a workspace means adding one folder, and you can
copy a working setup from the example or another project instead of writing install
scripts. Because every kit declares the network hosts it needs, the setup also
documents exactly what the sandbox may reach. Under a restrictive network policy,
each run can therefore reach only those hosts, which keeps the attack surface of an
agent with full permissions small.

**Flexible in what it measures.** You can measure how much a skill improves an agent,
by comparing runs with and without the skill. You can also measure how well the same
skill works across agents, to make sure that it stays portable. Portability matters
most for large skill libraries that are shared across teams or published online,
because their users work with many different agents, versions and setups.

**Isolated and reproducible.** Every run starts in a fresh sandbox with a pinned agent
version, and none of your local configuration, skills or plugins can leak into it.
The results therefore describe a known setup instead of your machine, so you can run
meaningful tests locally and get the same picture as a colleague or a CI runner.
When the standard setup is not enough, custom base images and kits extend the
sandbox in the same declarative way.

## Concepts

`skill-evals` runs every **eval** in every **harness**: once without a library,
which is the `none` baseline, and once with each **library** that the eval lists. An
eval can skip the baseline with `baseline: false`.
Each of these combinations is called a *cell*. Within a cell, every case of the eval
runs as many times as `-n` specifies. Each run gets a fresh sandbox whose workspace
is built by the case's **fixture**. The agent answers the case's prompt, the trace
goes to MLflow, and the **scorers** grade the trace.

Each sandbox is assembled from layers of
[sbx environment files](https://docs.docker.com/ai/sandboxes/configuration/environment-files/):
a shared base, the harness, the library and the fixture. Each layer installs what it
adds with [kits](https://docs.docker.com/ai/sandboxes/customize/kits-v2/), and each
kit opens only the network hosts that it uses: npm for the agent CLI, github.com for
a plugin, and nothing at all for a fixture that only copies files.

### Harnesses

A harness is an agent that runs the evals. The folder `harnesses/<name>/` contains an
`sbxenv.yaml`, which selects the sbx agent and its kits, and a `harness.yaml`, which
describes how to run a single prompt. The included harnesses pin the version of the
agent CLI (`cli/`) and install MLflow tracing (`tracing/`). To compare models, copy a
harness and change its `run` command:

```yaml
# harnesses/claude-opus/harness.yaml
run: [claude, -p, "{prompt}", --model, claude-opus-5-5]
inventory: [sh, -c, "claude --version && claude plugin list"]
trace_reader: claude    # How to read this agent's traces: claude or codex
```

Supporting a different kind of agent requires an MLflow tracing kit and a trace
reader in `skill_evals.traces`. Contributions are welcome.

### Libraries

A library contains the skills under test. The folder `libraries/<name>/<harness>/`
holds an sbxenv layer with a kit that installs the skills into that agent, ideally in
exactly the way that the library's README tells its users to. A library that only
supports some agents leaves out the folders for the others. For skills that live in
your own repository, a kit can copy them directly into the agent's skills folder:

```
libraries/my-skills/claude/sbxenv.yaml                       kits: [./kit]
libraries/my-skills/claude/kit/spec.yaml                     A kit without setup steps
libraries/my-skills/claude/kit/files/home/.claude/skills/my-skill/SKILL.md
```

### Fixtures

A fixture sets up the workspace that the agent starts in, so that the skill has the
context it needs. That can be a code repository with a history to review, but also a
folder of documents to summarise, a data set to analyse, or a project with its
dependencies installed. Without a fixture, the agent starts in an empty workspace.

The folder `fixtures/<name>/` is a kit that sets up the workspace inside the sandbox.
Store the files in the kit as real files, and put the steps that need commands, such
as git commits or installing packages, in its `setup.install` section, which runs in
`$WORKSPACE_DIR`. A fixture that downloads something also declares the hosts it
needs in the kit's network permissions. Files under
`files/workspace/` are copied into the workspace unchanged, but only after
`setup.install` has run. Files that a command needs therefore belong under
`files/home/`, which is copied first. Kit arguments let one fixture produce variants.
The example fixture builds a repository with a feature branch to review:

```
fixtures/slugify-repo/
  spec.yaml                                  Arguments and the git steps
  files/home/.fixtures/slugify-repo/
    main/slugify.py, main/test_slugify.py    The first commit, on main
    spec/CONTRIBUTING.md, spec/docs/...      Added to main with with_spec: true
    feature/slugify.py, ...                  The change under review, on a branch
```

```yaml
# fixtures/slugify-repo/spec.yaml (abridged)
args:
  with_spec: { default: "false" }
setup:
  install:
    - command: >-
        cd "$WORKSPACE_DIR" && git init -q -b main &&
        cp -r ~/.fixtures/slugify-repo/main/. . &&
        if [ "${{ kit.args.with_spec }}" = "true" ]; then
        cp -r ~/.fixtures/slugify-repo/spec/. .; fi &&
        git add -A && git commit -qm "Add slugify"
      user: "1000"
    - command: >-
        cd "$WORKSPACE_DIR" && git checkout -qb feature/unicode-slugs &&
        cp -r ~/.fixtures/slugify-repo/feature/. . && git commit -qam "Change slugify"
      user: "1000"
```

### Evals

An eval describes what to test. The file `evals/<name>.yaml` names the libraries to
test and contains one or more cases. A `fixture` or `scorers` entry at the top level
of the file acts as a default, which a case can replace with its own. By default,
every case also runs without a library, as a baseline to compare against. Set
`baseline: false` to skip it, for example when you have already measured the
baseline and only want to compare libraries or versions of your skills:

```yaml
# yaml-language-server: $schema=../schemas/eval.schema.json
description: Review a branch; expects the library's two-axis review.
libraries: [matt-pocock-skills]
cases:
  - id: branch-review
    prompt: Review the changes on this branch since main.
    fixture: { name: slugify-repo, args: { with_spec: true } }
    scorers:
      - name: skill_invoked
        args: { skill: code-review, namespace_required: true }
        min_pass: 0.8
      - name: answer_matches
        args: { pattern: '(?ms)(?=.*^#+ Standards)(?=.*^#+ Spec\b)' }
```

Write prompts the way a user would, and do not name the skill in them. Whether the
agent picks up the skill based on its description is part of what you measure.

### Scorers

Scorers grade the runs. `skill-evals` includes three of them:

- `skill_invoked` checks whether the agent loaded the skill. Claude Code loads skills
  with its Skill tool, and Codex reads the skill's `SKILL.md`. With
  `namespace_required`, a built-in skill that has the same name does not count.
- `answer_matches` checks whether the final answer matches a regular expression, for
  example one that requires certain sections.
- `skills_used` lists every skill that the agent loaded, and is shown next to the
  scores.

You can add your own scorers by pointing `scorers:` in `.skill-evals.yaml` to a
Python package whose `__init__.py` defines a `REGISTRY` of
[MLflow scorer](https://mlflow.org/docs/latest/genai/concepts/scorers/) factories.
Read the traces through `skill_evals.traces`, so that the scorer works for every
agent. The example's [`command_ran`](https://github.com/maxvandenhoven/skill-evals/blob/main/example/scorers/__init__.py) scorer checks what
the agent did, rather than what it answered:

```python
import re

from mlflow.entities import Trace
from mlflow.genai.scorers import Scorer, scorer
from skill_evals.traces import reader_for


def command_ran(pattern: str) -> Scorer:
    compiled = re.compile(pattern)

    @scorer(name=f"command_ran:{pattern}")
    def _command_ran(trace: Trace) -> bool:
        calls = reader_for(trace).tool_calls(trace)
        return any(compiled.search(call.inputs_text) for call in calls)

    return _command_ran


REGISTRY = {"command_ran": command_ran}
```

### Results

Each run leaves a folder `.skill-evals/runs/<stamp>/<cell>-<case>-<i>/`. It contains
the workspace as the agent left it, the agent's answer and error output, the
installed versions (`inventory.txt`) and the sandbox log. Each trace is stored in the
MLflow experiment `skill-evals/<eval>/<harness>/<library>` and is tagged with its
case, repeat and installed versions. Run `skill-evals mlflow` to open the MLflow UI.

## Limitations

- Each case is a single, non-interactive prompt. Conversations with several turns
  are not supported.
- Checking whether an agent follows a skill relies on matching the answer against a
  regular expression. This works for skills that produce a recognisable output
  format. Skills that describe a process, such as writing tests first, need a scorer
  that inspects the trace or uses an LLM as a judge, which you have to write yourself.
- Trace readers exist only for Claude Code and Codex. Other agents need a tracing
  kit and a trace reader in the package.
- Each harness uses its own model, so a difference between harnesses can come from
  the model rather than from the agent.
- Results from a few runs are noisy. Three runs cannot reliably tell a pass rate of
  100% from one of 33%, so use ten or more runs before you draw conclusions.
- Local sandboxes require macOS 14 or later on Apple silicon, Windows 11, or Ubuntu
  24.04 or later with KVM. The `sbx env` command, which `skill-evals` relies on, is
  marked as experimental. `skill-evals` was tested with sbx v0.47.0.
- Running in CI requires a prepared runner. `sbx login` opens a browser, and
  subscription logins are not suitable for CI, so use API keys and a runner on which
  sbx is already set up.
- The MLflow server always uses port 5000, because the base harness layer points the
  sandboxes at that port.
- Codex tracing relies on a patch. Version 0.4.0 of `@mlflow/codex` drops the tool
  calls of current Codex versions, including the `SKILL.md` reads. The tracing kit
  patches the package and fails if the package's code has changed. A future change
  to the Codex transcript format could still make tool calls disappear from the
  traces without an error, so check a trace after you upgrade Codex.
- Codex creates a separate trace for every subagent. When a skill spawns subagents,
  `skill-evals` scores the trace of the main session, so skills loaded inside a
  subagent are not counted.
- The runs within a cell run one after another, because traces are matched to runs
  by their start time. Different cells run in parallel.
- Not every version is pinned. The agent CLIs and `@mlflow/codex` are pinned, but
  plugins from marketplaces and the sbx images are not. Every trace records what was
  installed in the tag `eval.inventory`. For example, Anthropic's plugin marketplace
  pins Matt Pocock's skills to an older release than the one in the skills'
  repository, so Claude Code installs a different version of the skills than Codex.
- `init` copies the JSON Schemas so that your editor can use them, and these copies
  are not updated when you upgrade `skill-evals`. Validation always uses the schemas
  of the installed package.

## Development

```bash
uv sync --all-groups && make check   # ruff, ty, yamllint and validate
make evals                           # The reference run of this repository's evals
```

The repository has two parts. `src/skill_evals/` is the package. It contains the CLI,
the built-in scorers and trace readers, and the files that ship for reuse as they
are, namely `harnesses/` and `schemas/`. [`example/`](https://github.com/maxvandenhoven/skill-evals/tree/main/example/) is a project like
yours, whose evals, libraries, fixtures and scorers are specific to it and are not
shipped. The `.skill-evals.yaml` in the root of the repository connects the two
parts. It uses the package's harnesses directly, so that the example's runs test
exactly the harnesses that `init` copies.

See [CONTRIBUTING.md](https://github.com/maxvandenhoven/skill-evals/blob/main/CONTRIBUTING.md) for how to contribute.

## License

[MIT](https://github.com/maxvandenhoven/skill-evals/blob/main/LICENSE)
