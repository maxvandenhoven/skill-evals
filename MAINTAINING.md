# Maintaining

Notes for the maintainer: how releases work and which repository settings they rely on.

## Releasing

A release is one pull request. From a clean checkout, run:

```bash
make release-prepare                  # Or: make release-prepare VERSION=0.2.0
```

This creates the branch `release/vX.Y.Z` from an up-to-date `main`. The version that
commitizen picks from the conventional commits since the last tag is written to
`pyproject.toml` and `uv.lock`, and `CHANGELOG.md` is updated. Nothing is committed or
tagged. Edit the changelog by hand, commit, and open a pull request titled
`chore: release vX.Y.Z`. The first release has no tag to bump from, so only the
changelog is written and the version stays as it is in `pyproject.toml`.

When the pull request is merged, the Release workflow sees a version without a tag. It
builds the package, smoke-tests the wheel, and waits for you to approve the `pypi`
environment. After approval it publishes to PyPI, then tags the commit and creates the
GitHub release with that version's changelog section.

To rehearse, run the Release workflow by hand from the Actions tab. It builds a
throwaway `.devN` version and publishes it to TestPyPI, without tagging anything.

## Settings the workflows rely on

- Environment `pypi`: you as required reviewer, with "prevent self-review" off.
- Environment `testpypi`: no reviewer needed.
- A trusted publisher on PyPI and another on TestPyPI, for owner `maxvandenhoven`,
  repository `skill-evals`, workflow `release.yml`, and the environment of that index.
- Ruleset `protect-main`: pull requests with one approval, squash merges only, and the
  CI checks required. Admins can bypass the approval.
- Ruleset `protect-gh-pages`: no deletion or force-push.
