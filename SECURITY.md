# Security policy

## Reporting a vulnerability

Please report it privately through
[GitHub's private vulnerability reporting](https://github.com/maxvandenhoven/skill-evals/security/advisories/new)
instead of opening a public issue.

Include what you found, how to reproduce it, and what you think the impact is. This
project has one maintainer, so replies are best effort, but every report is read.

## What counts

`skill-evals` runs coding agents in Docker Sandboxes and stores their traces. Reports
about these are especially welcome:

- A credential reaching a sandbox, a trace or a run folder when it should not.
- A project file (eval, kit, scorer) causing something to run outside the sandbox
  that the documentation says runs inside it.

## Supported versions

Only the latest release gets fixes.
